"""
Build DS005620 artifact manifest from P18.1 execution outputs (P18.2).

Walks the artifact root, collects all output files with sizes and types,
and writes artifact_manifest.json.

Usage:
  python tools/build_ds005620_artifact_manifest.py \\
    --root outputs/btc_icft/ds005620_real_benchmark_execution_mock \\
    --out outputs/btc_icft/ds005620_real_benchmark_execution_mock
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


_KNOWN_ARTIFACT_TYPES = {
    ".json": "json",
    ".csv": "csv",
    ".md": "markdown",
    ".jsonl": "jsonl",
    ".tsv": "tsv",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".txt": "text",
}

_SAFE_CLAIM = (
    "DS005620 artifact manifest built from P18.1 execution outputs. "
    "No pipeline stages executed, no data downloaded, no contracts activated."
)


def _collect_artifacts(root: Path) -> list[dict]:
    artifacts = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = p.relative_to(root)
            artifact_type = _KNOWN_ARTIFACT_TYPES.get(p.suffix.lower(), "unknown")
            size_bytes = p.stat().st_size
            artifacts.append({
                "name": p.name,
                "relative_path": str(rel),
                "absolute_path": str(p),
                "artifact_type": artifact_type,
                "size_bytes": size_bytes,
            })
    return artifacts


def _load_execution_summary(root: Path) -> dict:
    exec_path = root / "ds005620_real_benchmark_execution.json"
    if not exec_path.exists():
        return {"found": False}
    try:
        data = json.loads(exec_path.read_text(encoding="utf-8"))
        return {
            "found": True,
            "benchmark_completed": data.get("benchmark_completed"),
            "p12_succeeded": data.get("p12_succeeded"),
            "p13_succeeded": data.get("p13_succeeded"),
            "p11_succeeded": data.get("p11_succeeded"),
            "mode": data.get("mode"),
        }
    except Exception:
        return {"found": True, "parse_error": True}


def build_artifact_manifest(root: str, out_dir: str) -> str:
    root_path = Path(root)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    artifacts = _collect_artifacts(root_path)
    execution_summary = _load_execution_summary(root_path)

    manifest = {
        "dataset_id": "DS005620",
        "artifact_root": str(root_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifact_count": len(artifacts),
        "execution_summary": execution_summary,
        "artifacts": artifacts,
        "safe_claim": _SAFE_CLAIM,
    }

    manifest_path = out_path / "artifact_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return str(manifest_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build DS005620 artifact manifest (P18.2)")
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    out_dir = args.out or args.root
    manifest_path = build_artifact_manifest(args.root, out_dir)
    print(f"artifact_manifest written: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
