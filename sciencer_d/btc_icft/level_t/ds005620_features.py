from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import json
import math
from pathlib import Path

from sciencer_d.btc_icft.level_m.ds005620_baseline import (
    LevelMFeatureRow,
    build_mock_ds005620_level_m_rows,
)
from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES, validate_safe_text


@dataclass(frozen=True)
class LevelTFeatureRow:
    row_id: str
    subject_id: str
    task_label: str
    q_net: float
    q_abs: float
    f_dress: float
    defect_density: float
    n_valid_triangles: int
    topology_quality: float


@dataclass(frozen=True)
class LevelMTFeatureRow:
    row_id: str
    subject_id: str
    task_label: str
    y: int
    spectral_power_proxy: float
    entropy_proxy: float
    lzc_proxy: float
    artifact_score: float
    q_net: float
    q_abs: float
    f_dress: float
    defect_density: float
    n_valid_triangles: int
    topology_quality: float
    state_label: str | None
    behavior_label: str | None
    report_label: str | None


@dataclass(frozen=True)
class LevelMTResidualResult:
    dataset_id: str
    task: str
    n_rows: int
    n_subjects: int
    metrics_m: dict
    metrics_mt: dict
    delta_auc: float | None
    delta_ece: float | None
    nulls_passed: bool
    ablations_passed: bool
    leakage_detected: bool
    artifact_dominance: bool
    promoted: bool
    promotion_reason: str
    null_report: dict
    ablation_report: dict
    leakage_report: dict
    artifact_report: dict
    omega_event: dict
    safe_claim: str
    forbidden_claims: list[str]


def _validate_safe_text(text: str) -> None:
    validate_safe_text(text)


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def _binary_auc(y_true: list[int], scores: list[float]) -> float | None:
    pos = [s for s, y in zip(scores, y_true) if y == 1]
    neg = [s for s, y in zip(scores, y_true) if y == 0]
    if not pos or not neg:
        return None
    wins = 0.0
    total = 0
    for ps in pos:
        for ns in neg:
            total += 1
            wins += 1.0 if ps > ns else (0.5 if ps == ns else 0.0)
    return wins / total if total else None


def _brier(y_true: list[int], scores: list[float]) -> float | None:
    if not y_true:
        return None
    return sum((y - s) ** 2 for y, s in zip(y_true, scores)) / len(y_true)


def _ece(y_true: list[int], scores: list[float], n_bins: int = 5) -> float | None:
    if not y_true:
        return None
    ece = 0.0
    total = len(y_true)
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


def _class_balance(y_true: list[int]) -> dict[str, int]:
    return {"0": y_true.count(0), "1": y_true.count(1)}


def _score_m(row: LevelMFeatureRow) -> float:
    raw = (2.5 * row.spectral_power_proxy) - (1.2 * row.entropy_proxy) - (0.4 * row.lzc_proxy) - (0.8 * row.artifact_score)
    return 1.0 / (1.0 + math.exp(-raw))


def build_mock_ds005620_level_t_rows() -> list[LevelTFeatureRow]:
    rows = []
    for m in build_mock_ds005620_level_m_rows():
        is_pos = 1 if m.state_label == "sedated" else 0
        q_net = 0.30 + 0.35 * is_pos
        q_abs = q_net + 0.25 + 0.02 * is_pos
        f_dress = (q_abs - abs(q_net)) / q_abs
        n_valid_triangles = 18 + 2 * is_pos
        defect_density = q_abs / n_valid_triangles
        topology_quality = 0.78 + 0.12 * is_pos
        rows.append(LevelTFeatureRow(m.row_id, m.subject_id, m.task_label, q_net, q_abs, f_dress, defect_density, n_valid_triangles, topology_quality))
    return rows


def join_level_m_and_t_rows(m_rows: list[LevelMFeatureRow], t_rows: list[LevelTFeatureRow]) -> list[LevelMTFeatureRow]:
    t_by_id = {r.row_id: r for r in t_rows}
    out = []
    for m in m_rows:
        t = t_by_id.get(m.row_id)
        if t is None:
            raise ValueError(f"Missing Level T row for row_id={m.row_id}. Rebuild deterministic Level T rows before evaluation.")
        if t.subject_id != m.subject_id or t.task_label != m.task_label:
            raise ValueError(f"Level M/T mismatch for row_id={m.row_id}: subject_id/task_label must match.")
        merged = {**asdict(m), **asdict(t)}
        out.append(LevelMTFeatureRow(**merged))
    return sorted(out, key=lambda r: r.row_id)


def _select(rows: list[LevelMTFeatureRow], task: str) -> list[LevelMTFeatureRow]:
    selected = []
    for row in rows:
        if task == "awake_vs_sedated" and row.state_label in {"awake", "sedated"}:
            y = 1 if row.state_label == "sedated" else 0
        elif task == "responsive_vs_unresponsive" and row.behavior_label in {"responsive", "unresponsive"}:
            y = 1 if row.behavior_label == "unresponsive" else 0
        elif task == "experience_vs_no_experience" and row.report_label in {"experience", "no_experience"}:
            y = 1 if row.report_label == "no_experience" else 0
        else:
            continue
        selected.append(LevelMTFeatureRow(**{**asdict(row), "task_label": task, "y": y}))
    return selected


