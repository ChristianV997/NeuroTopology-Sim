"""Repository-backed inventory for the Science R&D command centre.

The inventory deliberately reports only files that exist in the checkout.  It
does not infer experiment outcomes, dataset labels, or scientific claims.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any


def find_repository_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").exists():
            return candidate
    return Path.cwd().resolve()


def _record(path: Path, root: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "path": path.relative_to(root).as_posix(),
        "kind": path.suffix.lstrip(".").lower() or "file",
        "bytes": stat.st_size,
        "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def _files(root: Path, pattern: str) -> list[Path]:
    return sorted((p for p in root.glob(pattern) if p.is_file()), key=lambda p: p.as_posix())


def build_research_snapshot(root: Path | None = None) -> dict[str, Any]:
    """Return a deterministic, repository-derived overview for the web UI."""
    repo = (root or find_repository_root()).resolve()
    reports = _files(repo, "REPORT_*.md") + _files(repo, "outputs/**/REPORT_*.md")
    # Avoid duplicate records if a future glob overlaps through a symlink.
    reports = list(dict.fromkeys(p.resolve() for p in reports))
    artifacts = _files(repo, "outputs/**/*")
    command_payloads = _files(repo, "outputs/command_center/mock_payloads/*.json")
    rag_artifacts = [p for p in artifacts if "rag" in p.name.lower() or "rag" in p.parts]

    simulations = []
    for path in reports:
        item = _record(path, repo)
        item["title"] = path.stem.removeprefix("REPORT_").replace("_", " ")
        dataset_match = re.search(r"(?<![a-zA-Z0-9])(ds\d{6})(?!\d)", path.as_posix())
        item["dataset"] = dataset_match.group(1) if dataset_match else None
        simulations.append(item)

    groups: dict[str, int] = {}
    for path in artifacts:
        relative = path.relative_to(repo / "outputs")
        group = relative.parts[0] if len(relative.parts) > 1 else "root"
        groups[group] = groups.get(group, 0) + 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "repository_checkout",
        "claim_scope": "artifact_inventory_only",
        "counts": {
            "simulation_reports": len(simulations),
            "output_artifacts": len(artifacts),
            "command_center_payloads": len(command_payloads),
            "rag_artifacts": len(rag_artifacts),
        },
        "simulations": simulations,
        "recent_artifacts": [_record(p, repo) for p in sorted(artifacts, key=lambda p: p.stat().st_mtime, reverse=True)[:16]],
        "artifact_groups": [{"name": name, "count": count} for name, count in sorted(groups.items(), key=lambda row: (-row[1], row[0]))],
        "command_center_payloads": [_record(p, repo) for p in command_payloads],
        "guardrails": [
            "No clinical claims",
            "No ontology promotion",
            "Artifact inventory only",
            "No inferred labels or outcomes",
        ],
    }


def resolve_repository_file(relative_path: str, root: Path | None = None) -> Path:
    """Resolve a UI-requested file while preventing traversal outside the repo."""
    repo = (root or find_repository_root()).resolve()
    candidate = (repo / relative_path).resolve()
    if candidate != repo and repo not in candidate.parents:
        raise ValueError("Path is outside the repository")
    if not candidate.is_file():
        raise FileNotFoundError(relative_path)
    return candidate
