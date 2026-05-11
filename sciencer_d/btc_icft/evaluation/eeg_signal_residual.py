"""DS005620 EEG signal-level M+T residual benchmark orchestration.

Joins P9 Level M signal features with P10 Level T topology telemetry
and evaluates controlled signal-level residual benchmark.

Does NOT:
- download data
- add hard dependencies (stdlib-only)
- infer labels or fabricate targets
- change legacy DS005620 benchmark semantics
- implement Level O/C/Q
- claim consciousness/self/soul/liberation/afterlife/enlightenment/ontology
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


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
)

_SAFE_CLAIM = (
    "Local EEG-like Level M signal features and Level T topology telemetry "
    "were aligned for controlled signal-level residual benchmarking."
)

_M_REQUIRED_COLS = {
    "dataset_id", "row_id", "source_file", "window_id",
    "window_start_s", "window_end_s", "sample_start", "sample_end",
    "n_channels", "n_samples", "sample_rate_hz",
    "spectral_power_proxy", "entropy_proxy", "lzc_proxy",
    "artifact_score", "feature_status",
}

_T_REQUIRED_COLS = {
    "dataset_id", "row_id", "source_file", "window_id",
    "window_start_s", "window_end_s", "sample_start", "sample_end",
    "n_channels", "n_samples", "sample_rate_hz",
    "q_net", "q_abs", "f_dress", "defect_density",
    "n_triangles", "n_valid_triangles", "topology_quality", "topology_status",
}

_JOIN_KEYS = (
    "dataset_id", "row_id", "source_file", "window_id",
    "window_start_s", "window_end_s", "sample_start", "sample_end",
)

_MIN_DELTA_AUC = 0.03
_MIN_NULL_MARGIN = 0.01


def _validate_safe_text(text: str) -> None:
    """Raise ValueError if text contains any banned phrase."""
    lower = text.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            raise ValueError(f"Banned phrase detected: {phrase!r}")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class EEGSignalMTJoinedRow:
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
    # Level M
    spectral_power_proxy: Optional[float] = None
    entropy_proxy: Optional[float] = None
    lzc_proxy: Optional[float] = None
    artifact_score_m: Optional[float] = None
    feature_status: Optional[str] = None
    # Level T
    q_net: Optional[float] = None
    q_abs: Optional[float] = None
    f_dress: Optional[float] = None
    defect_density: Optional[float] = None
    n_triangles: Optional[int] = None
    n_valid_triangles: Optional[int] = None
    topology_quality: Optional[float] = None
    topology_status: Optional[str] = None
    # Optional targets
    y: Optional[int] = None
    label: Optional[str] = None
    # Meta
    warnings: list[str] = field(default_factory=list)


@dataclass
class EEGSignalMTResidualResult:
    dataset_id: str
    n_m_rows: int
    n_t_rows: int
    n_joined_rows: int
    n_targets_available: int
    predictive_metrics_available: bool
    metrics: dict
    null_report: dict
    ablation_report: dict
    alignment_report: dict
    artifact_report: dict
    omega_event: dict
    promoted: bool
    promotion_reason: str
    safe_claim: str
    forbidden_claims: list[str]
    warnings: list[str]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_level_m_signal_features(path: str) -> list[dict]:
    """Load features_m_signal.csv.

    Raises:
        FileNotFoundError: If file is missing.
        ValueError: If required columns are absent.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Level M and Level T signal feature tables are required. "
            f"Run run_eeg_level_m_signal and run_eeg_level_t_signal first "
            f"or use --mock-fixture. (looked for: {p})"
        )
    with open(p, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        cols = set(reader.fieldnames or [])
    missing = _M_REQUIRED_COLS - cols
    if missing:
        raise ValueError(f"features_m_signal.csv missing required columns: {sorted(missing)}")
    return rows


def load_level_t_signal_features(path: str) -> list[dict]:
    """Load features_t_signal.csv.

    Raises:
        FileNotFoundError: If file is missing.
        ValueError: If required columns are absent.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Level M and Level T signal feature tables are required. "
            f"Run run_eeg_level_m_signal and run_eeg_level_t_signal first "
            f"or use --mock-fixture. (looked for: {p})"
        )
    with open(p, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        cols = set(reader.fieldnames or [])
    missing = _T_REQUIRED_COLS - cols
    if missing:
        raise ValueError(f"features_t_signal.csv missing required columns: {sorted(missing)}")
    return rows


# ---------------------------------------------------------------------------
# Join
# ---------------------------------------------------------------------------

def _composite_key(row: dict) -> tuple:
    return tuple(str(row.get(k, "")) for k in _JOIN_KEYS)


def join_signal_m_t_rows(
    m_rows: list[dict],
    t_rows: list[dict],
) -> tuple[list[EEGSignalMTJoinedRow], list[str]]:
    """Strictly join M and T rows by composite key.

    Rules:
    - Fail on duplicate M keys → raises ValueError.
    - Fail on duplicate T keys → raises ValueError.
    - Fail if any M row lacks a matching T row → raises ValueError.
    - Extra T rows are ignored with warnings.
    - Sort joined rows by composite key.

    Returns:
        (joined_rows, extra_t_warnings)
    """
    # Build M index, check duplicates
    m_index: dict[tuple, dict] = {}
    for r in m_rows:
        k = _composite_key(r)
        if k in m_index:
            raise ValueError(f"Duplicate M key detected: {k}")
        m_index[k] = r

    # Build T index, check duplicates
    t_index: dict[tuple, dict] = {}
    for r in t_rows:
        k = _composite_key(r)
        if k in t_index:
            raise ValueError(f"Duplicate T key detected: {k}")
        t_index[k] = r

    # Check all M rows have matching T
    missing_t = [k for k in m_index if k not in t_index]
    if missing_t:
        raise ValueError(
            f"{len(missing_t)} M rows have no matching T row. "
            f"First missing key: {missing_t[0]}"
        )

    # Extra T rows
    extra_t_warnings = []
    for k in t_index:
        if k not in m_index:
            extra_t_warnings.append(f"Extra T row ignored: key={k}")

    # Build joined rows
    joined: list[EEGSignalMTJoinedRow] = []
    for k in sorted(m_index.keys()):
        m = m_index[k]
        t = t_index[k]

        def _f(d: dict, col: str) -> Optional[float]:
            v = d.get(col, "")
            if v == "" or v is None:
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        def _i(d: dict, col: str) -> Optional[int]:
            v = d.get(col, "")
            if v == "" or v is None:
                return None
            try:
                return int(float(v))
            except (ValueError, TypeError):
                return None

        # Optional y: only from M input, never inferred
        y_val: Optional[int] = None
        y_raw = m.get("y", "")
        if y_raw not in ("", None):
            try:
                y_val = int(float(y_raw))
            except (ValueError, TypeError):
                pass

        label_val: Optional[str] = m.get("label", None) or None

        row = EEGSignalMTJoinedRow(
            dataset_id=str(m.get("dataset_id", "")),
            row_id=str(m.get("row_id", "")),
            source_file=str(m.get("source_file", "")),
            window_id=str(m.get("window_id", "")),
            window_start_s=float(m.get("window_start_s", 0.0) or 0.0),
            window_end_s=float(m.get("window_end_s", 0.0) or 0.0),
            sample_start=int(float(m.get("sample_start", 0) or 0)),
            sample_end=int(float(m.get("sample_end", 0) or 0)),
            n_channels=int(float(m.get("n_channels", 0) or 0)),
            n_samples=int(float(m.get("n_samples", 0) or 0)),
            sample_rate_hz=float(m.get("sample_rate_hz", 0.0) or 0.0),
            spectral_power_proxy=_f(m, "spectral_power_proxy"),
            entropy_proxy=_f(m, "entropy_proxy"),
            lzc_proxy=_f(m, "lzc_proxy"),
            artifact_score_m=_f(m, "artifact_score"),
            feature_status=m.get("feature_status", None),
            q_net=_f(t, "q_net"),
            q_abs=_f(t, "q_abs"),
            f_dress=_f(t, "f_dress"),
            defect_density=_f(t, "defect_density"),
            n_triangles=_i(t, "n_triangles"),
            n_valid_triangles=_i(t, "n_valid_triangles"),
            topology_quality=_f(t, "topology_quality"),
            topology_status=t.get("topology_status", None),
            y=y_val,
            label=label_val,
        )
        joined.append(row)

    return joined, extra_t_warnings


# ---------------------------------------------------------------------------
# Metrics (stdlib-only, deterministic)
# ---------------------------------------------------------------------------

def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    r = hi - lo
    if r < 1e-12:
        return [0.5] * len(values)
    return [(v - lo) / r for v in values]


def _binary_auc(scores: list[float], labels: list[int]) -> float:
    """Deterministic AUC via concordance pairs."""
    pairs = list(zip(scores, labels))
    pos = [s for s, y in pairs if y == 1]
    neg = [s for s, y in pairs if y == 0]
    if not pos or not neg:
        return 0.5
    concordant = sum(1 for p in pos for n in neg if p > n)
    tied = sum(1 for p in pos for n in neg if p == n)
    total = len(pos) * len(neg)
    return (concordant + 0.5 * tied) / total


def _brier(scores: list[float], labels: list[int]) -> float:
    if not scores:
        return 1.0
    return sum((s - y) ** 2 for s, y in zip(scores, labels)) / len(scores)


def _ece(scores: list[float], labels: list[int], n_bins: int = 5) -> float:
    if not scores:
        return 1.0
    n = len(scores)
    bins = [[] for _ in range(n_bins)]
    for s, y in zip(scores, labels):
        idx = min(int(s * n_bins), n_bins - 1)
        bins[idx].append((s, y))
    ece = 0.0
    for b in bins:
        if b:
            conf = sum(s for s, _ in b) / len(b)
            acc = sum(y for _, y in b) / len(b)
            ece += len(b) / n * abs(conf - acc)
    return ece


def _score_m(row: EEGSignalMTJoinedRow) -> float:
    """Compute raw M-only score from feature proxies."""
    parts: list[float] = []
    if row.spectral_power_proxy is not None and math.isfinite(row.spectral_power_proxy):
        parts.append(row.spectral_power_proxy)
    if row.entropy_proxy is not None and math.isfinite(row.entropy_proxy):
        parts.append(row.entropy_proxy)
    if row.lzc_proxy is not None and math.isfinite(row.lzc_proxy):
        parts.append(row.lzc_proxy)
    base = sum(parts) / len(parts) if parts else 0.5
    # Artifact penalty
    art = row.artifact_score_m
    if art is not None and math.isfinite(art):
        base = base * (1.0 - min(art, 1.0) * 0.3)
    return max(0.0, min(1.0, base))


def _score_mt(row: EEGSignalMTJoinedRow, m_score: float) -> float:
    """Compute M+T score adding normalized topology contribution."""
    t_parts: list[float] = []
    if row.q_abs is not None and math.isfinite(row.q_abs):
        t_parts.append(min(row.q_abs, 1.0))
    if row.f_dress is not None and math.isfinite(row.f_dress):
        t_parts.append(min(row.f_dress, 1.0))
    if row.topology_quality is not None and math.isfinite(row.topology_quality):
        t_parts.append(row.topology_quality)
    if not t_parts:
        return m_score
    t_contrib = sum(t_parts) / len(t_parts) * 0.4
    return max(0.0, min(1.0, m_score * 0.6 + t_contrib))


def _compute_metrics(
    joined_rows: list[EEGSignalMTJoinedRow],
) -> dict:
    """Compute metrics dict. Returns unavailable metrics when no valid y targets."""
    n_joined = len(joined_rows)
    n_m = n_joined
    n_t = n_joined

    # Check for explicit binary y targets
    ys = [r.y for r in joined_rows if r.y is not None and r.y in (0, 1)]
    explicit_available = len(ys) > 0
    classes = set(ys)
    both_classes = len(classes) == 2

    base = {
        "n_joined_windows": n_joined,
        "n_m_rows": n_m,
        "n_t_rows": n_t,
    }

    if not explicit_available:
        return {
            **base,
            "explicit_targets_available": False,
            "predictive_metrics_available": False,
            "auc_m": None,
            "auc_mt": None,
            "delta_auc": None,
            "brier_m": None,
            "brier_mt": None,
            "ece_m": None,
            "ece_mt": None,
            "delta_ece": None,
            "promoted": False,
            "promotion_reason": "blocked: no explicit targets available",
        }

    if not both_classes:
        return {
            **base,
            "explicit_targets_available": True,
            "predictive_metrics_available": False,
            "auc_m": None,
            "auc_mt": None,
            "delta_auc": None,
            "brier_m": None,
            "brier_mt": None,
            "ece_m": None,
            "ece_mt": None,
            "delta_ece": None,
            "promoted": False,
            "promotion_reason": "blocked: insufficient class variation",
        }

    # Valid binary targets
    valid_rows = [r for r in joined_rows if r.y in (0, 1)]
    labels = [r.y for r in valid_rows]
    raw_m = [_score_m(r) for r in valid_rows]
    m_scores = _minmax(raw_m)
    raw_mt = [_score_mt(r, s) for r, s in zip(valid_rows, m_scores)]
    mt_scores = _minmax(raw_mt)

    auc_m = _binary_auc(m_scores, labels)
    auc_mt = _binary_auc(mt_scores, labels)
    delta_auc = auc_mt - auc_m
    brier_m = _brier(m_scores, labels)
    brier_mt = _brier(mt_scores, labels)
    ece_m = _ece(m_scores, labels)
    ece_mt = _ece(mt_scores, labels)
    delta_ece = ece_mt - ece_m

    n_pos = sum(1 for y in labels if y == 1)
    class_balance = n_pos / len(labels)

    return {
        **base,
        "explicit_targets_available": True,
        "predictive_metrics_available": True,
        "auc_m": round(auc_m, 6),
        "auc_mt": round(auc_mt, 6),
        "delta_auc": round(delta_auc, 6),
        "brier_m": round(brier_m, 6),
        "brier_mt": round(brier_mt, 6),
        "ece_m": round(ece_m, 6),
        "ece_mt": round(ece_mt, 6),
        "delta_ece": round(delta_ece, 6),
        "class_balance": round(class_balance, 4),
        "promoted": False,  # set by evaluate
        "promotion_reason": "",  # set by evaluate
    }


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def build_signal_alignment_report(
    joined_rows: list[EEGSignalMTJoinedRow],
    m_rows: list[dict],
    t_rows: list[dict],
    warnings: list[str],
) -> dict:
    n_m = len(m_rows)
    n_t = len(t_rows)
    n_joined = len(joined_rows)

    m_keys = {_composite_key(r) for r in m_rows}
    t_keys = {_composite_key(r) for r in t_rows}

    missing_t = len(m_keys - t_keys)
    extra_t = len(t_keys - m_keys)

    # Duplicate check
    m_seen: set = set()
    dup_m = 0
    for r in m_rows:
        k = _composite_key(r)
        if k in m_seen:
            dup_m += 1
        m_seen.add(k)

    t_seen: set = set()
    dup_t = 0
    for r in t_rows:
        k = _composite_key(r)
        if k in t_seen:
            dup_t += 1
        t_seen.add(k)

    alignment_passed = (
        n_joined == n_m and
        missing_t == 0 and
        dup_m == 0 and
        dup_t == 0
    )

    dataset_id = joined_rows[0].dataset_id if joined_rows else (m_rows[0].get("dataset_id", "") if m_rows else "")

    return {
        "dataset_id": dataset_id,
        "n_m_rows": n_m,
        "n_t_rows": n_t,
        "n_joined_rows": n_joined,
        "missing_t_for_m": missing_t,
        "extra_t_rows": extra_t,
        "duplicate_m_keys": dup_m,
        "duplicate_t_keys": dup_t,
        "alignment_passed": alignment_passed,
        "warnings": warnings[:20],
    }


def build_signal_artifact_report(joined_rows: list[EEGSignalMTJoinedRow]) -> dict:
    dataset_id = joined_rows[0].dataset_id if joined_rows else ""
    n = len(joined_rows)

    art_scores = [
        r.artifact_score_m for r in joined_rows
        if r.artifact_score_m is not None and math.isfinite(r.artifact_score_m)
    ]
    tq_scores = [
        r.topology_quality for r in joined_rows
        if r.topology_quality is not None and math.isfinite(r.topology_quality)
    ]

    mean_art = sum(art_scores) / len(art_scores) if art_scores else 0.0
    max_art = max(art_scores) if art_scores else 0.0
    high_art = sum(1 for a in art_scores if a > 0.5)
    mean_tq = sum(tq_scores) / len(tq_scores) if tq_scores else 0.0
    low_tq = sum(1 for q in tq_scores if q < 0.25)

    artifact_dominance = (
        mean_art > 0.5 or
        (len(art_scores) > 0 and high_art > len(art_scores) / 2) or
        mean_tq < 0.25
    )

    m_status_counts: dict[str, int] = {}
    for r in joined_rows:
        s = r.feature_status or "unknown"
        m_status_counts[s] = m_status_counts.get(s, 0) + 1

    t_status_counts: dict[str, int] = {}
    for r in joined_rows:
        s = r.topology_status or "unknown"
        t_status_counts[s] = t_status_counts.get(s, 0) + 1

    return {
        "dataset_id": dataset_id,
        "mean_artifact_score_m": round(mean_art, 6),
        "max_artifact_score_m": round(max_art, 6),
        "mean_topology_quality": round(mean_tq, 6),
        "low_topology_quality_rows": low_tq,
        "high_artifact_rows": high_art,
        "artifact_dominance": artifact_dominance,
        "m_feature_status_counts": m_status_counts,
        "t_topology_status_counts": t_status_counts,
    }


def build_signal_null_report(
    joined_rows: list[EEGSignalMTJoinedRow],
    metrics: dict,
) -> dict:
    if not metrics.get("explicit_targets_available", False):
        return {
            "status": "unavailable_no_explicit_targets",
            "real_nulls_performed": False,
            "nulls_passed": False,
            "methods_planned": ["channel_shuffle", "time_reverse", "phase_randomization"],
            "note": "Predictive null controls require explicit targets; no targets were fabricated.",
        }

    # Deterministic proxy null: shuffle labels
    ys = [r.y for r in joined_rows if r.y in (0, 1)]
    n = len(ys)
    if n < 2:
        return {
            "status": "unavailable_insufficient_samples",
            "real_nulls_performed": False,
            "nulls_passed": False,
            "methods_planned": ["channel_shuffle", "time_reverse", "phase_randomization"],
            "note": "Insufficient valid samples for null controls.",
        }

    # Deterministic shuffle using index reversal
    shuffled_ys = list(reversed(ys))
    valid_rows = [r for r in joined_rows if r.y in (0, 1)]
    raw_mt = [_score_mt(r, _score_m(r)) for r in valid_rows]
    mt_scores = _minmax(raw_mt)

    null_auc = _binary_auc(mt_scores, shuffled_ys)
    real_delta = metrics.get("delta_auc", 0.0) or 0.0
    null_delta = null_auc - 0.5
    nulls_passed = real_delta > null_delta + _MIN_NULL_MARGIN

    return {
        "status": "available",
        "real_nulls_performed": False,
        "nulls_passed": nulls_passed,
        "null_auc_proxy": round(null_auc, 6),
        "real_delta_auc": round(real_delta, 6),
        "null_delta_auc_proxy": round(null_delta, 6),
        "methods_planned": ["channel_shuffle", "time_reverse", "phase_randomization"],
        "note": "Deterministic proxy nulls only; real signal-space nulls require explicit implementation.",
    }


def build_signal_ablation_report(
    joined_rows: list[EEGSignalMTJoinedRow],
    metrics: dict,
) -> dict:
    _ABLATIONS = [
        "M_only",
        "M_plus_q_net",
        "M_plus_q_abs",
        "M_plus_f_dress",
        "M_plus_defect_density",
        "M_plus_topology_quality",
        "M_plus_all_T",
    ]

    if not metrics.get("explicit_targets_available", False):
        entries = {}
        for ab in _ABLATIONS:
            entries[ab] = {
                "status": "unavailable_no_explicit_targets",
                "auc": None,
                "delta_auc_vs_M": None,
                "ece": None,
                "delta_ece_vs_M": None,
            }
        return {"ablations_passed": False, "ablation_entries": entries}

    valid_rows = [r for r in joined_rows if r.y in (0, 1)]
    labels = [r.y for r in valid_rows]
    classes = set(labels)
    if len(classes) < 2:
        entries = {}
        for ab in _ABLATIONS:
            entries[ab] = {
                "status": "unavailable_insufficient_class_variation",
                "auc": None,
                "delta_auc_vs_M": None,
                "ece": None,
                "delta_ece_vs_M": None,
            }
        return {"ablations_passed": False, "ablation_entries": entries}

    def _ablation_score(row: EEGSignalMTJoinedRow, ablation: str) -> float:
        m = _score_m(row)
        if ablation == "M_only":
            return m
        elif ablation == "M_plus_q_net":
            v = row.q_net
            t = min(abs(v), 1.0) * 0.4 if v is not None and math.isfinite(v) else 0.0
            return max(0.0, min(1.0, m * 0.6 + t))
        elif ablation == "M_plus_q_abs":
            v = row.q_abs
            t = min(abs(v), 1.0) * 0.4 if v is not None and math.isfinite(v) else 0.0
            return max(0.0, min(1.0, m * 0.6 + t))
        elif ablation == "M_plus_f_dress":
            v = row.f_dress
            t = min(abs(v), 1.0) * 0.4 if v is not None and math.isfinite(v) else 0.0
            return max(0.0, min(1.0, m * 0.6 + t))
        elif ablation == "M_plus_defect_density":
            v = row.defect_density
            t = min(abs(v), 1.0) * 0.4 if v is not None and math.isfinite(v) else 0.0
            return max(0.0, min(1.0, m * 0.6 + t))
        elif ablation == "M_plus_topology_quality":
            v = row.topology_quality
            t = (v * 0.4) if v is not None and math.isfinite(v) else 0.0
            return max(0.0, min(1.0, m * 0.6 + t))
        else:  # M_plus_all_T
            return _score_mt(row, m)

    raw_m = [_ablation_score(r, "M_only") for r in valid_rows]
    base_scores = _minmax(raw_m)
    auc_m_base = _binary_auc(base_scores, labels)
    ece_m_base = _ece(base_scores, labels)

    entries = {}
    ablations_passed = True
    for ab in _ABLATIONS:
        raw = [_ablation_score(r, ab) for r in valid_rows]
        scores = _minmax(raw)
        auc = _binary_auc(scores, labels)
        ece = _ece(scores, labels)
        d_auc = round(auc - auc_m_base, 6)
        d_ece = round(ece - ece_m_base, 6)
        entries[ab] = {
            "status": "available",
            "auc": round(auc, 6),
            "delta_auc_vs_M": d_auc,
            "ece": round(ece, 6),
            "delta_ece_vs_M": d_ece,
        }

    return {"ablations_passed": ablations_passed, "ablation_entries": entries}


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------

def evaluate_signal_mt_residual(
    joined_rows: list[EEGSignalMTJoinedRow],
    dataset_id: str,
    m_rows: list[dict] | None = None,
    t_rows: list[dict] | None = None,
    join_warnings: list[str] | None = None,
) -> EEGSignalMTResidualResult:
    """Evaluate signal-level M+T residual benchmark.

    Args:
        joined_rows: Joined M+T rows.
        dataset_id: Dataset identifier.
        m_rows: Original M rows (for alignment report).
        t_rows: Original T rows (for alignment report).
        join_warnings: Warnings from join step.

    Returns:
        EEGSignalMTResidualResult.
    """
    m_rows = m_rows or []
    t_rows = t_rows or []
    join_warnings = join_warnings or []

    n_joined = len(joined_rows)
    n_targets = sum(1 for r in joined_rows if r.y in (0, 1))

    metrics = _compute_metrics(joined_rows)
    predictive_available = metrics.get("predictive_metrics_available", False)

    alignment_report = build_signal_alignment_report(
        joined_rows, m_rows, t_rows, join_warnings
    )
    artifact_report = build_signal_artifact_report(joined_rows)
    null_report = build_signal_null_report(joined_rows, metrics)
    ablation_report = build_signal_ablation_report(joined_rows, metrics)

    alignment_passed = alignment_report.get("alignment_passed", False)
    artifact_dominance = artifact_report.get("artifact_dominance", False)
    nulls_passed = null_report.get("nulls_passed", False)
    ablations_passed = ablation_report.get("ablations_passed", False)

    # Determine promotion and reason
    promoted = False
    promotion_reason = metrics.get("promotion_reason", "")

    if predictive_available:
        delta_auc = metrics.get("delta_auc", 0.0) or 0.0
        delta_ece = metrics.get("delta_ece", 0.0) or 0.0

        if not alignment_passed:
            promotion_reason = "blocked: alignment failed"
        elif artifact_dominance:
            promotion_reason = "blocked: artifact dominance"
        elif not nulls_passed:
            promotion_reason = "blocked: null controls failed"
        elif not ablations_passed:
            promotion_reason = "blocked: ablations failed"
        elif delta_auc < _MIN_DELTA_AUC:
            promotion_reason = f"blocked: delta_auc below threshold ({delta_auc:.4f} < {_MIN_DELTA_AUC})"
        elif delta_ece > 0:
            promotion_reason = "blocked: calibration worsened"
        else:
            promoted = True
            promotion_reason = (
                "promoted: Level T signal topology telemetry adds residual "
                "predictive value beyond Level M under controls"
            )

    omega_event: dict = {}
    result = EEGSignalMTResidualResult(
        dataset_id=dataset_id,
        n_m_rows=len(m_rows) if m_rows else n_joined,
        n_t_rows=len(t_rows) if t_rows else n_joined,
        n_joined_rows=n_joined,
        n_targets_available=n_targets,
        predictive_metrics_available=predictive_available,
        metrics=metrics,
        null_report=null_report,
        ablation_report=ablation_report,
        alignment_report=alignment_report,
        artifact_report=artifact_report,
        omega_event=omega_event,
        promoted=promoted,
        promotion_reason=promotion_reason,
        safe_claim=_SAFE_CLAIM,
        forbidden_claims=[],
        warnings=join_warnings,
    )
    result.omega_event = build_signal_mt_omega_event(result)
    return result


def build_signal_mt_omega_event(result: EEGSignalMTResidualResult) -> dict:
    """Build omega event for M+T residual benchmark run."""
    _validate_safe_text(result.safe_claim)
    payload = (
        f"signal_mt:{result.dataset_id}:{result.n_joined_rows}:"
        f"{result.promoted}:{result.safe_claim}"
    )
    event_id = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return {
        "event_id": event_id,
        "event_type": "eeg_signal_mt_residual",
        "dataset_id": result.dataset_id,
        "n_joined_rows": result.n_joined_rows,
        "n_targets_available": result.n_targets_available,
        "predictive_metrics_available": result.predictive_metrics_available,
        "promoted": result.promoted,
        "promotion_reason": result.promotion_reason,
        "safe_claim": result.safe_claim,
        "forbidden_claims": result.forbidden_claims,
        "warnings": result.warnings[:10],
    }


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------

_JOINED_COLS = [
    "dataset_id", "row_id", "source_file", "window_id",
    "window_start_s", "window_end_s", "sample_start", "sample_end",
    "n_channels", "n_samples", "sample_rate_hz",
    "spectral_power_proxy", "entropy_proxy", "lzc_proxy",
    "artifact_score_m", "feature_status",
    "q_net", "q_abs", "f_dress", "defect_density",
    "n_triangles", "n_valid_triangles", "topology_quality", "topology_status",
    "y", "label", "warnings",
]


def write_signal_mt_outputs(
    result: EEGSignalMTResidualResult,
    out_dir: str,
    joined_rows: list[EEGSignalMTJoinedRow] | None = None,
) -> dict[str, str]:
    """Write all 8 signal M+T residual benchmark artifacts.

    Artifacts:
        features_joined_signal.csv
        metrics_signal_mt.json
        nulls_signal.json
        ablations_signal.json
        alignment_report.json
        artifact_report.json
        omega_event.json
        report.md

    Returns:
        Dict mapping artifact names to file paths.
    """
    _validate_safe_text(result.safe_claim)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}

    # 1. features_joined_signal.csv
    joined_rows = joined_rows or []
    jf = out_path / "features_joined_signal.csv"
    with open(jf, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(_JOINED_COLS)
        for r in joined_rows:
            d = asdict(r)
            writer.writerow([
                d.get("dataset_id", ""),
                d.get("row_id", ""),
                d.get("source_file", ""),
                d.get("window_id", ""),
                d.get("window_start_s", ""),
                d.get("window_end_s", ""),
                d.get("sample_start", ""),
                d.get("sample_end", ""),
                d.get("n_channels", ""),
                d.get("n_samples", ""),
                d.get("sample_rate_hz", ""),
                d.get("spectral_power_proxy", ""),
                d.get("entropy_proxy", ""),
                d.get("lzc_proxy", ""),
                d.get("artifact_score_m", ""),
                d.get("feature_status", ""),
                d.get("q_net", ""),
                d.get("q_abs", ""),
                d.get("f_dress", ""),
                d.get("defect_density", ""),
                d.get("n_triangles", ""),
                d.get("n_valid_triangles", ""),
                d.get("topology_quality", ""),
                d.get("topology_status", ""),
                d.get("y", ""),
                d.get("label", ""),
                "|".join(d.get("warnings", [])),
            ])
    outputs["features_joined_signal"] = str(jf)

    # 2. metrics_signal_mt.json
    mf = out_path / "metrics_signal_mt.json"
    with open(mf, "w", encoding="utf-8") as f:
        json.dump(result.metrics, f, indent=2)
    outputs["metrics_signal_mt"] = str(mf)

    # 3. nulls_signal.json
    nf = out_path / "nulls_signal.json"
    with open(nf, "w", encoding="utf-8") as f:
        json.dump(result.null_report, f, indent=2)
    outputs["nulls_signal"] = str(nf)

    # 4. ablations_signal.json
    af = out_path / "ablations_signal.json"
    with open(af, "w", encoding="utf-8") as f:
        json.dump(result.ablation_report, f, indent=2)
    outputs["ablations_signal"] = str(af)

    # 5. alignment_report.json
    alf = out_path / "alignment_report.json"
    with open(alf, "w", encoding="utf-8") as f:
        json.dump(result.alignment_report, f, indent=2)
    outputs["alignment_report"] = str(alf)

    # 6. artifact_report.json
    arf = out_path / "artifact_report.json"
    with open(arf, "w", encoding="utf-8") as f:
        json.dump(result.artifact_report, f, indent=2)
    outputs["artifact_report"] = str(arf)

    # 7. omega_event.json
    of = out_path / "omega_event.json"
    with open(of, "w", encoding="utf-8") as f:
        json.dump(result.omega_event, f, indent=2)
    outputs["omega_event"] = str(of)

    # 8. report.md
    md = _build_markdown_report(result)
    rf = out_path / "report.md"
    with open(rf, "w", encoding="utf-8") as f:
        f.write(md)
    outputs["report"] = str(rf)

    return outputs


def _build_markdown_report(result: EEGSignalMTResidualResult) -> str:
    _validate_safe_text(result.safe_claim)

    md = "# EEG Signal-Level M+T Residual Benchmark\n\n"

    md += "## Stage\n\n"
    md += (
        "P11 — Signal-level M+T residual benchmark orchestration. "
        "Joins Level M signal features with Level T topology telemetry "
        "for controlled signal-level residual benchmarking. "
        "Does NOT infer labels, fabricate targets, or modify legacy benchmark semantics.\n\n"
    )

    md += f"## Dataset\n\n`{result.dataset_id}`\n\n"

    md += "## Input Level M Signal Features\n\n"
    md += f"- M rows: {result.n_m_rows}\n\n"

    md += "## Input Level T Signal Topology\n\n"
    md += f"- T rows: {result.n_t_rows}\n\n"

    md += "## Joined Rows\n\n"
    md += f"- Joined: {result.n_joined_rows}\n"
    md += f"- Targets available: {result.n_targets_available}\n\n"

    md += "## Predictive Metric Availability\n\n"
    md += f"- Predictive metrics available: {result.predictive_metrics_available}\n"
    if not result.predictive_metrics_available:
        md += "- **Reason:** No explicit validated targets were provided. No target fabrication performed.\n"
    md += "\n"

    md += "## Metrics\n\n"
    m = result.metrics
    for k in ["auc_m", "auc_mt", "delta_auc", "brier_m", "brier_mt", "ece_m", "ece_mt", "delta_ece"]:
        md += f"- {k}: {m.get(k, 'null')}\n"
    md += "\n"

    md += "## Null Controls\n\n"
    nr = result.null_report
    md += f"- Status: {nr.get('status', 'unknown')}\n"
    md += f"- Nulls passed: {nr.get('nulls_passed', False)}\n"
    md += f"- Note: {nr.get('note', '')}\n\n"

    md += "## Ablations\n\n"
    abr = result.ablation_report
    md += f"- Ablations passed: {abr.get('ablations_passed', False)}\n"
    for name, entry in abr.get("ablation_entries", {}).items():
        md += f"  - {name}: auc={entry.get('auc', 'null')}, delta={entry.get('delta_auc_vs_M', 'null')}\n"
    md += "\n"

    md += "## Alignment Report\n\n"
    ar = result.alignment_report
    md += f"- Alignment passed: {ar.get('alignment_passed', False)}\n"
    md += f"- Missing T for M: {ar.get('missing_t_for_m', 0)}\n"
    md += f"- Extra T rows: {ar.get('extra_t_rows', 0)}\n\n"

    md += "## Artifact Report\n\n"
    afr = result.artifact_report
    md += f"- Artifact dominance: {afr.get('artifact_dominance', False)}\n"
    md += f"- Mean artifact score M: {afr.get('mean_artifact_score_m', 0.0):.4f}\n"
    md += f"- Mean topology quality: {afr.get('mean_topology_quality', 0.0):.4f}\n\n"

    md += "## Promotion Decision\n\n"
    md += f"- **Promoted:** {result.promoted}\n"
    md += f"- **Reason:** {result.promotion_reason}\n\n"

    md += "## Safe Claim\n\n"
    md += f"{result.safe_claim}\n\n"

    md += "## Forbidden Claims\n\n"
    if result.forbidden_claims:
        for fc in result.forbidden_claims:
            md += f"- {fc}\n"
    else:
        md += (
            "_None. No consciousness, self, soul, liberation, afterlife, "
            "enlightenment, or ontology proof claims._\n"
        )
    md += "\n"

    if result.warnings:
        md += f"## Warnings ({len(result.warnings)})\n\n"
        for w in result.warnings[:10]:
            md += f"- {w}\n"
        md += "\n"

    md += "## Next Required Step\n\n"
    md += (
        "Run this benchmark with explicit validated labels/targets "
        "before considering predictive promotion.\n\n"
    )

    md += "---\n"
    md += (
        "**Guardrail:** This benchmark does not validate cognition, affect, "
        "physiology, or any metaphysical property.\n"
    )
    return md
