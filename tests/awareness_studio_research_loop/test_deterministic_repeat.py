from __future__ import annotations

import json

from tools.awareness_studio_research_loop.compiler import compile_research_cycle
from tests.awareness_studio_research_loop.fixtures_data import complete_cycle_overrides

NOW = "2026-01-01T00:00:00+00:00"


def test_repeated_compile_is_byte_identical(manifest_factory):
    manifest = manifest_factory(complete_cycle_overrides())

    report1 = compile_research_cycle(manifest, now=NOW, repo="r")
    report2 = compile_research_cycle(manifest, now=NOW, repo="r")

    json1 = json.dumps(report1, indent=2, sort_keys=True, allow_nan=False)
    json2 = json.dumps(report2, indent=2, sort_keys=True, allow_nan=False)
    assert json1 == json2
    assert report1["canonical_checksum"] == report2["canonical_checksum"]
    assert report1["paper_draft_markdown"] == report2["paper_draft_markdown"]


def test_omitted_now_only_changes_generated_at_and_checksum(manifest_factory):
    manifest = manifest_factory(complete_cycle_overrides())

    report1 = compile_research_cycle(manifest)
    report2 = compile_research_cycle(manifest)

    volatile = {"generated_at", "canonical_checksum"}
    stable1 = {k: v for k, v in report1.items() if k not in volatile}
    stable2 = {k: v for k, v in report2.items() if k not in volatile}
    assert stable1 == stable2