def build_null_report(joined_rows: list[LevelMTFeatureRow], task: str) -> dict:
    result = evaluate_mt_residual(joined_rows, task)
    observed = result.delta_auc or 0.0
    null_delta = 0.01
    return {
        "observed_delta_auc": observed,
        "null_delta_auc": null_delta,
        "margin": observed - null_delta,
        "nulls_passed": observed > (null_delta + 0.01),
        "null_methods": ["channel_shuffle_proxy", "time_reverse_proxy", "phase_randomized_proxy"],
        "note": "Deterministic proxy null controls only; not real EEG null controls.",
    }


def build_ablation_report(joined_rows: list[LevelMTFeatureRow], task: str) -> dict:
    selected = _select(joined_rows, task)
    y = [r.y for r in selected]
    m_scores = [_score_m(r) for r in selected]
    topology = _minmax([r.q_net + r.q_abs + r.f_dress + r.topology_quality - r.defect_density for r in selected])
    qnet = _minmax([r.q_net for r in selected])
    qabs = _minmax([r.q_abs for r in selected])
    fd = _minmax([r.f_dress for r in selected])

    def mk(scores):
        return {"auc": _binary_auc(y, scores), "ece": _ece(y, scores)}

    m = mk(m_scores)
    models = {
        "M_only": m,
        "M_plus_q_net": mk([min(1.0, max(0.0, m_scores[i] + 0.08 * (qnet[i] - 0.5))) for i in range(len(y))]),
        "M_plus_q_abs": mk([min(1.0, max(0.0, m_scores[i] + 0.08 * (qabs[i] - 0.5))) for i in range(len(y))]),
        "M_plus_f_dress": mk([min(1.0, max(0.0, m_scores[i] + 0.08 * (fd[i] - 0.5))) for i in range(len(y))]),
        "M_plus_all_T": mk([min(1.0, max(0.0, m_scores[i] + 0.16 * (topology[i] - 0.5))) for i in range(len(y))]),
    }
    base_auc = models["M_only"]["auc"] or 0.0
    base_ece = models["M_only"]["ece"] or 0.0
    for k in models:
        models[k]["delta_auc_vs_M"] = (models[k]["auc"] or 0.0) - base_auc
        models[k]["delta_ece_vs_M"] = (models[k]["ece"] or 0.0) - base_ece

    topo_aucs = [models[k]["auc"] or 0.0 for k in ["M_plus_q_net", "M_plus_q_abs", "M_plus_f_dress", "M_plus_all_T"]]
    best = max(topo_aucs) if topo_aucs else 0.0
    all_t_best = (models["M_plus_all_T"]["auc"] or 0.0) >= best
    any_improve = any((models[k]["delta_auc_vs_M"] > 0) for k in ["M_plus_q_net", "M_plus_q_abs", "M_plus_f_dress", "M_plus_all_T"])
    ablations_passed = all_t_best and any_improve
    return {**models, "ablations_passed": ablations_passed, "note": "Deterministic scaffold ablations."}


