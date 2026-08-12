"""CLI for `benchmark_packs.verification`/`benchmark_packs.gallery`/
`benchmark_packs.gallery_renderer` -- verify a built `BenchmarkPackV1`,
build a gallery over multiple verified packs, and render the gallery's
static index.

    python -m benchmark_packs.export_gallery verify \\
        --pack outputs/benchmark_packs/<name>/BenchmarkPack.json

    python -m benchmark_packs.export_gallery build-gallery \\
        --pack outputs/benchmark_packs/<name1>/BenchmarkPack.json \\
        --pack outputs/benchmark_packs/<name2>/BenchmarkPack.json \\
        --out outputs/benchmark_gallery --gallery-name "NeuroTopology Demo Gallery"

    python -m benchmark_packs.export_gallery scan-and-build \\
        --root outputs/benchmark_packs --out outputs/benchmark_gallery

    python -m benchmark_packs.export_gallery render-index \\
        --gallery outputs/benchmark_gallery/BenchmarkGallery.json

`verify` only reads an already-built pack -- it never executes a job or
reruns a report pipeline. `build-gallery`/`scan-and-build` verify each
pack (unless `--no-verify`) and only list `passed`/`passed_with_warnings`
packs as verified; `--non-strict` downgrades a missing optional artifact
(an HTML report pack, a pack's own static index) to a warning rather than
a failure. `render-index` only re-renders the gallery's static index.
See docs/benchmark_gallery.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Optional

from dataset_acquisition.store import TargetRootError
from job_runner.validation import JobStoreError
from workflows.report_pipeline import ReportPipelineError, ReportPipelineValidationError

_PROG = "benchmark_packs.export_gallery"


def _all_cli_errors():
    from benchmark_packs.gallery import BenchmarkGalleryValidationError
    from benchmark_packs.gallery_renderer import BenchmarkGalleryIndexValidationError
    from benchmark_packs.pack_manifest import BenchmarkPackIndexValidationError, BenchmarkPackValidationError
    from benchmark_packs.validation import BenchmarkPackStoreError
    from benchmark_packs.verification import BenchmarkPackVerificationValidationError

    return (
        BenchmarkPackStoreError, BenchmarkGalleryValidationError, BenchmarkGalleryIndexValidationError,
        BenchmarkPackValidationError, BenchmarkPackIndexValidationError, BenchmarkPackVerificationValidationError,
        JobStoreError, TargetRootError, ReportPipelineValidationError, ReportPipelineError,
        OSError, json.JSONDecodeError, ValueError,
    )


def _verification_summary(v) -> dict[str, Any]:
    return {
        "verification_id": v.verification_id,
        "benchmark_pack_id": v.benchmark_pack_id,
        "verification_status": v.verification_status,
        "files_missing": v.files_missing,
        "files_failed": v.files_failed,
        "ids_failed": v.ids_failed,
        "guardrail_status": v.guardrail_status,
        "warnings": v.warnings,
        "errors": v.errors,
    }


def _gallery_summary(gallery) -> dict[str, Any]:
    return {
        "gallery_id": gallery.gallery_id,
        "gallery_name": gallery.gallery_name,
        "verified_pack_ids": gallery.verified_pack_ids,
        "failed_pack_ids": gallery.failed_pack_ids,
        "dataset_ids": gallery.dataset_ids,
        "modalities": gallery.modalities,
        "input_modes": gallery.input_modes,
        "generated_gallery_index_path": gallery.generated_gallery_index_path,
    }


def _cmd_verify(args: argparse.Namespace) -> int:
    from benchmark_packs.verification import verify_benchmark_pack

    v = verify_benchmark_pack(args.pack, strict=not args.non_strict)
    print(json.dumps(_verification_summary(v), indent=2, default=str))
    return 1 if v.verification_status == "failed" else 0


def _cmd_build_gallery(args: argparse.Namespace) -> int:
    from benchmark_packs.gallery import build_benchmark_gallery

    gallery = build_benchmark_gallery(
        args.pack, args.out, gallery_name=args.gallery_name, verify=not args.no_verify, strict=not args.non_strict,
    )
    print(json.dumps(_gallery_summary(gallery), indent=2, default=str))
    return 1 if gallery.failed_pack_ids and not gallery.verified_pack_ids else 0


def _cmd_scan_and_build(args: argparse.Namespace) -> int:
    from benchmark_packs.gallery import build_benchmark_gallery, discover_benchmark_pack_paths
    from benchmark_packs.validation import BenchmarkPackStoreError

    pack_paths = discover_benchmark_pack_paths(args.root)
    if not pack_paths:
        raise BenchmarkPackStoreError(f"no BenchmarkPack.json files found under {args.root!r}")

    gallery = build_benchmark_gallery(
        pack_paths, args.out, gallery_name=args.gallery_name, verify=not args.no_verify,
        strict=not args.non_strict, source_roots=[args.root],
    )
    print(json.dumps(_gallery_summary(gallery), indent=2, default=str))
    return 1 if gallery.failed_pack_ids and not gallery.verified_pack_ids else 0


def _cmd_render_index(args: argparse.Namespace) -> int:
    from benchmark_packs.gallery import BenchmarkGalleryV1
    from pathlib import Path

    from benchmark_packs.gallery_renderer import render_benchmark_gallery_index

    gallery_path = Path(args.gallery)
    gallery = BenchmarkGalleryV1.from_json(gallery_path.read_text(encoding="utf-8"))
    index = render_benchmark_gallery_index(gallery, args.out or str(gallery_path.parent))
    print(json.dumps({
        "gallery_index_id": index.gallery_index_id, "index_html_path": index.index_html_path,
        "sections_rendered": index.sections_rendered,
    }, indent=2, default=str))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=_PROG, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify", help="verify an already-built BenchmarkPackV1")
    p_verify.add_argument("--pack", type=str, required=True)
    p_verify.add_argument("--non-strict", action="store_true", help="downgrade missing optional artifacts to warnings")
    p_verify.set_defaults(func=_cmd_verify)

    p_build_gallery = sub.add_parser("build-gallery", help="build a gallery from explicitly listed pack paths")
    p_build_gallery.add_argument("--pack", action="append", required=True, dest="pack")
    p_build_gallery.add_argument("--out", type=str, required=True)
    p_build_gallery.add_argument("--gallery-name", type=str, default="NeuroTopology Benchmark Gallery")
    p_build_gallery.add_argument("--no-verify", action="store_true")
    p_build_gallery.add_argument("--non-strict", action="store_true")
    p_build_gallery.set_defaults(func=_cmd_build_gallery)

    p_scan_and_build = sub.add_parser("scan-and-build", help="discover BenchmarkPack.json files under --root and build a gallery")
    p_scan_and_build.add_argument("--root", type=str, required=True)
    p_scan_and_build.add_argument("--out", type=str, required=True)
    p_scan_and_build.add_argument("--gallery-name", type=str, default="NeuroTopology Benchmark Gallery")
    p_scan_and_build.add_argument("--no-verify", action="store_true")
    p_scan_and_build.add_argument("--non-strict", action="store_true")
    p_scan_and_build.set_defaults(func=_cmd_scan_and_build)

    p_render_index = sub.add_parser("render-index", help="re-render only the static gallery index")
    p_render_index.add_argument("--gallery", type=str, required=True, help="path to BenchmarkGallery.json")
    p_render_index.add_argument("--out", type=str, default=None, help="output dir (default: the gallery's own directory)")
    p_render_index.set_defaults(func=_cmd_render_index)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except _all_cli_errors() as exc:
        print(f"[{_PROG}] FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
