"""Strict finite-JSON serialization and a readable Markdown report."""
from __future__ import annotations

import json
import math
from typing import Any

from .models import ReleaseCandidateManifest


class NonFiniteValueError(ValueError):
    """Raised when a manifest contains a NaN/Infinity value that would
    otherwise silently leak into JSON output."""


def _check_finite(obj: Any, path: str = "$") -> None:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            raise NonFiniteValueError(f"non-finite float at {path}: {obj!r}")
    elif isinstance(obj, dict):
        for key, value in obj.items():
            _check_finite(value, f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            _check_finite(value, f"{path}[{index}]")


def to_finite_json(manifest: ReleaseCandidateManifest, *, indent: int = 2) -> str:
    """Serialize ``manifest`` to JSON, raising :class:`NonFiniteValueError`
    rather than silently emitting ``NaN``/``Infinity`` (which
    ``json.dumps`` does by default via ``allow_nan=True``)."""
    payload = manifest.to_dict()
    _check_finite(payload)
    return json.dumps(payload, indent=indent, allow_nan=False, sort_keys=False)


def _fmt_evidence(evidence: dict) -> str:
    return f"`{evidence['value']!r}` _(evidence: {evidence['evidence']})_"


def to_markdown(manifest: ReleaseCandidateManifest) -> str:
    d = manifest.to_dict()
    lines: list[str] = []
    lines.append(f"# Release Candidate Manifest — {d['repository'] or '(unnamed)'}")
    lines.append("")
    lines.append(f"Schema: `{d['schema']}`")
    lines.append("")
    lines.append(f"- **Target branch:** `{d['target_branch']}`")
    lines.append(f"- **Integration branch:** `{d['integration_branch']}`")
    lines.append(f"- **Source commit:** `{d['source_commit']}`")
    lines.append(f"- **Verified head commit:** {_fmt_evidence(d['verified_head_commit'])}")
    lines.append(f"- **GitHub state:** `{d['github_state']}`")
    lines.append(f"- **PR number:** {_fmt_evidence(d['pr_number'])}")
    lines.append(f"- **PR status:** {_fmt_evidence(d['pr_status'])}")
    lines.append(f"- **Draft status:** {_fmt_evidence(d['draft_status'])}")
    lines.append("")
    lines.append(f"## Merge state: `{d['merge_state']}`")
    lines.append("")
    lines.append(f"**Technical target-branch reachability:** `{d['merge_eligibility']}`")
    lines.append("")
    lines.append(f"## Release state: `{d['release_state']}`")
    lines.append("")
    lines.append(f"**Release eligibility:** `{d['release_eligibility']}`")
    lines.append("")
    if d["blockers"]:
        lines.append("### Blockers / contributing evidence")
        for b in d["blockers"]:
            lines.append(f"- {b}")
        lines.append("")
    lines.append("## Branch ancestry")
    for key, value in d["branch_ancestry"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## CI classifications")
    if d["ci_classifications"]:
        for name, evidence in d["ci_classifications"].items():
            lines.append(f"- `{name}`: {_fmt_evidence(evidence)}")
    else:
        lines.append("- (no checks available)")
    lines.append("")
    lines.append("## Changed-file ownership")
    for label, files in d["changed_file_ownership"].items():
        lines.append(f"- `{label}`: {len(files)} file(s)")
    if d["duplicate_file_findings"]:
        lines.append("")
        lines.append("### Duplicate-ownership findings")
        for finding in d["duplicate_file_findings"]:
            lines.append(
                f"- {finding['labels']}: jaccard={finding['jaccard']}, "
                f"shared={finding['shared_files']}"
            )
    lines.append("")
    lines.append(f"## Scientific gate: {_fmt_evidence(d['scientific_gate_status'])}")
    lines.append("")
    lines.append(f"## Governance status: {_fmt_evidence(d['governance_status'])}")
    lines.append(f"## Dashboard isolation status: {_fmt_evidence(d['dashboard_isolation_status'])}")
    lines.append(f"## Memory/timeout status: {_fmt_evidence(d['memory_timeout_status'])}")
    lines.append("")
    lines.append("## Provenance")
    for key, value in d["provenance"].items():
        lines.append(f"- `{key}`: `{value}`")
    if d["generated_at"] is not None:
        lines.append("")
        lines.append(f"_Generated at: {d['generated_at']}_")
    lines.append("")
    return "\n".join(lines)
