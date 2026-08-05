"""Write-once run envelopes and content-addressed input manifests."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_input_manifest(paths: Iterable[str | Path], root: str | Path | None = None) -> dict[str, Any]:
    """Hash files deterministically; missing inputs are explicit failures."""
    root_path = Path(root).resolve() if root is not None else None
    entries = []
    for raw_path in sorted((Path(path) for path in paths), key=lambda p: str(p)):
        path = raw_path.resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        relative = str(path.relative_to(root_path)) if root_path is not None else str(path)
        entries.append({"path": relative.replace("\\", "/"), "sha256": _sha256_file(path), "bytes": path.stat().st_size})
    manifest = {"schema": "NeuroTopologySim.InputManifest.v1", "files": entries}
    manifest["manifest_sha256"] = sha256_text(canonical_json(manifest))
    return manifest


def build_code_manifest(
    paths: Iterable[str | Path],
    *,
    root: str | Path | None = None,
    git_commit: str = "unknown",
    dirty_tree: bool = False,
) -> dict[str, Any]:
    """Build a code snapshot manifest without modifying the checkout."""
    manifest = build_input_manifest(paths, root=root)
    return {
        "schema": "NeuroTopologySim.CodeManifest.v1",
        "git_commit": git_commit,
        "dirty_tree": bool(dirty_tree),
        "files": manifest["files"],
        "manifest_sha256": sha256_text(canonical_json({
            "git_commit": git_commit,
            "dirty_tree": bool(dirty_tree),
            "files": manifest["files"],
        })),
    }


@dataclass
class RunEnvelope:
    root: Path
    stage: str
    run_id: str
    protocol: dict[str, Any]
    hypothesis: dict[str, Any]

    REQUIRED_FILES = (
        "protocol.json", "hypothesis.json", "code_manifest.json", "input_manifest.json",
        "stage_lock.json", "metrics.json", "transition_operators.json",
        "surrogate_summary.json", "promotion_decision.json", "events.jsonl", "RunRecord.json",
    )

    def initialize(self, *, code_manifest: dict[str, Any], input_manifest: dict[str, Any], stage_lock: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=False)
        self.write_once("protocol.json", self.protocol)
        self.write_once("hypothesis.json", self.hypothesis)
        self.write_once("code_manifest.json", code_manifest)
        self.write_once("input_manifest.json", input_manifest)
        self.write_once("stage_lock.json", stage_lock)

    def write_once(self, name: str, payload: Any) -> Path:
        if name not in self.REQUIRED_FILES:
            raise ValueError(f"unknown envelope file: {name}")
        destination = self.root / name
        if destination.exists():
            raise FileExistsError(destination)
        if name == "events.jsonl":
            destination.write_text("", encoding="utf-8")
        else:
            destination.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        return destination

    def append_event(self, event: dict[str, Any]) -> None:
        with (self.root / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(event) + "\n")

    def finalize(self, payloads: dict[str, Any]) -> None:
        for name, payload in payloads.items():
            if name not in self.REQUIRED_FILES:
                raise ValueError(f"unknown envelope file: {name}")
            self.write_once(name, payload)
        missing = set(self.REQUIRED_FILES) - {p.name for p in self.root.iterdir()}
        if missing:
            raise ValueError(f"cannot finalize incomplete envelope: {sorted(missing)}")
