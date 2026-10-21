"""End-to-end suite, CLI exit codes, governance invariants, compilation surface."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.release_readiness.batch2_security.report import dumps, write_reports
from tools.release_readiness.batch2_security.runner import run_security_suite
from tools.release_readiness.batch2_security.schema import (
    EVIDENCE_CLASS,
    EXIT_OK,
    EXIT_SECURITY_FAIL,
    REMEDIATION_OWNERS,
    SCHEMA_VERSION,
    ThreatClass,
)


def test_security_suite_passes_and_never_emits_scientific_pass(tmp_path: Path):
    payload = run_security_suite(work_root=tmp_path / "work")
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["evidence_class"] == EVIDENCE_CLASS
    assert payload["security_pass"] is True
    assert payload["scientific_pass_emitted"] is False
    assert payload["bayes_factor_emitted"] is False
    assert payload["network_accessed"] is False
    assert payload["rea_status"] == "REA_UNAVAILABLE"
    assert payload["deterministic"] is True
    assert payload["checks_passed"] == payload["n_checks"]
    text = dumps(payload)
    assert "NaN" not in text
    assert "Infinity" not in text
    json.loads(text)


def test_security_pass_is_not_scientific_pass_alias(tmp_path: Path):
    payload = run_security_suite(work_root=tmp_path / "work")
    assert "security_pass" in payload
    assert "scientific_pass_emitted" in payload
    assert payload["security_pass"] is True
    assert payload["scientific_pass_emitted"] is False
    # Explicit anti-confusion: fields must remain distinct keys.
    assert payload.get("scientific_pass") is None


def test_security_suite_cleans_up_path_fixture_files(tmp_path: Path):
    work_root = tmp_path / "work"
    run_security_suite(work_root=work_root)
    assert list(work_root.iterdir()) == []


def test_all_threat_classes_have_remediation_owners():
    for threat in ThreatClass:
        owners = REMEDIATION_OWNERS.get(threat.value)
        assert owners, threat
        assert all(isinstance(o, str) and o for o in owners)


def test_write_reports(tmp_path: Path):
    payload = run_security_suite(work_root=tmp_path / "work")
    paths = write_reports(payload, tmp_path / "out")
    data = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    md = Path(paths["markdown"]).read_text(encoding="utf-8")
    assert data["security_pass"] is True
    assert "scientific validity" in md.lower() or "scientific PASS" in md


def test_cli_exit_codes(tmp_path: Path):
    repo = Path(__file__).resolve().parents[3]
    script = repo / "scripts" / "run_batch2_security_audit.py"
    out = tmp_path / "cli_out"
    proc = subprocess.run(
        [sys.executable, str(script), "--output", str(out), "--work-root", str(tmp_path / "w")],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert proc.returncode == EXIT_OK, proc.stdout + proc.stderr
    assert "security_pass=True" in proc.stdout
    assert "scientific_pass_emitted=False" in proc.stdout
    assert (out / "batch2_security_report.json").is_file()


def test_owned_paths_compile():
    repo = Path(__file__).resolve().parents[3]
    targets = [
        repo / "tools" / "release_readiness" / "batch2_security",
        repo / "scripts" / "run_batch2_security_audit.py",
        repo / "tests" / "release_readiness" / "batch2_security",
    ]
    proc = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", *[str(t) for t in targets]],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_check_matrix_covers_required_domains(tmp_path: Path):
    payload = run_security_suite(work_root=tmp_path / "work")
    ids = {row["check_id"] for row in payload["check_matrix"]}
    assert {
        "network_policy",
        "static_scan",
        "path_containment",
        "subprocess_isolation",
        "finite_json",
        "evidence_boundary",
        "artifact_states",
        "security_vs_scientific",
    }.issubset(ids)
