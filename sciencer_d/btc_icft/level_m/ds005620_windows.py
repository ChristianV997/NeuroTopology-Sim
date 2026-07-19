from __future__ import annotations

from dataclasses import asdict, dataclass, field
import csv
import json
import math
from pathlib import Path

from sciencer_d.btc_icft.level_m.features import extract_level_m_features

BANNED_REPORT_PHRASES = (
    "proves consciousness",
    "soul proven",
    "afterlife proven",
    "liberation detected",
    "ontology solved",
    "ultimate reality",
    "q equals self",
    "q equals soul",
    "q_abs equals suffering",
    "f_dress equals karma",
)


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
    low = text.lower()
    for phrase in BANNED_REPORT_PHRASES:
        if phrase in low:
            raise ValueError(f"banned phrase detected: {phrase}")


def load_bids_inspection_outputs(inspection_dir: str) -> dict:
    base = Path(inspection_dir)
    required = ["file_inventory.json", "label_candidates.json", "contract_report.json", "report.md"]
    missing = [name for name in required if not (base / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing required BIDS inspection outputs in {inspection_dir}: {missing}. "
            "Run inspect_ds005620_bids first to generate file_inventory.json, label_candidates.json, contract_report.json, and report.md."
        )
    return {
        "file_inventory": json.loads((base / "file_inventory.json").read_text(encoding="utf-8")),
        "label_candidates": json.loads((base / "label_candidates.json").read_text(encoding="utf-8")),
        "contract_report": json.loads((base / "contract_report.json").read_text(encoding="utf-8")),
        "report_md": (base / "report.md").read_text(encoding="utf-8"),
        "inspection_dir": str(base),
    }


def _pick_label(match: dict | None, key: str, warnings: list[str]) -> str | None:
    if not match:
        warnings.append("missing label candidate row; labels left unknown")
        return None
    value = match.get(key)
    if value is None:
        warnings.append(f"missing {key} in label candidate")
    return value


def build_level_m_windows_from_bids_inventory(inspection: dict, window_seconds: float = 10.0, max_windows_per_file: int = 2) -> list[LevelMWindowRow]:
    inventory = inspection.get("file_inventory", {})
    labels = inspection.get("label_candidates", [])
    by_source = {x.get("source") or x.get("relative_path"): x for x in labels if isinstance(x, dict)}
    rows: list[LevelMWindowRow] = []
    eeg_candidates = inventory.get("eeg_candidates", [])

    for rec in eeg_candidates:
        if not rec.get("is_eeg_candidate", True):
            continue
        source_file = rec.get("path") or rec.get("relative_path") or "unknown"
        rel = rec.get("relative_path")
        subject = rec.get("subject_id") or "unknown_subject"
        session = rec.get("session_id")
        run = rec.get("run_id")
        task = rec.get("task_label")
        match = by_source.get(rel)

        for idx in range(max_windows_per_file):
            warns: list[str] = []
            state = _pick_label(match, "state_label", warns)
            behavior = _pick_label(match, "behavior_label", warns)
            report = _pick_label(match, "report_label", warns)
            task_label = _pick_label(match, "task_label", warns) or task

            row_id = f"{subject}_{session or 'noses'}_{run or 'norun'}_{task_label or 'unknown'}_win-{idx}"
            rows.append(LevelMWindowRow(
                row_id=row_id,
                subject_id=subject,
                session_id=session,
                run_id=run,
                window_id=f"win-{idx}",
                task_label=task_label,
                state_label=state,
                behavior_label=behavior,
                report_label=report,
                y=None,
                spectral_power_proxy=None,
                entropy_proxy=None,
                lzc_proxy=None,
                artifact_score=None,
                source_file=source_file,
                window_start_s=idx * window_seconds,
                window_end_s=(idx + 1) * window_seconds,
                warnings=warns,
            ))
    return rows


def build_mock_level_m_windows_from_inspection() -> list[LevelMWindowRow]:
    return [
        LevelMWindowRow("sub-01_ses-01_run-01_awake_win-0", "sub-01", "ses-01", "01", "win-0", "awake", "awake", "responsive", "experience", None, None, None, None, None, "mock/sub-01_task-awake_run-01_eeg.edf", 0.0, 10.0, []),
        LevelMWindowRow("sub-01_ses-01_run-01_sedated_win-1", "sub-01", "ses-01", "01", "win-1", "sedated", "sedated", "unresponsive", "experience", None, None, None, None, None, "mock/sub-01_task-sedated_run-01_eeg.edf", 10.0, 20.0, []),
        LevelMWindowRow("sub-02_ses-01_run-01_awake_win-0", "sub-02", "ses-01", "01", "win-0", "awake", "awake", "responsive", "no_experience", None, None, None, None, None, "mock/sub-02_task-awake_run-01_eeg.edf", 0.0, 10.0, []),
        LevelMWindowRow("sub-02_ses-01_run-01_sedated_win-1", "sub-02", "ses-01", "01", "win-1", "sedated", "sedated", "unresponsive", "no_experience", None, None, None, None, None, "mock/sub-02_task-sedated_run-01_eeg.edf", 10.0, 20.0, []),
    ]


def _signal_from_seed(seed: str) -> list[float]:
    base = max(1, sum(ord(ch) for ch in seed) % 91)
    return [((base + i * 7) % 97) / 100.0 for i in range(64)]


def extract_level_m_window_features(windows: list[LevelMWindowRow]) -> list[LevelMWindowRow]:
    out: list[LevelMWindowRow] = []
    for row in windows:
        signal = _signal_from_seed(f"{row.source_file}:{row.row_id}")
        feats = extract_level_m_features(signal)
        warns = list(row.warnings)
        warns.append("fixture-derived Level M features; not real EEG signal extraction")
        out.append(LevelMWindowRow(**{**asdict(row), **feats, "warnings": warns}))
    return out


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


def evaluate_level_m_windows(rows: list[LevelMWindowRow], task: str) -> LevelMRealWindowResult:
    warnings: list[str] = []
    selected: list[LevelMWindowRow] = []
    for row in rows:
        y = None
        if task == "awake_vs_sedated":
            if row.state_label == "awake": y = 0
            elif row.state_label == "sedated": y = 1
        elif task == "responsive_vs_unresponsive":
            if row.behavior_label == "responsive": y = 0
            elif row.behavior_label == "unresponsive": y = 1
        elif task == "experience_vs_no_experience":
            if row.report_label == "experience": y = 0
            elif row.report_label == "no_experience": y = 1
        else:
            raise ValueError(f"Unknown task: {task}")
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
    safe_claim = "Local DS005620-style files were mapped into operational Level M window-feature candidates for future residual testing."
    forbidden_claims = [
        "No consciousness proof.", "No self or soul claim.", "No liberation or enlightenment claim.", "No afterlife claim.", "No ontology proof.", "No unsafe label inference.",
    ]
    omega_event = {"dataset_id": "ds005620", "task": task, "status": "operational_level_m", "safe_claim": safe_claim}
    return LevelMRealWindowResult(
        dataset_id="ds005620", task=task, n_rows=len(selected), n_subjects=len({r.subject_id for r in selected}), n_windows=len(selected),
        class_balance=_class_balance(y_true), auc=auc, brier=brier, ece=ece, leakage_detected=bool(leakage_report["leakage_detected"]),
        artifact_dominance=bool(artifact_report["artifact_dominance"]), artifact_report=artifact_report, leakage_report=leakage_report,
        omega_event=omega_event, safe_claim=safe_claim, forbidden_claims=forbidden_claims, warnings=warnings,
        rows=[asdict(r) for r in selected],
    )


def write_level_m_window_outputs(result: LevelMRealWindowResult, out_dir: str) -> dict[str, str]:
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    features_path = base / "features_m.csv"
    metrics_path = base / "metrics_m.json"
    artifact_path = base / "artifact_report.json"
    leakage_path = base / "leakage_report.json"
    omega_path = base / "omega_event.json"
    report_path = base / "report.md"

    # Per-window rows (not just the aggregate summary): this is the contract
    # `ds005620_real_topology.load_level_m_window_features` requires (REQUIRED_M_COLUMNS)
    # to compute Level T topology aligned to each Level M window. Previously this file
    # held only one aggregate row, which silently broke the P9->P10 handoff.
    row_fieldnames = list(LevelMWindowRow.__dataclass_fields__.keys())
    with features_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row_fieldnames)
        writer.writeheader()
        for row in result.rows:
            out_row = dict(row)
            out_row["warnings"] = "; ".join(row.get("warnings") or [])
            writer.writerow(out_row)

    # rows are already in features_m.csv; keep metrics_m.json aggregate-only
    metrics_dict = {k: v for k, v in asdict(result).items() if k != "rows"}
    metrics_path.write_text(json.dumps(metrics_dict, indent=2), encoding="utf-8")
    artifact_path.write_text(json.dumps(result.artifact_report, indent=2), encoding="utf-8")
    leakage_path.write_text(json.dumps(result.leakage_report, indent=2), encoding="utf-8")
    omega_path.write_text(json.dumps(result.omega_event, indent=2), encoding="utf-8")

    report_text = "\n".join([
        "# DS005620 Real/Local Level M Window Extraction",
        "## Dataset/task",
        f"- dataset_id: {result.dataset_id}",
        f"- task: {result.task}",
        "## Input inspection",
        "- Source: local BIDS inspection outputs or mock fixture mode.",
        "## Window rows",
        f"- n_rows: {result.n_rows}",
        f"- n_windows: {result.n_windows}",
        "- operational Level M telemetry only.",
        "- window-feature candidates prepared.",
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
        "- This is for future residual testing.",
    ])
    _validate_safe_text(report_text)
    report_path.write_text(report_text + "\n", encoding="utf-8")

    return {"features_m.csv": str(features_path), "metrics_m.json": str(metrics_path), "artifact_report.json": str(artifact_path), "leakage_report.json": str(leakage_path), "omega_event.json": str(omega_path), "report.md": str(report_path)}
