"""P14 — Dataset label adapter readiness planning scaffold.

Inspects local metadata files and reports whether each dataset has enough
explicit metadata to activate a P12 label contract. Non-invasive read-only
layer; does not download data, infer labels, or fabricate targets.

Readiness statuses
------------------
metadata_file_not_found        No local metadata file found at known search paths.
metadata_empty_or_unreadable   File exists but could not be parsed.
no_candidate_label_column      File parsed but no recognizable label column.
insufficient_label_values      Candidate column has fewer than 2 distinct values.
needs_explicit_mapping         2+ distinct values found; binary mapping requires human declaration.
ready_to_activate              Explicit binary mapping declared in adapter spec and metadata present.
planning_required              Stub spec; adapter plan not yet authored.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

_BANNED_PHRASES = (
    "proves consciousness",
    "consciousness proven",
    "soul proven",
    "afterlife proven",
    "liberation detected",
    "ontology solved",
    "ultimate reality",
    "q equals self",
    "q equals soul",
    "q_abs equals suffering",
    "f_dress equals karma",
    "sedated implies no_experience",
    "unresponsive implies unconscious",
)

_SAFE_CLAIM = (
    "Local EEG study metadata files were inspected for label adapter readiness. "
    "No labels were inferred, no targets were fabricated, and no data was downloaded."
)

_READINESS_STATUSES = frozenset({
    "metadata_file_not_found",
    "metadata_empty_or_unreadable",
    "no_candidate_label_column",
    "insufficient_label_values",
    "needs_explicit_mapping",
    "ready_to_activate",
    "planning_required",
})

_CANDIDATE_LABEL_KEYWORDS = frozenset({
    "label", "condition", "trial_type", "state", "category",
    "task", "class", "type", "group", "annotation",
})


def _validate_safe_text(text: str) -> None:
    lower = text.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            raise ValueError(f"Banned phrase detected: {phrase!r}")


@dataclass
class DatasetLabelAdapterSpec:
    """Planning-time knowledge about how to activate a P12 label contract."""
    dataset_id: str
    title: str
    source_hint: str
    metadata_search_subdirs: list[str]
    candidate_metadata_filenames: list[str]
    known_label_columns: list[str]
    label_scope: str
    known_positive_values: list[str]
    known_negative_values: list[str]
    join_scope_note: str
    planning_status: str
    adapter_caveats: list[str]


@dataclass
class LabelAdapterProbeResult:
    """Result of probing one candidate metadata file."""
    dataset_id: str
    metadata_path: str
    metadata_found: bool
    parse_ok: bool
    n_rows: int
    columns_found: list[str]
    candidate_label_columns: list[str]
    unique_values: dict[str, list[str]]
    has_sufficient_label_values: bool
    readiness_status: str
    readiness_note: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class DatasetAdapterReadiness:
    """Full per-dataset adapter readiness assessment."""
    dataset_id: str
    adapter_spec: dict
    probes: list[dict]
    best_probe: dict | None
    can_activate_contract: bool
    activation_blockers: list[str]
    suggested_label_column: str | None
    suggested_positive_values: list[str]
    suggested_negative_values: list[str]
    readiness_status: str
    next_required_step: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class LabelAdapterReadinessSummary:
    """Multi-dataset readiness summary."""
    n_datasets: int
    n_ready_to_activate: int
    n_needs_explicit_mapping: int
    n_missing_metadata: int
    n_planning_required: int
    per_dataset: dict[str, dict]
    safe_claim: str
    forbidden_claims: list[str]


def get_label_adapter_specs() -> dict[str, DatasetLabelAdapterSpec]:
    """Return planning-time adapter specs for all known seed datasets."""
    specs = [
        DatasetLabelAdapterSpec(
            dataset_id="DS005620",
            title="OpenNeuro meditation EEG DS005620 — label adapter plan",
            source_hint="OpenNeuro",
            metadata_search_subdirs=[".", "sub-*/ses-*", "sub-*"],
            candidate_metadata_filenames=[
                "*_events.tsv", "events.tsv", "*_events.csv", "events.csv",
                "conditions.tsv", "labels.csv", "metadata.csv",
            ],
            known_label_columns=["trial_type", "condition", "state_label", "explicit_state_label"],
            label_scope="window",
            known_positive_values=[],
            known_negative_values=[],
            join_scope_note=(
                "Window-level join: metadata onset/duration maps to "
                "window_start_s/window_end_s via P12 align_eeg_labels."
            ),
            planning_status="planning_required",
            adapter_caveats=[
                "Explicit binary mapping (positive_values/negative_values) requires human declaration.",
                "No label inference from trial_type strings.",
                "No consciousness/state/self/soul claims.",
            ],
        ),
        DatasetLabelAdapterSpec(
            dataset_id="DS002094",
            title="OpenNeuro EEG DS002094 — label adapter plan",
            source_hint="OpenNeuro",
            metadata_search_subdirs=[".", "sub-*/ses-*", "sub-*"],
            candidate_metadata_filenames=[
                "*_events.tsv", "events.tsv", "*_events.csv", "events.csv",
                "conditions.tsv", "labels.csv", "metadata.csv",
            ],
            known_label_columns=["trial_type", "condition", "label"],
            label_scope="window",
            known_positive_values=[],
            known_negative_values=[],
            join_scope_note=(
                "Window-level join via onset/duration fields in events sidecar."
            ),
            planning_status="planning_required",
            adapter_caveats=[
                "Explicit binary mapping requires human declaration.",
                "No label inference from event codes.",
            ],
        ),
        DatasetLabelAdapterSpec(
            dataset_id="ds001787",
            title="OpenNeuro meditation EEG ds001787 — label adapter plan",
            source_hint="OpenNeuro",
            metadata_search_subdirs=[".", "sub-*/ses-*", "sub-*"],
            candidate_metadata_filenames=[
                "*_events.tsv", "events.tsv", "*_events.csv", "events.csv",
                "conditions.tsv", "labels.csv", "metadata.csv",
            ],
            known_label_columns=["trial_type", "condition", "meditation_state"],
            label_scope="window",
            known_positive_values=[],
            known_negative_values=[],
            join_scope_note="Window-level join via BIDS events sidecar onset/duration.",
            planning_status="planning_required",
            adapter_caveats=[
                "Explicit binary mapping requires human declaration.",
                "No inference from meditation session names.",
            ],
        ),
        DatasetLabelAdapterSpec(
            dataset_id="ds003969",
            title="OpenNeuro meditation EEG ds003969 — label adapter plan",
            source_hint="OpenNeuro",
            metadata_search_subdirs=[".", "sub-*/ses-*", "sub-*"],
            candidate_metadata_filenames=[
                "*_events.tsv", "events.tsv", "*_events.csv", "events.csv",
                "conditions.tsv", "labels.csv", "metadata.csv",
            ],
            known_label_columns=["trial_type", "condition", "label"],
            label_scope="window",
            known_positive_values=[],
            known_negative_values=[],
            join_scope_note="Window-level join via BIDS events sidecar.",
            planning_status="planning_required",
            adapter_caveats=[
                "Explicit binary mapping requires human declaration.",
                "No label inference across cohorts.",
            ],
        ),
        DatasetLabelAdapterSpec(
            dataset_id="ds003816",
            title="OpenNeuro meditation EEG ds003816 — label adapter plan",
            source_hint="OpenNeuro",
            metadata_search_subdirs=[".", "sub-*/ses-*", "sub-*"],
            candidate_metadata_filenames=[
                "*_events.tsv", "events.tsv", "*_events.csv", "events.csv",
                "conditions.tsv", "labels.csv", "metadata.csv",
            ],
            known_label_columns=["trial_type", "condition", "label"],
            label_scope="window",
            known_positive_values=[],
            known_negative_values=[],
            join_scope_note="Window-level join via BIDS events sidecar.",
            planning_status="planning_required",
            adapter_caveats=[
                "Explicit binary mapping requires human declaration.",
                "No label inference from condition names.",
            ],
        ),
        DatasetLabelAdapterSpec(
            dataset_id="PhysioNet_GABA",
            title="PhysioNet GABA EEG — label adapter plan",
            source_hint="PhysioNet",
            metadata_search_subdirs=[".", "metadata"],
            candidate_metadata_filenames=[
                "labels.csv", "metadata.csv", "conditions.tsv",
                "*_events.tsv", "events.tsv", "*_events.csv", "events.csv",
            ],
            known_label_columns=["group", "condition", "treatment", "label"],
            label_scope="subject",
            known_positive_values=[],
            known_negative_values=[],
            join_scope_note=(
                "Subject-level join: metadata group/condition applies per subject. "
                "Requires subject_id join key in metadata."
            ),
            planning_status="planning_required",
            adapter_caveats=[
                "Explicit binary mapping requires human declaration.",
                "No label inference for intervention/control mapping.",
            ],
        ),
    ]
    return {s.dataset_id: s for s in specs}


def _discover_metadata_files(
    local_root: Path,
    spec: DatasetLabelAdapterSpec,
) -> list[Path]:
    """Find candidate metadata files under local_root using spec patterns."""
    found: list[Path] = []
    if not local_root.is_dir():
        return found
    for name_pattern in spec.candidate_metadata_filenames:
        for path in local_root.rglob(name_pattern):
            if path.is_file():
                found.append(path)
    return sorted(set(found))


def _is_candidate_label_column(col: str) -> bool:
    col_lower = col.lower()
    return any(kw in col_lower for kw in _CANDIDATE_LABEL_KEYWORDS)


def probe_metadata_file(
    dataset_id: str,
    path: Path,
    spec: DatasetLabelAdapterSpec,
) -> LabelAdapterProbeResult:
    """Probe one candidate metadata file for label adapter readiness."""
    if not path.is_file():
        return LabelAdapterProbeResult(
            dataset_id=dataset_id,
            metadata_path=str(path),
            metadata_found=False,
            parse_ok=False,
            n_rows=0,
            columns_found=[],
            candidate_label_columns=[],
            unique_values={},
            has_sufficient_label_values=False,
            readiness_status="metadata_file_not_found",
            readiness_note="Metadata file not found at specified path.",
        )

    ext = path.suffix.lower()
    if ext not in {".csv", ".tsv"}:
        return LabelAdapterProbeResult(
            dataset_id=dataset_id,
            metadata_path=str(path),
            metadata_found=True,
            parse_ok=False,
            n_rows=0,
            columns_found=[],
            candidate_label_columns=[],
            unique_values={},
            has_sufficient_label_values=False,
            readiness_status="metadata_empty_or_unreadable",
            readiness_note=f"Unsupported metadata extension: {ext}",
        )

    delimiter = "\t" if ext == ".tsv" else ","
    try:
        with path.open("r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter=delimiter)
            rows = list(reader)
            columns_found = list(reader.fieldnames or [])
    except (OSError, UnicodeDecodeError) as exc:
        return LabelAdapterProbeResult(
            dataset_id=dataset_id,
            metadata_path=str(path),
            metadata_found=True,
            parse_ok=False,
            n_rows=0,
            columns_found=[],
            candidate_label_columns=[],
            unique_values={},
            has_sufficient_label_values=False,
            readiness_status="metadata_empty_or_unreadable",
            readiness_note=f"Parse error: {exc}",
        )

    if not rows:
        return LabelAdapterProbeResult(
            dataset_id=dataset_id,
            metadata_path=str(path),
            metadata_found=True,
            parse_ok=True,
            n_rows=0,
            columns_found=columns_found,
            candidate_label_columns=[],
            unique_values={},
            has_sufficient_label_values=False,
            readiness_status="metadata_empty_or_unreadable",
            readiness_note="Metadata file has no data rows.",
        )

    known_cols = set(spec.known_label_columns)
    candidate_cols = [
        c for c in columns_found
        if c in known_cols or _is_candidate_label_column(c)
    ]

    if not candidate_cols:
        return LabelAdapterProbeResult(
            dataset_id=dataset_id,
            metadata_path=str(path),
            metadata_found=True,
            parse_ok=True,
            n_rows=len(rows),
            columns_found=columns_found,
            candidate_label_columns=[],
            unique_values={},
            has_sufficient_label_values=False,
            readiness_status="no_candidate_label_column",
            readiness_note=(
                f"No recognized label column in {len(columns_found)} columns. "
                f"Known: {spec.known_label_columns}."
            ),
        )

    unique_values: dict[str, list[str]] = {}
    for col in candidate_cols:
        vals = sorted({str(r.get(col, "")).strip() for r in rows if str(r.get(col, "")).strip()})
        unique_values[col] = vals

    has_sufficient = any(len(v) >= 2 for v in unique_values.values())
    warnings: list[str] = []

    if spec.known_positive_values and spec.known_negative_values:
        mapping_known = any(
            set(spec.known_positive_values) <= set(v) and set(spec.known_negative_values) <= set(v)
            for v in unique_values.values()
        )
        if mapping_known:
            status = "ready_to_activate"
            note = (
                "Known binary mapping values found in metadata. "
                "Contract can be activated after human review."
            )
        elif has_sufficient:
            status = "needs_explicit_mapping"
            note = (
                "Candidate label column with 2+ distinct values found. "
                "Binary mapping (positive_values/negative_values) requires human declaration."
            )
        else:
            status = "insufficient_label_values"
            note = "Candidate label column found but fewer than 2 distinct values."
    elif has_sufficient:
        status = "needs_explicit_mapping"
        note = (
            "Candidate label column with 2+ distinct values found. "
            "Binary mapping (positive_values/negative_values) requires human declaration."
        )
    else:
        status = "insufficient_label_values"
        note = "Candidate label column has fewer than 2 distinct values."
        warnings.append("Only one distinct label value found; binary classification not possible.")

    return LabelAdapterProbeResult(
        dataset_id=dataset_id,
        metadata_path=str(path),
        metadata_found=True,
        parse_ok=True,
        n_rows=len(rows),
        columns_found=columns_found,
        candidate_label_columns=candidate_cols,
        unique_values=unique_values,
        has_sufficient_label_values=has_sufficient,
        readiness_status=status,
        readiness_note=note,
        warnings=warnings,
    )


def assess_dataset_adapter_readiness(
    dataset_id: str,
    local_root: str,
    spec: DatasetLabelAdapterSpec | None = None,
) -> DatasetAdapterReadiness:
    """Full readiness assessment for one dataset."""
    specs = get_label_adapter_specs()
    if spec is None:
        if dataset_id not in specs:
            raise ValueError(f"Unknown dataset_id: {dataset_id!r}. Known: {sorted(specs)}")
        spec = specs[dataset_id]

    root = Path(local_root)
    metadata_files = _discover_metadata_files(root, spec)

    if not metadata_files:
        return DatasetAdapterReadiness(
            dataset_id=dataset_id,
            adapter_spec=asdict(spec),
            probes=[],
            best_probe=None,
            can_activate_contract=False,
            activation_blockers=["No local metadata file found at known search paths."],
            suggested_label_column=None,
            suggested_positive_values=[],
            suggested_negative_values=[],
            readiness_status="metadata_file_not_found",
            next_required_step=(
                f"Supply local metadata file for {dataset_id} at one of: "
                f"{spec.metadata_search_subdirs}. "
                f"Expected filenames: {spec.candidate_metadata_filenames}."
            ),
        )

    probes = [probe_metadata_file(dataset_id, f, spec) for f in metadata_files]
    probe_dicts = [asdict(p) for p in probes]

    best = max(
        probes,
        key=lambda p: (
            p.readiness_status == "ready_to_activate",
            p.readiness_status == "needs_explicit_mapping",
            p.has_sufficient_label_values,
            p.n_rows,
        ),
    )
    best_dict = asdict(best)
    blockers: list[str] = []
    suggested_col: str | None = None
    suggested_pos: list[str] = []
    suggested_neg: list[str] = []

    if best.readiness_status == "ready_to_activate":
        can_activate = True
        overall_status = "ready_to_activate"
        next_step = (
            "Metadata and binary mapping are ready. Activate the P12 contract by declaring "
            "explicit_label_column, positive_values, and negative_values, then run align_eeg_labels."
        )
    elif best.readiness_status == "needs_explicit_mapping":
        can_activate = False
        overall_status = "needs_explicit_mapping"
        blockers.append("Binary mapping (positive_values/negative_values) requires human declaration.")
        if best.candidate_label_columns:
            suggested_col = best.candidate_label_columns[0]
            vals = best.unique_values.get(suggested_col, [])
            if len(vals) >= 2:
                suggested_pos = [vals[0]]
                suggested_neg = [vals[1]]
        next_step = (
            f"Declare explicit binary mapping for {dataset_id}: "
            f"set explicit_label_column={suggested_col!r}, "
            f"positive_values, negative_values in the P12 contract, then run align_eeg_labels."
        )
    elif best.readiness_status == "insufficient_label_values":
        can_activate = False
        overall_status = "insufficient_label_values"
        blockers.append("Candidate label column has fewer than 2 distinct values.")
        next_step = (
            f"Ensure the metadata for {dataset_id} contains at least 2 distinct label values "
            "for binary classification."
        )
    else:
        can_activate = False
        overall_status = best.readiness_status
        blockers.append(best.readiness_note)
        next_step = (
            f"Resolve metadata readiness for {dataset_id}: {best.readiness_note}"
        )

    warnings = [w for p in probes for w in p.warnings]

    return DatasetAdapterReadiness(
        dataset_id=dataset_id,
        adapter_spec=asdict(spec),
        probes=probe_dicts,
        best_probe=best_dict,
        can_activate_contract=can_activate,
        activation_blockers=blockers,
        suggested_label_column=suggested_col,
        suggested_positive_values=suggested_pos,
        suggested_negative_values=suggested_neg,
        readiness_status=overall_status,
        next_required_step=next_step,
        warnings=warnings,
    )


def assess_all_datasets(
    data_root: str,
    dataset_id_subdirs: bool = True,
) -> LabelAdapterReadinessSummary:
    """Assess all known seed datasets under data_root."""
    specs = get_label_adapter_specs()
    per_dataset: dict[str, dict] = {}
    n_ready = 0
    n_needs_mapping = 0
    n_missing = 0
    n_planning = 0

    for ds_id, spec in specs.items():
        if dataset_id_subdirs:
            ds_root = str(Path(data_root) / ds_id)
        else:
            ds_root = data_root
        try:
            result = assess_dataset_adapter_readiness(ds_id, ds_root, spec)
        except Exception as exc:
            result = DatasetAdapterReadiness(
                dataset_id=ds_id,
                adapter_spec=asdict(spec),
                probes=[],
                best_probe=None,
                can_activate_contract=False,
                activation_blockers=[str(exc)],
                suggested_label_column=None,
                suggested_positive_values=[],
                suggested_negative_values=[],
                readiness_status="metadata_file_not_found",
                next_required_step=f"Error during assessment: {exc}",
            )

        d = asdict(result)
        per_dataset[ds_id] = d
        s = result.readiness_status
        if s == "ready_to_activate":
            n_ready += 1
        elif s == "needs_explicit_mapping":
            n_needs_mapping += 1
        elif s in ("metadata_file_not_found", "metadata_empty_or_unreadable"):
            n_missing += 1
        else:
            n_planning += 1

    return LabelAdapterReadinessSummary(
        n_datasets=len(specs),
        n_ready_to_activate=n_ready,
        n_needs_explicit_mapping=n_needs_mapping,
        n_missing_metadata=n_missing,
        n_planning_required=n_planning,
        per_dataset=per_dataset,
        safe_claim=_SAFE_CLAIM,
        forbidden_claims=[
            "No consciousness proof.",
            "No self or soul claim.",
            "No liberation or enlightenment claim.",
            "No afterlife claim.",
            "No ontology proof.",
            "No label inference.",
            "No target fabrication.",
        ],
    )


def _build_omega_event(summary: LabelAdapterReadinessSummary) -> dict:
    _validate_safe_text(summary.safe_claim)
    payload = f"{summary.n_datasets}:{summary.n_ready_to_activate}:{summary.safe_claim}"
    return {
        "event_id": hashlib.sha256(payload.encode()).hexdigest()[:16],
        "event_type": "dataset_label_adapter_readiness",
        "n_datasets": summary.n_datasets,
        "n_ready_to_activate": summary.n_ready_to_activate,
        "n_needs_explicit_mapping": summary.n_needs_explicit_mapping,
        "n_missing_metadata": summary.n_missing_metadata,
        "safe_claim": summary.safe_claim,
        "forbidden_claims": summary.forbidden_claims,
    }


def write_adapter_readiness_outputs(
    summary: LabelAdapterReadinessSummary,
    out_dir: str,
) -> dict[str, str]:
    """Write all P14 output artifacts."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}

    # Per-dataset plans
    for ds_id, d in summary.per_dataset.items():
        p = out / f"adapter_plan_{ds_id}.json"
        p.write_text(json.dumps(d, indent=2), encoding="utf-8")
        outputs[f"adapter_plan_{ds_id}"] = str(p)

    # Summary
    summary_dict = {
        "n_datasets": summary.n_datasets,
        "n_ready_to_activate": summary.n_ready_to_activate,
        "n_needs_explicit_mapping": summary.n_needs_explicit_mapping,
        "n_missing_metadata": summary.n_missing_metadata,
        "n_planning_required": summary.n_planning_required,
        "per_dataset_status": {
            ds_id: d["readiness_status"]
            for ds_id, d in summary.per_dataset.items()
        },
        "safe_claim": summary.safe_claim,
    }
    p = out / "adapter_readiness_summary.json"
    p.write_text(json.dumps(summary_dict, indent=2), encoding="utf-8")
    outputs["adapter_readiness_summary"] = str(p)

    # Omega event
    omega = _build_omega_event(summary)
    p = out / "omega_event.json"
    p.write_text(json.dumps(omega, indent=2), encoding="utf-8")
    outputs["omega_event"] = str(p)

    # Report
    lines = [
        "# Dataset Label Adapter Readiness Report",
        "",
        "## Stage",
        "",
        "P14 — Dataset label adapter readiness planning scaffold. "
        "Local metadata files were inspected for P12 label contract activation readiness.",
        "",
        "## Summary",
        "",
        f"- Datasets assessed: {summary.n_datasets}",
        f"- Ready to activate: {summary.n_ready_to_activate}",
        f"- Needs explicit mapping: {summary.n_needs_explicit_mapping}",
        f"- Missing metadata: {summary.n_missing_metadata}",
        f"- Planning required: {summary.n_planning_required}",
        "",
        "## Per-Dataset Status",
        "",
    ]
    for ds_id, d in summary.per_dataset.items():
        lines.append(f"### {ds_id}")
        lines.append(f"- readiness_status: {d['readiness_status']}")
        lines.append(f"- can_activate_contract: {d['can_activate_contract']}")
        lines.append(f"- next_required_step: {d['next_required_step']}")
        if d.get("activation_blockers"):
            for b in d["activation_blockers"]:
                lines.append(f"  - blocker: {b}")
        lines.append("")

    lines += [
        "## Guardrails",
        "",
        "- No labels inferred from metadata.",
        "- No targets fabricated.",
        "- No data downloaded.",
        "- No consciousness/self/soul/liberation/afterlife/ontology proof claims.",
        "",
        "## Safe claim",
        "",
        summary.safe_claim,
        "",
        "## Forbidden claims",
        "",
    ]
    for fc in summary.forbidden_claims:
        lines.append(f"- {fc}")
    lines.append("")
    lines.append(
        "## Next required step\n\n"
        "For datasets with `needs_explicit_mapping`: declare "
        "`explicit_label_column`, `positive_values`, and `negative_values` "
        "in the P12 contract, then run `align_eeg_labels`.\n"
        "For datasets with `metadata_file_not_found`: supply local metadata "
        "files at the expected paths and rerun P14."
    )

    report = "\n".join(lines) + "\n"
    _validate_safe_text(report)
    p = out / "report.md"
    p.write_text(report, encoding="utf-8")
    outputs["report"] = str(p)

    return outputs
