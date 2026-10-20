"""Offline evaluation harness: manifest -> rubric outcomes -> leakage report.

Labels are read only by :func:`label_consistency`, which runs after all
outcomes are fixed and reports synthetic-expectation consistency. It is not
human agreement and not ground truth.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from tools.research_plan_quality.models import RUBRIC_DIMENSIONS

from .errors import ManifestError
from .isolation import configuration_fingerprint, harness_configuration, run_development_stage, run_held_out_stage
from .leakage import detect_cross_split_leaks
from .manifest import (
    Manifest,
    load_labels,
    load_manifest,
    load_plan_records,
    rubric_dimensions_sha256,
    rubric_source_sha256,
    split_definition_sha256,
)
from .records import PlanRecord
from .splits import LOCKED_INTERNAL_VALIDATION, require_sufficient, split_summary

REPORT_SCHEMA = "NTS.ResearchPlanEvalReport.v1"
DEFAULT_MANIFEST = Path(__file__).resolve().parent / "fixtures" / "v1" / "manifest.json"

HARNESS_EVIDENCE_CLASS = "software_validation_on_synthetic_fixtures"

# Digest of the shipped split definition (manifest.split_definition_sha256). A changed split or plan
# digest fails the default run until this pin is changed in a reviewed commit.
PINNED_SPLIT_DEFINITION_SHA256 = "d587144e4960e78b343f0a2274673d0fa63341afbe8143a8baf62940a3fd016c"

NOT_MEASURED: tuple[str, ...] = (
    "criterion_leakage_rate",
    "human_agreement",
    "inter_rater_reliability",
    "generalization_performance",
    "scientific_validity_of_plans",
    "semantic_paraphrase_duplicate_rate",
)

LIMITATIONS: tuple[str, ...] = (
    "Fixtures are synthetic, authored by one person, and not drawn from real research plans or any external corpus.",
    "Labels are single-author expectations (independent=false). Consistency with them is not human agreement and not ground truth.",
    "Only lexical duplicate signals are implemented. Semantic paraphrase leakage and criterion inferability from questions are not measured.",
    "The rubric is structural. It does not judge domain soundness, statistical validity, or whether a hypothesis is true.",
    "Ten plans in eight groups cannot support any generalisation estimate.",
    "The duplicate threshold (0.85) and shingle size (3) were set by inspection, not calibrated against a labelled duplicate set.",
    "No LLM-judged leakage detection is implemented, and no leakage rate is reported.",
    "A rubric score is not scientific confirmation, preregistration, or evidence that a hypothesis is true.",
)


def label_consistency(manifest: Manifest, outcomes: Sequence[dict[str, Any]]) -> dict[str, Any]:
    labels_file = load_labels(manifest)
    labels = labels_file["labels"]
    held_out_ids = {e.fixture_id for e in manifest.entries if e.split == LOCKED_INTERNAL_VALIDATION}
    outcome_ids = {o["fixture_id"] for o in outcomes}
    mismatches: list[dict[str, Any]] = []
    matches = 0
    for outcome in outcomes:
        expected = labels.get(outcome["fixture_id"])
        if expected is None:
            mismatches.append({"fixture_id": outcome["fixture_id"], "reason": "no expectation recorded"})
            continue
        expected_dims = sorted(expected.get("expected_non_passing_dimensions", []))
        if (outcome["overall_status"] == expected.get("expected_overall_status")
                and outcome["non_passing_dimensions"] == expected_dims):
            matches += 1
        elif outcome["fixture_id"] in held_out_ids:
            mismatches.append({
                "fixture_id": outcome["fixture_id"],
                "reason": "outcome differs from expectation; expected values withheld for held-out fixtures",
            })
        else:
            mismatches.append({
                "fixture_id": outcome["fixture_id"],
                "reason": "outcome differs from expectation",
                "expected_overall_status": expected.get("expected_overall_status"),
                "observed_overall_status": outcome["overall_status"],
                "expected_non_passing_dimensions": expected_dims,
                "observed_non_passing_dimensions": outcome["non_passing_dimensions"],
            })
    orphan = sorted(set(labels) - outcome_ids)
    return {
        "adjudication": labels_file["adjudication"],
        "fixture_count": len(outcomes),
        "expectation_matches": matches,
        "expectation_mismatches": mismatches,
        "expectations_without_fixture": orphan,
        "human_agreement": None,
        "independent_adjudication": False,
        "statement": "Consistency with single-author synthetic expectations. Not human agreement and not ground truth.",
    }


def build_report(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    include_label_consistency: bool = True,
    allow_unpinned: bool = False,
) -> dict[str, Any]:
    manifest = load_manifest(Path(manifest_path))
    definition = split_definition_sha256(manifest.entries)
    pinned = definition == PINNED_SPLIT_DEFINITION_SHA256
    if not pinned and not allow_unpinned:
        raise ManifestError(
            "split definition does not match the pinned digest: a split or plan digest changed; "
            "re-pin in a reviewed change, or declare an unpinned run"
        )
    records: tuple[PlanRecord, ...] = load_plan_records(manifest)
    require_sufficient(records)

    development = run_development_stage(manifest)
    held_out = run_held_out_stage(manifest, development)
    leakage = detect_cross_split_leaks(records)

    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA,
        "harness_evidence_class": HARNESS_EVIDENCE_CLASS,
        "rubric_evidence_class": "research_plan_audit",
        "fixture_set": {
            "fixture_set_id": manifest.fixture_set_id,
            "fixture_set_version": manifest.fixture_set_version,
            "synthetic": True,
            "manifest_sha256": manifest.manifest_sha256,
            "split_definition_sha256": definition,
            "split_definition_pinned": pinned,
            "plan_count": len(records),
            "plans": [
                {"fixture_id": e.fixture_id, "group_id": e.group_id, "split": e.split, "plan_sha256": e.plan_sha256}
                for e in manifest.entries
            ],
        },
        "rubric": {
            "dimension_count": len(RUBRIC_DIMENSIONS),
            "dimensions_sha256": rubric_dimensions_sha256(),
            "source_sha256": rubric_source_sha256(),
            "configuration": harness_configuration(),
            "configuration_fingerprint": configuration_fingerprint(),
        },
        "split_definition": split_summary(records),
        "development_stage": {"outcomes": list(development.outcomes)},
        "held_out_stage": {"outcomes": list(held_out.outcomes), "configuration_fingerprint": held_out.config_fingerprint},
        "leakage": leakage.to_dict(),
        "not_measured": list(NOT_MEASURED),
        "limitations": list(LIMITATIONS),
    }
    if include_label_consistency:
        report["label_consistency"] = label_consistency(manifest, list(development.outcomes) + list(held_out.outcomes))
    return report


def to_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
