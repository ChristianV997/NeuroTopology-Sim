"""Tests for 8-stage complete chain validation in Simulation Release Bridge."""
from __future__ import annotations

import pytest

from tools.simulation_release_bridge.contracts import (
    CHAIN_STAGES,
    ExecutionOutcomeState,
    ReleasePromotionStatus,
)
from tools.simulation_release_bridge.fixtures import (
    create_complete_pass_stages,
    create_missing_validation_stages,
)
from tools.simulation_release_bridge.validator import validate_stages
from tools.simulation_release_bridge.builder import SimulationReleaseBuilder


def test_complete_chain_passes_validation():
    """Verify that a compliant 8-stage dictionary passes chain validation."""
    stages = create_complete_pass_stages()
    result = validate_stages(stages, require_canonical_runner=False)

    assert result.is_valid is True
    assert result.chain_complete is True
    assert result.missing_stages == []
    assert result.errors == []
    assert result.promotion_eligible is True
    assert result.execution_state == ExecutionOutcomeState.PASS.value


@pytest.mark.parametrize("missing_stage", CHAIN_STAGES)
def test_each_missing_stage_fails_chain_completeness(missing_stage: str):
    """Verify that omitting any single stage marks chain_complete as False and records error."""
    stages = create_complete_pass_stages()
    del stages[missing_stage]

    result = validate_stages(stages, require_canonical_runner=False)

    assert result.chain_complete is False
    assert missing_stage in result.missing_stages
    assert result.promotion_eligible is False
    assert any("incomplete chain" in err for err in result.errors)


def test_builder_reports_incomplete_chain():
    """Verify that SimulationReleaseBuilder records incomplete chain diagnostics."""
    stages = create_missing_validation_stages()
    builder = SimulationReleaseBuilder("rc-test-001", require_canonical_runner=False)
    bundle = builder.build_from_stages(stages)

    assert bundle.chain_complete is False
    assert "validation" in bundle.diagnostics["missing"]
    assert bundle.promotion_status in (
        ReleasePromotionStatus.NOT_PROMOTED.value,
        ReleasePromotionStatus.BLOCKED.value,
    )
    assert bundle.promotion_checksum is None
