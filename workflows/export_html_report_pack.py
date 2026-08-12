"""CLI for `workflows.html_report_pack`.

    python -m workflows.export_html_report_pack \\
        --report-pack outputs/report_packs/<id>/ReportPack.json \\
        --out outputs/report_packs/<id>/html

    python -m workflows.export_html_report_pack \\
        --report-pack outputs/report_packs/<id>/ReportPack.json \\
        --pipeline-manifest outputs/report_packs/<id>/PipelineRunManifest.json \\
        --out outputs/report_packs/<id>/html --no-copy-artifacts --title "My Report"

Renders a deterministic, static `index.html` (plus `HtmlReportPack.json`)
from an already-built `ReportPackV1`. This module does not run the
pipeline itself -- see `workflows.export_report_pack --include-html` to
do both in one invocation.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dataset_acquisition.store import TargetRootError
from workflows.html_report_pack import HtmlReportPackError, render_html_report_pack
from workflows.html_validation import HtmlReportPackValidationError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report-pack", type=Path, required=True, help="ReportPackV1 JSON file")
    parser.add_argument("--out", type=str, required=True, help="output directory for index.html (must be under outputs/ or data/)")
    parser.add_argument("--pipeline-manifest", type=Path, default=None, help="optional ReportPipelineRunManifestV1 JSON file")
    parser.add_argument("--title", type=str, default=None, help="override the page title")
    copy_group = parser.add_mutually_exclusive_group()
    copy_group.add_argument("--copy-artifacts", dest="copy_artifacts", action="store_true", default=None, help="copy small JSON/Markdown artifacts alongside index.html (default)")
    copy_group.add_argument("--no-copy-artifacts", dest="copy_artifacts", action="store_false", help="write relative links to the original artifact paths instead of copying")
    args = parser.parse_args()

    if not args.report_pack.exists():
        print(f"[workflows.export_html_report_pack] FAILED: --report-pack does not exist: {args.report_pack}")
        return 1

    try:
        html_pack = render_html_report_pack(
            report_pack_path=args.report_pack, out_dir=args.out,
            pipeline_manifest_path=args.pipeline_manifest, title=args.title,
            copy_artifacts=True if args.copy_artifacts is None else args.copy_artifacts,
        )
    except (HtmlReportPackError, HtmlReportPackValidationError, TargetRootError) as exc:
        print(f"[workflows.export_html_report_pack] FAILED: {exc}")
        return 1

    summary = {
        "html_pack_id": html_pack.html_pack_id,
        "report_pack_id": html_pack.report_pack_id,
        "dataset_id": html_pack.dataset_id,
        "input_mode": html_pack.input_mode,
        "output_root": html_pack.output_root,
        "index_html_path": html_pack.index_html_path,
        "copied_artifact_count": len(html_pack.copied_artifact_paths),
        "rendered_sections": html_pack.rendered_sections,
        "validation_status": "valid" if not html_pack.validate() else "invalid",
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
