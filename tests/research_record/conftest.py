"""Shared fixtures for research-record compiler tests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

DEFAULT_SECTIONS: dict[str, dict[str, Any]] = {
    "reconciliation": {"pull_requests": []},
    "agent_contributions": {
        "repository": None,
        "baseline_commit": None,
        "evidence_source": None,
        "inventory_is_not_evidence": True,
        "required_warnings": [],
        "contributions": [],
    },
    "dashboard_isolation": {"ok": None, "scanned_files": 0, "violations": [], "evidence": None},
    "test_runner": {"jobs": []},
    "performance_benchmark": {"benchmarks": []},
    "memory_evidence": {"benchmarks": []},
    "dataset_provenance": {"datasets": []},
    "cohort_readiness": {"cohorts": []},
    "topology_validation": {"checks": []},
    "falsification": {"results": []},
    "merge_gate": {"decisions": []},
    "release_manifest": {"schema_version": None, "repo": None, "commit": None, "branch": None, "generated_at": None, "entries": []},
    "scientific_gate_reports": {"gates": []},
    "blocker_reports": {"blockers": []},
    "artifact_references": {"artifacts": []},
    "operator_notes": {"notes": []},
}

_DEFAULT_EXTENSION = {
    "agent_contributions": "yaml",
}


@pytest.fixture
def manifest_factory(tmp_path: Path):
    """Return a function that writes a manifest + section files and returns the manifest path.

    ``overrides`` maps section-name -> one of:
      - a dict: written as JSON (or YAML for ``agent_contributions``, whose
        real-world source is YAML).
      - a raw string: written verbatim, for malformed-JSON/YAML tests.
      - a ``(extension, content)`` tuple: forces the file extension
        (``"json"``/``"yaml"``/``"csv"``); ``content`` is a dict (dumped
        appropriately) or a raw string for csv/malformed-content tests.

    Sections omitted from ``overrides`` fall back to a minimal empty-but-
    valid document so ``status == "complete"`` unless a test cares about
    partial records. Pass a section name in ``omit`` to leave it out of the
    manifest entirely (simulating "not provided").
    """

    def _make(overrides: dict[str, Any] | None = None, omit: list[str] | None = None) -> Path:
        overrides = overrides or {}
        omit = omit or []
        sections = {**DEFAULT_SECTIONS, **overrides}
        for key in omit:
            sections.pop(key, None)

        manifest: dict[str, str] = {}
        for name, content in sections.items():
            extension = _DEFAULT_EXTENSION.get(name, "json")
            if isinstance(content, tuple):
                extension, content = content

            file_path = tmp_path / f"{name}.{extension}"
            if isinstance(content, str):
                file_path.write_text(content, encoding="utf-8")
            elif extension == "yaml":
                file_path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
            elif extension == "csv":
                file_path.write_text(content, encoding="utf-8")
            else:
                file_path.write_text(json.dumps(content), encoding="utf-8")
            manifest[name] = file_path.name

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path

    return _make
