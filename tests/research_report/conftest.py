"""Shared fixtures for research-state report compiler tests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

DEFAULT_SECTIONS: dict[str, dict[str, Any]] = {
    "reconciliation": {"pull_requests": []},
    "capability_snapshot": {"capabilities": []},
    "dataset_provenance": {"datasets": []},
    "falsification": {"results": []},
    "performance_benchmark": {"benchmarks": []},
    "memory_evidence": {"benchmarks": []},
    "interoperability": {"adapters": []},
    "topology_validation": {"checks": []},
    "test_runner": {"jobs": []},
    "merge_gate": {"decisions": []},
    "pr_retirement": {"decisions": []},
}


@pytest.fixture
def manifest_factory(tmp_path: Path):
    """Return a function that writes a manifest + section files and returns the manifest path.

    ``sections`` maps section-name -> either a dict (written as JSON) or a
    raw string (written verbatim, for malformed/non-finite-JSON tests).
    Sections omitted from ``overrides`` fall back to a minimal empty-but-valid
    document so a test can focus on the one or two sections it cares about
    while keeping ``status == "complete"``. Pass a section name in
    ``omit`` to leave it out of the manifest entirely (simulating "not
    provided").
    """

    def _make(overrides: dict[str, Any] | None = None, omit: list[str] | None = None) -> Path:
        overrides = overrides or {}
        omit = omit or []
        sections = {**DEFAULT_SECTIONS, **overrides}
        for key in omit:
            sections.pop(key, None)

        manifest: dict[str, str] = {}
        for name, content in sections.items():
            file_path = tmp_path / f"{name}.json"
            if isinstance(content, str):
                file_path.write_text(content, encoding="utf-8")
            else:
                file_path.write_text(json.dumps(content), encoding="utf-8")
            manifest[name] = file_path.name

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path

    return _make
