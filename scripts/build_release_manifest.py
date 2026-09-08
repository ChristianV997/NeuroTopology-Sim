#!/usr/bin/env python3
"""Thin CLI over tools.release_manifest. Read-only end to end; makes
no network call itself -- GitHub-side facts come only from an optional
pre-fetched JSON snapshot passed via --pr-snapshot.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.release_manifest.manifest_builder import build_manifest  # noqa: E402
from tools.release_manifest.models import ChangedFileOwnership, ScientificGateInput  # noqa: E402
from tools.release_manifest.reporting import to_finite_json, to_markdown  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-path", default=".", type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--target-branch", required=True)
    parser.add_argument("--integration-branch", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--pr-snapshot", type=Path, default=None)
    parser.add_argument("--scientific-data-mode", default=None)
    parser.add_argument("--scientific-verdict", default=None)
    parser.add_argument("--scientific-bayes-factor", type=float, default=None)
    parser.add_argument("--scientific-evidence-kind", default=None)
    parser.add_argument(
        "--other-ownership",
        action="append",
        default=[],
        metavar="LABEL=FILE1,FILE2,...",
        help="another concurrent owner's changed-file set, for duplicate detection",
    )
    parser.add_argument("--dependency-blocker", action="append", default=[])
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--markdown-out", type=Path, default=None)
    parser.add_argument(
        "--include-generated-at",
        default=None,
        help="explicit timestamp string to embed as generated_at (omit to leave it null)",
    )
    args = parser.parse_args()

    scientific_gate_input = None
    if args.scientific_verdict is not None or args.scientific_data_mode is not None:
        scientific_gate_input = ScientificGateInput(
            data_mode=args.scientific_data_mode,
            verdict=args.scientific_verdict,
            bayes_factor=args.scientific_bayes_factor,
            evidence_kind=args.scientific_evidence_kind,
        )

    other_ownerships = []
    for entry in args.other_ownership:
        label, _, files_str = entry.partition("=")
        files = tuple(f for f in files_str.split(",") if f)
        other_ownerships.append(ChangedFileOwnership(label=label, changed_files=files))

    manifest = build_manifest(
        repo_path=args.repo_path,
        repository=args.repository,
        target_branch=args.target_branch,
        integration_branch=args.integration_branch,
        source_commit=args.source_commit,
        pr_snapshot_path=args.pr_snapshot,
        scientific_gate_input=scientific_gate_input,
        other_ownerships=other_ownerships,
        dependency_blockers=tuple(args.dependency_blocker),
        include_generated_at=args.include_generated_at is not None,
        generated_at_value=args.include_generated_at,
    )

    json_text = to_finite_json(manifest)
    markdown_text = to_markdown(manifest)

    if args.json_out:
        args.json_out.write_text(json_text)
    else:
        print(json_text)

    if args.markdown_out:
        args.markdown_out.write_text(markdown_text)

    print(f"merge_state={manifest.merge_state} merge_eligibility={manifest.merge_eligibility}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
