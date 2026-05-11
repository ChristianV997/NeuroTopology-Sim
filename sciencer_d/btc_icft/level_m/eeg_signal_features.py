from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import median
import hashlib

from sciencer_d.btc_icft.io.eeg_signal_blocks import parse_fixture_signal_file


_BANNED_PHRASES = [
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
]


@dataclass
class EEGLevelMSignalFeatureRow:
    dataset_id: str
    row_id: str
    source_file: str
    window_id: str
    window_start_s: float
    window_end_s: float
    sample_start: int
    sample_end: int
    n_channels: int
    n_samples: int
    sample_rate_hz: float
    spectral_power_proxy: float | None
    entropy_proxy: float | None
    lzc_proxy: float | None
    artifact_score: float | None
    feature_status: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class EEGLevelMSignalResult:
    dataset_id: str
    n_windows: int
    n_feature_rows: int
    n_skipped_windows: int
    feature_rows: list[dict]
    skipped_windows: list[dict]
    feature_quality_report: dict
    artifact_report: dict
    omega_event: dict
    safe_claim: str
    forbidden_claims: list[str]
    warnings: list[str]


def _validate_safe_text(text: str) -> None:
    lower = text.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            raise ValueError(f"Banned phrase detected in output text: {phrase!r}")


def load_signal_window_inventory(signal_blocks_dir: str) -> list[dict]:
    p = Path(signal_blocks_dir) / "window_inventory.csv"
    if not p.exists():
        raise FileNotFoundError(
            "Signal block window inventory is required. Run probe_eeg_signal_blocks first or use --mock-fixture."
        )
    with p.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        req = {
            "file_path", "row_id", "window_id", "window_start_s", "window_end_s", "sample_start",
            "sample_end", "n_channels", "n_samples", "sample_rate_hz", "status",
        }
        missing = sorted(req - set(cols))
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")
        rows = [dict(r) for r in reader]
    return rows


def load_study_readiness(study_dir: str | None) -> dict:
    warnings: list[str] = []
    out = {}
    if not study_dir:
        warnings.append("Study readiness metadata was not supplied.")
        return {"warnings": warnings}
    base = Path(study_dir)
    for name in ["study_card.json", "dataset_readiness_report.json", "file_readability_report.json"]:
        p = base / name
        if p.exists():
            out[name] = json.loads(p.read_text(encoding="utf-8"))
    if not out:
        warnings.append("Study readiness metadata was not supplied.")
    return {**out, "warnings": warnings}


def _float(v: str | float | int) -> float:
    return float(v)


def _int(v: str | float | int) -> int:
    return int(float(v))


def _compute_entropy(values: list[float], bins: int = 10) -> float:
    vmin, vmax = min(values), max(values)
    if math.isclose(vmax, vmin):
        return 0.0
    width = (vmax - vmin) / bins
    hist = [0] * bins
    for x in values:
        idx = min(bins - 1, int((x - vmin) / width))
        hist[idx] += 1
    n = len(values)
    ent = 0.0
    for c in hist:
        if c:
            p = c / n
            ent -= p * math.log2(p)
    return ent / math.log2(bins)


def _compute_lzc(values: list[float]) -> float:
    if not values:
        return 0.0
    m = median(values)
    bits = "".join("1" if x >= m else "0" for x in values)
    i = 0
    c = 1
    l = 1
    n = len(bits)
    while True:
        if i + l > n:
            break
        sub = bits[i:i + l]
        if sub in bits[:i]:
            l += 1
            if i + l > n:
                c += 1
                break
        else:
            c += 1
            i += l
            l = 1
        if i >= n:
            break
    return c / n


