"""CLI + benchmark-candidate conversion for dataset_importers.

    python -m dataset_importers.export_candidates --source moabb --out outputs/candidates/moabb_candidates.json
    python -m dataset_importers.export_candidates --source eegdash --out outputs/candidates/eegdash_candidates.json
    python -m dataset_importers.export_candidates --source all --out outputs/candidates/all_candidates.json
    python -m dataset_importers.export_candidates --from-fixture <fixture.json> --out <out.json>
    python -m dataset_importers.export_candidates --source all --rank --top 20 --out <out.json>
    python -m dataset_importers.export_candidates --source all --to-benchmark-candidates <out_benchmark_json>

Never downloads raw data. `--source all` (the default when neither
`--source` nor `--from-fixture` is given) aggregates every source that is
either installed or explicitly supplied via fixture; it only fails if
*every* attempted source is unavailable. An explicit single `--source`
fails immediately and clearly if that source is unavailable and no fixture
was supplied.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from benchmarks.artifact_registry import ArtifactRecordV1
from benchmarks.dataset_registry import DatasetRecordV1
from dataset_importers.candidate_record import DatasetCandidateRecordV1
from dataset_importers.eegdash_importer import (
    EegdashImporterUnavailable,
    import_eegdash_candidates,
    import_eegdash_candidates_from_fixture,
)
from dataset_importers.moabb_importer import (
    MoabbImporterUnavailable,
    import_moabb_candidates,
    import_moabb_candidates_from_fixture,
)
from dataset_importers.scoring import rank_candidates

_CONVERTIBLE_ROLES: frozenset[str] = frozenset({"development_candidate", "exploration_candidate"})

_BENCHMARK_FORBIDDEN_USES: tuple[str, ...] = (
    "transition_export",
    "phase_space_export",
    "final_claim_confirmation",
    "clinical_claim",
    "mechanistic_causal_claim",
    "prospective_prediction_claim",
)
_BENCHMARK_ALLOWED_USES: tuple[str, ...] = ("documentation", "feature_design")


def _slugify(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def convert_candidates_to_benchmark_records(
    candidates: list[DatasetCandidateRecordV1],
) -> dict[str, list[Any]]:
    """Convert only `development_candidate`/`exploration_candidate` tier
    candidates into conservative `DatasetRecordV1`/`ArtifactRecordV1`
    stubs. `blocked`/`review_needed`/`documentation_only` candidates are
    never converted -- candidate status is not validation, and only
    already-promising candidates are worth registering at all. The seed
    benchmark registry (`benchmarks/registry_seed.json`) is never touched;
    callers write this output to a separate file."""
    dataset_records: list[DatasetRecordV1] = []
    artifact_records: list[ArtifactRecordV1] = []

    for candidate in candidates:
        if candidate.benchmark_role_recommendation not in _CONVERTIBLE_ROLES:
            continue

        dataset_id = f"{_slugify(candidate.source_catalog)}-{_slugify(candidate.source_dataset_id)}"
        provenance = (
            f"Converted from a DatasetCandidateRecordV1 (candidate_id={candidate.candidate_id}, "
            f"source_catalog={candidate.source_catalog}, source_dataset_id={candidate.source_dataset_id}) "
            "produced by dataset_importers.export_candidates; not independently re-verified beyond "
            "the candidate's own catalog metadata."
        )
        limitations = list(candidate.limitations) + [
            "This dataset registry entry was converted from candidate scouting metadata only -- "
            "its existence does not imply the dataset has been validated, downloaded, or processed."
        ]
        common_kwargs = dict(
            current_role="exploration",
            allowed_uses=list(_BENCHMARK_ALLOWED_USES),
            forbidden_uses=list(_BENCHMARK_FORBIDDEN_USES),
            contamination_status="unseen",
            claim_scope_ceiling="exploratory_metric",
            evidence_level_ceiling="L0_computational_artifact",
            limitations=limitations,
        )

        dataset_records.append(
            DatasetRecordV1.make(
                dataset_id=dataset_id,
                display_name=candidate.display_name,
                modalities=list(candidate.modalities) or ["unknown"],
                transition_classes=list(candidate.potential_transition_classes),
                artifact_kinds=["dataset_candidate_metadata"],
                label_quality="",
                provenance=provenance,
                metadata={
                    "candidate_id": candidate.candidate_id,
                    "source_catalog": candidate.source_catalog,
                    "benchmark_role_recommendation": candidate.benchmark_role_recommendation,
                },
                **common_kwargs,
            )
        )

        path = candidate.public_url or candidate.documentation_url or (
            f"external://{candidate.source_catalog}/{candidate.source_dataset_id}"
        )
        artifact_records.append(
            ArtifactRecordV1.make(
                dataset_id=dataset_id,
                path=path,
                artifact_kind="dataset_candidate_metadata",
                record_kind="candidate_unstructured",
                external=True,
                modality=(candidate.modalities[0] if candidate.modalities else ""),
                produced_by="dataset_importers.export_candidates",
                metadata={
                    "candidate_id": candidate.candidate_id,
                    "source_catalog": candidate.source_catalog,
                    "source_dataset_id": candidate.source_dataset_id,
                },
                **common_kwargs,
            )
        )

    return {"dataset_records": dataset_records, "artifact_records": artifact_records}


def _load_candidates(args: argparse.Namespace) -> tuple[list[DatasetCandidateRecordV1], list[str]]:
    if args.from_fixture:
        data = json.loads(Path(args.from_fixture).read_text(encoding="utf-8"))
        catalog = data.get("source_catalog")
        if catalog == "moabb":
            return import_moabb_candidates_from_fixture(args.from_fixture), []
        if catalog == "eegdash":
            return import_eegdash_candidates_from_fixture(args.from_fixture), []
        raise ValueError(
            f"fixture file must declare a top-level 'source_catalog' of 'moabb' or 'eegdash', got {catalog!r}"
        )

    source = args.source or "all"
    candidates: list[DatasetCandidateRecordV1] = []
    notes: list[str] = []
    succeeded: list[str] = []

    if source in ("moabb", "all"):
        try:
            candidates.extend(import_moabb_candidates(prefer_installed=True))
            succeeded.append("moabb")
        except MoabbImporterUnavailable as exc:
            if source == "moabb":
                raise
            notes.append(f"moabb: {exc}")

    if source in ("eegdash", "all"):
        try:
            candidates.extend(
                import_eegdash_candidates(prefer_installed=True, live_query=bool(args.allow_live_query))
            )
            succeeded.append("eegdash")
        except EegdashImporterUnavailable as exc:
            if source == "eegdash":
                raise
            notes.append(f"eegdash: {exc}")

    if source == "all" and not succeeded:
        raise RuntimeError("; ".join(notes) or "no dataset source was available")

    return candidates, notes


def _counts_by_role(candidates: list[DatasetCandidateRecordV1]) -> dict[str, int]:
    roles = ("blocked", "review_needed", "development_candidate", "exploration_candidate", "documentation_only")
    return {role: sum(1 for c in candidates if c.benchmark_role_recommendation == role) for role in roles}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=["moabb", "eegdash", "all"], default=None)
    parser.add_argument("--out", type=Path, default=None, help="write the full candidate export here")
    parser.add_argument("--from-fixture", type=Path, default=None, help="synthetic/manual fixture JSON to import from")
    parser.add_argument("--rank", action="store_true", help="rank candidates and include scores in the output")
    parser.add_argument("--top", type=int, default=20, help="how many top-ranked candidates to print/include")
    parser.add_argument(
        "--to-benchmark-candidates",
        type=Path,
        default=None,
        help="also write a conservative DatasetRecordV1/ArtifactRecordV1 conversion here (never touches the seed registry)",
    )
    parser.add_argument(
        "--allow-live-query",
        action="store_true",
        help="opt into a real eegdash metadata-only catalog query (never used by default or in tests)",
    )
    args = parser.parse_args()

    try:
        candidates, notes = _load_candidates(args)
    except Exception as exc:
        print(f"[dataset_importers.export_candidates] FAILED: {exc}")
        return 1

    summary: dict[str, Any] = {
        "n_candidates": len(candidates),
        "counts": _counts_by_role(candidates),
    }
    if notes:
        summary["notes"] = notes

    ranked = None
    if args.rank:
        ranked = rank_candidates(candidates)
        summary["top_candidates"] = [s.to_dict() for s in ranked[: args.top]]

    if args.out:
        payload: dict[str, Any] = {
            "schema": "NeuroTopologySim.DatasetCandidateExport.v1",
            "candidates": [c.to_dict() for c in sorted(candidates, key=lambda c: c.candidate_id)],
        }
        if ranked is not None:
            payload["scores"] = [s.to_dict() for s in ranked]
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary["out"] = str(args.out)

    if args.to_benchmark_candidates:
        bench = convert_candidates_to_benchmark_records(candidates)
        bench_payload = {
            "schema": "NeuroTopologySim.DatasetCandidateBenchmarkConversion.v1",
            "dataset_records": [r.to_dict() for r in bench["dataset_records"]],
            "artifact_records": [r.to_dict() for r in bench["artifact_records"]],
        }
        args.to_benchmark_candidates.parent.mkdir(parents=True, exist_ok=True)
        args.to_benchmark_candidates.write_text(json.dumps(bench_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary["to_benchmark_candidates"] = str(args.to_benchmark_candidates)
        summary["n_benchmark_dataset_records"] = len(bench["dataset_records"])
        summary["n_benchmark_artifact_records"] = len(bench["artifact_records"])

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
