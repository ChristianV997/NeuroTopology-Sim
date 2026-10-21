from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
PRIOR_RUNS_DIR = FIXTURES_DIR / "prior_runs"

# fixture_name -> (expected_operational_readiness, expected_scientific_admissibility, expected_cleared_for_execution)
EXPECTED_CASES: dict[str, tuple[str, str, bool]] = {
    "complete_plan": ("READY", "NOT_APPLICABLE", True),
    "needs_revision_plan": ("NEEDS_REVISION", "NOT_APPLICABLE", False),
    "missing_provenance": ("BLOCKED", "NOT_APPLICABLE", False),
    "invalid_labels": ("BLOCKED", "NOT_APPLICABLE", False),
    "missing_null_metadata": ("BLOCKED", "NOT_APPLICABLE", False),
    "partial_run": ("NEEDS_REVISION", "NOT_APPLICABLE", False),
    "network_violation": ("BLOCKED", "NOT_APPLICABLE", False),
    "non_finite_artifacts": ("BLOCKED", "NOT_APPLICABLE", False),
    "synthetic_only_inputs": ("READY", "BLOCKED", False),
    "unsupported_claim": ("READY", "BLOCKED", False),
}
ALL_FIXTURE_NAMES: tuple[str, ...] = tuple(EXPECTED_CASES)


def resolve_request(raw: dict[str, Any]) -> dict[str, Any]:
    """Fixtures store ``prior_run_dir`` as a bare directory name under
    ``fixtures/prior_runs/`` so the JSON stays portable across machines
    and working directories; resolve it to a real path here."""
    request = dict(raw)
    if "prior_run_dir" in request:
        request["prior_run_dir"] = str(PRIOR_RUNS_DIR / request["prior_run_dir"])
    return request


@pytest.fixture
def load_request():
    def _load(name: str) -> dict[str, Any]:
        raw = json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))
        return resolve_request(raw)
    return _load

