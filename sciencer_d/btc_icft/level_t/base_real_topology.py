"""Shared real signal-derived Level T topology logic for all datasets.

Extracted from `ds005620_real_topology.py`, `ds003969_real_topology.py`, and
`ds001787_real_topology.py`, which were confirmed function-for-function
identical (same dataclasses, same 10 functions, same order) except for
`dataset_id`-dependent strings (error messages naming the CLI command, the
`dataset_id` field itself, report titles/safe-claim text). Each per-dataset
module is now a thin shim over this file, parameterized by its own
`DATASET_ID`.

`compute_real_topology_for_window` reads the actual per-channel signal for a
window and computes topology via `eeg_signal_topology.compute_topology_from_channels`
-- not a hash of row_id/metadata text. `compute_fixture_topology_for_window`
(hash-based) is kept only as the explicit, clearly-labeled `--mock-fixture`
fallback; `--real` never falls back to it (see `build_level_t_rows_from_m_windows`'s
mutual-exclusivity contract, enforced by each dataset's CLI).

One behavioral fix made during consolidation: `write_level_t_topology_outputs`
now takes `rows` as an explicit parameter instead of reading a module-level
`result_rows_cache` global from within this shared module (that pattern still
exists at the per-dataset shim layer, unchanged from the caller's perspective,
but no longer leaks into the shared logic itself -- the shared function has no
hidden dependency on which dataset module happens to have set its own global
before the call).

Phase 3 addition: `build_null_gate_report` and `build_group_significance_report`
replace the `"status": "placeholder_only", "real_nulls_performed": False` stub
that every one of the three pre-consolidation files wrote (a self-reporting
"we didn't run this" blob, referencing `validation.nulls`' function names as
strings without ever calling them). Both are now real:
- `build_null_gate_report` calls `validation.nulls.phase_randomize_time` on
  the actual per-channel signal and recomputes topology on each surrogate --
  the same phase-randomization surrogate gate used manually, ad hoc, in prior
  report-writing sessions, now committed as reusable pipeline code. Compute-
  heavy (N surrogates x per-window topology recomputation), so it is opt-in
  and bounded by `sample_size` by default -- gating every window in a
  1000+-window dataset by default would make every real run dramatically
  slower for a check most callers don't need every time.
- `build_group_significance_report` uses `analysis.permutation`'s
  window-pooled and subject-blocked permutation tests (Phase 1) to test
  whether a Level M grouping column (`state_label` by default -- present in
  every dataset's Level M output: awake/sedated, meditation/thinking,
  expert/novice) predicts Level T topology metrics. Joins Level T rows back
  to Level M rows by row_id (same join `build_artifact_alignment_report`
  already does for artifact_score) since Level T rows do not themselves carry
  the semantic group label, only `task_label`. Cheap (no surrogates), so it
  runs by default whenever exactly 2 group values are present; reports
  `"not_applicable"` with a reason otherwise (e.g. more than 2 task values,
  or a continuous variable like ds001787's depth-of-meditation rating, which
  needs a correlation test this function does not attempt -- see that
  dataset's own report for how that analysis was actually done).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from sciencer_d.btc_icft.level_t.eeg_signal_topology import compute_topology_from_channels
from sciencer_d.btc_icft.report_guardrails import validate_safe_text

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

REQUIRED_M_COLUMNS = [
    "row_id", "subject_id", "session_id", "run_id", "window_id", "task_label",
    "source_file", "window_start_s", "window_end_s",
]


@dataclass
class LevelTRealTopologyRow:
    row_id: str
    subject_id: str
    session_id: str | None
    run_id: str | None
    window_id: str
    task_label: str | None
    q_net: float
    q_abs: float
    f_dress: float
    defect_density: float
    n_triangles: int
    n_valid_triangles: int
    topology_quality: float
    null_method: str
    null_seed: int
    source_file: str
    window_start_s: float
    window_end_s: float
    warnings: list[str]


@dataclass
class LevelTRealTopologyResult:
    dataset_id: str
    n_rows: int
    n_subjects: int
    n_windows: int
    topology_quality_report: dict
    null_placeholder_report: dict
    artifact_alignment_report: dict
    omega_event: dict
    safe_claim: str
    forbidden_claims: list[str]
    warnings: list[str]


def _validate_safe_text(text: str) -> None:
    validate_safe_text(text)


def _h(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)


def load_level_m_window_features(m_windows_dir: str, dataset_id: str) -> list[dict]:
    p = Path(m_windows_dir) / "features_m.csv"
    if not p.exists():
        raise FileNotFoundError(
            f"Level M window features are required. Run run_{dataset_id}_m_real first or use --mock-fixture."
        )
    with p.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    missing = [c for c in REQUIRED_M_COLUMNS if c not in (rows[0].keys() if rows else [])]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return rows


def compute_fixture_topology_for_window(m_row: dict, index: int = 0) -> LevelTRealTopologyRow:
    seed_src = f"{m_row.get('row_id')}|{m_row.get('source_file')}|{m_row.get('task_label')}|{m_row.get('window_id')}|{index}"
    hv = _h(seed_src)
    n_triangles = 8 + (hv % 25)
    n_valid = 1 + (hv // 7) % n_triangles
    q_net = round((((hv % 6001) / 1000.0) - 3.0), 6)
    q_abs = round(abs(q_net) + (((hv // 13) % 3000) / 1000.0), 6)
    f_dress = round(max(0.0, q_abs - abs(q_net)), 6)
    defect_density = round(q_abs / max(n_valid, 1), 6)
    topo = round(n_valid / n_triangles, 6)
    return LevelTRealTopologyRow(
        row_id=str(m_row.get("row_id")), subject_id=str(m_row.get("subject_id")),
        session_id=m_row.get("session_id") or None, run_id=m_row.get("run_id") or None,
        window_id=str(m_row.get("window_id")), task_label=m_row.get("task_label") or None,
        q_net=q_net, q_abs=q_abs, f_dress=f_dress, defect_density=defect_density,
        n_triangles=int(n_triangles), n_valid_triangles=int(n_valid), topology_quality=topo,
        null_method="fixture_none", null_seed=int(_h(str(m_row.get("row_id"))) % (2**31 - 1)),
        source_file=str(m_row.get("source_file")),
        window_start_s=float(m_row.get("window_start_s") or 0.0),
        window_end_s=float(m_row.get("window_end_s") or 0.0),
        warnings=[],
    )


def compute_real_topology_for_window(m_row: dict, max_channels: int | None = 16) -> LevelTRealTopologyRow:
    """Compute topology telemetry from the ACTUAL EEG signal for one window.

    Unlike `compute_fixture_topology_for_window` (which derives numbers from a hash of
    row_id/metadata text, independent of signal content), this reads the real per-channel
    samples for the window and computes topology from them via
    `eeg_signal_topology.compute_topology_from_channels` (the same real, signal-derived
    computation already used by the generic multi-dataset Level T pipeline).

    If the source file can't be read (missing file, out-of-range window, unsupported
    format), returns a zero/`topology_status`-flagged row with a warning instead of
    raising, matching the generic pipeline's skip-and-report convention.
    """
    from data.bids_ingest import read_window_signal

    row_id = str(m_row.get("row_id"))
    source_file = str(m_row.get("source_file") or "")
    window_start_s = float(m_row.get("window_start_s") or 0.0)
    window_end_s = float(m_row.get("window_end_s") or 0.0)
    warnings: list[str] = []

    def _zero_row(reason: str) -> LevelTRealTopologyRow:
        warnings.append(reason)
        return LevelTRealTopologyRow(
            row_id=row_id, subject_id=str(m_row.get("subject_id")),
            session_id=m_row.get("session_id") or None, run_id=m_row.get("run_id") or None,
            window_id=str(m_row.get("window_id")), task_label=m_row.get("task_label") or None,
            q_net=0.0, q_abs=0.0, f_dress=0.0, defect_density=0.0,
            n_triangles=0, n_valid_triangles=0, topology_quality=0.0,
            null_method="real_none", null_seed=0,
            source_file=source_file, window_start_s=window_start_s, window_end_s=window_end_s,
            warnings=warnings,
        )

    if not source_file or not Path(source_file).exists():
        return _zero_row(f"source file not found: {source_file!r}; topology skipped")

    try:
        channels = read_window_signal(
            source_file, window_start_s, window_end_s, pick="all", max_channels=max_channels
        )
    except (ValueError, OSError) as exc:
        # OSError (e.g. FileNotFoundError): a companion file for a
        # multi-file format (BrainVision .vhdr/.eeg/.vmrk) can be genuinely
        # missing from the dataset even though the .vhdr itself (checked
        # above) exists -- confirmed for real on ds003816 (one task/session
        # missing its .vmrk on the dataset's own S3 bucket). Same
        # skip-and-report fix as level_m/base_windows_real.py's identical
        # bug for this exact failure mode.
        return _zero_row(f"window skipped: {exc}")

    channel_data = [list(map(float, ch)) for ch in channels]
    (
        q_net, q_abs, f_dress, defect_density,
        n_triangles, n_valid_triangles, topology_quality,
    ) = compute_topology_from_channels(channel_data)

    return LevelTRealTopologyRow(
        row_id=row_id, subject_id=str(m_row.get("subject_id")),
        session_id=m_row.get("session_id") or None, run_id=m_row.get("run_id") or None,
        window_id=str(m_row.get("window_id")), task_label=m_row.get("task_label") or None,
        q_net=q_net, q_abs=q_abs, f_dress=f_dress, defect_density=defect_density,
        n_triangles=n_triangles, n_valid_triangles=n_valid_triangles, topology_quality=topology_quality,
        null_method="real_none", null_seed=int(_h(row_id) % (2**31 - 1)),
        source_file=source_file, window_start_s=window_start_s, window_end_s=window_end_s,
        warnings=warnings,
    )


def build_level_t_rows_from_m_windows(
    m_rows: list[dict], mock_fixture: bool = False, real: bool = False
) -> list[LevelTRealTopologyRow]:
    if real:
        return [compute_real_topology_for_window(r) for r in m_rows]
    if not mock_fixture:
        raise ValueError("real EEG topology extraction requires --real or --mock-fixture")
    return [compute_fixture_topology_for_window(r, i) for i, r in enumerate(m_rows)]


def compute_phase_based_topology_for_window(
    m_row: dict, band: str = "alpha", max_channels: int | None = 16,
) -> dict:
    """Real band-specific Hilbert-phase topology for one window.

    Unlike `compute_real_topology_for_window` (a channel-mean/correlation-
    threshold heuristic -- see `eeg_signal_topology.py`'s own docstring; it
    uses no phase or frequency information at all), this bandpass-filters the
    real per-channel signal to `band` (default alpha, 8-13 Hz -- classically
    the band most associated with conscious-state EEG differences), extracts
    the analytic (Hilbert) phase via
    `validation.analytic_phase.bandpass_hilbert_phase`, and computes
    Q/Qabs/f_dress from genuine inter-channel phase relationships via
    `validation.analytic_phase.channel_phase_gradient_metrics` -- a real,
    already-tested instrument this repo built (for `pipelines/run_eeg.py`) but
    never wired into the dataset-report pipeline.

    Additive, not a replacement: returns a plain dict (not a
    `LevelTRealTopologyRow`) so it can be reported alongside the existing
    channel-mean-based q_net/q_abs/f_dress without silently changing them.
    Returns `{"status": "skipped", ...}` (not a raised exception) for any
    unreadable/out-of-range/too-few-channels/band-above-Nyquist case, matching
    this module's existing skip-and-report convention.
    """
    from data.bids_ingest import get_sample_rate, read_window_signal
    from validation.analytic_phase import (
        DEFAULT_EEG_BANDS,
        bandpass_hilbert_phase,
        channel_phase_gradient_metrics,
    )

    row_id = str(m_row.get("row_id"))
    source_file = str(m_row.get("source_file") or "")
    window_start_s = float(m_row.get("window_start_s") or 0.0)
    window_end_s = float(m_row.get("window_end_s") or 0.0)

    if band not in DEFAULT_EEG_BANDS:
        raise ValueError(f"Unknown band {band!r}; choose from {sorted(DEFAULT_EEG_BANDS)}")

    if not source_file or not Path(source_file).exists():
        return {"row_id": row_id, "band": band, "status": "skipped", "reason": f"source file not found: {source_file!r}"}

    try:
        sfreq = get_sample_rate(source_file)
        channels = read_window_signal(
            source_file, window_start_s, window_end_s, pick="all", max_channels=max_channels
        )
    except (ValueError, OSError) as exc:
        # OSError: a companion file for a multi-file format (e.g. BrainVision
        # .vhdr/.eeg/.vmrk) can be genuinely missing even though the .vhdr
        # itself exists -- see compute_real_topology_for_window's docstring
        # for the real case this was found on (ds003816).
        return {"row_id": row_id, "band": band, "status": "skipped", "reason": f"window skipped: {exc}"}

    if channels.shape[0] < 2:
        return {
            "row_id": row_id, "band": band, "status": "skipped",
            "reason": f"need >=2 channels for phase-gradient metrics, got {channels.shape[0]}",
        }

    lo, hi = DEFAULT_EEG_BANDS[band]
    nyq = sfreq / 2.0
    if hi >= nyq:
        return {
            "row_id": row_id, "band": band, "status": "skipped",
            "reason": f"band {band} upper edge {hi} Hz >= Nyquist {nyq} Hz at sfreq={sfreq}",
        }

    try:
        phase = bandpass_hilbert_phase(channels, sfreq, lo, hi)
    except ValueError as exc:
        return {"row_id": row_id, "band": band, "status": "skipped", "reason": f"phase extraction failed: {exc}"}

    metrics = channel_phase_gradient_metrics(phase)
    return {"row_id": row_id, "band": band, "status": "computed", "sfreq": sfreq, **metrics}


def build_phase_based_topology_report(
    rows: list[LevelTRealTopologyRow], m_rows: list[dict], band: str = "alpha",
    sample_size: int | None = None, seed: int = 0, max_channels: int | None = 16,
) -> dict:
    """Aggregate `compute_phase_based_topology_for_window` over (optionally a
    bounded sample of) rows.

    Unlike `build_null_gate_report`, `sample_size` defaults to `None` (gate
    every window): a single bandpass+Hilbert-transform per window is far
    cheaper than the surrogate gate's N-surrogate recomputation loop, so there
    is no default need to bound it. `sample_size` is still accepted for callers
    who want to bound compute on very large datasets.
    """
    by_id = {str(m.get("row_id")): m for m in m_rows}
    candidate_rows = [r for r in rows if r.row_id in by_id]

    if sample_size is not None and len(candidate_rows) > sample_size:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(candidate_rows), size=sample_size, replace=False)
        candidate_rows = [candidate_rows[i] for i in sorted(idx)]

    results = [
        compute_phase_based_topology_for_window(by_id[r.row_id], band=band, max_channels=max_channels)
        for r in candidate_rows
    ]
    computed = [x for x in results if x["status"] == "computed"]
    skipped = [x for x in results if x["status"] != "computed"]

    def _mean(key: str) -> float:
        vals = [x[key] for x in computed if key in x and np.isfinite(x[key])]
        return float(np.mean(vals)) if vals else float("nan")

    return {
        "status": "phase_based_topology_computed",
        "band": band,
        "method": "bandpass_hilbert_phase + channel_phase_gradient_metrics",
        "n_windows_computed": len(computed),
        "n_windows_skipped": len(skipped),
        "n_windows_total_candidates": len(rows),
        "mean_Q": _mean("Q"),
        "mean_Qabs": _mean("Qabs"),
        "mean_phase_grad": _mean("phase_grad"),
        "mean_f_dress": _mean("f_dress"),
        "seed": seed,
        "sample_size": sample_size,
        "results": results,
    }


def compute_connectivity_for_window(
    m_row: dict, methods: tuple[str, ...] = ("plv", "pli", "wpli"),
    max_channels: int | None = 16, compute_granger: bool = False, granger_maxlag: int = 5,
) -> dict:
    """Real connectivity (PLV/PLI/wPLI, optionally directed Granger
    causality) for one window, from the actual per-channel signal --
    `analysis/connectivity_topology.py`'s instruments (Phase 0/3 of the
    "beyond topology" pass), applied per-dataset-window here for the first
    time (they previously existed only in the separate ITCT script).

    Additive report function, not wired into `LevelTRealTopologyRow` --
    keeps the existing q_net/q_abs/f_dress columns and the three published
    reports untouched. PLI/wPLI matter here specifically because scalp EEG
    connectivity is prone to zero-lag volume-conduction artifacts that PLV
    cannot distinguish from genuine coupling; PLI/wPLI are insensitive to
    exactly that artifact by construction (see their docstrings).
    """
    from data.bids_ingest import read_window_signal

    from analysis.connectivity_topology import (
        compute_granger_causality_matrix,
        compute_pli,
        compute_plv,
        compute_wpli,
    )

    row_id = str(m_row.get("row_id"))
    source_file = str(m_row.get("source_file") or "")
    window_start_s = float(m_row.get("window_start_s") or 0.0)
    window_end_s = float(m_row.get("window_end_s") or 0.0)

    if not source_file or not Path(source_file).exists():
        return {"row_id": row_id, "status": "skipped", "reason": f"source file not found: {source_file!r}"}

    try:
        channels = read_window_signal(
            source_file, window_start_s, window_end_s, pick="all", max_channels=max_channels
        )
    except (ValueError, OSError) as exc:
        # OSError: see compute_real_topology_for_window's docstring -- a
        # multi-file format's companion file can be genuinely missing.
        return {"row_id": row_id, "status": "skipped", "reason": f"window skipped: {exc}"}

    channel_data = np.asarray(channels, dtype=float)
    if channel_data.shape[0] < 2:
        return {
            "row_id": row_id, "status": "skipped",
            "reason": f"need >=2 channels for connectivity, got {channel_data.shape[0]}",
        }

    result: dict = {"row_id": row_id, "status": "computed", "n_channels": int(channel_data.shape[0])}
    method_fns = {"plv": compute_plv, "pli": compute_pli, "wpli": compute_wpli}
    for m in methods:
        fn = method_fns.get(m)
        if fn is None:
            continue
        mat = fn(channel_data)
        off_diag = mat[~np.eye(mat.shape[0], dtype=bool)]
        result[f"mean_{m}"] = float(np.mean(off_diag)) if off_diag.size else float("nan")
        result[f"{m}_matrix"] = mat.tolist()

    if compute_granger:
        gc = compute_granger_causality_matrix(channel_data, maxlag=granger_maxlag)
        p_values = list(gc.values())
        result["granger_causality_p_values"] = gc
        result["n_significant_granger_pairs"] = sum(
            1 for p in p_values if np.isfinite(p) and p < 0.05
        )

    return result


def build_connectivity_report(
    rows: list[LevelTRealTopologyRow], m_rows: list[dict], methods: tuple[str, ...] = ("plv", "pli", "wpli"),
    sample_size: int | None = None, seed: int = 0, max_channels: int | None = 16,
    compute_granger: bool = False, granger_maxlag: int = 5,
) -> dict:
    """Aggregate `compute_connectivity_for_window` over (optionally a bounded
    sample of) rows. `compute_granger` is a separate, more expensive opt-in
    flag (O(n_channels^2) directed OLS-based tests per window) -- keep it off
    for large datasets unless directed influence is specifically needed;
    PLV/PLI/wPLI alone are cheap enough to gate every window by default.
    """
    by_id = {str(m.get("row_id")): m for m in m_rows}
    candidate_rows = [r for r in rows if r.row_id in by_id]

    if sample_size is not None and len(candidate_rows) > sample_size:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(candidate_rows), size=sample_size, replace=False)
        candidate_rows = [candidate_rows[i] for i in sorted(idx)]

    results = [
        compute_connectivity_for_window(
            by_id[r.row_id], methods=methods, max_channels=max_channels,
            compute_granger=compute_granger, granger_maxlag=granger_maxlag,
        )
        for r in candidate_rows
    ]
    computed = [x for x in results if x["status"] == "computed"]
    skipped = [x for x in results if x["status"] != "computed"]

    def _mean(key: str) -> float:
        vals = [x[key] for x in computed if key in x and np.isfinite(x[key])]
        return float(np.mean(vals)) if vals else float("nan")

    summary = {f"mean_{m}": _mean(f"mean_{m}") for m in methods}
    if compute_granger:
        summary["mean_n_significant_granger_pairs"] = _mean("n_significant_granger_pairs")

    return {
        "status": "connectivity_computed",
        "methods": list(methods),
        "compute_granger": compute_granger,
        "n_windows_computed": len(computed),
        "n_windows_skipped": len(skipped),
        "n_windows_total_candidates": len(rows),
        **summary,
        "seed": seed,
        "sample_size": sample_size,
        "results": results,
    }


def build_topology_quality_report(rows: list[LevelTRealTopologyRow]) -> dict:
    qs = [r.topology_quality for r in rows]
    return {
        "n_rows": len(rows), "n_subjects": len({r.subject_id for r in rows}), "n_windows": len(rows),
        "mean_topology_quality": (sum(qs) / len(qs)) if qs else 0.0,
        "min_topology_quality": min(qs) if qs else 0.0, "max_topology_quality": max(qs) if qs else 0.0,
        "low_quality_rows": [r.row_id for r in rows if r.topology_quality < 0.25 or r.n_valid_triangles <= 0],
        "n_valid_triangles_total": sum(r.n_valid_triangles for r in rows),
        "n_triangles_total": sum(r.n_triangles for r in rows),
        "quality_passed": all(r.topology_quality >= 0.25 and r.n_valid_triangles > 0 for r in rows),
    }


def build_null_placeholder_report(rows: list[LevelTRealTopologyRow]) -> dict:
    return {"status": "placeholder_only", "real_nulls_performed": False, "methods_planned": ["channel_shuffle", "time_reverse", "phase_randomization"], "note": "Null controls are placeholders at Level T extraction; residual benchmark controls run in Issue #54.", "n_rows": len(rows)}


def compute_surrogate_gate_for_window(
    m_row: dict, n_surrogates: int = 50, seed: int = 0, max_channels: int | None = 16,
) -> dict:
    """Phase-randomization surrogate gate for one window: is the observed
    topological charge (q_abs) genuine cross-channel structure, or would a
    phase-randomized surrogate with the same per-channel power spectrum give
    a similar value?

    Reads the real per-channel signal (same source as `compute_real_topology_for_window`),
    generates `n_surrogates` phase-randomized copies via
    `validation.nulls.phase_randomize_time` (preserves each channel's power
    spectrum, destroys cross-channel phase relationships), recomputes q_abs on
    each surrogate, and returns `validation.nulls.compute_null_summary` (a
    z-score of the observed value against the surrogate null distribution)
    plus row identity. Returns a `{"status": "skipped", ...}` dict (not a
    raised exception) if the source file can't be read, matching this
    module's existing skip-and-report convention.
    """
    from data.bids_ingest import read_window_signal
    from validation.nulls import compute_null_summary, phase_randomize_time

    row_id = str(m_row.get("row_id"))
    source_file = str(m_row.get("source_file") or "")
    window_start_s = float(m_row.get("window_start_s") or 0.0)
    window_end_s = float(m_row.get("window_end_s") or 0.0)

    if not source_file or not Path(source_file).exists():
        return {"row_id": row_id, "status": "skipped", "reason": f"source file not found: {source_file!r}"}

    try:
        channels = read_window_signal(
            source_file, window_start_s, window_end_s, pick="all", max_channels=max_channels
        )
    except (ValueError, OSError) as exc:
        # OSError: see compute_real_topology_for_window's docstring -- a
        # multi-file format's companion file can be genuinely missing.
        return {"row_id": row_id, "status": "skipped", "reason": f"window skipped: {exc}"}

    channel_data = [list(map(float, ch)) for ch in channels]
    observed_q_abs = compute_topology_from_channels(channel_data)[1]  # (q_net, q_abs, ...)

    arr = np.asarray(channel_data, dtype=float)
    surrogate_q_abs = []
    for i in range(n_surrogates):
        surrogate = phase_randomize_time(arr, seed=seed + i)
        surrogate_q_abs.append(compute_topology_from_channels(surrogate.tolist())[1])

    summary = compute_null_summary(observed_q_abs, surrogate_q_abs)
    return {"row_id": row_id, "status": "gated", "n_surrogates": n_surrogates, **summary}


def build_null_gate_report(
    rows: list[LevelTRealTopologyRow], m_rows: list[dict],
    n_surrogates: int = 50, seed: int = 0, sample_size: int | None = 20, max_channels: int | None = 16,
) -> dict:
    """Aggregate `compute_surrogate_gate_for_window` over (optionally a bounded
    sample of) rows.

    `sample_size` bounds compute cost: gating every window in a large dataset
    by default would make every real run substantially slower for a check
    most callers don't need every time. `sample_size=None` gates all rows.
    Sampling uses a fixed seeded choice, so results are reproducible.
    """
    by_id = {str(m.get("row_id")): m for m in m_rows}
    candidate_rows = [r for r in rows if r.row_id in by_id]

    if sample_size is not None and len(candidate_rows) > sample_size:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(candidate_rows), size=sample_size, replace=False)
        candidate_rows = [candidate_rows[i] for i in sorted(idx)]

    gate_results = [
        compute_surrogate_gate_for_window(by_id[r.row_id], n_surrogates=n_surrogates, seed=seed, max_channels=max_channels)
        for r in candidate_rows
    ]
    gated = [g for g in gate_results if g["status"] == "gated"]
    skipped = [g for g in gate_results if g["status"] == "skipped"]
    z_values = [g["z"] for g in gated if g["z"] == g["z"]]  # filter nan

    return {
        "status": "real_nulls_performed",
        "real_nulls_performed": True,
        "method": "phase_randomize_time",
        "n_surrogates_per_window": n_surrogates,
        "n_windows_gated": len(gated),
        "n_windows_skipped": len(skipped),
        "n_windows_total_candidates": len(rows),
        "mean_abs_z": float(np.mean(np.abs(z_values))) if z_values else float("nan"),
        "n_passed_z_ge_2": sum(1 for z in z_values if abs(z) >= 2.0),
        "seed": seed,
        "sample_size": sample_size,
        "gate_results": gate_results,
    }


def build_group_significance_report(
    rows: list[LevelTRealTopologyRow], m_rows: list[dict],
    group_col: str = "state_label", value_cols: tuple[str, ...] = ("q_net", "q_abs", "f_dress", "defect_density"),
    n_permutations: int = 2000, seed: int = 0,
) -> dict:
    """Test whether a Level M grouping column (default `state_label`) predicts
    each Level T topology metric, using both the window-pooled and
    subject-blocked permutation tests from `analysis.permutation`.

    Joins Level T rows back to Level M rows by row_id (Level T rows do not
    themselves carry the semantic group label, only `task_label`). Reports
    `"not_applicable"` with a reason if `group_col` is absent from the joined
    data or doesn't have exactly 2 distinct non-null values -- this function
    only covers the 2-group comparison case; continuous-variable correlation
    (e.g. a 0-3 depth rating) needs a different test this function does not
    attempt.
    """
    import pandas as pd

    from analysis.permutation import permutation_test, subject_blocked_permutation_test

    by_id = {str(m.get("row_id")): m for m in m_rows}
    joined = []
    for r in rows:
        m = by_id.get(r.row_id)
        if m is None:
            continue
        group_val = m.get(group_col)
        if group_val in (None, ""):
            continue
        joined.append({"subject_id": r.subject_id, "group": group_val, **{c: getattr(r, c) for c in value_cols}})

    if not joined:
        return {"status": "not_applicable", "reason": f"no rows with a non-null {group_col!r} value", "group_col": group_col}

    df = pd.DataFrame(joined)
    groups = sorted(df["group"].unique(), key=str)
    if len(groups) != 2:
        return {
            "status": "not_applicable",
            "reason": f"{group_col!r} has {len(groups)} distinct values ({groups}), this report only covers 2-group comparisons",
            "group_col": group_col,
        }

    metric_results = {}
    for value_col in value_cols:
        sub = df[["subject_id", "group", value_col]].dropna()
        a = sub.loc[sub["group"] == groups[0], value_col].to_numpy(dtype=float)
        b = sub.loc[sub["group"] == groups[1], value_col].to_numpy(dtype=float)
        if len(a) < 2 or len(b) < 2:
            metric_results[value_col] = {"status": "insufficient_data"}
            continue
        pooled = permutation_test(a, b, n_permutations=n_permutations, seed=seed)
        blocked = subject_blocked_permutation_test(sub.rename(columns={value_col: "value"}), "value", "group", "subject_id", n_permutations=n_permutations, seed=seed)
        metric_results[value_col] = {"window_pooled": pooled.to_dict(), "subject_blocked": blocked.to_dict()}

    return {
        "status": "computed",
        "group_col": group_col,
        "groups": [str(g) for g in groups],
        "n_permutations": n_permutations,
        "seed": seed,
        "metrics": metric_results,
    }


def build_ml_decoding_report(
    rows: list[LevelTRealTopologyRow], m_rows: list[dict],
    group_col: str = "state_label",
    value_cols: tuple[str, ...] = ("q_net", "q_abs", "f_dress", "defect_density", "topology_quality"),
    extra_feature_reports: list[dict] | None = None,
    n_permutations: int = 1000, cv_folds: int = 5, seed: int = 0,
) -> dict:
    """Complementary validity check to `build_group_significance_report`:
    can any COMBINATION of real features decode `group_col` above chance,
    with a proper cross-validated permutation-test null (`analysis.ml_decoding`)?
    Additive, not a replacement for the per-metric univariate tests above.

    Same 2-group-only, row_id-join convention as `build_group_significance_report`
    (see its docstring). `value_cols` defaults to this row's own real topology
    columns (always available, no extra compute); `extra_feature_reports`
    optionally accepts additional per-window `results` lists from other
    reports in this pass (e.g. `connectivity_report["results"]`,
    `phase_based_topology_report["results"]`, `real_level_m_features_report["results"]`
    keyed by `row_id`) to widen the feature set to the "full real feature set"
    the repo-hardening plan's Phase 6 describes, without this function
    re-running any of that (compute-heavy) work itself.
    """
    from analysis.ml_decoding import build_decoding_report

    by_id = {str(m.get("row_id")): m for m in m_rows}
    extra_by_row: dict[str, dict] = {}
    for report_results in extra_feature_reports or []:
        for entry in report_results:
            row_id = str(entry.get("row_id", ""))
            if not row_id:
                continue
            extra_by_row.setdefault(row_id, {}).update(
                {k: v for k, v in entry.items() if isinstance(v, (int, float)) and k not in ("status",)}
            )

    feature_dicts: list[dict] = []
    labels: list = []
    for r in rows:
        m = by_id.get(r.row_id)
        if m is None:
            continue
        group_val = m.get(group_col)
        if group_val in (None, ""):
            continue
        feats = {c: getattr(r, c) for c in value_cols}
        feats.update(extra_by_row.get(r.row_id, {}))
        feature_dicts.append(feats)
        labels.append(group_val)

    if not feature_dicts:
        return {"status": "not_applicable", "reason": f"no rows with a non-null {group_col!r} value", "group_col": group_col}

    groups = sorted({str(g) for g in labels})
    if len(groups) != 2:
        return {
            "status": "not_applicable",
            "reason": f"{group_col!r} has {len(groups)} distinct values ({groups}), this report only covers 2-group comparisons",
            "group_col": group_col,
        }

    report = build_decoding_report(
        feature_dicts, labels, seed=seed, n_permutations=n_permutations, cv_folds=cv_folds,
    )
    report["group_col"] = group_col
    return report


def build_artifact_alignment_report(rows: list[LevelTRealTopologyRow], m_rows: list[dict]) -> dict:
    by_id = {str(r.get("row_id")): r for r in m_rows}
    art = []
    missing = 0
    for r in rows:
        v = by_id.get(r.row_id, {}).get("artifact_score")
        if v in (None, ""):
            missing += 1
        else:
            art.append(float(v))
    return {
        "n_rows": len(rows), "n_matched_m_rows": sum(1 for r in rows if r.row_id in by_id),
        "n_missing_artifact_scores": missing, "mean_artifact_score": (sum(art)/len(art)) if art else 0.0,
        "high_artifact_rows": [r.row_id for r in rows if (by_id.get(r.row_id, {}).get("artifact_score") not in (None, "") and float(by_id[r.row_id]["artifact_score"]) > 0.5)],
        "topology_quality_mean": (sum(r.topology_quality for r in rows)/len(rows)) if rows else 0.0,
        "low_topology_quality_rows": [r.row_id for r in rows if r.topology_quality < 0.25],
        "artifact_alignment_warning": "artifact scores partially missing" if missing else "none",
        "artifact_dominance_proxy": ((sum(art)/len(art)) > 0.5) if art else False,
    }


def build_level_t_omega_event(rows: list[LevelTRealTopologyRow], dataset_id: str) -> dict:
    safe = (
        f"Local {dataset_id.upper()}-style EEG windows were mapped into operational "
        "Level T topology telemetry candidates for future M+T residual testing."
    )
    _validate_safe_text(safe)
    return {"dataset_id": dataset_id, "status": "operational_level_t", "n_rows": len(rows), "safe_claim": safe}


def write_level_t_topology_outputs(
    result: LevelTRealTopologyResult, out_dir: str, rows: list[LevelTRealTopologyRow], dataset_id: str,
    null_gate_report: dict | None = None, group_significance_report: dict | None = None,
    phase_based_topology_report: dict | None = None, connectivity_report: dict | None = None,
    spatial_topology_report: dict | None = None, microstate_report: dict | None = None,
    ml_decoding_report: dict | None = None,
) -> dict[str, str]:
    """`null_gate_report`/`group_significance_report`/`phase_based_topology_report`/
    `connectivity_report`/`spatial_topology_report`/`microstate_report`/
    `ml_decoding_report` are optional (default None, writing nothing extra)
    so existing callers that don't pass them keep getting exactly the same
    output files as before.
    Passing them writes additional JSON files and adds report.md sections --
    see `build_null_gate_report`/`build_group_significance_report`/
    `build_phase_based_topology_report`/`build_connectivity_report`/
    `spatial_topology.py::build_spatial_topology_report`/
    `microstates.py::build_microstate_report`.
    """
    base = Path(out_dir); base.mkdir(parents=True, exist_ok=True)
    paths = {
        "features_t.csv": base / "features_t.csv",
        "topology_quality_report.json": base / "topology_quality_report.json",
        "null_placeholder_report.json": base / "null_placeholder_report.json",
        "artifact_alignment_report.json": base / "artifact_alignment_report.json",
        "omega_event.json": base / "omega_event.json",
        "report.md": base / "report.md",
    }
    if null_gate_report is not None:
        paths["null_gate_report.json"] = base / "null_gate_report.json"
    if group_significance_report is not None:
        paths["group_significance_report.json"] = base / "group_significance_report.json"
    if phase_based_topology_report is not None:
        paths["phase_based_topology_report.json"] = base / "phase_based_topology_report.json"
    if connectivity_report is not None:
        paths["connectivity_report.json"] = base / "connectivity_report.json"
    if spatial_topology_report is not None:
        paths["spatial_topology_report.json"] = base / "spatial_topology_report.json"
    if microstate_report is not None:
        paths["microstate_report.json"] = base / "microstate_report.json"
    if ml_decoding_report is not None:
        paths["ml_decoding_report.json"] = base / "ml_decoding_report.json"

    with paths["features_t.csv"].open("w", encoding="utf-8", newline="") as f:
        writer = None
        for r in rows:
            d = asdict(r)
            if writer is None:
                writer = csv.DictWriter(f, fieldnames=list(d.keys())); writer.writeheader()
            writer.writerow(d)
    paths["topology_quality_report.json"].write_text(json.dumps(result.topology_quality_report, indent=2), encoding="utf-8")
    paths["null_placeholder_report.json"].write_text(json.dumps(result.null_placeholder_report, indent=2), encoding="utf-8")
    paths["artifact_alignment_report.json"].write_text(json.dumps(result.artifact_alignment_report, indent=2), encoding="utf-8")
    paths["omega_event.json"].write_text(json.dumps(result.omega_event, indent=2), encoding="utf-8")
    if null_gate_report is not None:
        paths["null_gate_report.json"].write_text(json.dumps(null_gate_report, indent=2), encoding="utf-8")
    if group_significance_report is not None:
        paths["group_significance_report.json"].write_text(json.dumps(group_significance_report, indent=2), encoding="utf-8")
    if phase_based_topology_report is not None:
        paths["phase_based_topology_report.json"].write_text(json.dumps(phase_based_topology_report, indent=2), encoding="utf-8")
    if connectivity_report is not None:
        paths["connectivity_report.json"].write_text(json.dumps(connectivity_report, indent=2), encoding="utf-8")
    if spatial_topology_report is not None:
        paths["spatial_topology_report.json"].write_text(json.dumps(spatial_topology_report, indent=2), encoding="utf-8")
    if microstate_report is not None:
        paths["microstate_report.json"].write_text(json.dumps(microstate_report, indent=2), encoding="utf-8")
    if ml_decoding_report is not None:
        paths["ml_decoding_report.json"].write_text(json.dumps(ml_decoding_report, indent=2), encoding="utf-8")

    report_lines = [
        f"# {dataset_id.upper()} Real/Local Level T Topology Extraction",
        "## Dataset/stage",
        f"- dataset_id: {dataset_id}",
        "- stage: operational Level T topology telemetry",
        "## Input Level M windows",
        f"- n_rows: {result.n_rows}",
        "## Topology rows",
        f"- n_windows: {result.n_windows}",
        "## Topology quality report",
        f"- {result.topology_quality_report}",
        "## Null placeholder report",
        f"- {result.null_placeholder_report}",
    ]
    if null_gate_report is not None:
        report_lines += ["## Null gate report (real phase-randomization surrogates)", f"- {null_gate_report}"]
    if group_significance_report is not None:
        report_lines += ["## Group significance report (permutation tests)", f"- {group_significance_report}"]
    if phase_based_topology_report is not None:
        report_lines += ["## Phase-based topology report (real band-specific Hilbert phase)", f"- {phase_based_topology_report}"]
    if connectivity_report is not None:
        report_lines += ["## Connectivity report (real PLV/PLI/wPLI, optional directed Granger causality)", f"- {connectivity_report}"]
    if spatial_topology_report is not None:
        report_lines += ["## Spatial topology report (real montage-aware winding number on a genuine 2D phase field)", f"- {spatial_topology_report}"]
    if microstate_report is not None:
        report_lines += ["## Microstate report (real pycrostates modified K-means, per-recording not per-window)", f"- {microstate_report}"]
    if ml_decoding_report is not None:
        report_lines += ["## ML decoding report (cross-validated logistic regression + permutation-test null, complementary to per-metric group significance)", f"- {ml_decoding_report}"]
    report_lines += [
        "## Artifact alignment report",
        f"- {result.artifact_alignment_report}",
        "## Safe claim",
        f"- {result.safe_claim}",
        "## Forbidden claims", *[f"- {x}" for x in result.forbidden_claims],
        "## Warnings", *[f"- {w}" for w in result.warnings],
        "## Next required step",
        "- Run Issue #54 real/local M+T residual benchmark orchestration after Level M and Level T feature tables are available.",
    ]
    report = "\n".join(report_lines)
    _validate_safe_text(report)
    paths["report.md"].write_text(report + "\n", encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}
