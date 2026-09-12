"""Tests for fail-closed security, integrity, and provenance rejections."""
from __future__ import annotations

import sys
from pathlib import Path
import pytest

from tools.simulation_release_bridge.contracts import (
    ReleasePromotionStatus,
    SimulationReleaseError,
)
from tools.simulation_release_bridge.builder import SimulationReleaseBuilder
from tools.simulation_release_bridge.fixtures import (
    create_complete_pass_stages,
    create_fabricated_provenance_stages,
    create_incomplete_manifest_stages,
    create_non_finite_metrics_stages,
    create_output_root_escape_stages,
    create_temporary_only_artifacts_stages,
)
from tools.simulation_release_bridge.validator import (
    check_canonical_runner_presence,
    validate_stages,
)


def test_reject_fabricated_provenance():
    """Verify that placeholder run_id, source, and code_revision trigger fail-closed rejections."""
    stages = create_fabricated_provenance_stages()
    builder = SimulationReleaseBuilder("rc-test-fab", require_canonical_runner=False)
    bundle = builder.build_from_stages(stages)

    assert "FABRICATED_PROVENANCE" in bundle.diagnostics["rejected"]
    assert bundle.promotion_status == ReleasePromotionStatus.BLOCKED.value
    assert bundle.promotion_checksum is None


def test_reject_output_root_escapes(tmp_path: Path):
    """Verify that paths with '..' or root escapes are rejected."""
    stages = create_output_root_escape_stages()
    builder = SimulationReleaseBuilder("rc-test-escape", require_canonical_runner=False)
    bundle = builder.build_from_stages(stages, output_root=tmp_path)

    assert "OUTPUT_ROOT_ESCAPE" in bundle.diagnostics["rejected"]
    assert bundle.promotion_status == ReleasePromotionStatus.BLOCKED.value
    assert bundle.promotion_checksum is None


def test_reject_temporary_only_artifacts():
    """Verify that manifests consisting exclusively of temporary scratch files are rejected."""
    stages = create_temporary_only_artifacts_stages()
    builder = SimulationReleaseBuilder("rc-test-temp", require_canonical_runner=False)
    bundle = builder.build_from_stages(stages)

    assert "TEMPORARY_ONLY_ARTIFACTS" in bundle.diagnostics["rejected"]
    assert bundle.promotion_status == ReleasePromotionStatus.BLOCKED.value
    assert bundle.promotion_checksum is None


def test_reject_incomplete_manifest():
    """Verify that manifests lacking RunRecord or summary/metrics are rejected."""
    stages = create_incomplete_manifest_stages()
    builder = SimulationReleaseBuilder("rc-test-incomp", require_canonical_runner=False)
    bundle = builder.build_from_stages(stages)

    assert "INCOMPLETE_MANIFEST" in bundle.diagnostics["rejected"]
    assert bundle.promotion_status == ReleasePromotionStatus.BLOCKED.value
    assert bundle.promotion_checksum is None


def test_reject_non_finite_metrics():
    """Verify that NaN or Infinity in metrics triggers fail-closed error."""
    stages = create_non_finite_metrics_stages()
    builder = SimulationReleaseBuilder("rc-test-nan", require_canonical_runner=False)
    bundle = builder.build_from_stages(stages)

    assert "NON_FINITE_METRICS" in bundle.diagnostics["rejected"]
    assert bundle.promotion_status == ReleasePromotionStatus.BLOCKED.value
    assert bundle.promotion_checksum is None


def test_canonical_runner_presence_probe():
    """Verify that probe_canonical_runner accurately detects presence or absence."""
    is_present, err = check_canonical_runner_presence()
    assert is_present is True
    assert err is None


def test_fail_closed_when_canonical_runner_absent(monkeypatch: pytest.MonkeyPatch):
    """Verify fail-closed rejection when canonical runner cannot be imported."""
    # Hide tools.simulation_execution.runner
    monkeypatch.setitem(sys.modules, "tools.simulation_execution.runner", None)

    builder = SimulationReleaseBuilder("rc-test-missing-runner", require_canonical_runner=True)
    stages = create_complete_pass_stages()
    bundle = builder.build_from_stages(stages)

    assert "MISSING_CANONICAL_RUNNER" in bundle.diagnostics["rejected"]
    assert bundle.promotion_status == ReleasePromotionStatus.BLOCKED.value
    assert bundle.promotion_checksum is None
