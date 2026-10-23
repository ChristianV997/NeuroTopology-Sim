"""Pinned digests must not depend on the checkout's line endings.

Git on Windows with core.autocrlf=true checks text files out as CRLF, while the
fixture pins were computed over the LF bytes committed to the repository. A
CRLF-only difference is not a content change, so the pins must still verify.
Any other byte change must still fail closed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.research_plan_quality_eval.errors import ManifestError
from tools.research_plan_quality_eval.manifest import _read_checked, rubric_source_sha256

FIXTURES = Path(__file__).resolve().parents[2] / "tools" / "research_plan_quality_eval" / "fixtures" / "v1"


def _shipped_manifest() -> dict:
    return json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


def test_crlf_checkout_of_shipped_plan_verifies_against_its_lf_pin(tmp_path: Path):
    record = _shipped_manifest()["records"][0]
    lf_bytes = (FIXTURES / record["plan_file"]).read_bytes().replace(b"\r\n", b"\n")
    crlf_copy = tmp_path / "plan.json"
    crlf_copy.write_bytes(lf_bytes.replace(b"\n", b"\r\n"))
    assert _read_checked(crlf_copy, record["plan_sha256"], "plan file") == crlf_copy.read_bytes()


def test_shipped_rubric_source_pin_verifies_on_this_checkout():
    assert rubric_source_sha256() == _shipped_manifest()["rubric"]["source_sha256"]


def test_lone_carriage_return_still_changes_the_digest():
    from tools.research_plan_quality_eval.records import normalized_text_sha256

    assert normalized_text_sha256(b"a\r\nb\r\n") == normalized_text_sha256(b"a\nb\n")
    assert normalized_text_sha256(b"a\rb\n") != normalized_text_sha256(b"a\nb\n")


def test_content_change_in_crlf_checkout_still_fails_closed(tmp_path: Path):
    record = _shipped_manifest()["records"][0]
    altered = (FIXTURES / record["plan_file"]).read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n") + b" "
    copy = tmp_path / "plan.json"
    copy.write_bytes(altered)
    with pytest.raises(ManifestError, match="hash mismatch"):
        _read_checked(copy, record["plan_sha256"], "plan file")
