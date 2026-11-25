"""Finite JSON / Markdown writers for Batch 2 security reports."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union

from tools.release_readiness.batch2_security.finite_json import dumps_finite

PathLike = Union[str, Path]


def dumps(obj: Any, *, indent: Optional[int] = 2) -> str:
    return dumps_finite(obj, indent=indent)


def render_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Batch 2 Security Acceptance Report",
        "",
        f"- schema_version: `{payload.get('schema_version')}`",
        f"- evidence_class: `{payload.get('evidence_class')}`",
        f"- security_pass: `{payload.get('security_pass')}`",
        f"- scientific_pass_emitted: `{payload.get('scientific_pass_emitted')}`",
        f"- network_accessed: `{payload.get('network_accessed')}`",
        f"- rea_status: `{payload.get('rea_status')}`",
        f"- deterministic: `{payload.get('deterministic')}`",
        f"- n_checks: `{payload.get('n_checks')}`",
        f"- checks_passed: `{payload.get('checks_passed')}`",
        "",
        "## Check matrix",
        "",
        "| check_id | passed |",
        "| --- | --- |",
    ]
    for row in payload.get("check_matrix") or []:
        lines.append(f"| `{row.get('check_id')}` | `{row.get('passed')}` |")
    lines.extend(["", "## Critical findings (expected fixture detections)", ""])
    critical = [
        f
        for f in payload.get("findings") or []
        if f.get("severity") == "critical" and f.get("expected")
    ]
    if not critical:
        lines.append("- (none)")
    for finding in critical:
        lines.append(
            f"- `{finding.get('threat_class')}` @ `{finding.get('fixture_id')}`: "
            f"{finding.get('message')}"
        )
    lines.extend(["", "## Remediation owners (report-only)", ""])
    for threat, owners in (payload.get("remediation_owners") or {}).items():
        owner_list = ", ".join(f"`{o}`" for o in owners)
        lines.append(f"- `{threat}` → {owner_list}")
    lines.extend(["", "## Limitations", ""])
    for lim in payload.get("limitations") or []:
        lines.append(f"- {lim}")
    lines.append("")
    lines.append(
        "> A passing security harness does not establish scientific validity "
        "or repository-wide compliance."
    )
    lines.append("")
    return "\n".join(lines)


def _write_text_atomically(destination: Path, text: str) -> None:
    """Replace a report entry without following an existing file link."""
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_reports(
    payload: Dict[str, Any],
    output_dir: PathLike,
    trusted_root: PathLike | None = None,
) -> Dict[str, str]:
    """Write JSON and Markdown reports.

    When ``trusted_root`` is provided, the resolved output directory must stay
    inside that root. Traversal, absolute escapes, Windows-drive patterns, and
    report-file symlink escapes are rejected via the path-containment guard.
    Atomic replacement prevents writes from following pre-existing hard links.
    This is a local harness boundary, not a repository-wide security claim.
    """
    from tools.release_readiness.batch2_security.path_containment import resolve_under_root

    trusted = Path(trusted_root) if trusted_root is not None else None
    if trusted is not None:
        out = resolve_under_root(trusted, output_dir)
    else:
        out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    jp = out / "batch2_security_report.json"
    mp = out / "batch2_security_report.md"
    json_text = dumps(payload) + "\n"
    markdown_text = render_markdown(payload)
    if trusted is not None:
        # Validate both final names before writing either file. Atomic replacement
        # below avoids following a file symlink/hard link after this check.
        resolve_under_root(trusted, jp)
        resolve_under_root(trusted, mp)
    _write_text_atomically(jp, json_text)
    _write_text_atomically(mp, markdown_text)
    return {"json": str(jp), "markdown": str(mp)}
