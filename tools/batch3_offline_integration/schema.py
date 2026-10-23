"""Schema constants for the Batch 3 offline integration harness."""
from __future__ import annotations

from enum import Enum
from typing import Tuple

SCHEMA_VERSION = "NeuroTopology.Batch3OfflineIntegrationReport.v1"
EVIDENCE_CLASS = "batch3_offline_integration_engineering"
RESULT_LABEL_ENGINEERING = "ENGINEERING_ONLY"
RESULT_LABEL_SYNTHETIC = "SYNTHETIC_ONLY"

OWNED_PATH_PREFIXES: Tuple[str, ...] = (
    "tools/batch3_offline_integration/",
    "tests/tools/batch3_offline_integration/",
    "docs/tools/batch3_offline_integration.md",
    "scripts/run_batch3_offline_integration.py",
)

# Adjacent harnesses audited and intentionally NOT forked (different purpose).
RELATED_BUT_DISTINCT = (
    "tools/release_readiness/research_cycle_smoke/ — release-decision matrix over static stage fixtures",
    "ops/research_cycle/runner.py — subprocess catalog operator pack (argv allowlist)",
    "tests/integration/research_cycle/ — file-chain contract inspector",
    "tools/research_cycle_preflight/ — single preflight composition gate (reused as a stage)",
    "scripts/assemble_ecosystem_run.py — topology ecosystem assembly (different lane)",
)


class StageOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED_UPSTREAM_FAILED = "skipped_upstream_failed"
    SKIPPED_OPTIONAL_ABSENT = "skipped_optional_absent"
    FIXTURE_SUBSTITUTED = "fixture_substituted"
    REJECTED_NONFINITE = "rejected_nonfinite"
    REJECTED_SCHEMA = "rejected_schema"
    REJECTED_INVALID_INPUT = "rejected_invalid_input"


class ExecutionMode(str, Enum):
    ALLOWLISTED_CALLABLE = "allowlisted_callable"
    FIXTURE_PRODUCER = "fixture_producer"
    FIXTURE_SUBSTITUTE = "fixture_substitute"
    NOT_EXECUTED = "not_executed"
