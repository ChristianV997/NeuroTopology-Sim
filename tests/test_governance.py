"""
Tests for the governance harness (D1).

Covers:
- HypothesisSpec dataclass instantiation
- Validation gating: K/C fail without discriminator/controls/readouts
- M passes without discriminator/controls/readouts
- C fails without alternatives_considered or empty thresholds
- Valid K spec passes
- Valid C spec passes
- IO round-trip (YAML and JSON)
- Hypothesis pipeline produces summary.json
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from governance.spec import (
    ArtifactsSpec,
    Control,
    DataSpec,
    Discriminator,
    HypothesisSpec,
    PassFail,
    Readout,
)
from governance.validate import ValidationError, validate_spec
from governance.io import load_spec, save_spec


# ── fixtures ───────────────────────────────────────────────────────────────────

def _make_m_spec() -> HypothesisSpec:
    return HypothesisSpec(
        id="HYP-20260101-001",
        title="Marker test",
        claim_type="M",
        layer="Marker",
        summary="A simple marker hypothesis.",
        pass_fail=PassFail(criteria="Any result", thresholds={}),
    )


def _make_k_spec() -> HypothesisSpec:
    return HypothesisSpec(
        id="HYP-20260101-002",
        title="Known test",
        claim_type="K",
        layer="Topology",
        summary="A known hypothesis with discriminator and controls.",
        discriminator=Discriminator(
            description="Contrast awake vs anesthesia",
            mode="dataset_contrast",
        ),
        readouts=[Readout(name="Q"), Readout(name="Qabs")],
        controls=[Control(name="label_shuffle")],
        pass_fail=PassFail(criteria="Q_mean > 0", thresholds={}),
    )


def _make_c_spec() -> HypothesisSpec:
    return HypothesisSpec(
        id="HYP-20260101-003",
        title="Causal test",
        claim_type="C",
        layer="Topology",
        summary="A causal hypothesis with all required fields.",
        discriminator=Discriminator(
            description="Stimulus sweep", mode="stimulus_sweep",
        ),
        readouts=[Readout(name="Q")],
        controls=[Control(name="label_shuffle")],
        alternatives_considered=["Null: topology tracks but does not drive"],
        pass_fail=PassFail(
            criteria="AUC > 0.65",
            thresholds={"auc_min": 0.65},
        ),
    )


# ── M claim type ───────────────────────────────────────────────────────────────

def test_m_spec_valid_without_discriminator():
    """M-type spec passes validation with no discriminator, controls, or readouts."""
    validate_spec(_make_m_spec())


def test_m_spec_valid_minimal():
    spec = HypothesisSpec(
        id="HYP-20260101-099",
        title="Minimal M",
        claim_type="M",
        layer="Substrate",
        summary="Minimal marker spec.",
    )
    validate_spec(spec)  # must not raise


# ── K claim type ───────────────────────────────────────────────────────────────

def test_k_spec_valid():
    validate_spec(_make_k_spec())


def test_k_spec_fails_without_discriminator():
    spec = _make_k_spec()
    spec.discriminator = None
    with pytest.raises(ValidationError) as exc_info:
        validate_spec(spec)
    assert any("discriminator" in e for e in exc_info.value.errors)


def test_k_spec_fails_with_empty_discriminator_description():
    spec = _make_k_spec()
    spec.discriminator = Discriminator(description="  ", mode="dataset_contrast")
    with pytest.raises(ValidationError) as exc_info:
        validate_spec(spec)
    assert any("discriminator" in e for e in exc_info.value.errors)


def test_k_spec_fails_without_controls():
    spec = _make_k_spec()
    spec.controls = []
    with pytest.raises(ValidationError) as exc_info:
        validate_spec(spec)
    assert any("controls" in e for e in exc_info.value.errors)


def test_k_spec_fails_without_readouts():
    spec = _make_k_spec()
    spec.readouts = []
    with pytest.raises(ValidationError) as exc_info:
        validate_spec(spec)
    assert any("readouts" in e for e in exc_info.value.errors)


def test_k_spec_error_message_contains_spec_id():
    spec = _make_k_spec()
    spec.controls = []
    with pytest.raises(ValidationError) as exc_info:
        validate_spec(spec)
    assert spec.id in str(exc_info.value)


# ── C claim type ───────────────────────────────────────────────────────────────

def test_c_spec_valid():
    validate_spec(_make_c_spec())


def test_c_spec_fails_without_alternatives_considered():
    spec = _make_c_spec()
    spec.alternatives_considered = []
    with pytest.raises(ValidationError) as exc_info:
        validate_spec(spec)
    assert any("alternatives_considered" in e for e in exc_info.value.errors)


def test_c_spec_fails_with_empty_thresholds():
    spec = _make_c_spec()
    spec.pass_fail = PassFail(criteria="AUC > 0.65", thresholds={})
    with pytest.raises(ValidationError) as exc_info:
        validate_spec(spec)
    assert any("thresholds" in e for e in exc_info.value.errors)


def test_c_spec_fails_without_discriminator():
    spec = _make_c_spec()
    spec.discriminator = None
    with pytest.raises(ValidationError):
        validate_spec(spec)


def test_c_spec_accumulates_multiple_errors():
    """ValidationError should list all violations at once."""
    spec = _make_c_spec()
    spec.discriminator = None
    spec.controls = []
    spec.alternatives_considered = []
    with pytest.raises(ValidationError) as exc_info:
        validate_spec(spec)
    # Multiple errors collected
    assert len(exc_info.value.errors) >= 3


# ── invalid claim_type ─────────────────────────────────────────────────────────

def test_invalid_claim_type_rejected():
    spec = _make_m_spec()
    spec.claim_type = "X"
    with pytest.raises(ValidationError) as exc_info:
        validate_spec(spec)
    assert any("claim_type" in e for e in exc_info.value.errors)


def test_invalid_layer_rejected():
    spec = _make_m_spec()
    spec.layer = "Unknown"
    with pytest.raises(ValidationError) as exc_info:
        validate_spec(spec)
    assert any("layer" in e for e in exc_info.value.errors)


# ── IO round-trip ──────────────────────────────────────────────────────────────

def test_yaml_round_trip(tmp_path):
    spec = _make_k_spec()
    path = tmp_path / "spec.yaml"
    save_spec(spec, path)
    loaded = load_spec(path)
    assert loaded.id == spec.id
    assert loaded.claim_type == spec.claim_type
    assert len(loaded.readouts) == len(spec.readouts)
    assert len(loaded.controls) == len(spec.controls)
    assert loaded.discriminator.description == spec.discriminator.description


def test_json_round_trip(tmp_path):
    spec = _make_c_spec()
    path = tmp_path / "spec.json"
    save_spec(spec, path)
    loaded = load_spec(path)
    assert loaded.id == spec.id
    assert loaded.alternatives_considered == spec.alternatives_considered
    assert loaded.pass_fail.thresholds == spec.pass_fail.thresholds


def test_load_spec_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_spec(tmp_path / "does_not_exist.yaml")


def test_load_example_m_spec():
    """The bundled M-type example spec loads and validates without error."""
    spec_path = Path(__file__).parent.parent / "governance" / "specs" / "HYP-20260506-001.yaml"
    spec = load_spec(spec_path)
    validate_spec(spec)


def test_load_example_k_spec():
    """The bundled K-type example spec loads and validates without error."""
    spec_path = Path(__file__).parent.parent / "governance" / "specs" / "HYP-20260506-002.yaml"
    spec = load_spec(spec_path)
    validate_spec(spec)


def test_load_example_c_spec():
    """The bundled C-type example spec loads and validates without error."""
    spec_path = Path(__file__).parent.parent / "governance" / "specs" / "HYP-20260506-003.yaml"
    spec = load_spec(spec_path)
    validate_spec(spec)


# ── Hypothesis pipeline ────────────────────────────────────────────────────────

def test_hypothesis_pipeline_produces_summary_json(tmp_path):
    """A valid M spec runs end-to-end and produces summary.json."""
    from pipelines.hypothesis import run_hypothesis
    spec = _make_m_spec()
    summary = run_hypothesis(spec, output_dir=tmp_path)
    assert summary["validation_status"] == "valid"
    assert summary["spec_id"] == spec.id
    assert "run_id" in summary
    summary_file = tmp_path / summary["run_id"] / "summary.json"
    assert summary_file.exists()
    with open(summary_file) as fh:
        on_disk = json.load(fh)
    assert on_disk["spec_id"] == spec.id


def test_hypothesis_pipeline_raises_on_invalid_spec(tmp_path):
    """A K spec without controls must raise ValidationError before running."""
    from pipelines.hypothesis import run_hypothesis
    spec = _make_k_spec()
    spec.controls = []
    with pytest.raises(ValidationError):
        run_hypothesis(spec, output_dir=tmp_path)


def test_hypothesis_pipeline_writes_metrics_csv(tmp_path):
    from pipelines.hypothesis import run_hypothesis
    spec = _make_m_spec()
    summary = run_hypothesis(spec, output_dir=tmp_path)
    run_dir = tmp_path / summary["run_id"]
    assert (run_dir / "metrics.csv").exists()


def test_hypothesis_pipeline_with_db(tmp_path):
    """Pipeline logs to SQLite when db_path is provided."""
    from pipelines.hypothesis import run_hypothesis
    from database.database import connect
    spec = _make_k_spec()
    db_path = tmp_path / "runs.sqlite"
    summary = run_hypothesis(spec, output_dir=tmp_path, db_path=db_path)
    assert summary["validation_status"] == "valid"
    conn = connect(db_path)
    row = conn.execute("SELECT name FROM runs WHERE name=?", (spec.id,)).fetchone()
    assert row is not None
    conn.close()


def test_hypothesis_pipeline_verdict_ambiguous_without_thresholds(tmp_path):
    """M spec without thresholds yields 'ambiguous' verdict."""
    from pipelines.hypothesis import run_hypothesis
    spec = _make_m_spec()
    summary = run_hypothesis(spec, output_dir=tmp_path)
    assert summary["verdict"] == "ambiguous"
