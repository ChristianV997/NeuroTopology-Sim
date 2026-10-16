"""Schema, threat classes, and exit codes for Batch 2 security harness."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"
EVIDENCE_CLASS = "batch2_security_engineering"

# Explicit exit codes for the CLI / runner.
EXIT_OK = 0
EXIT_SECURITY_FAIL = 1
EXIT_USAGE = 2

DEFAULT_LIMITATIONS = (
    "security_pass is an engineering acceptance signal only; it is never scientific PASS.",
    "This harness does not download neurodata, touch credentials, or call AWS/DANDI/OpenNeuro.",
    "Static detections against fixtures prove scanner coverage; they do not prove repository-wide compliance.",
    "Inventory remediations name production owner paths without modifying them.",
    "REA was not used for live inspection; static fixture inspection only (REA_UNAVAILABLE when REA absent).",
    "ecc:* and gstack:* tooling was unavailable in this agent environment; harness implements equivalent local checks.",
)


class ThreatClass(str, Enum):
    NETWORK_DEFAULT_ENABLED = "NETWORK_DEFAULT_ENABLED"
    UNBOUNDED_REMOTE_MATERIALIZATION = "UNBOUNDED_REMOTE_MATERIALIZATION"
    FULL_DATASET_DOWNLOAD = "FULL_DATASET_DOWNLOAD"
    UNAUTHORIZED_SHELL_TRANSFER = "UNAUTHORIZED_SHELL_TRANSFER"
    UNAUTHORIZED_BOTO3_FULL_OBJECT = "UNAUTHORIZED_BOTO3_FULL_OBJECT"
    UNAUTHORIZED_AWS_FULL_TRANSFER = "UNAUTHORIZED_AWS_FULL_TRANSFER"
    UNRESTRICTED_URLLIB = "UNRESTRICTED_URLLIB"
    OUTPUT_ROOT_ESCAPE = "OUTPUT_ROOT_ESCAPE"
    SYMLINK_ESCAPE = "SYMLINK_ESCAPE"
    WINDOWS_DRIVE_ESCAPE = "WINDOWS_DRIVE_ESCAPE"
    UNSAFE_SUBPROCESS = "UNSAFE_SUBPROCESS"
    SHELL_TRUE = "SHELL_TRUE"
    MISSING_TIMEOUT = "MISSING_TIMEOUT"
    UNBOUNDED_PROCESS_IO = "UNBOUNDED_PROCESS_IO"
    WORKER_LIMIT_EXCEEDED = "WORKER_LIMIT_EXCEEDED"
    NON_FINITE_JSON = "NON_FINITE_JSON"
    FABRICATED_PROVENANCE = "FABRICATED_PROVENANCE"
    MISSING_CHECKSUM = "MISSING_CHECKSUM"
    MISSING_COMMIT_IDENTITY = "MISSING_COMMIT_IDENTITY"
    SYNTHETIC_TO_EMPIRICAL = "SYNTHETIC_TO_EMPIRICAL"
    ARTIFACT_INCOMPLETE_STATE = "ARTIFACT_INCOMPLETE_STATE"


# Exact production remediation owners (report-only; harness does not edit these).
REMEDIATION_OWNERS: Dict[str, List[str]] = {
    ThreatClass.NETWORK_DEFAULT_ENABLED.value: [
        "validation/s3_fetchers.py",
        "tools/stream_process_ds006644.py",
        "tools/stream_process_ds005917.py",
        "tools/stream_process_dandi000458.py",
    ],
    ThreatClass.UNBOUNDED_REMOTE_MATERIALIZATION.value: [
        "tools/stream_pitnn_cohort_ds005620.py",
        "tools/streaming/base_runner.py",
        "validation/s3_fetchers.py",
    ],
    ThreatClass.FULL_DATASET_DOWNLOAD.value: [
        "tools/data_access/policy_enforcement/scanner.py",
        "OPENNEURO_DATA_ACCESS.md",
    ],
    ThreatClass.UNAUTHORIZED_SHELL_TRANSFER.value: [
        "tools/data_access/policy_enforcement/scanner.py",
        "scripts/",
    ],
    ThreatClass.UNAUTHORIZED_BOTO3_FULL_OBJECT.value: [
        "tools/stream_pitnn_cohort_ds005620.py",
        "validation/s3_fetchers.py",
        "tools/streaming/base_runner.py",
    ],
    ThreatClass.UNAUTHORIZED_AWS_FULL_TRANSFER.value: [
        "tools/data_access/policy_enforcement/scanner.py",
        "scripts/",
    ],
    ThreatClass.UNRESTRICTED_URLLIB.value: [
        "tools/data_access/policy_enforcement/scanner.py",
        "apps/awareness_studio/",
    ],
    ThreatClass.OUTPUT_ROOT_ESCAPE.value: [
        "validation/s3_fetchers.py",
        "tools/data_access/chunk_cache/cache_engine.py",
    ],
    ThreatClass.SYMLINK_ESCAPE.value: [
        "validation/s3_fetchers.py",
        "tools/data_access/chunk_cache/cache_engine.py",
    ],
    ThreatClass.WINDOWS_DRIVE_ESCAPE.value: [
        "validation/s3_fetchers.py",
        "tools/data_access/chunk_cache/cache_engine.py",
    ],
    ThreatClass.UNSAFE_SUBPROCESS.value: [
        "tools/validate_ds005620_generated_language.py",
        "scripts/",
    ],
    ThreatClass.SHELL_TRUE.value: [
        "scripts/",
        "tools/",
    ],
    ThreatClass.MISSING_TIMEOUT.value: [
        "scripts/",
        "tools/",
    ],
    ThreatClass.UNBOUNDED_PROCESS_IO.value: [
        "scripts/",
        "tools/",
    ],
    ThreatClass.WORKER_LIMIT_EXCEEDED.value: [
        "tools/streaming/base_runner.py",
        "job_runner/",
    ],
    ThreatClass.NON_FINITE_JSON.value: [
        "runs/run_record.py",
        "tools/research_cycle_release/",
    ],
    ThreatClass.FABRICATED_PROVENANCE.value: [
        "tools/research_claim_gate/gate.py",
        "tools/simulation_artifacts/extractor.py",
    ],
    ThreatClass.MISSING_CHECKSUM.value: [
        "tools/research_claim_gate/gate.py",
        "validation/s3_fetchers.py",
    ],
    ThreatClass.MISSING_COMMIT_IDENTITY.value: [
        "tools/research_claim_gate/gate.py",
        "runs/run_record.py",
    ],
    ThreatClass.SYNTHETIC_TO_EMPIRICAL.value: [
        "tools/research_claim_gate/gate.py",
        "tools/research_cycle_release/",
    ],
    ThreatClass.ARTIFACT_INCOMPLETE_STATE.value: [
        "tools/simulation_artifacts/extractor.py",
        "tools/research_cycle_release/",
    ],
}


def json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


@dataclass
class Finding:
    threat_class: str
    severity: str
    message: str
    fixture_id: Optional[str] = None
    location: Optional[str] = None
    remediation_owners: List[str] = field(default_factory=list)
    expected: bool = True  # True when the fixture is supposed to trigger detection

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(
            {
                "threat_class": self.threat_class,
                "severity": self.severity,
                "message": self.message,
                "fixture_id": self.fixture_id,
                "location": self.location,
                "remediation_owners": list(self.remediation_owners),
                "expected": self.expected,
            }
        )


@dataclass
class CheckResult:
    check_id: str
    passed: bool
    findings: List[Finding] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(
            {
                "check_id": self.check_id,
                "passed": self.passed,
                "findings": [f.to_dict() for f in self.findings],
                "details": self.details,
            }
        )
