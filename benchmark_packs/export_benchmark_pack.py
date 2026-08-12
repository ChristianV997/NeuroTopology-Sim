"""CLI for `benchmark_packs` -- create curated pack specs, build them
through `job_runner`'s batch/worker infrastructure, and render a
benchmark pack's static index.

    python -m benchmark_packs.export_benchmark_pack create-spec \\
        --kind demo_pack --out outputs/benchmark_packs/demo_pack_spec.json

    python -m benchmark_packs.export_benchmark_pack build \\
        --spec outputs/benchmark_packs/demo_pack_spec.json

    python -m benchmark_packs.export_benchmark_pack build-default \\
        --kind demo_pack --out outputs/benchmark_packs/demo_pack --run-immediately --include-html

    python -m benchmark_packs.export_benchmark_pack render-index \\
        --pack outputs/benchmark_packs/demo_pack/BenchmarkPack.json

`create-spec` only writes a pack spec -- it never creates or runs a job.
`build` creates jobs (and, if the spec's `run_immediately` is set, runs
them) from an already-written spec file. `build-default` generates one of
this repository's curated default specs (over already-committed
contracts or synthetic fixtures -- never a download) and builds it in one
step. `render-index` only re-renders a pack's static index from an
already-built `BenchmarkPack.json`. See docs/benchmark_pack_generator.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from dataset_acquisition.store import TargetRootError
from job_runner.validation import JobStoreError
from workflows.report_pipeline import ReportPipelineError, ReportPipelineValidationError

_PROG = "benchmark_packs.export_benchmark_pack"

_DEFAULT_GENERATOR_KINDS = {"demo_pack", "internal_regression_pack", "methods_supplement"}


def _all_cli_errors():
    from benchmark_packs.pack_manifest import BenchmarkPackIndexValidationError, BenchmarkPackValidationError
    from benchmark_packs.pack_spec import BenchmarkPackSpecValidationError
    from benchmark_packs.validation import BenchmarkPackStoreError

    return (
        BenchmarkPackStoreError, BenchmarkPackSpecValidationError, BenchmarkPackValidationError,
        BenchmarkPackIndexValidationError, JobStoreError, TargetRootError,
        ReportPipelineValidationError, ReportPipelineError, OSError, json.JSONDecodeError, ValueError,
    )


def _make_default_spec(kind: str, output_root: str, *, include_html: bool, run_immediately: bool):
    from benchmark_packs.builder import (
        make_builtin_demo_pack_spec, make_fixture_demo_pack_spec, make_methods_supplement_pack_spec,
    )
    from benchmark_packs.validation import BenchmarkPackStoreError

    if kind == "demo_pack":
        return make_builtin_demo_pack_spec(output_root=output_root, include_html=include_html, run_immediately=run_immediately)
    if kind == "internal_regression_pack":
        fixture_dir = str(Path(output_root) / "fixtures")
        return make_fixture_demo_pack_spec(
            fixture_dir, output_root=output_root, include_html=include_html, run_immediately=run_immediately,
        )
    if kind == "methods_supplement":
        return make_methods_supplement_pack_spec(output_root=output_root, include_html=include_html, run_immediately=run_immediately)
    raise BenchmarkPackStoreError(
        f"no default spec generator for pack_kind {kind!r} -- supported: {sorted(_DEFAULT_GENERATOR_KINDS)}. "
        "Use 'build' with a custom --spec for other pack_kind values."
    )


def _pack_summary(pack) -> dict[str, Any]:
    return {
        "benchmark_pack_id": pack.benchmark_pack_id,
        "pack_name": pack.pack_name,
        "pack_kind": pack.pack_kind,
        "batch_id": pack.batch_id,
        "job_ids": pack.job_ids,
        "execution_summary": pack.execution_summary,
        "coverage_summary": pack.coverage_summary,
        "report_pack_ids": pack.report_pack_ids,
        "html_pack_ids": pack.html_pack_ids,
        "generated_index_path": pack.generated_index_path,
    }


def _cmd_create_spec(args: argparse.Namespace) -> int:
    output_root = args.output_root or str(Path(args.out).parent)
    spec = _make_default_spec(args.kind, output_root, include_html=args.include_html, run_immediately=args.run_immediately)
    spec.write_json(args.out)
    print(json.dumps({"benchmark_pack_spec_id": spec.benchmark_pack_spec_id, "spec_path": args.out, "output_root": output_root}, indent=2, default=str))
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    from benchmark_packs.builder import build_benchmark_pack
    from benchmark_packs.pack_spec import BenchmarkPackSpecV1

    spec = BenchmarkPackSpecV1.from_json(Path(args.spec).read_text(encoding="utf-8"))
    pack = build_benchmark_pack(spec)
    print(json.dumps(_pack_summary(pack), indent=2, default=str))
    return 1 if pack.execution_summary.get("status") == "failed" else 0


def _cmd_build_default(args: argparse.Namespace) -> int:
    from benchmark_packs.builder import build_benchmark_pack

    spec = _make_default_spec(
        args.kind, args.out, include_html=args.include_html, run_immediately=args.run_immediately,
    )
    spec.write_json(str(Path(args.out) / "BenchmarkPackSpec.json"))
    pack = build_benchmark_pack(spec)
    print(json.dumps(_pack_summary(pack), indent=2, default=str))
    return 1 if pack.execution_summary.get("status") == "failed" else 0


def _cmd_render_index(args: argparse.Namespace) -> int:
    from benchmark_packs.pack_manifest import BenchmarkPackV1
    from benchmark_packs.renderer import render_benchmark_pack_index

    pack_path = Path(args.pack)
    pack = BenchmarkPackV1.from_json(pack_path.read_text(encoding="utf-8"))
    index = render_benchmark_pack_index(pack, args.out or str(pack_path.parent))
    print(json.dumps({
        "index_id": index.index_id, "index_html_path": index.index_html_path,
        "sections_rendered": index.sections_rendered,
    }, indent=2, default=str))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=_PROG, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_create_spec = sub.add_parser("create-spec", help="write a curated default pack spec, without building it")
    p_create_spec.add_argument("--kind", type=str, required=True, choices=sorted(_DEFAULT_GENERATOR_KINDS))
    p_create_spec.add_argument("--out", type=str, required=True, help="path to write BenchmarkPackSpec.json")
    p_create_spec.add_argument("--output-root", type=str, default=None, help="output_root for the pack (default: --out's parent directory)")
    p_create_spec.add_argument("--include-html", action="store_true")
    p_create_spec.add_argument("--run-immediately", action="store_true")
    p_create_spec.set_defaults(func=_cmd_create_spec)

    p_build = sub.add_parser("build", help="build a BenchmarkPackV1 from an already-written pack spec")
    p_build.add_argument("--spec", type=str, required=True)
    p_build.set_defaults(func=_cmd_build)

    p_build_default = sub.add_parser("build-default", help="generate a curated default pack spec and build it in one step")
    p_build_default.add_argument("--kind", type=str, required=True, choices=sorted(_DEFAULT_GENERATOR_KINDS))
    p_build_default.add_argument("--out", type=str, required=True, help="output_root for the pack")
    p_build_default.add_argument("--include-html", action="store_true")
    p_build_default.add_argument("--run-immediately", action="store_true")
    p_build_default.set_defaults(func=_cmd_build_default)

    p_render_index = sub.add_parser("render-index", help="render only the static index for an already-built pack")
    p_render_index.add_argument("--pack", type=str, required=True, help="path to BenchmarkPack.json")
    p_render_index.add_argument("--out", type=str, default=None, help="output dir for index.html (default: the pack's own directory)")
    p_render_index.set_defaults(func=_cmd_render_index)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except _all_cli_errors() as exc:
        print(f"[{_PROG}] FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
