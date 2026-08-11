"""Tests for PhaseSpaceStore and PhaseSpaceTrajectoryV1."""
from __future__ import annotations

import pytest

from phase_space.coordinate import ESTIMATOR_VERSION, CLAIM_SCOPE_ORDER
from phase_space.estimators import estimate_coordinates
from phase_space.store import PhaseSpaceStore
from phase_space.trajectory import PhaseSpaceTrajectoryV1, compute_trajectory_id
from transitions.record import TransitionRecordV1


def _record(**overrides):
    kwargs = dict(
        dataset_id="ds005620",
        subject_id="sub-9001",
        modality="EEG",
        source_state="awake",
        target_state="sedated",
        transition_class="anesthesia_propofol_awake_to_sedated",
        feature_names=["topology.q_abs", "connectivity.mean_plv"],
        limitations=["synthetic fixture only"],
        claim_scope="exploratory_metric",
        evidence_level="L2_single_subject_real_signal",
        delta_summary={
            "status": "ok", "delta_per_feature": [4.0, -0.2],
            "mean_abs_delta": 2.1, "n_timepoints": 2, "n_features": 2,
        },
        time_axis={"unit": "condition_summary", "n_samples": 2},
    )
    kwargs.update(overrides)
    return TransitionRecordV1.make(**kwargs)


# ── Store ────────────────────────────────────────────────────────────────────

def test_write_creates_coordinates_file(tmp_path):
    rec = _record()
    store = PhaseSpaceStore(tmp_path)
    written = store.write(rec.transition_id, estimate_coordinates(rec))
    assert written["coordinates"].exists()
    assert written["coordinates"].name == "PhaseSpaceCoordinates.json"


def test_read_roundtrip_preserves_coordinates(tmp_path):
    rec = _record()
    coords = estimate_coordinates(rec)
    store = PhaseSpaceStore(tmp_path)
    store.write(rec.transition_id, coords)
    loaded = store.read(rec.transition_id)
    assert [c.to_dict() for c in loaded] == [c.to_dict() for c in coords]


def test_read_preserves_transition_id(tmp_path):
    rec = _record()
    store = PhaseSpaceStore(tmp_path)
    store.write(rec.transition_id, estimate_coordinates(rec))
    for c in store.read(rec.transition_id):
        assert c.transition_id == rec.transition_id


def test_read_missing_record_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        PhaseSpaceStore(tmp_path).read("nonexistent00000")


def test_list_records_empty_store(tmp_path):
    assert PhaseSpaceStore(tmp_path / "not_created_yet").list_records() == []


def test_list_records_returns_sorted_ids(tmp_path):
    store = PhaseSpaceStore(tmp_path)
    a, b = _record(subject_id="sub-9001"), _record(subject_id="sub-9002")
    store.write(a.transition_id, estimate_coordinates(a))
    store.write(b.transition_id, estimate_coordinates(b))
    assert store.list_records() == sorted([a.transition_id, b.transition_id])


def test_read_all_returns_every_record(tmp_path):
    store = PhaseSpaceStore(tmp_path)
    a, b = _record(subject_id="sub-9001"), _record(subject_id="sub-9002")
    store.write(a.transition_id, estimate_coordinates(a))
    store.write(b.transition_id, estimate_coordinates(b))
    assert set(store.read_all()) == {a.transition_id, b.transition_id}


def test_trajectory_written_and_read_back(tmp_path):
    rec = _record()
    coords = estimate_coordinates(rec)
    traj = PhaseSpaceTrajectoryV1.from_coordinates(
        coords, normalization_mode="within_record", estimator_version=ESTIMATOR_VERSION
    )
    store = PhaseSpaceStore(tmp_path)
    store.write(rec.transition_id, coords, trajectory=traj)
    assert store.read_trajectory(rec.transition_id).to_dict() == traj.to_dict()


def test_read_trajectory_missing_raises(tmp_path):
    rec = _record()
    store = PhaseSpaceStore(tmp_path)
    store.write(rec.transition_id, estimate_coordinates(rec))
    with pytest.raises(FileNotFoundError):
        store.read_trajectory(rec.transition_id)


# ── Trajectory ───────────────────────────────────────────────────────────────

def _traj(rec=None, **kw):
    rec = rec or _record()
    return PhaseSpaceTrajectoryV1.from_coordinates(
        estimate_coordinates(rec),
        normalization_mode="within_record",
        estimator_version=ESTIMATOR_VERSION,
        **kw,
    )


def test_trajectory_dict_and_json_roundtrip():
    t = _traj()
    assert PhaseSpaceTrajectoryV1.from_dict(t.to_dict()).to_dict() == t.to_dict()
    assert PhaseSpaceTrajectoryV1.from_json(t.to_json()).to_dict() == t.to_dict()


def test_trajectory_validates_clean():
    assert _traj().validate() == []


def test_trajectory_records_source_transition_ids():
    rec = _record()
    assert _traj(rec).source_transition_ids == [rec.transition_id]


def test_trajectory_id_is_deterministic():
    rec = _record()
    assert _traj(rec).trajectory_id == _traj(rec).trajectory_id


def test_trajectory_id_ignores_ordering():
    ids = ["t1", "t2"]
    assert compute_trajectory_id(
        source_transition_ids=ids, axes=["a", "b"],
        normalization_mode="within_record", estimator_version="v1",
    ) == compute_trajectory_id(
        source_transition_ids=list(reversed(ids)), axes=["b", "a"],
        normalization_mode="within_record", estimator_version="v1",
    )


def test_trajectory_inherits_weakest_claim_scope():
    weak = _record(claim_scope="computational_artifact", evidence_level="L0_computational_artifact")
    strong = _record(
        subject_id="sub-9002", claim_scope="cross_subject_dataset_specific",
        record_level="cohort", evidence_level="L4_cross_subject_dataset_specific",
    )
    strong.subject_id = None
    coords = estimate_coordinates(weak) + estimate_coordinates(strong)
    t = PhaseSpaceTrajectoryV1.from_coordinates(
        coords, normalization_mode="within_record", estimator_version=ESTIMATOR_VERSION
    )
    assert t.claim_scope == "computational_artifact"
    assert t.evidence_level == "L0_computational_artifact"


def test_trajectory_never_exceeds_any_member_scope():
    t = _traj()
    for c in t.coordinates:
        assert CLAIM_SCOPE_ORDER.index(t.claim_scope) <= CLAIM_SCOPE_ORDER.index(
            c.output_claim_scope
        )


def test_trajectory_limitations_non_empty():
    assert _traj().limitations


def test_trajectory_flags_multiple_datasets():
    a = _record(dataset_id="ds005620")
    b = _record(dataset_id="ds006644", subject_id="sub-9002")
    t = PhaseSpaceTrajectoryV1.from_coordinates(
        estimate_coordinates(a) + estimate_coordinates(b),
        normalization_mode="within_record", estimator_version=ESTIMATOR_VERSION,
    )
    assert any("multiple datasets" in lim for lim in t.limitations)
    assert t.dataset_id is None


def test_trajectory_with_banned_text_fails_validation():
    # Sourced from the canonical list rather than hardcoded, so this tests the
    # real firewall and does not itself plant banned text in the repository.
    from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES

    t = _traj()
    t.limitations = t.limitations + [f"this {BANNED_REPORT_PHRASES[0]}"]
    assert any("banned phrase" in e for e in t.validate())
