from __future__ import annotations

import json
from pathlib import Path

from tools.toe_research.literature_bridge.generator import (
    BTC_ICFT_CONSTRUCTS,
    GUARDRAIL_FLAGS,
    PHYSICS_CONSTRAINTS,
    TOE_CONSTRUCTS,
    TOE_PRIMITIVES,
    TOL_CONSTRUCTS,
    generate,
)


def test_generator_records_missing_inputs_without_failing(tmp_path):
    output = tmp_path / "output"
    manifest, return_code = generate(
        [str(tmp_path / "missing_a"), str(tmp_path / "missing_b")], output
    )

    priority = json.loads(
        (output / "toe_literature_priority_matrix.json").read_text(encoding="utf-8")
    )
    assert return_code == 0
    assert manifest["ok"] is True
    assert set(priority["status"].values()) == {"not_available"}
    assert priority["toe_constructs"] == TOE_CONSTRUCTS


def test_generator_strict_mode_fails_when_an_input_is_missing(tmp_path):
    output = tmp_path / "output"
    manifest, return_code = generate([str(tmp_path / "missing")], output, strict=True)

    assert return_code == 1
    assert manifest["ok"] is False
    assert manifest["missing_upstream_roots"]


def test_generation_manifest_disables_unsafe_runtime_flags(tmp_path):
    output = tmp_path / "output"
    generate([str(tmp_path / "missing")], output)
    manifest = json.loads(
        (output / "generation_manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["guardrails"] == {flag: False for flag in GUARDRAIL_FLAGS}


def test_generator_covers_every_required_construct_family(tmp_path):
    output = tmp_path / "output"
    generate([str(tmp_path / "missing")], output)

    priority = json.loads(
        (output / "toe_literature_priority_matrix.json").read_text(encoding="utf-8")
    )
    required = set(
        TOE_PRIMITIVES + BTC_ICFT_CONSTRUCTS + TOL_CONSTRUCTS + PHYSICS_CONSTRAINTS
    )
    assert set(priority["toe_constructs"]) == required


def test_makefile_passes_every_required_upstream_root():
    makefile = (Path(__file__).resolve().parents[2] / "Makefile").read_text(
        encoding="utf-8"
    )
    for root in (
        "outputs/literature_senses",
        "outputs/project_corpus_digest",
        "outputs/public_repo_harvest",
        "outputs/tol_digest",
        "outputs/tol_digest/mental_health_bridge",
        "outputs/command_center/mock_payloads",
    ):
        assert root in makefile


def test_makefile_contains_every_p40_target():
    makefile = (Path(__file__).resolve().parents[2] / "Makefile").read_text(
        encoding="utf-8"
    )
    targets = [
        "toe-literature-bridge",
        "toe-literature-bridge-topology",
        "toe-literature-bridge-constraints",
        "validate-toe-literature-bridge",
        "toe-literature-bridge-sync-obsidian",
        "toe-literature-bridge-command-center-payloads",
        "toe-literature-bridge-rag-pack",
        "toe-literature-bridge-cycle",
    ]
    for target in targets:
        assert f"{target}:" in makefile
