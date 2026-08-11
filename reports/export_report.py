"""CLI for generating an `EvidenceReportV1` (Markdown/JSON) from an
already-built `EvidenceBundleV1`.

Usage::

    python -m reports.export_report \\
        --bundle outputs/evidence/ds005620_cohort_summary/EvidenceBundle.json \\
        --out outputs/evidence/ds005620_cohort_summary \\
        --format markdown,json

This is the package's only CLI entry point; `reports.evidence_report`,
`reports.tables`, `reports.renderer`, and `reports.validation` are
library-only, matching `evidence.bundle`/`benchmarks.dataset_registry`'s
precedent of having no CLI of their own. No LLM call is made anywhere in
this module -- report content is deterministic template text plus a
verbatim summary of the source bundle's own fields.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from evidence.bundle import EvidenceBundleV1  # noqa: E402
from reports.evidence_report import ReportBuildError, ReportValidationError, build_report  # noqa: E402
from reports.renderer import render_markdown  # noqa: E402

_KNOWN_FORMATS = frozenset({"markdown", "json"})


def _relative_path(path: Path, repo_root: Path = _REPO_ROOT) -> str:
    try:
        return str(path.resolve().relative_to(repo_root))
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundle", required=True, type=Path, help="path to an EvidenceBundle.json")
    parser.add_argument("--out", required=True, type=Path, help="output directory for the report")
    parser.add_argument("--format", default="markdown,json", help="comma-separated: markdown, json (default: both)")
    args = parser.parse_args()

    formats = {f.strip() for f in args.format.split(",") if f.strip()}
    unknown = formats - _KNOWN_FORMATS
    if unknown:
        print(f"[reports.export_report] FAILED: unknown format(s) {sorted(unknown)}; choose from {sorted(_KNOWN_FORMATS)}")
        return 1
    if not formats:
        print("[reports.export_report] FAILED: --format must name at least one of markdown, json")
        return 1

    if not args.bundle.exists():
        print(f"[reports.export_report] FAILED: bundle path does not exist: {args.bundle}")
        return 1
    try:
        bundle = EvidenceBundleV1.from_json(args.bundle.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        print(f"[reports.export_report] FAILED: could not read bundle: {exc}")
        return 1
    if not bundle.bundle_id or not bundle.dataset_id:
        print(f"[reports.export_report] FAILED: {args.bundle} does not look like a valid EvidenceBundle.json (missing bundle_id/dataset_id)")
        return 1

    try:
        report = build_report(bundle, args.bundle)
    except (ReportBuildError, ReportValidationError) as exc:
        print(f"[reports.export_report] FAILED: {exc}")
        return 1

    md_path = args.out / "EvidenceReport.md"
    json_path = args.out / "EvidenceReport.json"
    generated_files: list[str] = []
    if "markdown" in formats:
        generated_files.append(_relative_path(md_path))
    if "json" in formats:
        generated_files.append(_relative_path(json_path))
    report.generated_files = generated_files

    args.out.mkdir(parents=True, exist_ok=True)
    if "markdown" in formats:
        md_path.write_text(render_markdown(report), encoding="utf-8")
    if "json" in formats:
        report.write_json(json_path)

    errors = report.validate()
    summary = {
        "report_id": report.report_id,
        "bundle_id": report.bundle_id,
        "dataset_id": report.dataset_id,
        "output_paths": generated_files,
        "validation_status": "valid" if not errors else "invalid",
        "limitation_count": len(report.limitations),
        "bundle_validation_error_count": len(report.validation_summary.get("bundle_validation_errors") or []),
        "coordinate_status_counts": report.phase_space_summary.get("status_counts", {}),
    }
    print(json.dumps(summary, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