def extract_features_for_window(dataset_id: str, window: dict) -> EEGLevelMSignalFeatureRow:
    warnings = []
    try:
        sample_start = _int(window["sample_start"])
        sample_end = _int(window["sample_end"])
        if sample_start < 0 or sample_end <= sample_start:
            return EEGLevelMSignalFeatureRow(dataset_id, window["row_id"], window["file_path"], window["window_id"], _float(window["window_start_s"]), _float(window["window_end_s"]), sample_start, sample_end, _int(window["n_channels"]), _int(window["n_samples"]), _float(window["sample_rate_hz"]), None, None, None, None, "skipped_invalid_window", ["invalid sample range"])
        sig = parse_fixture_signal_file(window["file_path"], sample_rate_hz=_float(window["sample_rate_hz"]))
        if not sig.readable:
            return EEGLevelMSignalFeatureRow(dataset_id, window["row_id"], window["file_path"], window["window_id"], _float(window["window_start_s"]), _float(window["window_end_s"]), sample_start, sample_end, _int(window["n_channels"]), _int(window["n_samples"]), _float(window["sample_rate_hz"]), None, None, None, None, "skipped_unreadable_source", sig.errors[:5])
        data = sig.samples[sample_start:sample_end]
        vals = [x for row in data for x in row if isinstance(x, (float, int)) and math.isfinite(x)]
        if not vals:
            return EEGLevelMSignalFeatureRow(dataset_id, window["row_id"], window["file_path"], window["window_id"], _float(window["window_start_s"]), _float(window["window_end_s"]), sample_start, sample_end, _int(window["n_channels"]), _int(window["n_samples"]), _float(window["sample_rate_hz"]), None, None, None, None, "skipped_no_samples", ["no finite samples in window slice"])
        spectral = sum(v * v for v in vals) / len(vals)
        entropy = _compute_entropy(vals)
        lzc = _compute_lzc(vals)
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        std = math.sqrt(var)
        flatline = 1.0 if std < 1e-8 else 0.0
        outlier_ratio = sum(1 for v in vals if abs(v - mean) > 4 * (std + 1e-9)) / len(vals)
        vmax = max(abs(v) for v in vals)
        clip_like = sum(1 for v in vals if abs(abs(v) - vmax) < 1e-12) / len(vals)
        artifact = min(1.0, max(0.0, 0.4 * flatline + 0.3 * outlier_ratio + 0.3 * clip_like))
        status = "short_window" if window.get("status") == "short_window" else "ok"
        return EEGLevelMSignalFeatureRow(dataset_id, window["row_id"], window["file_path"], window["window_id"], _float(window["window_start_s"]), _float(window["window_end_s"]), sample_start, sample_end, _int(window["n_channels"]), _int(window["n_samples"]), _float(window["sample_rate_hz"]), spectral, entropy, lzc, artifact, status, warnings)
    except Exception as e:
        return EEGLevelMSignalFeatureRow(dataset_id, window.get("row_id", "unknown"), window.get("file_path", "unknown"), window.get("window_id", "unknown"), _float(window.get("window_start_s", 0.0)), _float(window.get("window_end_s", 0.0)), _int(window.get("sample_start", 0)), _int(window.get("sample_end", 0)), _int(window.get("n_channels", 0)), _int(window.get("n_samples", 0)), _float(window.get("sample_rate_hz", 0.0)), None, None, None, None, "skipped_parse_error", [str(e)])


def build_signal_artifact_report(rows: list[EEGLevelMSignalFeatureRow]) -> dict:
    scores = [r.artifact_score for r in rows if r.artifact_score is not None]
    if not scores:
        return {"dataset_id": "", "mean_artifact_score": 0.0, "max_artifact_score": 0.0, "high_artifact_windows": 0, "artifact_dominance": False, "flatline_windows": 0, "amplitude_outlier_windows": 0}
    high = sum(1 for s in scores if s > 0.5)
    mean = sum(scores) / len(scores)
    return {
        "dataset_id": rows[0].dataset_id if rows else "",
        "mean_artifact_score": mean,
        "max_artifact_score": max(scores),
        "high_artifact_windows": high,
        "artifact_dominance": mean > 0.5 or high > (len(scores) / 2),
        "flatline_windows": sum(1 for r in rows if (r.artifact_score or 0.0) >= 0.39 and (r.spectral_power_proxy or 1.0) == 0.0),
        "amplitude_outlier_windows": sum(1 for r in rows if (r.artifact_score or 0.0) > 0.25),
    }


def build_feature_quality_report(rows: list[EEGLevelMSignalFeatureRow], skipped_windows: list[dict]) -> dict:
    artifact = build_signal_artifact_report(rows)
    finite = sum(1 for r in rows if all(v is not None and math.isfinite(v) for v in [r.spectral_power_proxy, r.entropy_proxy, r.lzc_proxy, r.artifact_score]))
    return {
        "dataset_id": rows[0].dataset_id if rows else "",
        "n_windows": len(rows) + len(skipped_windows),
        "n_feature_rows": len(rows),
        "n_skipped_windows": len(skipped_windows),
        "mean_artifact_score": artifact["mean_artifact_score"],
        "high_artifact_windows": artifact["high_artifact_windows"],
        "finite_feature_rows": finite,
        "quality_passed": len(rows) > 0 and finite == len(rows) and not artifact["artifact_dominance"],
    }


