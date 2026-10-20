"""Shared builders for orchestrator evidence-state tests (offline, synthetic only)."""
from __future__ import annotations

import pytest

# A distinctive value so that a leak is unambiguous in any serialized output.
LEAK_SENTINEL = 0.31337
SHA = "ab" * 32  # 64 lowercase hex characters
CMD = "cd" * 32


def make_identified(run_id: str = "run-0001", evidence_class: str = "engineering_fact", **overrides):
    """An artifact carrying the full identity contract, with a sentinel metric."""
    artifact = {
        "run_id": run_id,
        "evidence_class": evidence_class,
        "source_identity": {"uri": "repo://fixtures/source.json", "sha256": SHA},
        "input_identity": {"sha256": SHA},
        "execution_identity": {
            "run_id": run_id,
            "code_commit": "abc1234",
            "seed": 42,
            "command_identity": CMD,
        },
        "artifact_lineage": {"status": "COMPLETE", "artifact_sha256": SHA},
        # Evidence-ready requires a declared run status; COMPLETED is the success path.
        "status": "COMPLETED",
        "metrics": {"I_mean": LEAK_SENTINEL},
    }
    artifact.update(overrides)
    return artifact


@pytest.fixture
def identified():
    return make_identified
