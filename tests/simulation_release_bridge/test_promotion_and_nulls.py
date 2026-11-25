"""Tests for promotion decisions, state preservation, and null checksum invariants."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from tools.simulation_release_bridge.contracts import (
    ExecutionOutcomeState,
    ReleasePromotionStatus,
)
from tools.simulation_release_bridge.builder import (
    SimulationReleaseBuilder,
    compile_simulation_release_bundle,
)
from tools.simulation_release_bridge.fixtures import (
    create_blocked_stages,
    create_complete_pass_stages,
    create_failed_stages,
    create_not_implemented_stages,
    create_partial_stages,
    create_timeout_stages,
    populate_run_directory,
)


def test_pass_record_promoted_with_checksum():
    """Verify that validated PASS execution record gets PROMOTED with a valid sha256 checksum."""
    stages = create_complete_pass_stages()
    builder = SimulationReleaseBuilder("rc-test-pass", require_canonical_runner=False)
    bundle = builder.build_from_stages(stages)

    assert bundle.promotion_status == ReleasePromotionStatus.PROMOTED.value
    assert bundle.promotion_checksum is not None
    assert len(bundle.promotion_checksum) == 64
    assert bundle.chain_complete is True


@pytest.mark.parametrize(
    ("fixture_func", "expected_state"),
    [
        (create_partial_stages, ExecutionOutcomeState.PARTIAL.value),
        (create_failed_stages, ExecutionOutcomeState.FAILED.value),
        (create_timeout_stages, ExecutionOutcomeState.TIMEOUT.value),
        (create_blocked_stages, ExecutionOutcomeState.BLOCKED.value),
        (create_not_implemented_stages, ExecutionOutcomeState.NOT_IMPLEMENTED.value),
    ],
)
def test_non_pass_states_preserved_and_checksum_null(fixture_func, expected_state: str):
    """Verify that non-PASS states are faithfully preserved and promotion_checksum is null."""
    stages = fixture_func()
    builder = SimulationReleaseBuilder(f"rc-test-{expected_state.lower()}", require_canonical_runner=False)
    bundle = builder.build_from_stages(stages)

    # State preservation
    assert bundle.stages["execution_outcome"]["state"] == expected_state

    # Non-PASS records must NOT be promoted
    assert bundle.promotion_status in (
        ReleasePromotionStatus.NOT_PROMOTED.value,
        ReleasePromotionStatus.BLOCKED.value,
    )

    # Invariant: Non-PASS checksum MUST remain null
    assert bundle.promotion_checksum is None

    # Check finite JSON serialization
    bundle_json = bundle.to_json()
    parsed = json.loads(bundle_json)
    assert parsed["promotion_checksum"] is None
    assert parsed["stages"]["execution_outcome"]["state"] == expected_state


def test_directory_compilation_preserves_states(tmp_path: Path):
    """Verify compilation from filesystem preserves non-PASS execution outcome with null checksum."""
    run_dir = tmp_path / "sim_timeout_run"
    stages = create_timeout_stages()
    populate_run_directory(run_dir, stages)

    bundle = compile_simulation_release_bundle(
        run_dir=run_dir,
        cycle_id="rc-timeout-test",
        require_canonical_runner=False,
    )

    assert bundle.stages["execution_outcome"]["state"] == ExecutionOutcomeState.TIMEOUT.value
    assert bundle.promotion_status == ReleasePromotionStatus.NOT_PROMOTED.value
    assert bundle.promotion_checksum is None
