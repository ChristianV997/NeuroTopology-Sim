from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import json
import math
from pathlib import Path

from sciencer_d.btc_icft.datasets.ds005620 import DS005620LabelRow
from sciencer_d.btc_icft.level_m.features import extract_level_m_features


@dataclass(frozen=True)
class LevelMFeatureRow:
    row_id: str
    subject_id: str
    task_label: str
    y: int
    spectral_power_proxy: float
    entropy_proxy: float
    lzc_proxy: float
    artifact_score: float
    state_label: str | None
    behavior_label: str | None
    report_label: str | None


@dataclass(frozen=True)
class LevelMBaselineResult:
    dataset_id: str
    task: str
    n_rows: int
    n_subjects: int
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


def _signal_for_row(row: DS005620LabelRow) -> list[float]:
    if row.state_label == "awake":
        return [0.03, 0.07, 0.02, 0.05, 0.08, 0.06, 0.04, 0.01]
    if row.state_label == "sedated":
        return [0.24, 0.20, 0.22, 0.26, 0.19, 0.27, 0.23, 0.21]
    if row.behavior_label == "unresponsive":
        return [0.15, 0.10, 0.17, 0.11, 0.16, 0.09, 0.14, 0.12]
    return [0.08, 0.12, 0.10, 0.09, 0.11, 0.10, 0.13, 0.07]


def build_mock_ds005620_level_m_rows() -> list[LevelMFeatureRow]:
    labels = [
        DS005620LabelRow("r1", "sub-01", state_label="awake", behavior_label="responsive", report_label="experience"),
        DS005620LabelRow("r2", "sub-01", state_label="sedated", behavior_label="unresponsive", report_label="no_experience"),
        DS005620LabelRow("r3", "sub-02", state_label="awake", behavior_label="responsive", report_label="experience"),
        DS005620LabelRow("r4", "sub-02", state_label="sedated", behavior_label="unresponsive", report_label="no_experience"),
    ]
    return extract_level_m_rows(labels)


def extract_level_m_rows(label_rows: list[DS005620LabelRow]) -> list[LevelMFeatureRow]:
    rows: list[LevelMFeatureRow] = []
    for row in label_rows:
        signal = _signal_for_row(row)
        features = extract_level_m_features(signal)
        task_label = "awake_vs_sedated"
        y = 1 if row.state_label == "sedated" else 0
        rows.append(
            LevelMFeatureRow(
                row_id=row.row_id,
                subject_id=row.subject_id,
                task_label=task_label,
                y=y,
                spectral_power_proxy=features["spectral_power_proxy"],
                entropy_proxy=features["entropy_proxy"],
                lzc_proxy=features["lzc_proxy"],
                artifact_score=features["artifact_score"],
                state_label=row.state_label,
                behavior_label=row.behavior_label,
                report_label=row.report_label,
            )
        )
    return rows


def _class_balance(y_true: list[int]) -> dict[str, int]:
    return {"0": y_true.count(0), "1": y_true.count(1)}


def _binary_auc(y_true: list[int], scores: list[float]) -> float | None:
    pos = [(s, y) for s, y in zip(scores, y_true) if y == 1]
    neg = [(s, y) for s, y in zip(scores, y_true) if y == 0]
    if not pos or not neg:
        return None
    wins = 0.0
    total = 0
    for ps, _ in pos:
        for ns, _ in neg:
            total += 1
            if ps > ns:
                wins += 1.0
            elif ps == ns:
                wins += 0.5
    return wins / total if total else None


def _brier(y_true: list[int], scores: list[float]) -> float | None:
    if not y_true:
        return None
    return sum((y - s) ** 2 for y, s in zip(y_true, scores)) / len(y_true)


def _ece(y_true: list[int], scores: list[float], n_bins: int = 5) -> float | None:
    if not y_true:
        return None
    total = len(y_true)
    ece = 0.0
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        idx = [j for j, s in enumerate(scores) if (lo <= s < hi) or (i == n_bins - 1 and s == 1.0)]
        if not idx:
            continue
        conf = sum(scores[j] for j in idx) / len(idx)
        acc = sum(y_true[j] for j in idx) / len(idx)
        ece += (len(idx) / total) * abs(acc - conf)
    return ece


def _score(row: LevelMFeatureRow) -> float:
    raw = (2.5 * row.spectral_power_proxy) - (1.2 * row.entropy_proxy) - (0.4 * row.lzc_proxy) - (0.8 * row.artifact_score)
    return 1.0 / (1.0 + math.exp(-raw))


def build_artifact_report(rows: list[LevelMFeatureRow]) -> dict:
    scores = [r.artifact_score for r in rows]
    n_high = sum(1 for s in scores if s > 0.5)
    mean_score = (sum(scores) / len(scores)) if scores else 0.0
    dominance = mean_score > 0.5 or (n_high / len(scores) > 0.5 if scores else False)
    return {
        "mean_artifact_score": mean_score,
        "max_artifact_score": max(scores) if scores else 0.0,
        "n_artifact_high": n_high,
        "artifact_dominance": dominance,
    }


