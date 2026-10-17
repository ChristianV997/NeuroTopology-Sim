"""Boundary guards: no file, network, or process access; a stdlib-only import surface; fixed status vocabulary."""
from __future__ import annotations

import ast
import builtins
import json
import socket
import subprocess
from pathlib import Path

import pytest

from shared.bids_inventory_audit import (
    audit_inventory,
    check_payload_digest,
    file_listing_digest,
    license_report,
    parse_bids_relpath,
    parse_participants_tsv,
)

PACKAGE = Path(__file__).resolve().parents[2] / "shared" / "bids_inventory_audit"
ALLOWED_IMPORTS = {"__future__", "collections", "dataclasses", "hashlib", "re", "typing"}


def _forbid(*args, **kwargs):
    raise AssertionError("forbidden access attempted during an audit")


def test_full_audit_runs_with_file_network_and_process_access_disabled(monkeypatch, synthetic_tsv,
                                                                       synthetic_listing, synthetic_readme,
                                                                       synthetic_nemar):
    monkeypatch.setattr(builtins, "open", _forbid)
    monkeypatch.setattr(socket, "socket", _forbid)
    monkeypatch.setattr(socket, "create_connection", _forbid)
    monkeypatch.setattr(subprocess, "Popen", _forbid)
    monkeypatch.setattr(subprocess, "run", _forbid)
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing,
                             expected_tasks=["rest", "stroop"], readme_text=synthetic_readme,
                             nemar_metadata=synthetic_nemar)
    assert report["status"] == "HOLD"
    assert parse_participants_tsv(synthetic_tsv).participants
    assert parse_bids_relpath("sub-01/eeg/sub-01_task-rest_eeg.edf").valid
    assert license_report("License: CC0", None)["resolved"] is False
    assert check_payload_digest(b"x", None)["registration_status"] == "UNREGISTERED_DRAFT"
    assert file_listing_digest([("a", b"1")])["manifest_sha256"]


def test_package_imports_only_the_standard_library_and_itself():
    offenders = []
    for source in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            offenders.extend((source.name, name) for name in names if name not in ALLOWED_IMPORTS)
    assert offenders == []


def test_package_source_contains_no_file_open_or_network_call():
    banned = ("open(", "urlopen", "requests.", "socket.", "subprocess.", "os.listdir", "os.scandir", ".read_text(", ".read_bytes(")
    for source in sorted(PACKAGE.glob("*.py")):
        text = source.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{source.name} contains {token!r}"


def test_status_vocabulary_is_fixed():
    from shared.bids_inventory_audit import COHORT_IDENTITY, REGISTRATION_STATUS, SCHEMA, SCOPE, STATUS
    from shared.bids_inventory_audit.schema import EVIDENCE_CLASS

    assert (STATUS, EVIDENCE_CLASS, COHORT_IDENTITY, REGISTRATION_STATUS) == (
        "HOLD", "SYNTHETIC_ONLY", "NOT_ESTABLISHED", "UNREGISTERED_DRAFT")
    assert SCOPE == "INVENTORY_LEVEL_ONLY_PENDING_AUTHORITATIVE_MANIFEST"
    assert SCHEMA == "NeuroTopologySim.BidsInventoryAudit.v1"


@pytest.mark.parametrize("payload, digest", [(b"x", None), (b"", "0" * 64), (b"x", "TBD")])
def test_no_check_result_ever_reports_a_pass_or_a_verified_registration(payload, digest):
    rendered = json.dumps(check_payload_digest(payload, digest), allow_nan=False)
    assert "PASS" not in rendered.upper().replace("PAYLOAD_INTEGRITY", "")
    assert '"preregistration_claim": false' in rendered