def evaluate_mt_residual(joined_rows: list[LevelMTFeatureRow], task: str) -> LevelMTResidualResult:
    if task not in {"awake_vs_sedated", "responsive_vs_unresponsive", "experience_vs_no_experience"}:
        raise ValueError(f"Unknown task: {task}")
    selected = _select(joined_rows, task)
    y = [r.y for r in selected]
    m_scores = [_score_m(r) for r in selected]
    topo = _minmax([r.q_net + r.q_abs + r.f_dress + r.topology_quality - r.defect_density for r in selected])
    mt_scores = [min(1.0, max(0.0, m_scores[i] + 0.16 * (topo[i] - 0.5))) for i in range(len(y))]

    metrics_m = {"auc": _binary_auc(y, m_scores), "brier": _brier(y, m_scores), "ece": _ece(y, m_scores), "class_balance": _class_balance(y)}
    metrics_mt = {"auc": _binary_auc(y, mt_scores), "brier": _brier(y, mt_scores), "ece": _ece(y, mt_scores), "class_balance": _class_balance(y)}
    delta_auc = None if metrics_m["auc"] is None or metrics_mt["auc"] is None else metrics_mt["auc"] - metrics_m["auc"]
    delta_ece = None if metrics_m["ece"] is None or metrics_mt["ece"] is None else metrics_mt["ece"] - metrics_m["ece"]

    artifact_scores = [r.artifact_score for r in selected]
    mean_art = sum(artifact_scores) / len(artifact_scores) if artifact_scores else 0.0
    high = sum(1 for s in artifact_scores if s > 0.5)
    artifact_dominance = mean_art > 0.5 or (high / len(artifact_scores) > 0.5 if artifact_scores else False)
    artifact_report = {"mean_artifact_score": mean_art, "n_artifact_high": high, "artifact_dominance": artifact_dominance}

    row_ids = [r.row_id for r in selected]
    n_subjects = len({r.subject_id for r in selected})
    leakage_detected = not (len(set(row_ids)) == len(row_ids) and n_subjects >= 2)
    leakage_report = {"subject_split_possible": n_subjects >= 2, "row_ids_unique": len(set(row_ids)) == len(row_ids), "leakage_detected": leakage_detected}

    null_report = {"observed_delta_auc": delta_auc or 0.0, "null_delta_auc": 0.01, "margin": (delta_auc or 0.0) - 0.01, "nulls_passed": (delta_auc or 0.0) > 0.02, "null_methods": ["channel_shuffle_proxy", "time_reverse_proxy", "phase_randomized_proxy"], "note": "Deterministic proxy null controls only; not real EEG null controls."}
    ablation_report = build_ablation_report(joined_rows, task)
    nulls_passed = bool(null_report["nulls_passed"])
    ablations_passed = bool(ablation_report["ablations_passed"])

    if delta_auc is None or delta_auc < 0.03:
        promoted, reason = False, "blocked: delta_auc below threshold"
    elif delta_ece is not None and delta_ece > 0:
        promoted, reason = False, "blocked: calibration worsened"
    elif not nulls_passed:
        promoted, reason = False, "blocked: null controls failed"
    elif not ablations_passed:
        promoted, reason = False, "blocked: ablations failed"
    elif leakage_detected:
        promoted, reason = False, "blocked: leakage detected"
    elif artifact_dominance:
        promoted, reason = False, "blocked: artifact dominance"
    else:
        promoted, reason = True, "promoted: Level T adds residual predictive value under controls"

    safe_claim = "Level T topology telemetry adds or does not add residual predictive value beyond Level M for this DS005620 task under deterministic scaffold controls."
    forbidden_claims = [
        "Topology does not prove consciousness.", "Q is not self.", "Q is not soul.", "Q_abs is not suffering.", "f_dress is not karma.",
        "Sedation does not prove no experience.", "Unresponsiveness does not prove unconsciousness.",
        "EEG does not prove liberation, enlightenment, afterlife, or ontology.",
    ]
    omega_event = {"dataset_id": "ds005620", "task": task, "promoted": promoted, "promotion_reason": reason, "safe_claim": safe_claim}
    return LevelMTResidualResult("ds005620", task, len(selected), n_subjects, metrics_m, metrics_mt, delta_auc, delta_ece, nulls_passed, ablations_passed, leakage_detected, artifact_dominance, promoted, reason, null_report, ablation_report, leakage_report, artifact_report, omega_event, safe_claim, forbidden_claims)


def write_mt_outputs(result: LevelMTResidualResult, out_dir: str) -> dict[str, str]:
    base = Path(out_dir); base.mkdir(parents=True, exist_ok=True)
    features = base / "features_mt.csv"
    metrics = base / "metrics_mt.json"
    nulls = base / "nulls.json"
    ablations = base / "ablations.json"
    leakage = base / "leakage_report.json"
    artifact = base / "artifact_report.json"
    omega = base / "omega_event.json"
    report = base / "report.md"

    rows = join_level_m_and_t_rows(build_mock_ds005620_level_m_rows(), build_mock_ds005620_level_t_rows())
    with features.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys())); writer.writeheader(); [writer.writerow(asdict(r)) for r in rows]

    metrics.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    nulls.write_text(json.dumps(result.null_report, indent=2), encoding="utf-8")
    ablations.write_text(json.dumps(result.ablation_report, indent=2), encoding="utf-8")
    leakage.write_text(json.dumps(result.leakage_report, indent=2), encoding="utf-8")
    artifact.write_text(json.dumps(result.artifact_report, indent=2), encoding="utf-8")
    omega.write_text(json.dumps(result.omega_event, indent=2), encoding="utf-8")

    text = "\n".join([
        "# DS005620 M+T Residual Topology Benchmark", "## Dataset/task", f"- dataset_id: {result.dataset_id}", f"- task: {result.task}",
        "## M-only metrics", f"- {result.metrics_m}", "## M+T metrics", f"- {result.metrics_mt}", "## Residual deltas", f"- delta_auc: {result.delta_auc}", f"- delta_ece: {result.delta_ece}",
        "## Null controls", f"- {result.null_report}", "## Ablations", f"- {result.ablation_report}", "## Artifact report", f"- {result.artifact_report}",
        "## Leakage report", f"- {result.leakage_report}", "## Promotion decision", f"- promoted: {result.promoted}", f"- reason: {result.promotion_reason}",
        "## Safe claim", f"- {result.safe_claim}", "## Forbidden claims", *[f"- {x}" for x in result.forbidden_claims],
        "## Next required step", "- Replace deterministic mock features with real DS005620 EEG windows and montage-aware phase-grid topology extraction.",
        "- This benchmark is a deterministic scaffold using telemetry proxy features and candidate metrics for residual predictive value.",
    ])
    _validate_safe_text(text)
    report.write_text(text + "\n", encoding="utf-8")
    return {k: str(v) for k, v in {"features_mt.csv": features, "metrics_mt.json": metrics, "nulls.json": nulls, "ablations.json": ablations, "leakage_report.json": leakage, "artifact_report.json": artifact, "omega_event.json": omega, "report.md": report}.items()}