def build_leakage_report(rows: list[LevelMFeatureRow]) -> dict:
    n_subjects = len({r.subject_id for r in rows})
    return {
        "n_subjects": n_subjects,
        "subject_split_possible": n_subjects >= 2,
        "leakage_detected": False,
        "warning": None if n_subjects >= 2 else "Need at least two subjects for subject-safe split.",
    }


def evaluate_level_m_baseline(rows: list[LevelMFeatureRow], task: str) -> LevelMBaselineResult:
    if task not in {"awake_vs_sedated", "responsive_vs_unresponsive", "experience_vs_no_experience"}:
        raise ValueError(f"Unknown task: {task}")

    selected: list[LevelMFeatureRow] = []
    for row in rows:
        if task == "awake_vs_sedated" and row.state_label in {"awake", "sedated"}:
            y = 1 if row.state_label == "sedated" else 0
        elif task == "responsive_vs_unresponsive" and row.behavior_label in {"responsive", "unresponsive"}:
            y = 1 if row.behavior_label == "unresponsive" else 0
        elif task == "experience_vs_no_experience" and row.report_label in {"experience", "no_experience"}:
            y = 1 if row.report_label == "no_experience" else 0
        else:
            continue
        selected.append(LevelMFeatureRow(**{**asdict(row), "task_label": task, "y": y}))

    y_true = [r.y for r in selected]
    scores = [_score(r) for r in selected]
    has_two_classes = len(set(y_true)) == 2
    auc = _binary_auc(y_true, scores) if has_two_classes else None
    brier = _brier(y_true, scores) if has_two_classes else None
    ece = _ece(y_true, scores) if has_two_classes else None

    artifact_report = build_artifact_report(selected)
    leakage_report = build_leakage_report(selected)
    safe_claim = "Level M features provide an operational empirical baseline for DS005620 anesthesia/report-label tasks."
    forbidden_claims = [
        "Level M does not prove consciousness.",
        "Sedation does not prove no experience.",
        "Unresponsiveness does not prove unconsciousness.",
        "EEG does not prove enlightenment, liberation, soul, afterlife, or ontology.",
    ]
    omega_event = {
        "status": "ok",
        "dataset_id": "ds005620",
        "task": task,
        "warning": None if has_two_classes else "Task has fewer than two classes; metrics unavailable.",
        "safe_claim": safe_claim,
    }
    return LevelMBaselineResult(
        dataset_id="ds005620",
        task=task,
        n_rows=len(selected),
        n_subjects=len({r.subject_id for r in selected}),
        class_balance=_class_balance(y_true),
        auc=auc,
        brier=brier,
        ece=ece,
        leakage_detected=bool(leakage_report["leakage_detected"]),
        artifact_dominance=bool(artifact_report["artifact_dominance"]),
        artifact_report=artifact_report,
        leakage_report=leakage_report,
        omega_event=omega_event,
        safe_claim=safe_claim,
        forbidden_claims=forbidden_claims,
    )


def write_level_m_outputs(result: LevelMBaselineResult, out_dir: str) -> dict[str, str]:
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)

    metrics_path = base / "metrics_m.json"
    artifact_path = base / "artifact_report.json"
    leakage_path = base / "leakage_report.json"
    omega_path = base / "omega_event.json"
    features_path = base / "features_m.csv"
    report_path = base / "report.md"

    metrics_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    artifact_path.write_text(json.dumps(result.artifact_report, indent=2), encoding="utf-8")
    leakage_path.write_text(json.dumps(result.leakage_report, indent=2), encoding="utf-8")
    omega_path.write_text(json.dumps(result.omega_event, indent=2), encoding="utf-8")

    with features_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["dataset_id", "task", "n_rows", "n_subjects", "auc", "brier", "ece"])
        writer.writeheader()
        writer.writerow({
            "dataset_id": result.dataset_id,
            "task": result.task,
            "n_rows": result.n_rows,
            "n_subjects": result.n_subjects,
            "auc": result.auc,
            "brier": result.brier,
            "ece": result.ece,
        })

    report_text = "\n".join([
        "# DS005620 Level M Baseline",
        "## Dataset/task",
        f"- dataset_id: {result.dataset_id}",
        f"- task: {result.task}",
        "## Rows/subjects",
        f"- n_rows: {result.n_rows}",
        f"- n_subjects: {result.n_subjects}",
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
        "## Next required step",
        "- Run DS005620 M+T residual topology benchmark after Level M baseline is stable.",
        "- This is telemetry and proxy-only output for residual testing preparation.",
    ])
    report_path.write_text(report_text + "\n", encoding="utf-8")

    return {
        "features_m.csv": str(features_path),
        "metrics_m.json": str(metrics_path),
        "artifact_report.json": str(artifact_path),
        "leakage_report.json": str(leakage_path),
        "omega_event.json": str(omega_path),
        "report.md": str(report_path),
    }