def extract_signal_window_features(dataset_id: str, windows: list[dict]) -> EEGLevelMSignalResult:
    rows=[]; skipped=[]; warnings=[]
    for w in windows:
        row = extract_features_for_window(dataset_id, w)
        if row.feature_status.startswith("skipped"):
            skipped.append({"row_id": row.row_id, "source_file": row.source_file, "window_id": row.window_id, "reason": row.feature_status, "warnings": row.warnings})
        else:
            rows.append(row)
    art = build_signal_artifact_report(rows)
    qual = build_feature_quality_report(rows, skipped)
    safe = "Readable local EEG-like signal windows were mapped into operational Level M signal feature candidates for future residual testing."
    forbidden = [
        "No consciousness proof.", "No self or soul claim.", "No liberation or enlightenment claim.",
        "No afterlife claim.", "No ontology proof.", "No Level T topology conclusion.", "No residual promotion."
    ]
    _validate_safe_text(safe)
    omega = build_level_m_signal_omega_event(EEGLevelMSignalResult(dataset_id, len(windows), len(rows), len(skipped), [asdict(r) for r in rows], skipped, qual, art, {}, safe, forbidden, warnings))
    return EEGLevelMSignalResult(dataset_id, len(windows), len(rows), len(skipped), [asdict(r) for r in rows], skipped, qual, art, omega, safe, forbidden, warnings)


def build_level_m_signal_omega_event(result: EEGLevelMSignalResult) -> dict:
    payload = f"{result.dataset_id}:{result.n_feature_rows}:{result.n_skipped_windows}:{result.safe_claim}"
    return {"event_id": hashlib.sha256(payload.encode()).hexdigest()[:16], "event_type": "eeg_level_m_signal_features", "dataset_id": result.dataset_id, "n_feature_rows": result.n_feature_rows, "n_skipped_windows": result.n_skipped_windows, "safe_claim": result.safe_claim, "warnings": result.warnings[:20]}


def write_level_m_signal_outputs(result: EEGLevelMSignalResult, out_dir: str) -> dict[str, str]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    outputs={}
    cols=["dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end","n_channels","n_samples","sample_rate_hz","spectral_power_proxy","entropy_proxy","lzc_proxy","artifact_score","feature_status","warnings"]
    fp=out/"features_m_signal.csv"
    with fp.open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in result.feature_rows:
            row=dict(r); row["warnings"]=" | ".join(row.get("warnings", [])); w.writerow(row)
    outputs["features_m_signal.csv"]=str(fp)
    for name, obj in [("feature_quality_report.json", result.feature_quality_report),("artifact_report.json", result.artifact_report),("skipped_windows.json", {"skipped_windows": result.skipped_windows}),("omega_event.json", result.omega_event)]:
        p=out/name; p.write_text(json.dumps(obj, indent=2), encoding="utf-8"); outputs[name]=str(p)
    report = "\n".join([
        "# EEG Level M Signal Feature Extraction", "", "## Stage", "Local signal feature extraction scaffold.", "", "## Dataset", f"- dataset_id: {result.dataset_id}", "", "## Input signal windows", f"- n_windows: {result.n_windows}", "", "## Feature rows", f"- n_feature_rows: {result.n_feature_rows}", "", "## Feature quality", f"- {result.feature_quality_report}", "", "## Artifact report", f"- {result.artifact_report}", "", "## Skipped windows", f"- n_skipped_windows: {result.n_skipped_windows}", "", "## Safe claim", result.safe_claim, "", "## Forbidden claims", *[f"- {x}" for x in result.forbidden_claims], "", "## Next required step", "Use Level M signal features with future Level T signal topology extraction before any signal-level residual benchmark.", "", "This report describes operational Level M signal feature candidates for future residual testing and signal feature telemetry."])
    _validate_safe_text(report)
    rp=out/"report.md"; rp.write_text(report+"\n", encoding="utf-8"); outputs["report.md"]=str(rp)
    return outputs
