"""Shared fixtures for research-cycle orchestrator tests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

DEFAULT_SECTIONS: dict[str, dict[str, Any]] = {
    "literature_evidence": {"sources": [], "claims": [], "hypothesis_links": [], "experiment_links": [], "evidence_updates": []},
    "hypothesis_registry": {"hypotheses": []},
    "experiment_plans": {"plans": []},
    "execution_results": {"executions": []},
    "null_surrogate_results": {"null_tests": []},
    "validation_reports": {"reports": []},
    "reviewer_decisions": {"decisions": []},
    "theory_state": {"theory_id": None, "version": None, "statements": [], "contradictory_evidence_ids": [], "alternative_explanations": []},
    "cycle_config": {"research_question": "Does the fixture pipeline behave deterministically?", "repo": "NeuroTopology-Sim"},
}


@pytest.fixture
def manifest_factory(tmp_path: Path):
    """Return a function that writes a manifest + section files and returns the manifest path.

    ``overrides`` maps section-name -> a dict (written as JSON by
    default), a raw string (written verbatim, for malformed-content
    tests), or a ``(extension, content)`` tuple to force a different
    extension. Sections omitted from ``overrides`` fall back to a minimal
    empty-but-valid document. Pass a section name in ``omit`` to leave it
    out of the manifest entirely (simulating "not provided").
    """

    def _make(overrides: dict[str, Any] | None = None, omit: list[str] | None = None) -> Path:
        overrides = overrides or {}
        omit = omit or []
        sections = {**DEFAULT_SECTIONS, **overrides}
        for key in omit:
            sections.pop(key, None)

        manifest: dict[str, str] = {}
        for name, content in sections.items():
            extension = "json"
            if isinstance(content, tuple):
                extension, content = content

            file_path = tmp_path / f"{name}.{extension}"
            if isinstance(content, str):
                file_path.write_text(content, encoding="utf-8")
            elif extension == "yaml":
                file_path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
            else:
                file_path.write_text(json.dumps(content), encoding="utf-8")
            manifest[name] = file_path.name

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path

    return _make
