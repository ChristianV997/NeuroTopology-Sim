#!/usr/bin/env python3
"""CLI for P20.1 Awareness RAG ingestion pack builder."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def _parse_bool_str(value: str) -> bool:
    lowered = str(value).strip().lower()
    if lowered in {"true", "1", "yes", "y"}:
        return True
    if lowered in {"false", "0", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError("expected one of: true/false/1/0/yes/no")


def _load_module():
    module_name = "sciencer_d.btc_icft.rag.ingestion_pack"
    module_path = (
        Path(__file__).parent.parent
        / "sciencer_d"
        / "btc_icft"
        / "rag"
        / "ingestion_pack.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic Awareness Research RAG ingestion pack.")
    parser.add_argument("--manifest", default="outputs/btc_icft/rag_manifest/rag_artifact_manifest.jsonl")
    parser.add_argument("--artifact-root", default="outputs/btc_icft")
    parser.add_argument("--docs", default="docs")
    parser.add_argument("--out", default="outputs/btc_icft/rag_ingestion_pack")
    parser.add_argument("--max-chars-per-chunk", type=int, default=1800)
    parser.add_argument("--overlap-chars", type=int, default=200)
    parser.add_argument("--max-artifacts", type=int, default=None)
    parser.add_argument("--include-priority-max", type=int, default=3)
    parser.add_argument(
        "--include-quarantined",
        default=False,
        type=_parse_bool_str,
        help="Include quarantined chunks in index candidate outputs",
    )
    parser.add_argument("--mock-fixture", action="store_true")
    args = parser.parse_args()

    mod = _load_module()
    out_dir = Path(args.out)

    if args.mock_fixture:
        manifest = mod.build_with_mock_fixture(
            out_dir=out_dir,
            max_chars_per_chunk=args.max_chars_per_chunk,
            overlap_chars=args.overlap_chars,
            max_artifacts=args.max_artifacts,
            include_priority_max=args.include_priority_max,
            include_quarantined=args.include_quarantined,
        )
        print(f"[P20.1] mock ingestion pack written to {out_dir} ({manifest['counts']['chunks_total']} chunks)")
        return 0

    manifest = mod.build_ingestion_pack(
        manifest_path=Path(args.manifest),
        artifact_root=Path(args.artifact_root),
        docs_root=Path(args.docs),
        out_dir=out_dir,
        max_chars_per_chunk=args.max_chars_per_chunk,
        overlap_chars=args.overlap_chars,
        max_artifacts=args.max_artifacts,
        include_priority_max=args.include_priority_max,
        include_quarantined=args.include_quarantined,
    )

    blockers = manifest.get("blockers", [])
    if "rag_manifest_missing" in blockers:
        print(f"[P20.1] manifest missing ({args.manifest}), wrote empty-valid outputs to {out_dir}")
    else:
        print(f"[P20.1] ingestion pack written to {out_dir} ({manifest['counts']['chunks_total']} chunks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
