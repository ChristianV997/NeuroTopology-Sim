"""Tests for evidence.builder.build_evidence_bundle against the real,
small, already-committed contract artifacts (contracts/btc_icft/ds005620/pitnn_cohort/,
contracts/fmri_tda/ds000245/) and the real committed benchmarks/registry_seed.json.
No raw data is fetched or reprocessed; these are the same committed artifacts
the existing exporter test suites already read.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.export_registry import BenchmarkRegistry
from evidence.builder import BuildError, build_evidence_bundle
from evidence.store import EvidenceBundleStore

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"
_DS005620_SOURCE = _REPO_ROOT / "contracts" / "btc_icft" / "ds005620" / "pitnn_cohort"
_DS000245_SOURCE = _REPO_ROOT / "contracts" / "fmri_tda" / "ds000245"


def test_builds_ds005620_cohort_summary_bundle(tmp_path):
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=tmp_path / "out",
        registry_path=_SEED_REGISTRY,
    )
    assert bundle.dataset_id == "ds005620"
    assert len(bundle.transition_record_ids) == 21  # 20 subjects + 1 cohort
    assert bundle.phase_space_coordinate_ids == []
    assert bundle.metadata["phase_space_status"] == "not_requested"


def test_builds_ds005620_spatial_defect_map_bundle(tmp_path):
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="spatial_defect_map",
        source=_DS005620_SOURCE, out=tmp_path / "out",
        registry_path=_SEED_REGISTRY,
    )
    assert bundle.dataset_id == "ds005620"
    assert len(bundle.transition_record_ids) == 21
    assert bundle.metadata["feature_set"] == "spatial_defect_map"


def test_builds_ds000245_fmri_bundle(tmp_path):
    bundle = build_evidence_bundle(
        dataset="ds000245", feature_set="schaefer100_motcorr",
        source=_DS000245_SOURCE, out=tmp_path / "out",
        registry_path=_SEED_REGISTRY,
    )
    assert bundle.dataset_id == "ds000245"
    assert len(bundle.transition_record_ids) == 3  # CTL->ODN, CTL->ODP, ODN->ODP


def test_ds005620_cohort_summary_and_spatial_defect_map_are_distinct(tmp_path):
    b1 = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=tmp_path / "out1", registry_path=_SEED_REGISTRY,
    )
    b2 = build_evidence_bundle(
        dataset="ds005620", feature_set="spatial_defect_map",
        source=_DS005620_SOURCE, out=tmp_path / "out2", registry_path=_SEED_REGISTRY,
    )
    assert b1.bundle_id != b2.bundle_id
    assert set(b1.transition_record_ids).isdisjoint(b2.transition_record_ids)


def test_includes_transitions_and_phase_space_coordinates(tmp_path):
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=tmp_path / "out",
        registry_path=_SEED_REGISTRY, include_phase_space=True,
    )
    assert len(bundle.transition_record_ids) == 21
    assert len(bundle.phase_space_coordinate_ids) > 0
    assert bundle.metadata["phase_space_status"] == "estimated"
    for path in bundle.transition_record_paths + bundle.phase_space_coordinate_paths:
        assert (_REPO_ROOT / path).exists()


def test_writes_evidence_bundle_json(tmp_path):
    out = tmp_path / "out"
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=out, registry_path=_SEED_REGISTRY,
    )
    store = EvidenceBundleStore(out)
    assert store.exists()
    reloaded = store.read()
    assert reloaded.bundle_id == bundle.bundle_id
    assert reloaded.to_dict() == bundle.to_dict()


def test_records_registry_decisions(tmp_path):
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=tmp_path / "out", registry_path=_SEED_REGISTRY,
    )
    assert bundle.registry_decisions
    assert all(d["allowed"] for d in bundle.registry_decisions)
    dataset_decisions = [d for d in bundle.registry_decisions if d["id"] == "ds005620"]
    assert dataset_decisions


def test_records_contamination_update_when_mark_seen_requested(tmp_path):
    out = tmp_path / "out"
    updated_out = tmp_path / "updated_registry.json"
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=out, registry_path=_SEED_REGISTRY,
        mark_seen=True, updated_registry_out=updated_out,
    )
    assert bundle.contamination_updates
    assert any(u["id"] == "ds005620" and u["applied"] for u in bundle.contamination_updates)
    updated_registry = BenchmarkRegistry.load(updated_out)
    assert updated_registry.datasets["ds005620"].contamination_status == "seen_by_exploration"


def test_no_contamination_update_when_mark_seen_not_requested(tmp_path):
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=tmp_path / "out", registry_path=_SEED_REGISTRY,
    )
    assert bundle.contamination_updates == []


def test_seed_registry_unchanged_after_mark_seen_build(tmp_path):
    before = _SEED_REGISTRY.read_bytes()
    build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=tmp_path / "out", registry_path=_SEED_REGISTRY,
        mark_seen=True, updated_registry_out=tmp_path / "updated.json",
    )
    after = _SEED_REGISTRY.read_bytes()
    assert before == after


def test_mark_seen_without_updated_registry_out_fails_closed(tmp_path):
    with pytest.raises(BuildError, match="updated_registry_out"):
        build_evidence_bundle(
            dataset="ds005620", feature_set="cohort_summary",
            source=_DS005620_SOURCE, out=tmp_path / "out",
            registry_path=_SEED_REGISTRY, mark_seen=True,
        )


def test_forbidden_use_fails_before_any_output_written(tmp_path):
    out = tmp_path / "out"
    with pytest.raises(BuildError, match="benchmark registry denied"):
        build_evidence_bundle(
            dataset="ds005620", feature_set="cohort_summary",
            source=_DS005620_SOURCE, out=out,
            registry_path=_SEED_REGISTRY, requested_use="final_claim_confirmation",
        )
    assert not out.exists()


def test_missing_registry_without_no_registry_flag_fails_closed(tmp_path):
    with pytest.raises(BuildError, match="registry_path is required"):
        build_evidence_bundle(
            dataset="ds005620", feature_set="cohort_summary",
            source=_DS005620_SOURCE, out=tmp_path / "out",
        )


def test_no_registry_legacy_mode_succeeds(tmp_path):
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=tmp_path / "out", no_registry=True,
    )
    assert bundle.registry_path is None
    assert bundle.registry_decisions == []
    assert bundle.validate() == []


def test_unsupported_dataset_feature_set_combination_fails():
    with pytest.raises(BuildError, match="unsupported"):
        build_evidence_bundle(
            dataset="ds005917", feature_set="anything",
            source=_REPO_ROOT, out=Path("/tmp/never_written"),
            registry_path=_SEED_REGISTRY,
        )


def test_ds005917_candidate_dataset_has_no_dispatch_entry():
    from evidence.builder import DISPATCH

    assert not any(dataset == "ds005917" for dataset, _ in DISPATCH)
    assert not any(dataset == "ds006644" for dataset, _ in DISPATCH)


def test_ds005917_denied_by_registry_even_if_dispatch_existed():
    # Defense-in-depth: even bypassing DISPATCH, the seed registry itself
    # denies transition_export for the candidate/unstructured dataset.
    registry = BenchmarkRegistry.load(_SEED_REGISTRY)
    allowed, reason = registry.check_use("ds005917", "transition_export")
    assert not allowed
    allowed, reason = registry.check_use("ds006644", "transition_export")
    assert not allowed


def test_generated_claim_scope_never_exceeds_ceiling(tmp_path):
    bundle = build_evidence_bundle(
        dataset="ds000245", feature_set="schaefer100_motcorr",
        source=_DS000245_SOURCE, out=tmp_path / "out",
        registry_path=_SEED_REGISTRY, include_phase_space=True,
    )
    from phase_space.coordinate import CLAIM_SCOPE_ORDER

    assert CLAIM_SCOPE_ORDER.index(bundle.generated_claim_scope) <= CLAIM_SCOPE_ORDER.index(bundle.claim_scope_ceiling)


def test_null_control_status_is_honest_ds000245(tmp_path):
    bundle = build_evidence_bundle(
        dataset="ds000245", feature_set="schaefer100_motcorr",
        source=_DS000245_SOURCE, out=tmp_path / "out", registry_path=_SEED_REGISTRY,
    )
    # ds000245's real committed gate has a significant permutation p-value
    # for at least one contrast -- confirm the bundle reflects that honestly
    # rather than defaulting to a placeholder.
    assert bundle.null_control_summary["status"] in ("passed", "failed", "mixed")
    assert bundle.null_control_summary["per_transition"]


def test_bundle_does_not_promote_claim_scope(tmp_path):
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=tmp_path / "out", registry_path=_SEED_REGISTRY,
    )
    assert bundle.generated_claim_scope == "exploratory_metric"
    assert bundle.claim_scope_ceiling in ("exploratory_metric", "dataset_specific", "cross_subject_dataset_specific")


def test_deterministic_bundle_id_across_repeated_builds(tmp_path):
    b1 = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=tmp_path / "out1", registry_path=_SEED_REGISTRY,
    )
    b2 = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=tmp_path / "out2", registry_path=_SEED_REGISTRY,
    )
    assert b1.bundle_id == b2.bundle_id
