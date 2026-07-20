"""Generic, registry-driven Level-M window evaluation + output writing.

This module holds the ONE copy of the Level-M row dataclass, result dataclass,
metric helpers, contrast-evaluation, and output-writing logic that ds005620 /
ds003969 / ds003816 previously each duplicated in their own `{ds}_windows.py`.
It is driven by a `DatasetConfig` from the onboarding registry, so a new dataset
needs no new Python module for this layer.

Byte-identical guarantee: the dataclasses, helper math, and report-text templates
here reproduce the existing per-dataset modules exactly. Per-dataset report-text
divergences (e.g. ds005620's legacy "## Input inspection" heading and its two extra
lines) are expressed as `report_*` fields on `DatasetConfig`, so the generic writer
emits each dataset's currently-published report text verbatim.

ds001787 is deliberately NOT served by this module -- its dual-mode/behavioral-file
shape stays in its own dedicated modules.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import csv
import json
import math
from pathlib import Path

from sciencer_d.btc_icft.datasets.onboarding_registry import DatasetConfig
from sciencer_d.btc_icft.report_guardrails import validate_safe_text


@dataclass
class LevelMWindowRow:
    row_id: str
    subject_id: str
    session_id: str | None
    run_id: str | None
    window_id: str
    task_label: str | None
    state_label: str | None
    behavior_label: str | None
    report_label: str | None
    y: int | None
    spectral_power_proxy: float | None
    entropy_proxy: float | None
    lzc_proxy: float | None
    artifact_score: float | None
    source_file: str
    window_start_s: float
    window_end_s: float
    warnings: list[str]


@dataclass
class LevelMRealWindowResult:
    dataset_id: str
    task: str
    n_rows: int
    n_subjects: int
    n_windows: int
    class_balance: dict[str, int]
    auc: float | None
    brier: float | None
    ece: float | None
    leakage_detected: bool
    artifact_dominance: bool
    artifact_report: dict
    leakage_report: dict
    omega_event: dict
    safe_claim: str
    forbidden_claims: list[str]
    warnings: list[str]
    rows: list[dict] = field(default_factory=list)


def _validate_safe_text(text: str) -> None:
    validate_safe_text(text)


def _class_balance(y_true: list[int]) -> dict[str, int]:
    return {"0": y_true.count(0), "1": y_true.count(1)}


def _binary_auc(y_true: list[int], scores: list[float]) -> float | None:
    pos = [s for s, y in zip(scores, y_true) if y == 1]
    neg = [s for s, y in zip(scores, y_true) if y == 0]
    if not pos or not neg:
        return None
    wins, total = 0.0, 0
    for ps in pos:
        for ns in neg:
            total += 1
            wins += 1.0 if ps > ns else 0.5 if ps == ns else 0.0
    return wins / total if total else None


def _brier(y_true: list[int], scores: list[float]) -> float | None:
    if not y_true:
        return None
    return sum((y - s) ** 2 for y, s in zip(y_true, scores)) / len(y_true)


def _ece(y_true: list[int], scores: list[float], n_bins: int = 5) -> float | None:
    if not y_true:
        return None
    total, val = len(y_true), 0.0
    for i in range(n_bins):
        lo, hi = i / n_bins, (i + 1) / n_bins
        idx = [j for j, s in enumerate(scores) if (lo <= s < hi) or (i == n_bins - 1 and s == 1.0)]
        if not idx:
            continue
        conf = sum(scores[j] for j in idx) / len(idx)
        acc = sum(y_true[j] for j in idx) / len(idx)
        val += (len(idx) / total) * abs(acc - conf)
    return val


def _score_m(row: LevelMWindowRow) -> float:
    raw = (2.5 * (row.spectral_power_proxy or 0.0)) - (1.2 * (row.entropy_proxy or 0.0)) - (0.4 * (row.lzc_proxy or 0.0)) - (0.8 * (row.artifact_score or 0.0))
    return 1.0 / (1.0 + math.exp(-raw))


def build_window_artifact_report(rows: list[LevelMWindowRow]) -> dict:
    scores = [r.artifact_score for r in rows if r.artifact_score is not None]
    if not scores:
        return {"mean_artifact_score": 0.0, "max_artifact_score": 0.0, "n_artifact_high": 0, "artifact_dominance": False}
    n_high = sum(1 for s in scores if s > 0.5)
    mean_score = sum(scores) / len(scores)
    dominance = mean_score > 0.5 or (n_high > (len(scores) / 2))
    return {"mean_artifact_score": mean_score, "max_artifact_score": max(scores), "n_artifact_high": n_high, "artifact_dominance": dominance}


def build_window_leakage_report(rows: list[LevelMWindowRow]) -> dict:
    subject_ids = sorted({r.subject_id for r in rows if r.subject_id})
    unique_ids = len({r.row_id for r in rows}) == len(rows)
    leakage = (len(subject_ids) < 2) or (not unique_ids)
    return {"n_subjects": len(subject_ids), "subject_split_possible": len(subject_ids) >= 2, "row_ids_unique": unique_ids, "leakage_detected": leakage, "subject_ids": subject_ids}


def evaluate_level_m_windows(
    rows: list[LevelMWindowRow], config: DatasetConfig, task: str | None = None,
) -> LevelMRealWindowResult:
    """Assign y and compute AUC/Brier/ECE for one contrast, driven by config.

    `task` selects which of the dataset's registered contrasts to score; defaults
    to `config.default_task`. An unregistered task name raises ValueError -- same
    contract as the previous per-dataset `evaluate_level_m_windows`.
    """
    task = task or config.default_task
    contrast = config.contrast(task)  # raises ValueError("Unknown task: ...") if absent
    dataset_id = config.dataset_id

    warnings: list[str] = []
    selected: list[LevelMWindowRow] = []
    for row in rows:
        value = getattr(row, contrast.label_field)
        y = 0 if value == contrast.class0 else 1 if value == contrast.class1 else None
        nr = LevelMWindowRow(**{**asdict(row), "y": y})
        selected.append(nr)
        if y is None:
            warnings.append(f"row {row.row_id}: missing explicit label for {task}")

    metric_rows = [r for r in selected if r.y is not None]
    y_true = [r.y for r in metric_rows if r.y is not None]
    scores = [_score_m(r) for r in metric_rows]
    two_classes = len(set(y_true)) == 2
    if not two_classes:
        warnings.append("fewer than two classes available; auc/brier/ece set to None")
    auc = _binary_auc(y_true, scores) if two_classes else None
    brier = _brier(y_true, scores) if two_classes else None
    ece = _ece(y_true, scores) if two_classes else None

    artifact_report = build_window_artifact_report(selected)
    leakage_report = build_window_leakage_report(selected)
    safe_claim = (
        f"Local {dataset_id.upper()}-style files were mapped into operational "
        "Level M window-feature candidates for future residual testing."
    )
    forbidden_claims = [
        "No consciousness proof.", "No self or soul claim.", "No liberation or enlightenment claim.",
        "No afterlife claim.", "No ontology proof.", "No unsafe label inference.",
    ]
    omega_event = {"dataset_id": dataset_id, "task": task, "status": "operational_level_m", "safe_claim": safe_claim}
    return LevelMRealWindowResult(
        dataset_id=dataset_id, task=task, n_rows=len(selected), n_subjects=len({r.subject_id for r in selected}), n_windows=len(selected),
        class_balance=_class_balance(y_true), auc=auc, brier=brier, ece=ece, leakage_detected=bool(leakage_report["leakage_detected"]),
        artifact_dominance=bool(artifact_report["artifact_dominance"]), artifact_report=artifact_report, leakage_report=leakage_report,
        omega_event=omega_event, safe_claim=safe_claim, forbidden_claims=forbidden_claims, warnings=warnings,
        rows=[asdict(r) for r in selected],
    )


def write_level_m_window_outputs(
    result: LevelMRealWindowResult, out_dir: str, config: DatasetConfig,
) -> dict[str, str]:
    """Write features_m.csv + the four JSON reports + report.md.

    The report.md text is assembled from config's `report_*` fields so each
    dataset's currently-published report is reproduced byte-for-byte.
    """
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    features_path = base / "features_m.csv"
    metrics_path = base / "metrics_m.json"
    artifact_path = base / "artifact_report.json"
    leakage_path = base / "leakage_report.json"
    omega_path = base / "omega_event.json"
    report_path = base / "report.md"

    row_fieldnames = list(LevelMWindowRow.__dataclass_fields__.keys())
    with features_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row_fieldnames)
        writer.writeheader()
        for row in result.rows:
            out_row = dict(row)
            out_row["warnings"] = "; ".join(row.get("warnings") or [])
            writer.writerow(out_row)

    metrics_dict = {k: v for k, v in asdict(result).items() if k != "rows"}
    metrics_path.write_text(json.dumps(metrics_dict, indent=2), encoding="utf-8")
    artifact_path.write_text(json.dumps(result.artifact_report, indent=2), encoding="utf-8")
    leakage_path.write_text(json.dumps(result.leakage_report, indent=2), encoding="utf-8")
    omega_path.write_text(json.dumps(result.omega_event, indent=2), encoding="utf-8")

    report_lines = [
        f"# {config.dataset_id.upper()} Real/Local Level M Window Extraction",
        "## Dataset/task",
        f"- dataset_id: {result.dataset_id}",
        f"- task: {result.task}",
        config.report_input_heading,
        config.report_input_source,
        "## Window rows",
        f"- n_rows: {result.n_rows}",
        f"- n_windows: {result.n_windows}",
        "- operational Level M telemetry only.",
        *config.report_extra_window_lines,
        "## Metrics",
        f"- auc: {result.auc}",
        f"- brier: {result.brier}",
        f"- ece: {result.ece}",
        "## Artifact report",
        f"- {result.artifact_report}",
        "## Leakage report",
        f"- {result.leakage_report}",
        "## Safe claim",
        f"- {result.safe_claim}",
        "## Forbidden claims",
        *[f"- {x}" for x in result.forbidden_claims],
        "## Warnings",
        *[f"- {w}" for w in result.warnings],
        "## Next required step",
        "- Compute Level T topology rows aligned to these Level M windows.",
        *config.report_extra_next_step_lines,
    ]
    report_text = "\n".join(report_lines)
    _validate_safe_text(report_text)
    report_path.write_text(report_text + "\n", encoding="utf-8")

    return {"features_m.csv": str(features_path), "metrics_m.json": str(metrics_path), "artifact_report.json": str(artifact_path), "leakage_report.json": str(leakage_path), "omega_event.json": str(omega_path), "report.md": str(report_path)}
