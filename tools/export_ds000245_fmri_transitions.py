#!/usr/bin/env python3
"""Export TransitionRecordV1 artifacts from the committed ds000245 fMRI graph artifact.

Reads the already-computed, git-committed contract files under
`contracts/fmri_tda/ds000245/` (`cohort_result*.json`,
`global_efficiency_gate*.json`) and converts them into
`transitions.TransitionRecordV1` artifacts. No raw BOLD is read, no fMRI
pipeline is re-run: this is a pure format conversion over existing committed
real-output artifacts, reusing `transitions.record`, `transitions.metrics`,
and `transitions.store` rather than duplicating any transition-record logic.

## These are GROUP CONTRASTS, not within-subject transitions

ds000245 is a **cross-sectional, between-subject** design: 45 subjects in
three fixed groups (CTL / ODN / ODP), each scanned once. **No subject moves
between groups.** There is therefore no within-subject
source_state -> target_state trajectory anywhere in this dataset.

Consequently this exporter emits **cohort-level records only**
(`record_level="cohort"`). It deliberately does NOT emit per-subject
records, because a per-subject `TransitionRecordV1` would assert that that
subject underwent a transition, which is false for every subject here. The
`transition_class` names the design explicitly, and the non-transition
status is the first limitation on every emitted record.

## Modality and feature-family discipline

These are Pearson-correlation-derived **fMRI graph metrics**, not EEG phase
measures. They are never mapped to `connectivity.mean_plv`. The topological
features are computed on a thresholded fMRI connectivity graph, which is a
different measurement from this repository's EEG persistent-homology
features of the same short name, so they are exported under distinct
`topology.fmri_graph_*` names -- the same non-conflation discipline applied
to ds005620's two Betti-1-flavoured families.

Usage:
  python tools/export_ds000245_fmri_transitions.py \\
      --input contracts/fmri_tda/ds000245 \\
      --out outputs/transitions/ds000245_fmri \\
      --variant schaefer100_motcorr
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from transitions.metrics import trajectory_mean_delta, transition_velocity  # noqa: E402
from transitions.record import TransitionRecordV1, TransitionValidationError  # noqa: E402
from transitions.store import TransitionStore  # noqa: E402

_EXPECTED_GATE_SCHEMA = "NeuroTopologySim.DS000245GlobalEfficiencyGate.v1"
_MODALITY = "fMRI"
_ALPHA = 0.05

# The artifact ships in two parcellation variants; they differ scientifically
# (anonymous coordinate clustering vs. a real anatomical atlas), so the
# variant is part of the feature-set identity rather than a cosmetic flag.
_VARIANTS: dict[str, dict[str, str]] = {
    "kmeans100": {
        "suffix": "",
        "feature_set_id": "ds000245_fmri_graph_kmeans100",
        "parcellation_note": (
            "Parcel identities are anonymous/native-space K=100 coordinate-"
            "clustering features, not validated anatomical labels."
        ),
    },
    "schaefer100_motcorr": {
        "suffix": "_schaefer100_motcorr",
        "feature_set_id": "ds000245_fmri_graph_schaefer100_motcorr",
        "parcellation_note": (
            "Atlas labels (Schaefer2018 100Parcels 7Networks, FSL MNI152) are "
            "inherited from the source artifact and should be interpreted only "
            "within that preprocessing context (per-volume motion regression + "
            "framewise-displacement scrubbing, computed by the source tool)."
        ),
    },
}

# Source artifact field -> canonical transition feature name.
#
# `global_efficiency`/`mean_degree`/`modularity` are graph metrics whose
# canonical names mean exactly this; they are Pearson-correlation-derived and
# are deliberately NOT mapped to connectivity.mean_plv.
#
# The topology.fmri_graph_* names are new names under the existing
# `topology.*` namespace (no registry change needed) chosen so an fMRI graph
# Betti-1 count can never be conflated with this repository's EEG
# persistent-homology `topology.betti1` or ds005620's spatial-defect
# `topology.spatial_defect_betti1`.
_FEATURE_MAP: dict[str, str] = {
    "global_efficiency": "connectivity.global_efficiency",
    "mean_degree": "connectivity.degree",
    "modularity": "connectivity.modularity",
    "small_worldness": "connectivity.small_worldness",
    "betti0": "topology.fmri_graph_betti0",
    "betti1": "topology.fmri_graph_betti1",
    "total_persistence_h1": "topology.fmri_graph_h1_total_persistence",
}

_FEATURE_DEFINITIONS: dict[str, str] = {
    "connectivity.global_efficiency": (
        "Global efficiency of the density-thresholded (top 15% of edges) "
        "Pearson-correlation functional connectivity graph over 100 parcels, "
        "from ds000245 cohort_result subjects[].global_efficiency. A graph "
        "metric on correlation edges -- NOT a phase-locking (PLV) measure."
    ),
    "connectivity.degree": (
        "Mean node degree of the same density-thresholded correlation graph, "
        "from subjects[].mean_degree."
    ),
    "connectivity.modularity": (
        "Modularity of the same density-thresholded correlation graph, from "
        "subjects[].modularity. Higher modularity conventionally means more "
        "segregated community structure."
    ),
    "connectivity.small_worldness": (
        "Small-worldness of the same density-thresholded correlation graph, "
        "from subjects[].small_worldness."
    ),
    "topology.fmri_graph_betti0": (
        "Betti-0 (connected component count) of the thresholded fMRI "
        "connectivity graph, from subjects[].betti0. Computed on an fMRI "
        "correlation graph -- NOT the same measurement as this repository's "
        "EEG persistent-homology topology.betti0."
    ),
    "topology.fmri_graph_betti1": (
        "Betti-1 (independent loop count) of the thresholded fMRI "
        "connectivity graph, from subjects[].betti1. Computed on an fMRI "
        "correlation graph -- NOT the same measurement as ds005620's EEG "
        "windowed persistent-homology topology.betti1, nor its "
        "single-snapshot spatial topology.spatial_defect_betti1. Do not "
        "conflate the three."
    ),
    "topology.fmri_graph_h1_total_persistence": (
        "Total persistence of H1 features in the filtration of the fMRI "
        "connectivity graph, from subjects[].total_persistence_h1. Computed "
        "on an fMRI correlation graph -- not comparable to EEG persistence "
        "summaries without justification."
    ),
}

# Group means the source artifact computes itself, keyed by its own metric
# name. Anything not in `group_stats` is aggregated by this exporter from the
# committed per-subject values, and the distinction is recorded per record.
_ARTIFACT_GROUP_STATS_METRICS = frozenset(
    {"betti1", "global_efficiency", "modularity", "total_persistence_h1"}
)


class ExportError(ValueError):
    """Raised when the input artifact is missing or structurally malformed."""


def _git_commit(repo_root: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root,
            capture_output=True, text=True, timeout=5, check=True,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def _load_artifact(input_dir: Path, variant: str) -> dict[str, Any]:
    if variant not in _VARIANTS:
        raise ExportError(
            f"unknown variant {variant!r}; choose one of {sorted(_VARIANTS)}"
        )
    if not input_dir.exists():
        raise ExportError(f"input path does not exist: {input_dir}")

    suffix = _VARIANTS[variant]["suffix"]
    cohort_path = input_dir / f"cohort_result{suffix}.json"
    gate_path = input_dir / f"global_efficiency_gate{suffix}.json"

    if not cohort_path.exists():
        raise ExportError(f"{cohort_path.name} not found under {input_dir}")

    cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
    subjects = cohort.get("subjects") or []
    if not subjects:
        raise ExportError(f"{cohort_path} contains no subject entries")

    gate: dict[str, Any] = {}
    if gate_path.exists():
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        schema = gate.get("schema")
        if schema != _EXPECTED_GATE_SCHEMA:
            raise ExportError(
                f"unsupported gate schema {schema!r} (expected {_EXPECTED_GATE_SCHEMA!r})"
            )

    artifact_paths = {"cohort_result": _relative_path(cohort_path)}
    if gate_path.exists():
        artifact_paths["global_efficiency_gate"] = _relative_path(gate_path)

    return {
        "cohort": cohort,
        "subjects": subjects,
        "gate": gate,
        "artifact_paths": artifact_paths,
        "variant": variant,
    }


def _group_values(subjects: list[dict[str, Any]], group: str, field: str) -> list[float]:
    out: list[float] = []
    for s in subjects:
        if s.get("group") != group or s.get("error"):
            continue
        value = s.get(field)
        if isinstance(value, (int, float)):
            out.append(float(value))
    return out


def _build_group_means(
    subjects: list[dict[str, Any]], cohort: dict[str, Any], group: str
) -> tuple[dict[str, float], dict[str, str]]:
    """Return (feature -> mean, feature -> provenance-of-that-mean).

    Prefers the artifact's own `group_stats` mean where it exists; otherwise
    aggregates the committed per-subject values. Never invents a value for a
    field the artifact does not contain.
    """
    group_stats = cohort.get("group_stats") or {}
    means: dict[str, float] = {}
    provenance: dict[str, str] = {}

    for source_field, canonical in _FEATURE_MAP.items():
        artifact_mean = None
        if source_field in _ARTIFACT_GROUP_STATS_METRICS:
            entry = group_stats.get(source_field) or {}
            candidate = (entry.get("group_means") or {}).get(group)
            if isinstance(candidate, (int, float)):
                artifact_mean = float(candidate)

        if artifact_mean is not None:
            means[canonical] = artifact_mean
            provenance[canonical] = "source_artifact_group_stats"
            continue

        values = _group_values(subjects, group, source_field)
        if not values:
            continue  # absent field: omitted, never defaulted
        means[canonical] = sum(values) / len(values)
        provenance[canonical] = "aggregated_by_exporter_from_committed_per_subject_values"

    return means, provenance


def _null_control_summary(gate: dict[str, Any]) -> dict[str, Any]:
    """Build an honest null-control summary from the gate artifact.

    Both of ds000245's real controls are scoped to `global_efficiency` only,
    and the permutation ANOVA is an omnibus 3-group test rather than a test
    of any specific pairwise contrast. Both facts are stated in the record
    rather than left for a reader to infer.
    """
    if not gate:
        return {
            "status": "not_provided",
            "note": (
                "no global_efficiency_gate artifact accompanied this cohort "
                "result, so no null/surrogate/permutation control is available"
            ),
        }

    contrast = gate.get("question_b_contrast_reality") or {}
    validity = gate.get("question_a_metric_validity") or {}
    p_value = contrast.get("p_value")

    if not isinstance(p_value, (int, float)):
        return {
            "status": "not_provided",
            "note": "gate artifact carries no permutation p-value",
        }

    covered = ["connectivity.global_efficiency"]
    uncovered = sorted(set(_FEATURE_MAP.values()) - set(covered))

    return {
        "status": "passed" if p_value < _ALPHA else "failed",
        "method": contrast.get("method"),
        "alpha": _ALPHA,
        "p_value": p_value,
        "n_permutations": contrast.get("n_permutations"),
        "seed": contrast.get("seed"),
        "observed_f": contrast.get("observed_f"),
        "observed_eta_squared": contrast.get("observed_eta_squared"),
        "covered_features": covered,
        "uncovered_features": uncovered,
        "metric_validity_surrogate": {
            "method": validity.get("method"),
            "n_subjects_gated": validity.get("n_subjects_gated"),
            "n_pass_p05": validity.get("n_pass_p05"),
            "fraction_pass": validity.get("fraction_pass"),
            "scope": "connectivity.global_efficiency only",
        },
        "scope_note": (
            "Both controls are scoped to global_efficiency ONLY; the other "
            "exported features carry no null/surrogate control in this "
            "artifact. The permutation test is an omnibus 3-group "
            "(CTL/ODN/ODP) label-shuffle ANOVA, NOT a test of the specific "
            "pairwise group contrast this record represents."
        ),
    }


def _base_limitations(variant: str, cohort: dict[str, Any]) -> list[str]:
    return [
        "This record represents a CROSS-SECTIONAL, BETWEEN-SUBJECT GROUP "
        "CONTRAST, not a within-subject state transition: ds000245 scans each "
        "subject once in a fixed group, and no subject moves between groups. "
        "source_state/target_state name the two groups compared, not two "
        "states any individual passed through.",
        "TransitionRecord exported from existing committed fMRI/connectivity "
        "artifacts (contracts/fmri_tda/ds000245/); no raw data were "
        "reprocessed in this step.",
        "Exploratory graph/connectivity artifact; not a clinical anesthesia- "
        "or psychiatric-state measure.",
        "This artifact does not validate consciousness detection, treatment "
        "response, mechanistic causality, or spiritual/meditative attainment.",
        "Group labels are inherited from source artifacts and were not "
        "independently revalidated by this exporter.",
        "Feature definitions are source-specific (see "
        "metadata.feature_definitions and metadata.feature_set_id) and should "
        "not be conflated with this repository's EEG topology or "
        "phase-locking features; these are Pearson-correlation fMRI graph "
        "metrics, not PLV.",
        _VARIANTS[variant]["parcellation_note"],
        "Group means are a two-point endpoint contrast; velocity_summary "
        "reflects that contrast and is NOT a rate, a time derivative, or any "
        "kind of progression estimate.",
        "Graph construction used a density threshold (top 15% of edges) per "
        "the source tool; results are for that choice and were not shown to "
        "be threshold-invariant.",
        str(
            cohort.get("provenance")
            or "source provenance field absent from cohort_result"
        ),
    ]


def _build_group_contrast_record(
    artifact: dict[str, Any],
    source_group: str,
    target_group: str,
    *,
    repo_commit: Optional[str],
) -> tuple[TransitionRecordV1, list[list[float]], list[str]]:
    cohort = artifact["cohort"]
    subjects = artifact["subjects"]
    variant = artifact["variant"]
    spec = _VARIANTS[variant]

    available_groups = sorted({s.get("group") for s in subjects if s.get("group")})
    for group, role in ((source_group, "source"), (target_group, "target")):
        if group not in available_groups:
            raise ExportError(
                f"{role} group {group!r} not present in the artifact "
                f"(available: {available_groups})"
            )
    if source_group == target_group:
        raise ExportError("source and target group must differ")

    source_means, source_prov = _build_group_means(subjects, cohort, source_group)
    target_means, target_prov = _build_group_means(subjects, cohort, target_group)

    feature_names = sorted(set(source_means) & set(target_means))
    if not feature_names:
        raise ExportError(
            f"no feature is available for both {source_group!r} and "
            f"{target_group!r}; refusing to emit a record with no comparable data"
        )

    source_vec = [source_means[f] for f in feature_names]
    target_vec = [target_means[f] for f in feature_names]
    trajectory = [source_vec, target_vec]

    delta_summary = trajectory_mean_delta(trajectory)
    velocity_summary = transition_velocity(trajectory)

    group_n = {
        g: len([s for s in subjects if s.get("group") == g and not s.get("error")])
        for g in (source_group, target_group)
    }
    subject_count = group_n[source_group] + group_n[target_group]

    null_control = _null_control_summary(artifact["gate"])

    limitations = _base_limitations(variant, cohort) + [
        f"Compares group means over {group_n[source_group]} {source_group} and "
        f"{group_n[target_group]} {target_group} subjects; individual "
        "subject-level variation is not represented in this record.",
        "Null-control coverage is partial: see null_control_summary."
        "covered_features / uncovered_features and scope_note. The omnibus "
        "permutation result does not establish that this specific pairwise "
        "contrast is real.",
        "Parametric ANOVA F/p values from the source artifact are recorded in "
        "metadata.additional_statistics for reference only; a parametric "
        "p-value is not treated as a null-control pass.",
    ]

    group_stats = cohort.get("group_stats") or {}
    record = TransitionRecordV1.make(
        dataset_id="ds000245",
        subject_id=None,
        session_id=None,
        record_level="cohort",
        modality=_MODALITY,
        source_state=source_group,
        target_state=target_group,
        transition_class="cross_sectional_group_contrast_not_within_subject_transition",
        feature_names=feature_names,
        limitations=limitations,
        claim_scope="exploratory_metric",
        evidence_level="L4_cross_subject_dataset_specific",
        repo_commit=repo_commit,
        time_axis={
            "unit": "group_contrast",
            "n_samples": 2,
            "labels": [source_group, target_group],
        },
        duration=None,
        delta_summary=delta_summary,
        velocity_summary=velocity_summary,
        null_control_summary=null_control,
        preprocessing_provenance={
            "atlas": cohort.get("atlas"),
            "pipeline": cohort.get("pipeline"),
            "n_regions": (subjects[0] or {}).get("n_regions"),
            "n_timepoints": (subjects[0] or {}).get("n_timepoints"),
            "fd_threshold_mm": cohort.get("fd_threshold_mm"),
            "fd_exclude_fraction": cohort.get("fd_exclude_fraction"),
            "n_subjects_excluded_motion": cohort.get("n_subjects_excluded_motion"),
            "variant": variant,
            "source_tool": "tools/run_ds000245_schaefer100_motcorr.py",
            "gate_tool": "tools/gate_ds000245_global_efficiency.py",
        },
        artifact_paths=dict(artifact["artifact_paths"]),
        metadata={
            "feature_set_id": spec["feature_set_id"],
            "feature_definitions": {
                f: _FEATURE_DEFINITIONS[f] for f in feature_names
            },
            "design": "cross_sectional_between_subject_group_contrast",
            "subject_count": subject_count,
            "group_n": group_n,
            "cohort_n_subjects": cohort.get("n_subjects"),
            "group_mean_provenance": {
                "source": source_prov,
                "target": target_prov,
            },
            "group_means": {source_group: source_means, target_group: target_means},
            "additional_statistics": {
                "parametric_anova_group_stats": {
                    _FEATURE_MAP[m]: {
                        k: v for k, v in (group_stats.get(m) or {}).items()
                        if k in ("F", "p_value", "eta_squared", "group_n")
                    }
                    for m in sorted(_ARTIFACT_GROUP_STATS_METRICS)
                    if m in group_stats
                },
            },
            "source_scientific_note": (artifact["gate"] or {}).get("scientific_note"),
        },
    )

    errors = record.validate()
    if errors:
        raise TransitionValidationError(
            f"{source_group}->{target_group}: exported record failed validation: "
            f"{'; '.join(errors)}"
        )
    return record, trajectory, feature_names


def export(
    input_dir: Path,
    out_dir: Path,
    *,
    variant: str = "schaefer100_motcorr",
    contrasts: Optional[list[tuple[str, str]]] = None,
    registry_path: Optional[Path] = None,
    requested_use: str = "transition_export",
    claim_family: Optional[str] = None,
) -> dict[str, Any]:
    """Export TransitionRecordV1 group-contrast records.

    `registry_path` is optional and off by default (None), so existing
    callers and the default CLI invocation are unaffected. When provided,
    this exporter consults `benchmarks.export_registry.BenchmarkRegistry`
    for dataset_id "ds000245" and fails closed (raises ExportError) before
    reading any artifact if `requested_use` is not permitted -- see
    docs/benchmark_dataset_registry.md. This is a discovery-vs-confirmation
    usage check, not a scientific validity check.
    """
    if registry_path is not None:
        from benchmarks.export_registry import BenchmarkRegistry, RegistryError

        try:
            registry = BenchmarkRegistry.load(registry_path)
            allowed, reason = registry.check_use("ds000245", requested_use, claim_family=claim_family)
        except RegistryError as exc:
            raise ExportError(f"benchmark registry error: {exc}") from exc
        if not allowed:
            raise ExportError(
                f"benchmark registry denied requested_use={requested_use!r} for "
                f"dataset_id='ds000245': {reason}"
            )

    artifact = _load_artifact(input_dir, variant)
    repo_commit = _git_commit(_REPO_ROOT)

    if contrasts is None:
        groups = sorted({s.get("group") for s in artifact["subjects"] if s.get("group")})
        contrasts = [
            (a, b) for i, a in enumerate(groups) for b in groups[i + 1:]
        ]
    if not contrasts:
        raise ExportError("no group contrasts could be determined from the artifact")

    store = TransitionStore(out_dir)
    records: list[TransitionRecordV1] = []
    skipped: list[dict[str, str]] = []

    for source_group, target_group in contrasts:
        try:
            record, trajectory, feature_names = _build_group_contrast_record(
                artifact, source_group, target_group, repo_commit=repo_commit
            )
        except (ExportError, TransitionValidationError) as exc:
            skipped.append(
                {"contrast": f"{source_group}->{target_group}", "reason": str(exc)}
            )
            continue
        store.write(record, trajectory=trajectory, trajectory_columns=feature_names)
        records.append(record)

    if not records:
        raise ExportError(
            f"no group-contrast records could be exported from {input_dir} "
            f"(skipped {len(skipped)}: {skipped})"
        )

    return {
        "records": records,
        "skipped": skipped,
        "out_dir": out_dir,
        "variant": variant,
        "feature_set_id": _VARIANTS[variant]["feature_set_id"],
        "null_control_status": records[0].null_control_summary.get("status"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--input", type=Path, default=Path("contracts/fmri_tda/ds000245"),
        help="directory holding cohort_result*.json (default: contracts/fmri_tda/ds000245)",
    )
    parser.add_argument(
        "--out", type=Path, default=Path("outputs/transitions/ds000245_fmri"),
        help="output directory for the TransitionStore",
    )
    parser.add_argument(
        "--variant", choices=sorted(_VARIANTS), default="schaefer100_motcorr",
        help="which committed parcellation variant to read (default: schaefer100_motcorr)",
    )
    parser.add_argument(
        "--contrast", action="append", default=None, metavar="SRC:TGT",
        help="restrict to a group contrast, e.g. --contrast CTL:ODP (repeatable; "
             "default: every pairwise group contrast present)",
    )
    parser.add_argument(
        "--write-phase-space-smoke", type=Path, default=None,
        help="also run the phase_space exporter over the emitted records into this directory",
    )
    parser.add_argument(
        "--registry", type=Path, default=None,
        help="optional benchmarks.export_registry.BenchmarkRegistry JSON path; if given, "
             "fails closed before exporting if --requested-use is not permitted for ds000245 "
             "(default: no registry check, unchanged from prior behavior)",
    )
    parser.add_argument(
        "--requested-use", default="transition_export",
        help="use to check against --registry (default: transition_export; ignored if "
             "--registry is not given)",
    )
    parser.add_argument(
        "--claim-family", default=None,
        help="claim family for --registry validation-use checks (only relevant for "
             "internal_validation/external_validation/confirmatory requested uses)",
    )
    args = parser.parse_args()

    contrasts = None
    if args.contrast:
        contrasts = []
        for raw in args.contrast:
            if ":" not in raw:
                print(f"[export_ds000245_fmri_transitions] FAILED: bad --contrast {raw!r}, expected SRC:TGT")
                return 1
            src, tgt = raw.split(":", 1)
            contrasts.append((src.strip(), tgt.strip()))

    try:
        result = export(
            args.input, args.out, variant=args.variant, contrasts=contrasts,
            registry_path=args.registry, requested_use=args.requested_use,
            claim_family=args.claim_family,
        )
    except (ExportError, TransitionValidationError) as exc:
        print(f"[export_ds000245_fmri_transitions] FAILED: {exc}")
        return 1

    summary = {
        "variant": result["variant"],
        "feature_set_id": result["feature_set_id"],
        "records_written": len(result["records"]),
        "contrasts": [
            f"{r.source_state}->{r.target_state}" for r in result["records"]
        ],
        "n_features": len(result["records"][0].feature_names),
        "null_control_status": result["null_control_status"],
        "skipped": result["skipped"],
        "out_dir": str(result["out_dir"]),
    }

    if args.write_phase_space_smoke is not None:
        from phase_space.export_from_transitions import export as export_phase_space

        ps = export_phase_space(args.out, args.write_phase_space_smoke)
        summary["phase_space_smoke"] = {
            "coordinates_total": ps["n_coordinates"],
            "coordinates_estimated": ps["n_estimated"],
            "coordinates_insufficient_data": ps["n_insufficient_data"],
            "coordinates_failed_validation": ps["n_failed_validation"],
            "out_dir": str(ps["out_dir"]),
        }

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
