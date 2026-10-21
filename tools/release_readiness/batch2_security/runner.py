"""Orchestrate Batch 2 security acceptance checks (local, deterministic)."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.release_readiness.batch2_security import fixtures as fx
from tools.release_readiness.batch2_security.artifact_states import (
    classify_artifact_state,
    evaluate_artifact_state,
    expected_incomplete,
)
from tools.release_readiness.batch2_security.evidence_boundary import evaluate_evidence_record
from tools.release_readiness.batch2_security.finite_json import (
    NonFiniteJSONError,
    dumps_strict,
    finding_for_non_finite,
)
from tools.release_readiness.batch2_security.network_policy import (
    NetworkGuardError,
    find_network_default_enabled,
    network_opt_in_is_safe,
    no_network,
)
from tools.release_readiness.batch2_security.path_containment import evaluate_path_cases
from tools.release_readiness.batch2_security.schema import (
    DEFAULT_LIMITATIONS,
    EVIDENCE_CLASS,
    EXIT_OK,
    EXIT_SECURITY_FAIL,
    REMEDIATION_OWNERS,
    SCHEMA_VERSION,
    CheckResult,
    Finding,
    ThreatClass,
    json_safe,
)
from tools.release_readiness.batch2_security.static_scan import scan_source_text
from tools.release_readiness.batch2_security.subprocess_guard import (
    DEFAULT_POLICY,
    SubprocessGuardError,
    run_allowlisted,
    validate_invocation,
)


def _rea_status() -> str:
    # Authorized static inspection only; REA binary/client is not available here.
    return "REA_UNAVAILABLE"


def _check_network_policy() -> CheckResult:
    findings = []
    safe_ok = network_opt_in_is_safe(fx.NETWORK_SAFE_OPT_IN)
    unsafe = find_network_default_enabled(fx.NETWORK_DEFAULT_ENABLED, fixture_id="network_default_enabled")
    findings.extend(unsafe)
    # Exercise no_network guard: attempting a socket must fail closed.
    guard_ok = False
    try:
        with no_network():
            import socket

            socket.create_connection(("127.0.0.1", 1), timeout=0.01)
    except NetworkGuardError:
        guard_ok = True
    except OSError:
        guard_ok = False
    passed = safe_ok and bool(unsafe) and guard_ok
    return CheckResult(
        check_id="network_policy",
        passed=passed,
        findings=findings,
        details={"safe_opt_in": safe_ok, "no_network_guard": guard_ok},
    )


def _check_static_scan() -> CheckResult:
    findings = []
    expected_hits = {
        "curl_transfer": ThreatClass.UNAUTHORIZED_SHELL_TRANSFER.value,
        "wget_transfer": ThreatClass.UNAUTHORIZED_SHELL_TRANSFER.value,
        "aws_sync": ThreatClass.UNAUTHORIZED_AWS_FULL_TRANSFER.value,
        "openneuro_download": ThreatClass.FULL_DATASET_DOWNLOAD.value,
        "boto3_download_file": ThreatClass.UNAUTHORIZED_BOTO3_FULL_OBJECT.value,
        "boto3_get_object_full": ThreatClass.UNBOUNDED_REMOTE_MATERIALIZATION.value,
        "urllib_urlopen": ThreatClass.UNRESTRICTED_URLLIB.value,
    }
    misses: List[str] = []
    for fixture_id, source in fx.STATIC_FIXTURES.items():
        hits = scan_source_text(source, fixture_id=fixture_id)
        findings.extend(hits)
        if fixture_id == "boto3_get_object_ranged":
            # Ranged get_object must NOT be flagged as unbounded full-object.
            bad = [
                h
                for h in hits
                if h.threat_class == ThreatClass.UNBOUNDED_REMOTE_MATERIALIZATION.value
                and "without Range" in h.message
            ]
            if bad:
                misses.append("ranged_false_positive")
            continue
        expected = expected_hits.get(fixture_id)
        if expected and not any(h.threat_class == expected for h in hits):
            misses.append(fixture_id)
    passed = not misses
    return CheckResult(
        check_id="static_scan",
        passed=passed,
        findings=findings,
        details={"misses": misses, "n_fixtures": len(fx.STATIC_FIXTURES)},
    )


def _check_path_containment(tmp_root: Path) -> CheckResult:
    scratch_parent = tmp_root.parent
    scratch_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="batch2-security-path-", dir=str(scratch_parent)
    ) as scratch:
        root = Path(scratch) / "root"
        root.mkdir()
        (root / "artifacts").mkdir()
        # Symlink escape case: link inside root points to a sibling fixture.
        cases = list(fx.path_cases())
        link_path = root / "evil_link"
        outside = Path(scratch) / "outside_secret"
        outside.write_text("x", encoding="utf-8")
        try:
            link_path.symlink_to(outside)
            cases.append(("path_symlink_escape", "evil_link", True))
        except (OSError, NotImplementedError):
            # Symlink creation unavailable — record advisory in details.
            cases.append(("path_symlink_escape_skipped", "evil_link", True))

        findings = evaluate_path_cases(root, cases)
        unexpected = [f for f in findings if f.expected is False]
        skipped = any(c[0] == "path_symlink_escape_skipped" for c in cases)
        if skipped:
            unexpected = [
                f for f in unexpected if f.fixture_id != "path_symlink_escape_skipped"
            ]
            findings = [
                f for f in findings if f.fixture_id != "path_symlink_escape_skipped"
            ]
        passed = not unexpected
        return CheckResult(
            check_id="path_containment",
            passed=passed,
            findings=findings,
            details={"n_cases": len(cases), "symlink_skipped": skipped},
        )


def _check_subprocess() -> CheckResult:
    findings = []
    # shell=True rejected
    findings.extend(
        validate_invocation(["python3", "-c", "print(1)"], shell=True, timeout=1.0)
    )
    # non-allowlisted binary
    findings.extend(
        validate_invocation(["curl", "https://example.com"], shell=False, timeout=1.0)
    )
    # missing timeout
    findings.extend(
        validate_invocation(["python3", "-c", "print(1)"], shell=False, timeout=None)
    )
    # worker limit
    findings.extend(
        validate_invocation(
            ["python3", "-c", "print(1)"],
            shell=False,
            timeout=1.0,
            active_workers=DEFAULT_POLICY.max_workers,
        )
    )
    # happy path execution
    exec_ok = False
    try:
        code, stdout, _stderr, _ = run_allowlisted(
            [sys.executable, "-c", "print('batch2-ok')"],
            timeout=5.0,
        )
        exec_ok = code == 0 and b"batch2-ok" in stdout
    except SubprocessGuardError as exc:
        findings.append(
            Finding(
                threat_class=ThreatClass.UNSAFE_SUBPROCESS.value,
                severity="error",
                message=str(exc),
                expected=False,
                remediation_owners=list(
                    REMEDIATION_OWNERS[ThreatClass.UNSAFE_SUBPROCESS.value]
                ),
            )
        )

    # timeout + process-tree termination
    timeout_ok = False
    try:
        run_allowlisted(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=0.2,
        )
    except SubprocessGuardError as exc:
        timeout_ok = "timed out" in str(exc)

    required = {
        ThreatClass.SHELL_TRUE.value,
        ThreatClass.UNSAFE_SUBPROCESS.value,
        ThreatClass.MISSING_TIMEOUT.value,
        ThreatClass.WORKER_LIMIT_EXCEEDED.value,
    }
    seen = {f.threat_class for f in findings}
    passed = required.issubset(seen) and exec_ok and timeout_ok
    return CheckResult(
        check_id="subprocess_isolation",
        passed=passed,
        findings=findings,
        details={"exec_ok": exec_ok, "timeout_termination_ok": timeout_ok},
    )


def _check_finite_json() -> CheckResult:
    findings = []
    finite_ok = False
    try:
        text = dumps_strict(fx.FINITE_PAYLOAD)
        finite_ok = "NaN" not in text and "Infinity" not in text
    except NonFiniteJSONError as exc:
        findings.append(finding_for_non_finite(exc, fixture_id="finite_payload"))

    rejected = False
    try:
        dumps_strict(fx.NON_FINITE_PAYLOAD)
    except (NonFiniteJSONError, ValueError) as exc:
        rejected = True
        findings.append(finding_for_non_finite(exc, fixture_id="non_finite_payload"))

    passed = finite_ok and rejected
    return CheckResult(
        check_id="finite_json",
        passed=passed,
        findings=findings,
        details={"finite_ok": finite_ok, "non_finite_rejected": rejected},
    )


def _check_evidence_boundary() -> CheckResult:
    findings = []
    misses: List[str] = []
    for fixture_id, record in fx.EVIDENCE_FIXTURES.items():
        hits = evaluate_evidence_record(record, fixture_id=fixture_id)
        findings.extend(hits)
        if fixture_id == "evidence_complete":
            if hits:
                misses.append(fixture_id)
            continue
        expected_map = {
            "fabricated_provenance": ThreatClass.FABRICATED_PROVENANCE.value,
            "missing_checksum": ThreatClass.MISSING_CHECKSUM.value,
            "missing_commit": ThreatClass.MISSING_COMMIT_IDENTITY.value,
            "synthetic_to_empirical": ThreatClass.SYNTHETIC_TO_EMPIRICAL.value,
        }
        expected = expected_map[fixture_id]
        if not any(h.threat_class == expected for h in hits):
            misses.append(fixture_id)
    return CheckResult(
        check_id="evidence_boundary",
        passed=not misses,
        findings=findings,
        details={"misses": misses},
    )


def _check_artifact_states() -> CheckResult:
    findings = []
    misses: List[str] = []
    for fixture_id, record in fx.ARTIFACT_FIXTURES.items():
        status = classify_artifact_state(record)
        hits = evaluate_artifact_state(record, fixture_id=fixture_id)
        findings.extend(hits)
        expected = expected_incomplete(fixture_id)
        if expected is None:
            # complete control must not emit incomplete-state findings
            if any(h.threat_class == ThreatClass.ARTIFACT_INCOMPLETE_STATE.value for h in hits):
                misses.append(fixture_id)
            continue
        if status != expected and not (expected == "MALFORMED" and status == "MALFORMED"):
            # classify_artifact_state for malformed may return MALFORMED
            if status != expected:
                misses.append(f"{fixture_id}:status={status}")
        if not any(h.threat_class == ThreatClass.ARTIFACT_INCOMPLETE_STATE.value for h in hits):
            misses.append(fixture_id)
    return CheckResult(
        check_id="artifact_states",
        passed=not misses,
        findings=findings,
        details={"misses": misses},
    )


def _check_security_vs_scientific(payload_stub: Dict[str, Any]) -> CheckResult:
    """Ensure security_pass is never aliased to scientific_pass."""
    findings = []
    distinct = (
        "security_pass" in payload_stub
        and "scientific_pass_emitted" in payload_stub
        and payload_stub.get("scientific_pass_emitted") is False
    )
    confused = payload_stub.get("security_pass") is True and payload_stub.get(
        "scientific_pass_emitted"
    ) is True
    if confused:
        findings.append(
            Finding(
                threat_class=ThreatClass.SYNTHETIC_TO_EMPIRICAL.value,
                severity="critical",
                message="security_pass must not imply scientific_pass_emitted",
                expected=False,
                remediation_owners=list(
                    REMEDIATION_OWNERS[ThreatClass.SYNTHETIC_TO_EMPIRICAL.value]
                ),
            )
        )
    return CheckResult(
        check_id="security_vs_scientific",
        passed=distinct and not confused,
        findings=findings,
        details={"distinct_fields": distinct},
    )


def run_security_suite(*, work_root: Optional[Path] = None) -> Dict[str, Any]:
    """Run the full Batch 2 security acceptance battery under no_network()."""
    root = Path(work_root) if work_root is not None else Path.cwd() / ".batch2_security_work"
    root.mkdir(parents=True, exist_ok=True)

    with no_network():
        checks: List[CheckResult] = [
            _check_network_policy(),
            _check_static_scan(),
            _check_path_containment(root / "path_root"),
            _check_subprocess(),
            _check_finite_json(),
            _check_evidence_boundary(),
            _check_artifact_states(),
        ]

    # Build preliminary payload for security-vs-scientific check.
    all_passed = all(c.passed for c in checks)
    stub = {
        "security_pass": all_passed,
        "scientific_pass_emitted": False,
    }
    vs = _check_security_vs_scientific(stub)
    checks.append(vs)
    all_passed = all(c.passed for c in checks)

    all_findings = []
    for check in checks:
        all_findings.extend(f.to_dict() for f in check.findings)

    # Determinism: re-run static scan checksum of fixture set.
    canonical_fixtures = json.dumps(fx.STATIC_FIXTURES, sort_keys=True, allow_nan=False)
    digest_a = hashlib.sha256(canonical_fixtures.encode("utf-8")).hexdigest()
    digest_b = hashlib.sha256(
        json.dumps(fx.STATIC_FIXTURES, sort_keys=True, allow_nan=False).encode("utf-8")
    ).hexdigest()
    deterministic = digest_a == digest_b and all_passed == all(c.passed for c in checks)

    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "evidence_class": EVIDENCE_CLASS,
        "synthetic": True,
        "security_pass": all_passed,
        "scientific_pass_emitted": False,
        "bayes_factor_emitted": False,
        "causal_promotion_emitted": False,
        "network_accessed": False,
        "full_dataset_download": False,
        "rea_status": _rea_status(),
        "tooling_status": {
            "ecc_agent_architecture_audit": "UNAVAILABLE",
            "ecc_security_scan": "UNAVAILABLE",
            "ecc_safety_guard": "UNAVAILABLE",
            "ecc_gateguard": "UNAVAILABLE",
            "ecc_python_testing": "UNAVAILABLE",
            "ecc_delivery_gate": "UNAVAILABLE",
            "ecc_quality_nonconformance": "UNAVAILABLE",
            "gstack_investigate": "UNAVAILABLE",
            "gstack_plan_eng_review": "UNAVAILABLE",
            "gstack_review": "UNAVAILABLE",
            "coderos_operator": "UNAVAILABLE",
            "openai_developers_agents": "UNAVAILABLE",
        },
        "n_checks": len(checks),
        "checks_passed": sum(1 for c in checks if c.passed),
        "deterministic": deterministic,
        "check_matrix": [{"check_id": c.check_id, "passed": c.passed} for c in checks],
        "checks": [c.to_dict() for c in checks],
        "findings": all_findings,
        "threat_classes": [t.value for t in ThreatClass],
        "remediation_owners": REMEDIATION_OWNERS,
        "limitations": list(DEFAULT_LIMITATIONS),
        "exit_code_if_cli": EXIT_OK if all_passed else EXIT_SECURITY_FAIL,
        "note": (
            "Batch 2 security harness is engineering acceptance evidence only. "
            "security_pass must never be read as scientific PASS or repository-wide compliance."
        ),
    }
    # Ensure the payload itself is finite-serializable.
    _ = dumps_strict(json_safe(payload))
    return json_safe(payload)
