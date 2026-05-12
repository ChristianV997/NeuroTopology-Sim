#!/usr/bin/env python3
"""CLI for Awareness Research RAG artifact manifest builder (P20.0).

Usage:
    python tools/build_awareness_rag_manifest.py --mock-fixture --out outputs/btc_icft/rag_manifest
    python tools/build_awareness_rag_manifest.py --root outputs/btc_icft --docs docs --out outputs/btc_icft/rag_manifest

Stdlib only. Does not call external APIs, create embeddings, infer labels,
fabricate targets, or make ontology proof claims.
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import sys
import tempfile
from pathlib import Path


def _load_manifest_module():
    """Load artifact_manifest module from sciencer_d/btc_icft/rag/."""
    spec_path = (
        Path(__file__).parent.parent
        / "sciencer_d"
        / "btc_icft"
        / "rag"
        / "artifact_manifest.py"
    )
    module_name = "sciencer_d.btc_icft.rag.artifact_manifest"
    spec = importlib.util.spec_from_file_location(module_name, spec_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a claim-safe RAG ingestion manifest from BTC/ICFT artifacts."
    )
    parser.add_argument("--root", default="outputs/btc_icft", help="Artifact root directory")
    parser.add_argument("--docs", default="docs", help="Docs directory")
    parser.add_argument("--out", default="outputs/btc_icft/rag_manifest", help="Output directory")
    parser.add_argument("--dataset-id", default=None, help="Override dataset ID")
    parser.add_argument(
        "--include-docs",
        default=True,
        type=lambda x: x.lower() != "false",
        help="Include docs directory (default true)",
    )
    parser.add_argument(
        "--mock-fixture",
        action="store_true",
        help="Create deterministic mock fixtures and build manifest from them",
    )
    parser.add_argument("--max-artifacts", type=int, default=None, help="Max artifacts to scan")
    args = parser.parse_args()

    mod = _load_manifest_module()
    out_dir = Path(args.out)
    generated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if args.mock_fixture:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture_root = mod.create_mock_fixtures(tmp_path)
            records = mod.scan_artifacts(
                fixture_root,
                docs_root=None,
                dataset_id=args.dataset_id,
                include_docs=False,
                max_artifacts=args.max_artifacts,
            )
            mod.write_outputs(records, out_dir, fixture_root, generated_at)
        print(f"[P20.0] mock-fixture manifest written to {out_dir} ({len(records)} artifacts)")
        return 0

    root_path = Path(args.root)
    docs_path = Path(args.docs) if args.include_docs else None

    if not root_path.is_dir():
        mod.write_outputs(
            [], out_dir, root_path, generated_at, blockers=["artifact_root_missing"]
        )
        print(
            f"[P20.0] artifact root missing ({root_path}), wrote empty-valid outputs to {out_dir}"
        )
        return 0

    records = mod.scan_artifacts(
        root_path,
        docs_root=docs_path,
        dataset_id=args.dataset_id,
        include_docs=args.include_docs,
        max_artifacts=args.max_artifacts,
    )
    mod.write_outputs(records, out_dir, root_path, generated_at)
    print(f"[P20.0] manifest written to {out_dir} ({len(records)} artifacts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
