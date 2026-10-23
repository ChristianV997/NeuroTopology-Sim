"""Shared signal-reader-derived Level T topology logic for all datasets.

Extracted from `ds005620_real_topology.py`, `ds003969_real_topology.py`, and
`ds001787_real_topology.py`, which were confirmed function-for-function
identical (same dataclasses, same 10 functions, same order) except for
`dataset_id`-dependent strings (error messages naming the CLI command, the
`dataset_id` field itself, report titles/safe-claim text). Each per-dataset
module is now a thin shim over this file, parameterized by its own
`DATASET_ID`.

`compute_real_topology_for_window` computes topology from per-channel samples
returned by the configured local reader via
`eeg_signal_topology.compute_topology_from_channels` -- not a hash of row_id/
metadata text. This software path does not authenticate the source or establish
that returned samples are empirical. `compute_fixture_topology_for_window`
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
import math
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
    q_net: float | None
    q_abs: float | None
    f_dress: float | None
    defect_density: float | None
    n_triangles: int
    n_valid_triangles: int
    topology_quality: float | None
    null_method: str
    null_seed: int
    source_file: str
    window_start_s: float | None
    window_end_s: float | None
    warnings: list[str]
    topology_status: str = "computed"
    missingness_state: str = "computed"
    missingness_reason: str | None = None
    is_valid: bool = True
    run_status: str = "complete"
    replicate_count: int = 1
    uncertainty_metadata: dict | None = None

    def __post_init__(self) -> None:
        metric_fields = ("q_net", "q_abs", "f_dress", "defect_density", "topology_quality")
        has_missing_or_nonfinite = False
        for fname in metric_fields:
            val = getattr(self, fname)
            if val is None or isinstance(val, bool):
                setattr(self, fname, None)
                has_missing_or_nonfinite = True
            else:
                try:
                    fval = float(val)
                except (TypeError, ValueError, OverflowError):
                    setattr(self, fname, None)
                    has_missing_or_nonfinite = True
                else:
                    if not math.isfinite(fval):
                        setattr(self, fname, None)
                        has_missing_or_nonfinite = True
                    elif fname in ("q_abs", "f_dress", "defect_density") and fval < 0.0:
                        setattr(self, fname, None)
                        has_missing_or_nonfinite = True
                    elif fname == "topology_quality" and not (0.0 <= fval <= 1.0):
                        setattr(self, fname, None)
                        has_missing_or_nonfinite = True
        if not _has_valid_triangle_counts(self.n_triangles, self.n_valid_triangles):
            has_missing_or_nonfinite = True
            for fname in metric_fields:
                setattr(self, fname, None)
        has_invalid_bounds = not _has_valid_window_bounds(self.window_start_s, self.window_end_s)
        if has_invalid_bounds:
            has_missing_or_nonfinite = True
            for fname in metric_fields:
                setattr(self, fname, None)
            if self.missingness_reason is None:
                self.missingness_reason = "missing or invalid finite window bounds"
            if self.missingness_reason not in self.warnings:
                self.warnings.append(self.missingness_reason)
            if self.run_status == "complete":
                self.run_status = "failed"
        if has_missing_or_nonfinite:
            self.is_valid = False
            if self.topology_status == "computed":
                self.topology_status = "skipped"
            if self.missingness_state == "computed":
                self.missingness_state = "unobserved"
            if self.missingness_reason is None:
                self.missingness_reason = "missing or non-finite topology metric"
            if self.missingness_reason not in self.warnings:
                self.warnings.append(self.missingness_reason)
            if self.run_status == "complete":
                self.run_status = "failed"
            if self.replicate_count == 1:
                self.replicate_count = 0


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


def _has_valid_triangle_counts(n_triangles: object, n_valid_triangles: object) -> bool:
    if isinstance(n_triangles, bool) or isinstance(n_valid_triangles, bool):
        return False
    if not isinstance(n_triangles, int) or not isinstance(n_valid_triangles, int):
        return False
    return n_triangles >= 0 and n_valid_triangles >= 0 and n_valid_triangles <= n_triangles


def _is_eligible_topology_row(row: LevelTRealTopologyRow) -> bool:
    """Return True only for complete, computed, warning-free observed windows.

    Status / missingness metadata is part of the evidence contract: a row that
    still carries finite metric fields but reports ``run_status`` other than
    ``complete``, ``missingness_state`` other than ``computed``, or
    ``replicate_count <= 0`` must not enter cohort or optional-signal reports
    as valid evidence.
    """
    return (
        row.null_method != "fixture_none"
        and row.is_valid is True
        and row.topology_status == "computed"
        and row.missingness_state == "computed"
        and row.run_status == "complete"
        and isinstance(row.replicate_count, int)
        and not isinstance(row.replicate_count, bool)
        and row.replicate_count > 0
        and not row.warnings
        and _has_valid_window_bounds(row.window_start_s, row.window_end_s)
        and _has_valid_triangle_counts(row.n_triangles, row.n_valid_triangles)
        and all(
            _is_finite_metric(getattr(row, field_name))
            for field_name in ("q_net", "q_abs", "f_dress", "defect_density", "topology_quality")
        )
        and float(row.q_abs) >= 0.0
        and float(row.f_dress) >= 0.0
        and float(row.defect_density) >= 0.0
        and 0.0 <= float(row.topology_quality) <= 1.0
    )


def _validate_safe_text(text: str) -> None:
    validate_safe_text(text)


def _h(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)


def _finite_window_bound(value: object) -> float | None:
    if value is None or isinstance(value, bool) or (isinstance(value, str) and not value.strip()):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _is_finite_metric(value: object) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _has_valid_window_bounds(start: object, end: object) -> bool:
    start_s = _finite_window_bound(start)
    end_s = _finite_window_bound(end)
    return start_s is not None and end_s is not None and start_s >= 0 and end_s > start_s


def _normalized_label(value: object) -> object | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


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
    window_start_s = _finite_window_bound(m_row.get("window_start_s"))
    window_end_s = _finite_window_bound(m_row.get("window_end_s"))
    if not _has_valid_window_bounds(window_start_s, window_end_s):
        reason = "synthetic fixture excluded: missing or invalid finite window bounds"
        return LevelTRealTopologyRow(
            row_id=str(m_row.get("row_id")), subject_id=str(m_row.get("subject_id")),
            session_id=m_row.get("session_id") or None, run_id=m_row.get("run_id") or None,
            window_id=str(m_row.get("window_id")), task_label=_normalized_label(m_row.get("task_label")),
            q_net=None, q_abs=None, f_dress=None, defect_density=None,
            n_triangles=0, n_valid_triangles=0, topology_quality=None,
            null_method="fixture_none", null_seed=0, source_file=str(m_row.get("source_file") or ""),
            window_start_s=window_start_s, window_end_s=window_end_s,
            warnings=[reason], topology_status="skipped", missingness_state="unobserved",
            missingness_reason=reason, is_valid=False, run_status="failed", replicate_count=0,
        )
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
        window_start_s=window_start_s,
        window_end_s=window_end_s,
        warnings=[],
    )


def compute_real_topology_for_window(m_row: dict, max_channels: int | None = 16) -> LevelTRealTopologyRow:
    """Compute topology telemetry from samples returned for one window.

    Unlike `compute_fixture_topology_for_window` (which derives numbers from a hash of
    row_id/metadata text, independent of signal content), this requests per-channel
    samples from the configured local reader and computes topology from them via
    `eeg_signal_topology.compute_topology_from_channels` (the same real, signal-derived
    computation already used by the generic multi-dataset Level T pipeline). It does
    not authenticate source provenance or establish empirical/biological validity.

    If the source file or companion files can't be read (missing file, missing companion
    file like BrainVision .vmrk/.eeg, out-of-range window, unsupported format), returns
    an explicit missingness row with is_valid=False and None metric fields instead of
    raising or imputing zero-valued observations.
    """
    from data.bids_ingest import read_window_signal

    row_id = str(m_row.get("row_id"))
    source_file = str(m_row.get("source_file") or "")
    window_start_s = _finite_window_bound(m_row.get("window_start_s"))
    window_end_s = _finite_window_bound(m_row.get("window_end_s"))
    warnings: list[str] = []

    def _missing_row(
        reason: str,
        missingness_state: str = "failed_read",
        run_status: str = "failed",
    ) -> LevelTRealTopologyRow:
        warnings.append(reason)
        return LevelTRealTopologyRow(
            row_id=row_id,
            subject_id=str(m_row.get("subject_id")),
            session_id=m_row.get("session_id") or None,
            run_id=m_row.get("run_id") or None,
            window_id=str(m_row.get("window_id")),
            task_label=m_row.get("task_label") or None,
            q_net=None,
            q_abs=None,
            f_dress=None,
            defect_density=None,
            n_triangles=0,
            n_valid_triangles=0,
            topology_quality=None,
            null_method="real_none",
            null_seed=0,
            source_file=source_file,
            window_start_s=window_start_s,
            window_end_s=window_end_s,
            warnings=warnings,
            topology_status="skipped",
            missingness_state=missingness_state,
            missingness_reason=reason,
            is_valid=False,
            run_status=run_status,
            replicate_count=0,
            uncertainty_metadata={"error": reason, "missingness_state": missingness_state},
        )

    # Alias for backward compatibility
    _zero_row = _missing_row

    if not source_file or not Path(source_file).exists():
        return _missing_row(
            f"source file not found: {source_file!r}; topology skipped",
            missingness_state="missing_source_file",
        )

    if not _has_valid_window_bounds(window_start_s, window_end_s):
        return _missing_row(
            "window bounds are missing, non-finite, or not a positive interval",
            missingness_state="unobserved",
        )

    try:
        channels = read_window_signal(
            source_file, window_start_s, window_end_s, pick="all", max_channels=max_channels
        )
    except (ValueError, OSError) as exc:
        exc_str = str(exc).lower()
        is_partial_run = (
            "out of range" in exc_str
            or "duration" in exc_str
            or "short_window" in exc_str
            or "premature" in exc_str
            or "truncated" in exc_str
        )
        is_companion = (
            not is_partial_run
            and (
                isinstance(exc, FileNotFoundError)
                or "companion" in exc_str
                or "file not found" in exc_str
                or "no such file" in exc_str
                or "cannot find" in exc_str
                or "missing" in exc_str
            )
        )
        if is_partial_run:
            return _missing_row(
                f"partial run or out-of-range window: {exc}",
                missingness_state="partial_run",
                run_status="partial",
            )
        if is_companion:
            return _missing_row(
                f"companion file missing or unreadable: {exc}",
                missingness_state="missing_companion_file",
                run_status="failed",
            )
        return _missing_row(
            f"window signal read failed: {exc}",
            missingness_state="failed_read",
            run_status="failed",
        )

    if channels is None or len(channels) == 0:
        return _missing_row("no channels returned for window", missingness_state="failed_read")

    channel_arr = np.asarray(channels, dtype=float)
    if channel_arr.size == 0:
        return _missing_row("empty channel samples returned for window", missingness_state="failed_read")
    if not np.all(np.isfinite(channel_arr)):
        return _missing_row("non-finite samples in window signal", missingness_state="failed_read")

    channel_data = [list(map(float, ch)) for ch in channels]
    (
        q_net, q_abs, f_dress, defect_density,
        n_triangles, n_valid_triangles, topology_quality,
    ) = compute_topology_from_channels(channel_data)

    return LevelTRealTopologyRow(
        row_id=row_id,
        subject_id=str(m_row.get("subject_id")),
        session_id=m_row.get("session_id") or None,
        run_id=m_row.get("run_id") or None,
        window_id=str(m_row.get("window_id")),
        task_label=m_row.get("task_label") or None,
        q_net=q_net,
        q_abs=q_abs,
        f_dress=f_dress,
        defect_density=defect_density,
        n_triangles=n_triangles,
        n_valid_triangles=n_valid_triangles,
        topology_quality=topology_quality,
        null_method="real_none",
        null_seed=int(_h(row_id) % (2**31 - 1)),
        source_file=source_file,
        window_start_s=window_start_s,
        window_end_s=window_end_s,
        warnings=warnings,
        topology_status="computed",
        missingness_state="computed",
        missingness_reason=None,
        is_valid=True,
        run_status="complete",
        replicate_count=1,
        uncertainty_metadata={"q_net": q_net, "q_abs": q_abs, "quality": topology_quality},
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
    """Signal-reader-derived band-specific Hilbert-phase telemetry for one window.

    Unlike `compute_real_topology_for_window` (a channel-mean/correlation-
    threshold heuristic -- see `eeg_signal_topology.py`'s own docstring; it
    uses no phase or frequency information at all), this bandpass-filters
    reader-returned per-channel samples to `band` (default alpha, 8-13 Hz), extracts
    the analytic (Hilbert) phase via
    `validation.analytic_phase.bandpass_hilbert_phase`, and computes
    Q/Qabs/f_dress from phase-gradient telemetry via
    `validation.analytic_phase.channel_phase_gradient_metrics`. These values
    do not establish a biological mechanism or measurement validity.

    Additive, not a replacement: returns a plain dict (not a
    `LevelTRealTopologyRow`) so it can be reported alongside the existing
    channel-mean-based q_net/q_abs/f_dress without silently changing them.
    Returns `{"status": "skipped", ...}` (not a raised exception) for any
    unreadable/out-of-range/too-few-channels/band-above-Nyquist case, matching
    this module's existing skip-and-report convention.
    """
    row_id = str(m_row.get("row_id"))
    source_file = str(m_row.get("source_file") or "")
    window_start_s = _finite_window_bound(m_row.get("window_start_s"))
    window_end_s = _finite_window_bound(m_row.get("window_end_s"))

    if not _has_valid_window_bounds(window_start_s, window_end_s):
        return {"row_id": row_id, "band": band, "status": "skipped", "reason": "window bounds are missing or invalid"}

    from data.bids_ingest import get_sample_rate, read_window_signal
    from validation.analytic_phase import (
        DEFAULT_EEG_BANDS,
        bandpass_hilbert_phase,
        channel_phase_gradient_metrics,
    )

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

    channel_arr = np.asarray(channels, dtype=float)
    if channel_arr.ndim != 2 or channel_arr.shape[0] < 2:
        return {
            "row_id": row_id, "band": band, "status": "skipped",
            "reason": f"need >=2 channels for phase-gradient metrics, got {channel_arr.shape[0] if channel_arr.ndim >= 1 else 0}",
        }
    if channel_arr.shape[1] == 0 or not np.all(np.isfinite(channel_arr)):
        return {
            "row_id": row_id, "band": band, "status": "skipped",
            "reason": "window contains non-finite or empty signal samples",
        }
    if not _is_finite_metric(sfreq) or float(sfreq) <= 0.0:
        return {
            "row_id": row_id, "band": band, "status": "skipped",
            "reason": f"invalid sample rate sfreq={sfreq!r}",
        }
    sfreq = float(sfreq)

    lo, hi = DEFAULT_EEG_BANDS[band]
    nyq = sfreq / 2.0
    if hi >= nyq:
        return {
            "row_id": row_id, "band": band, "status": "skipped",
            "reason": f"band {band} upper edge {hi} Hz >= Nyquist {nyq} Hz at sfreq={sfreq}",
        }

    try:
        phase = bandpass_hilbert_phase(channel_arr, sfreq, lo, hi)
    except ValueError as exc:
        return {"row_id": row_id, "band": band, "status": "skipped", "reason": f"phase extraction failed: {exc}"}

    metrics = channel_phase_gradient_metrics(phase)
    if not all(_is_finite_metric(metrics.get(k)) for k in ("Q", "Qabs", "phase_grad", "f_dress")):
        return {
            "row_id": row_id, "band": band, "status": "skipped",
            "reason": "non-finite phase-gradient metric computed",
        }
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
    candidate_rows = list(rows)

    if sample_size is not None and len(candidate_rows) > sample_size:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(candidate_rows), size=sample_size, replace=False)
        candidate_rows = [candidate_rows[i] for i in sorted(idx)]

    results = []
    for row in candidate_rows:
        if row.null_method == "fixture_none":
            results.append({"row_id": row.row_id, "band": band, "status": "skipped", "reason": "synthetic fixture row is not signal-derived"})
        elif not _is_eligible_topology_row(row):
            results.append({"row_id": row.row_id, "band": band, "status": "skipped", "reason": "Level T row is invalid or unobserved"})
        elif row.row_id not in by_id:
            results.append({"row_id": row.row_id, "band": band, "status": "skipped", "reason": "matching Level M row is missing"})
        else:
            results.append(compute_phase_based_topology_for_window(by_id[row.row_id], band=band, max_channels=max_channels))
    computed = [x for x in results if x["status"] == "computed"]
    skipped = [x for x in results if x["status"] != "computed"]

    def _mean(key: str) -> float | None:
        vals = [x[key] for x in computed if key in x and np.isfinite(x[key])]
        return float(np.mean(vals)) if vals else None

    return {
        "status": "phase_based_topology_computed" if computed else "not_applicable",
        "reason": None if computed else "no eligible signal windows were processed",
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
    """Connectivity statistics (PLV/PLI/wPLI, optionally Granger prediction)
    for one window, from samples returned by the configured signal reader --
    `analysis/connectivity_topology.py`'s instruments (Phase 0/3 of the
    "beyond topology" pass), applied per-dataset-window here for the first
    time (they previously existed only in the separate ITCT script).

    Additive report function, not wired into `LevelTRealTopologyRow` --
    keeps the existing q_net/q_abs/f_dress columns and the three published
    reports untouched. The output is software telemetry only; it does not
    establish causal influence, biological coupling, or source authenticity.
    """
    row_id = str(m_row.get("row_id"))
    source_file = str(m_row.get("source_file") or "")
    window_start_s = _finite_window_bound(m_row.get("window_start_s"))
    window_end_s = _finite_window_bound(m_row.get("window_end_s"))

    if not _has_valid_window_bounds(window_start_s, window_end_s):
        return {"row_id": row_id, "status": "skipped", "reason": "window bounds are missing or invalid"}

    if not source_file or not Path(source_file).exists():
        return {"row_id": row_id, "status": "skipped", "reason": f"source file not found: {source_file!r}"}

    from data.bids_ingest import read_window_signal
    from analysis.connectivity_topology import (
        compute_granger_causality_matrix,
        compute_pli,
        compute_plv,
        compute_wpli,
    )

    try:
        channels = read_window_signal(
            source_file, window_start_s, window_end_s, pick="all", max_channels=max_channels
        )
    except (ValueError, OSError) as exc:
        # OSError: see compute_real_topology_for_window's docstring -- a
        # multi-file format's companion file can be genuinely missing.
        return {"row_id": row_id, "status": "skipped", "reason": f"window skipped: {exc}"}

    channel_data = np.asarray(channels, dtype=float)
    if channel_data.ndim != 2 or channel_data.shape[0] < 2:
        return {
            "row_id": row_id, "status": "skipped",
            "reason": f"need >=2 channels for connectivity, got {channel_data.shape[0] if channel_data.ndim >= 1 else 0}",
        }
    if channel_data.shape[1] == 0 or not np.all(np.isfinite(channel_data)):
        return {
            "row_id": row_id, "status": "skipped",
            "reason": "window contains non-finite or empty signal samples",
        }

    result: dict = {"row_id": row_id, "status": "computed", "n_channels": int(channel_data.shape[0])}
    method_fns = {"plv": compute_plv, "pli": compute_pli, "wpli": compute_wpli}
    for m in methods:
        fn = method_fns.get(m)
        if fn is None:
            continue
        mat = np.asarray(fn(channel_data), dtype=float)
        off_diag = mat[~np.eye(mat.shape[0], dtype=bool)]
        if not off_diag.size or not np.all(np.isfinite(mat)):
            return {
                "row_id": row_id, "status": "skipped",
                "reason": f"non-finite connectivity matrix computed for {m}",
            }
        result[f"mean_{m}"] = float(np.mean(off_diag))
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
    candidate_rows = list(rows)

    if sample_size is not None and len(candidate_rows) > sample_size:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(candidate_rows), size=sample_size, replace=False)
        candidate_rows = [candidate_rows[i] for i in sorted(idx)]

    results = []
    for row in candidate_rows:
        if row.null_method == "fixture_none":
            results.append({"row_id": row.row_id, "status": "skipped", "reason": "synthetic fixture row is not signal-derived"})
        elif not _is_eligible_topology_row(row):
            results.append({"row_id": row.row_id, "status": "skipped", "reason": "Level T row is invalid or unobserved"})
        elif row.row_id not in by_id:
            results.append({"row_id": row.row_id, "status": "skipped", "reason": "matching Level M row is missing"})
        else:
            results.append(compute_connectivity_for_window(
                by_id[row.row_id], methods=methods, max_channels=max_channels,
                compute_granger=compute_granger, granger_maxlag=granger_maxlag,
            ))
    computed = [x for x in results if x["status"] == "computed"]
    skipped = [x for x in results if x["status"] != "computed"]

    def _mean(key: str) -> float | None:
        vals = [x[key] for x in computed if key in x and np.isfinite(x[key])]
        return float(np.mean(vals)) if vals else None

    summary = {f"mean_{m}": _mean(f"mean_{m}") for m in methods}
    if compute_granger:
        summary["mean_n_significant_granger_pairs"] = _mean("n_significant_granger_pairs")

    return {
        "status": "connectivity_computed" if computed else "not_applicable",
        "reason": None if computed else "no eligible signal windows were processed",
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
    fixture_rows = [r for r in rows if r.null_method == "fixture_none"]
    valid_rows = [r for r in rows if _is_eligible_topology_row(r) and r.topology_quality is not None]
    missing_rows = [
        r for r in rows
        if r.null_method != "fixture_none" and (not _is_eligible_topology_row(r) or r.topology_quality is None)
    ]
    qs = [r.topology_quality for r in valid_rows]
    n_valid = len(valid_rows)
    n_missing = len(missing_rows)
    n_total = len(rows)
    skip_rate = (n_missing / n_total) if n_total > 0 else 0.0

    quality_passed = (
        n_total > 0
        and not fixture_rows
        and n_missing == 0
        and all(r.topology_quality >= 0.25 and r.n_valid_triangles > 0 for r in valid_rows)
    )

    if n_total == 0:
        status = "empty_dataset"
    elif fixture_rows:
        status = "incomplete"
    elif skip_rate > 0.20:
        status = "blocked_high_skip_rate"
    elif n_missing > 0:
        status = "incomplete"
    elif quality_passed:
        status = "pass"
    else:
        status = "failed_quality"

    return {
        "status": status,
        "n_rows": n_total,
        "n_valid_rows": n_valid,
        "n_missing_rows": n_missing,
        "n_synthetic_fixture_rows": len(fixture_rows),
        "synthetic_fixture_row_ids": [r.row_id for r in fixture_rows],
        "skip_rate": round(skip_rate, 4),
        "n_subjects": len({r.subject_id for r in rows}),
        "n_valid_subjects": len({r.subject_id for r in valid_rows}),
        "n_windows": n_total,
        "mean_topology_quality": (sum(qs) / len(qs)) if qs else None,
        "min_topology_quality": min(qs) if qs else None,
        "max_topology_quality": max(qs) if qs else None,
        "low_quality_rows": [r.row_id for r in valid_rows if r.topology_quality < 0.25 or r.n_valid_triangles <= 0],
        "missing_row_ids": [r.row_id for r in missing_rows],
        "n_valid_triangles_total": sum(r.n_valid_triangles for r in valid_rows),
        "n_triangles_total": sum(r.n_triangles for r in valid_rows),
        "quality_passed": quality_passed,
    }


def build_null_placeholder_report(rows: list[LevelTRealTopologyRow]) -> dict:
    return {"status": "placeholder_only", "real_nulls_performed": False, "methods_planned": ["channel_shuffle", "time_reverse", "phase_randomization"], "note": "Null controls are placeholders at Level T extraction; residual benchmark controls run in Issue #54.", "n_rows": len(rows)}


def compute_surrogate_gate_for_window(
    m_row: dict, n_surrogates: int = 50, seed: int = 0, max_channels: int | None = 16,
) -> dict:
    """Compare the returned-sample topology statistic to a phase-randomized null.

    Reads samples from the configured reader, generates `n_surrogates`
    phase-randomized copies via
    `validation.nulls.phase_randomize_time` (preserves each channel's power
    spectrum, destroys cross-channel phase relationships), recomputes q_abs on
    each surrogate, and returns `validation.nulls.compute_null_summary` (a
    z-score of the returned-sample value against the configured surrogate
    distribution) plus row identity. This is not source authentication,
    evidence verification, or scientific validation. Returns a skipped result
    when the source or window cannot be used.
    """
    row_id = str(m_row.get("row_id"))
    source_file = str(m_row.get("source_file") or "")
    window_start_s = _finite_window_bound(m_row.get("window_start_s"))
    window_end_s = _finite_window_bound(m_row.get("window_end_s"))

    if not _has_valid_window_bounds(window_start_s, window_end_s):
        return {"row_id": row_id, "status": "skipped", "reason": "window bounds are missing or invalid"}

    if not source_file or not Path(source_file).exists():
        return {"row_id": row_id, "status": "skipped", "reason": f"source file not found: {source_file!r}"}

    from data.bids_ingest import read_window_signal
    from validation.nulls import compute_null_summary, phase_randomize_time

    try:
        channels = read_window_signal(
            source_file, window_start_s, window_end_s, pick="all", max_channels=max_channels
        )
    except (ValueError, OSError) as exc:
        # OSError: see compute_real_topology_for_window's docstring -- a
        # multi-file format's companion file can be genuinely missing.
        return {"row_id": row_id, "status": "skipped", "reason": f"window skipped: {exc}"}

    arr = np.asarray(channels, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 2:
        return {
            "row_id": row_id, "status": "skipped",
            "reason": f"need >=2 channels for surrogate gate, got {arr.shape[0] if arr.ndim >= 1 else 0}",
        }
    if arr.shape[1] == 0 or not np.all(np.isfinite(arr)):
        return {
            "row_id": row_id, "status": "skipped",
            "reason": "window contains non-finite or empty signal samples",
        }
    channel_data = arr.tolist()
    observed_q_abs = compute_topology_from_channels(channel_data)[1]  # (q_net, q_abs, ...)
    if not _is_finite_metric(observed_q_abs):
        return {
            "row_id": row_id, "status": "skipped",
            "reason": "non-finite observed topology metric for surrogate gate",
        }

    surrogate_q_abs = []
    for i in range(n_surrogates):
        surrogate = phase_randomize_time(arr, seed=seed + i)
        surrogate_q_abs.append(compute_topology_from_channels(surrogate.tolist())[1])

    summary = compute_null_summary(observed_q_abs, surrogate_q_abs)
    if not all(_is_finite_metric(v) for v in summary.values()):
        return {
            "row_id": row_id, "status": "skipped",
            "reason": "non-finite surrogate null summary",
        }
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
    candidate_rows = list(rows)

    if sample_size is not None and len(candidate_rows) > sample_size:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(candidate_rows), size=sample_size, replace=False)
        candidate_rows = [candidate_rows[i] for i in sorted(idx)]

    gate_results = []
    for row in candidate_rows:
        if row.null_method == "fixture_none":
            gate_results.append({"row_id": row.row_id, "status": "skipped", "reason": "synthetic fixture row is not signal-derived"})
        elif not _is_eligible_topology_row(row):
            gate_results.append({"row_id": row.row_id, "status": "skipped", "reason": "Level T row is invalid or unobserved"})
        elif row.row_id not in by_id:
            gate_results.append({"row_id": row.row_id, "status": "skipped", "reason": "matching Level M row is missing"})
        else:
            gate_results.append(compute_surrogate_gate_for_window(
                by_id[row.row_id], n_surrogates=n_surrogates, seed=seed, max_channels=max_channels
            ))
    gated = [g for g in gate_results if g["status"] == "gated"]
    skipped = [g for g in gate_results if g["status"] == "skipped"]
    z_values = [g["z"] for g in gated if g["z"] == g["z"]]  # filter nan

    return {
        "status": "real_nulls_performed" if gated else "not_applicable",
        "real_nulls_performed": bool(gated),
        "reason": None if gated else "no eligible signal windows were gated",
        "method": "phase_randomize_time",
        "n_surrogates_per_window": n_surrogates,
        "n_windows_gated": len(gated),
        "n_windows_skipped": len(skipped),
        "n_windows_total_candidates": len(rows),
        "mean_abs_z": float(np.mean(np.abs(z_values))) if z_values else None,
        "n_passed_z_ge_2": sum(1 for z in z_values if abs(z) >= 2.0),
        "seed": seed,
        "sample_size": sample_size,
        "gate_results": gate_results,
    }


def build_group_significance_report(
    rows: list[LevelTRealTopologyRow], m_rows: list[dict],
    group_col: str = "state_label", value_cols: tuple[str, ...] = ("q_net", "q_abs", "f_dress", "defect_density"),
    n_permutations: int = 2000, seed: int = 0,
    min_paired_subjects: int | None = None,
    max_skip_rate: float | None = None,
) -> dict:
    """Test whether a Level M grouping column (default `state_label`) predicts
    each Level T topology metric, using both the window-pooled and
    subject-blocked permutation tests from `analysis.permutation`.

    Joins Level T rows back to Level M rows by row_id (Level T rows do not
    themselves carry the semantic group label, only `task_label`). Reports
    `"not_applicable"` with a reason if `group_col` is absent from the joined
    data or doesn't have exactly 2 distinct non-null values.

    Fails closed: excludes invalid or unobserved rows from permutation tests
    and blocks if overall window skip rate exceeds `max_skip_rate` or paired
    subject count falls below `min_paired_subjects`. Synthetic fixture rows
    are not eligible measurements. Ineligible grouping metadata prevents a
    partial join from being analyzed.
    """
    if max_skip_rate is not None:
        try:
            max_skip_rate = float(max_skip_rate)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("max_skip_rate must be finite and between 0 and 1") from exc
        if not math.isfinite(max_skip_rate) or not 0.0 <= max_skip_rate <= 1.0:
            raise ValueError("max_skip_rate must be finite and between 0 and 1")
    if min_paired_subjects is not None and min_paired_subjects < 0:
        raise ValueError("min_paired_subjects must be non-negative")

    eligible_rows = [
        r for r in rows
        if _is_eligible_topology_row(r)
    ]
    skip_rate = (len(rows) - len(eligible_rows)) / len(rows) if rows else 1.0

    if max_skip_rate is not None and skip_rate > max_skip_rate:
        return {
            "status": "blocked_high_skip_rate",
            "reason": f"skip rate {skip_rate:.2%} exceeds maximum threshold {max_skip_rate:.2%}",
            "skip_rate": round(skip_rate, 4),
            "max_skip_rate": max_skip_rate,
            "n_rows_total": len(rows),
            "n_rows_eligible": len(eligible_rows),
            "group_col": group_col,
        }

    if not eligible_rows:
        return {
            "status": "not_applicable",
            "reason": "no valid computed Level T rows available",
            "group_col": group_col,
            "n_rows_total": len(rows),
            "n_rows_eligible": 0,
            "n_rows_excluded": len(rows),
        }

    m_grouped: dict[str, list[dict]] = {}
    for m in m_rows:
        m_grouped.setdefault(str(m.get("row_id")), []).append(m)
    joined = []
    missing_group_metadata = 0
    contradictory_metadata = 0
    for r in eligible_rows:
        matches = m_grouped.get(r.row_id, [])
        if not matches:
            missing_group_metadata += 1
            continue
        group_vals = {_normalized_label(m.get(group_col)) for m in matches if _normalized_label(m.get(group_col)) is not None}
        if len(matches) > 1 and len(group_vals) != 1:
            contradictory_metadata += 1
            continue
        m_sub_ids = {_normalized_label(m.get("subject_id")) for m in matches if _normalized_label(m.get("subject_id")) is not None}
        if len(m_sub_ids) > 1 or (m_sub_ids and str(next(iter(m_sub_ids))) != str(r.subject_id)):
            contradictory_metadata += 1
            continue
        m_task_labels = {_normalized_label(m.get("task_label")) for m in matches if _normalized_label(m.get("task_label")) is not None}
        t_task = _normalized_label(r.task_label)
        if len(m_task_labels) > 1 or (t_task is not None and m_task_labels and str(next(iter(m_task_labels))) != str(t_task)):
            contradictory_metadata += 1
            continue
        if group_col == "task_label" and t_task is not None and group_vals and str(next(iter(group_vals))) != str(t_task):
            contradictory_metadata += 1
            continue
        group_val = next(iter(group_vals)) if group_vals else None
        if group_val is None:
            missing_group_metadata += 1
            continue
        row_vals = {}
        for c in value_cols:
            val = getattr(r, c, None)
            if val is not None:
                row_vals[c] = val
        joined.append({"subject_id": r.subject_id, "group": group_val, **row_vals})

    if contradictory_metadata:
        return {
            "status": "not_applicable",
            "reason": (
                f"{contradictory_metadata} eligible Level T rows have contradictory joined {group_col!r} "
                "or subject/task metadata; report not computed"
            ),
            "group_col": group_col,
            "n_rows_total": len(rows),
            "n_rows_eligible": len(eligible_rows),
            "n_rows_excluded": len(rows) - len(eligible_rows),
            "n_rows_contradictory_metadata": contradictory_metadata,
            "n_rows_used": 0,
        }

    if missing_group_metadata:
        return {
            "status": "not_applicable",
            "reason": (
                f"{missing_group_metadata} eligible Level T rows lack joined {group_col!r} "
                "group metadata; report not computed"
            ),
            "group_col": group_col,
            "n_rows_total": len(rows),
            "n_rows_eligible": len(eligible_rows),
            "n_rows_excluded": len(rows) - len(eligible_rows),
            "n_rows_missing_group_metadata": missing_group_metadata,
            "n_rows_used": 0,
        }

    if not joined:
        return {
            "status": "not_applicable",
            "reason": f"no eligible rows with a non-null {group_col!r} value",
            "group_col": group_col,
            "n_rows_total": len(rows),
            "n_rows_eligible": len(eligible_rows),
            "n_rows_excluded": len(rows) - len(eligible_rows),
        }

    groups = sorted({r["group"] for r in joined}, key=str)
    if len(groups) != 2:
        return {
            "status": "not_applicable",
            "reason": f"{group_col!r} has {len(groups)} distinct values ({groups}), this report only covers 2-group comparisons",
            "group_col": group_col,
        }

    subjects_g0 = {r["subject_id"] for r in joined if r["group"] == groups[0] and r.get("subject_id") is not None}
    subjects_g1 = {r["subject_id"] for r in joined if r["group"] == groups[1] and r.get("subject_id") is not None}
    paired_subjects = subjects_g0.intersection(subjects_g1)

    if min_paired_subjects is not None and len(paired_subjects) < min_paired_subjects:
        return {
            "status": "insufficient_power",
            "reason": f"paired subject count {len(paired_subjects)} < minimum required {min_paired_subjects}",
            "n_paired_subjects": len(paired_subjects),
            "min_paired_subjects": min_paired_subjects,
            "group_col": group_col,
        }

    try:
        import pandas as pd
        from analysis.permutation import permutation_test, subject_blocked_permutation_test
    except ImportError as exc:
        return {
            "status": "dependency_missing",
            "reason": f"pandas and analysis.permutation required for permutation testing: {exc}",
            "group_col": group_col,
            "n_paired_subjects": len(paired_subjects),
        }

    df = pd.DataFrame(joined)

    metric_results = {}
    for value_col in value_cols:
        if value_col not in df.columns:
            metric_results[value_col] = {"status": "not_found"}
            continue
        sub = df[["subject_id", "group", value_col]].dropna()
        a = sub.loc[sub["group"] == groups[0], value_col].to_numpy(dtype=float)
        b = sub.loc[sub["group"] == groups[1], value_col].to_numpy(dtype=float)
        if len(a) < 2 or len(b) < 2:
            metric_results[value_col] = {"status": "insufficient_data"}
            continue
        pooled = permutation_test(a, b, n_permutations=n_permutations, seed=seed)
        blocked = subject_blocked_permutation_test(sub.rename(columns={value_col: "value"}), "value", "group", "subject_id", n_permutations=n_permutations, seed=seed)

        mean_a, mean_b = float(np.mean(a)), float(np.mean(b))
        std_a = float(np.std(a, ddof=1)) if len(a) > 1 else 0.0
        std_b = float(np.std(b, ddof=1)) if len(b) > 1 else 0.0
        sem_a = float(std_a / np.sqrt(len(a))) if len(a) > 0 else 0.0
        sem_b = float(std_b / np.sqrt(len(b))) if len(b) > 0 else 0.0
        ci_95_a = [round(mean_a - 1.96 * sem_a, 6), round(mean_a + 1.96 * sem_a, 6)]
        ci_95_b = [round(mean_b - 1.96 * sem_b, 6), round(mean_b + 1.96 * sem_b, 6)]

        metric_results[value_col] = {
            "window_pooled": pooled.to_dict(),
            "subject_blocked": blocked.to_dict(),
            "group_a": str(groups[0]),
            "group_b": str(groups[1]),
            "mean_a": round(mean_a, 6),
            "mean_b": round(mean_b, 6),
            "sem_a": round(sem_a, 6),
            "sem_b": round(sem_b, 6),
            "ci_95_a": ci_95_a,
            "ci_95_b": ci_95_b,
            "diff_means": round(mean_b - mean_a, 6),
            "n_obs_a": len(a),
            "n_obs_b": len(b),
        }

    return {
        "status": "computed",
        "group_col": group_col,
        "groups": [str(g) for g in groups],
        "n_permutations": n_permutations,
        "seed": seed,
        "n_rows_total": len(rows),
        "n_rows_eligible": len(eligible_rows),
        "n_rows_excluded": len(rows) - len(eligible_rows),
        "n_rows_used": len(joined),
        "skip_rate": round(skip_rate, 4),
        "n_paired_subjects": len(paired_subjects),
        "metrics": metric_results,
    }


def build_ml_decoding_report(
    rows: list[LevelTRealTopologyRow], m_rows: list[dict],
    group_col: str = "state_label",
    value_cols: tuple[str, ...] = ("q_net", "q_abs", "f_dress", "defect_density", "topology_quality"),
    extra_feature_reports: list[dict] | None = None,
    n_permutations: int = 1000, cv_folds: int = 5, seed: int = 0,
) -> dict:
    """Summarize a configured classifier evaluation of supplied group labels.

    This is a software evaluation of label separability, not a measurement- or
    biological-validity test. It is additive to the per-metric group report.

    Same 2-group-only, row_id-join convention as `build_group_significance_report`
    (see its docstring). `value_cols` defaults to this row's own computed topology
    columns (always available, no extra compute); `extra_feature_reports`
    optionally accepts additional per-window `results` lists from other
    reports in this pass (e.g. `connectivity_report["results"]`,
    `phase_based_topology_report["results"]`, `real_level_m_features_report["results"]`
    keyed by `row_id`) to widen the feature set to the configured feature set
    the repo-hardening plan's Phase 6 describes, without this function
    re-running any of that (compute-heavy) work itself.
    """
    # Invalid, missing, and synthetic fixture rows are not observations for
    # this report. Keeping the filter explicit prevents fixture values from
    # entering a classifier as if they were signal-derived measurements.
    eligible_rows = [
        r for r in rows
        if (
            _is_eligible_topology_row(r)
            and r.n_triangles > 0
            and r.n_valid_triangles > 0
            and all(
                getattr(r, c, None) is not None and math.isfinite(float(getattr(r, c)))
                for c in value_cols
            )
        )
    ]
    if not eligible_rows:
        return {
            "status": "not_applicable",
            "reason": "no signal-derived, non-degenerate topology rows available",
            "n_rows_total": len(rows),
            "n_rows_excluded": len(rows),
        }

    m_grouped: dict[str, list[dict]] = {}
    for m in m_rows:
        m_grouped.setdefault(str(m.get("row_id")), []).append(m)
    extra_by_row: dict[str, dict] = {}
    for report_results in extra_feature_reports or []:
        for entry in report_results:
            if not isinstance(entry, dict):
                continue
            if entry.get("status") not in (None, "computed", "gated"):
                continue
            row_id = str(entry.get("row_id", ""))
            if not row_id:
                continue
            extra_by_row.setdefault(row_id, {}).update(
                {
                    k: float(v)
                    for k, v in entry.items()
                    if _is_finite_metric(v) and k not in ("status",)
                }
            )

    feature_dicts: list[dict] = []
    labels: list = []
    missing_group_metadata = 0
    contradictory_metadata = 0
    for r in eligible_rows:
        matches = m_grouped.get(r.row_id, [])
        if not matches:
            missing_group_metadata += 1
            continue
        group_vals = {_normalized_label(m.get(group_col)) for m in matches if _normalized_label(m.get(group_col)) is not None}
        if len(matches) > 1 and len(group_vals) != 1:
            contradictory_metadata += 1
            continue
        m_sub_ids = {_normalized_label(m.get("subject_id")) for m in matches if _normalized_label(m.get("subject_id")) is not None}
        if len(m_sub_ids) > 1 or (m_sub_ids and str(next(iter(m_sub_ids))) != str(r.subject_id)):
            contradictory_metadata += 1
            continue
        m_task_labels = {_normalized_label(m.get("task_label")) for m in matches if _normalized_label(m.get("task_label")) is not None}
        t_task = _normalized_label(r.task_label)
        if len(m_task_labels) > 1 or (t_task is not None and m_task_labels and str(next(iter(m_task_labels))) != str(t_task)):
            contradictory_metadata += 1
            continue
        if group_col == "task_label" and t_task is not None and group_vals and str(next(iter(group_vals))) != str(t_task):
            contradictory_metadata += 1
            continue
        group_val = next(iter(group_vals)) if group_vals else None
        if group_val is None:
            missing_group_metadata += 1
            continue
        feats = {c: getattr(r, c) for c in value_cols}
        feats.update(extra_by_row.get(r.row_id, {}))
        feature_dicts.append(feats)
        labels.append(group_val)

    if contradictory_metadata:
        return {
            "status": "not_applicable",
            "reason": (
                f"{contradictory_metadata} eligible Level T rows have contradictory joined {group_col!r} "
                "or subject/task metadata; report not computed"
            ),
            "group_col": group_col,
            "n_rows_total": len(rows),
            "n_rows_eligible": len(eligible_rows),
            "n_rows_excluded": len(rows) - len(eligible_rows),
            "n_rows_contradictory_metadata": contradictory_metadata,
            "n_rows_used": 0,
        }

    if missing_group_metadata:
        return {
            "status": "not_applicable",
            "reason": (
                f"{missing_group_metadata} eligible Level T rows lack joined {group_col!r} "
                "group metadata; report not computed"
            ),
            "group_col": group_col,
            "n_rows_total": len(rows),
            "n_rows_eligible": len(eligible_rows),
            "n_rows_excluded": len(rows) - len(eligible_rows),
            "n_rows_missing_group_metadata": missing_group_metadata,
            "n_rows_used": 0,
        }

    if not feature_dicts:
        return {
            "status": "not_applicable",
            "reason": f"no rows with a non-null {group_col!r} value",
            "group_col": group_col,
            "n_rows_total": len(rows),
            "n_rows_eligible": len(eligible_rows),
            "n_rows_excluded": len(rows) - len(eligible_rows),
        }

    groups = sorted({str(g) for g in labels})
    if len(groups) != 2:
        return {
            "status": "not_applicable",
            "reason": f"{group_col!r} has {len(groups)} distinct values ({groups}), this report only covers 2-group comparisons",
            "group_col": group_col,
        }

    from analysis.ml_decoding import build_decoding_report

    report = build_decoding_report(
        feature_dicts, labels, seed=seed, n_permutations=n_permutations, cv_folds=cv_folds,
    )
    report["group_col"] = group_col
    report["n_rows_total"] = len(rows)
    report["n_rows_eligible"] = len(eligible_rows)
    report["n_rows_excluded"] = len(rows) - len(eligible_rows)
    report["n_rows_used"] = len(feature_dicts)
    return report


def build_artifact_alignment_report(rows: list[LevelTRealTopologyRow], m_rows: list[dict]) -> dict:
    by_id = {str(r.get("row_id")): r for r in m_rows}
    art: list[float] = []
    high_artifact_rows: list[str] = []
    missing = 0
    for r in rows:
        v = by_id.get(r.row_id, {}).get("artifact_score")
        if v in (None, ""):
            missing += 1
        else:
            try:
                fv = float(v)
            except (ValueError, TypeError):
                missing += 1
            else:
                if not math.isfinite(fv):
                    missing += 1
                else:
                    art.append(fv)
                    if fv > 0.5:
                        high_artifact_rows.append(r.row_id)
    fixture_rows = [r for r in rows if r.null_method == "fixture_none"]
    valid_qualities = [
        r.topology_quality for r in rows
        if _is_eligible_topology_row(r) and r.topology_quality is not None
    ]
    return {
        "n_rows": len(rows),
        "n_matched_m_rows": sum(1 for r in rows if r.row_id in by_id),
        "n_missing_artifact_scores": missing,
        "mean_artifact_score": (sum(art) / len(art)) if art else None,
        "high_artifact_rows": high_artifact_rows,
        "topology_quality_mean": (sum(valid_qualities) / len(valid_qualities)) if valid_qualities else None,
        "low_topology_quality_rows": [
            r.row_id for r in rows
            if _is_eligible_topology_row(r) and r.topology_quality is not None and r.topology_quality < 0.25
        ],
        "missing_topology_rows": [
            r.row_id for r in rows
            if r.null_method != "fixture_none" and (not _is_eligible_topology_row(r) or r.topology_quality is None)
        ],
        "n_synthetic_fixture_topology_rows": len(fixture_rows),
        "synthetic_fixture_topology_rows": [r.row_id for r in fixture_rows],
        "artifact_alignment_warning": "artifact scores partially missing" if missing else "none",
        "artifact_dominance_proxy": ((sum(art) / len(art)) > 0.5) if art else False,
    }


def audit_cohort_missingness(
    t_rows: list[LevelTRealTopologyRow],
    m_rows: list[dict],
    group_col: str = "task_label",
    min_paired_subjects: int = 5,
    max_skip_rate: float = 0.20,
    min_windows_per_subject: int = 1,
    expected_subjects: list[str] | None = None,
) -> dict:
    """Audit cohort missingness, pairing integrity, and run completeness.

    Fails closed:
    - Overall window skip rate > max_skip_rate -> 'BLOCKED'
    - Paired subject count < min_paired_subjects in a 2-condition cohort -> 'INSUFFICIENT_POWER'
    - Missing companion files, missing windows, or incomplete cohorts -> 'INCOMPLETE'
    - Empty dataset -> 'EMPTY_DATASET'

    Passes only when all included windows are observed and valid, required
    condition labels are present, and the observed cohort is complete. When
    exactly two conditions are present, subjects must be paired. Explicit
    hash-based fixture rows are never eligible for this cohort gate; they are
    reported separately and prevent a PASS verdict.
    """
    try:
        max_skip_rate = float(max_skip_rate)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("max_skip_rate must be finite and between 0 and 1") from exc
    if not math.isfinite(max_skip_rate) or not 0.0 <= max_skip_rate <= 1.0:
        raise ValueError("max_skip_rate must be finite and between 0 and 1")
    if min_paired_subjects < 0 or min_windows_per_subject < 1:
        raise ValueError("minimum subject/window counts must be non-negative and positive, respectively")

    total_t_rows = len(t_rows)
    fixture_t_rows = [r for r in t_rows if r.null_method == "fixture_none"]
    valid_t_rows = [
        r for r in t_rows
        if _is_eligible_topology_row(r) and r.q_abs is not None
    ]
    missing_t_rows = [
        r for r in t_rows
        if r.null_method != "fixture_none" and (not _is_eligible_topology_row(r) or r.q_abs is None)
    ]

    n_valid = len(valid_t_rows)
    n_missing = len(missing_t_rows)
    skip_rate = (n_missing / total_t_rows) if total_t_rows > 0 else 1.0

    missingness_by_reason: dict[str, int] = {}
    missing_records: list[dict] = []
    for r in missing_t_rows:
        reason_key = r.missingness_state or "unobserved"
        if reason_key == "computed":
            reason_key = "unobserved"
        missingness_by_reason[reason_key] = missingness_by_reason.get(reason_key, 0) + 1
        missing_records.append({
            "row_id": r.row_id,
            "subject_id": r.subject_id,
            "session_id": r.session_id,
            "run_id": r.run_id,
            "missingness_state": reason_key,
            "missingness_reason": r.missingness_reason or "row failed eligibility checks",
        })
    if fixture_t_rows:
        missingness_by_reason["synthetic_fixture"] = len(fixture_t_rows)
        for r in fixture_t_rows:
            missing_records.append({
                "row_id": r.row_id,
                "subject_id": r.subject_id,
                "session_id": r.session_id,
                "run_id": r.run_id,
                "missingness_state": "unobserved",
                "missingness_reason": "hash-based fixture output is not an observed signal window",
            })

    all_subject_ids = sorted({r.subject_id for r in t_rows})
    subject_details: dict[str, dict] = {}
    complete_subjects = []
    partial_subjects = []
    failed_subjects = []

    m_grouped: dict[str, list[dict]] = {}
    for m in m_rows:
        m_grouped.setdefault(str(m.get("row_id")), []).append(m)

    def _resolve_cohort_condition(r: LevelTRealTopologyRow) -> tuple[str | None, bool]:
        matches = m_grouped.get(r.row_id, [])
        t_cond = _normalized_label(r.task_label) if group_col == "task_label" else None
        if not matches:
            return (str(t_cond) if t_cond is not None else None), False
        m_sub_ids = {_normalized_label(m.get("subject_id")) for m in matches if _normalized_label(m.get("subject_id")) is not None}
        if len(m_sub_ids) > 1 or (m_sub_ids and str(next(iter(m_sub_ids))) != str(r.subject_id)):
            return None, True
        m_task_labels = {_normalized_label(m.get("task_label")) for m in matches if _normalized_label(m.get("task_label")) is not None}
        t_task = _normalized_label(r.task_label)
        if len(m_task_labels) > 1 or (t_task is not None and m_task_labels and str(next(iter(m_task_labels))) != str(t_task)):
            return None, True
        m_group_vals = {_normalized_label(m.get(group_col)) for m in matches if _normalized_label(m.get(group_col)) is not None}
        if len(matches) > 1 and len(m_group_vals) != 1:
            return None, True
        m_cond = next(iter(m_group_vals)) if m_group_vals else None
        if group_col == "task_label":
            if t_cond is not None and m_cond is not None and str(t_cond) != str(m_cond):
                return None, True
            resolved = t_cond if t_cond is not None else m_cond
            return (str(resolved) if resolved is not None else None), False
        return (str(m_cond) if m_cond is not None else None), False

    for sub_id in all_subject_ids:
        sub_rows = [r for r in t_rows if r.subject_id == sub_id]
        sub_valid = [
            r for r in sub_rows
            if _is_eligible_topology_row(r) and r.q_abs is not None
        ]
        sub_fixture = [r for r in sub_rows if r.null_method == "fixture_none"]
        sub_missing = [
            r for r in sub_rows
            if r.null_method != "fixture_none" and (not _is_eligible_topology_row(r) or r.q_abs is None)
        ]

        sub_conditions = set()
        for r in sub_valid:
            c, is_contradictory = _resolve_cohort_condition(r)
            if c and not is_contradictory:
                sub_conditions.add(str(c))

        n_sub_total = len(sub_rows)
        n_sub_valid = len(sub_valid)
        sub_skip = ((len(sub_missing) + len(sub_fixture)) / n_sub_total) if n_sub_total > 0 else 1.0

        if n_sub_valid == n_sub_total and n_sub_valid >= min_windows_per_subject:
            status = "complete"
            complete_subjects.append(sub_id)
        elif n_sub_valid > 0:
            status = "partial"
            partial_subjects.append(sub_id)
        else:
            status = "failed"
            failed_subjects.append(sub_id)

        subject_details[sub_id] = {
            "status": status,
            "n_total_windows": n_sub_total,
            "n_valid_windows": n_sub_valid,
            "n_missing_windows": len(sub_missing),
            "n_synthetic_fixture_windows": len(sub_fixture),
            "skip_rate": round(sub_skip, 4),
            "conditions": sorted(list(sub_conditions)),
        }

    joined_valid = []
    unlabeled_valid_rows = []
    contradictory_label_rows = []
    for r in valid_t_rows:
        cond, is_contradictory = _resolve_cohort_condition(r)
        if is_contradictory:
            contradictory_label_rows.append(r)
        elif cond is None:
            unlabeled_valid_rows.append(r)
        else:
            joined_valid.append({"subject_id": r.subject_id, "condition": str(cond)})

    unique_conditions = sorted({item["condition"] for item in joined_valid})
    paired_subjects: list[str] = []
    unpaired_subjects: list[str] = []

    if len(unique_conditions) == 2:
        c0, c1 = unique_conditions[0], unique_conditions[1]
        subs_c0 = {item["subject_id"] for item in joined_valid if item["condition"] == c0}
        subs_c1 = {item["subject_id"] for item in joined_valid if item["condition"] == c1}
        paired_set = subs_c0.intersection(subs_c1)
        paired_subjects = sorted(list(paired_set))
        unpaired_subjects = sorted(list(set(all_subject_ids) - paired_set))
    elif len(unique_conditions) == 1:
        paired_subjects = complete_subjects
        unpaired_subjects = sorted(list(set(all_subject_ids) - set(complete_subjects)))
    else:
        paired_subjects = []
        unpaired_subjects = sorted(all_subject_ids)

    missing_expected_subjects = []
    if expected_subjects:
        missing_expected_subjects = sorted([s for s in expected_subjects if s not in all_subject_ids])

    if total_t_rows == 0:
        verdict = "EMPTY_DATASET"
        gate_passed = False
        verdict_reason = "No Level T rows provided."
    elif skip_rate > max_skip_rate:
        verdict = "BLOCKED"
        gate_passed = False
        verdict_reason = f"Window skip rate {skip_rate:.2%} exceeds maximum threshold {max_skip_rate:.2%}."
    elif fixture_t_rows or unlabeled_valid_rows or contradictory_label_rows:
        verdict = "INCOMPLETE"
        gate_passed = False
        reasons = []
        if fixture_t_rows:
            reasons.append(f"{len(fixture_t_rows)} synthetic fixture windows are not observed signal windows")
        if unlabeled_valid_rows:
            reasons.append(f"{len(unlabeled_valid_rows)} valid windows are missing condition labels")
        if contradictory_label_rows:
            reasons.append(f"{len(contradictory_label_rows)} valid windows have contradictory condition or subject metadata")
        if n_missing:
            reasons.append(f"{n_missing} windows are missing or invalid")
        if partial_subjects:
            reasons.append(f"{len(partial_subjects)} subjects are partial")
        if unpaired_subjects:
            reasons.append(f"{len(unpaired_subjects)} subjects are unpaired")
        if missing_expected_subjects:
            reasons.append(f"{len(missing_expected_subjects)} expected subjects are absent")
        verdict_reason = "Cohort incomplete: " + "; ".join(reasons) + "."
    elif len(unique_conditions) == 2 and len(paired_subjects) < min_paired_subjects:
        verdict = "INSUFFICIENT_POWER"
        gate_passed = False
        verdict_reason = f"Paired subject count ({len(paired_subjects)}) below minimum power requirement ({min_paired_subjects})."
    elif n_missing > 0 or len(unpaired_subjects) > 0 or len(missing_expected_subjects) > 0 or len(partial_subjects) > 0:
        verdict = "INCOMPLETE"
        gate_passed = False
        verdict_reason = (
            f"Cohort incomplete: {n_missing} missing windows, {len(partial_subjects)} partial subjects, "
            f"{len(unpaired_subjects)} unpaired subjects, {len(missing_expected_subjects)} missing expected subjects."
        )
    else:
        verdict = "PASS"
        gate_passed = True
        verdict_reason = "All cohort subjects, companion files, conditions, and windows complete and valid."

    return {
        "verdict": verdict,
        "gate_passed": gate_passed,
        "verdict_reason": verdict_reason,
        "n_total_windows": total_t_rows,
        "n_valid_windows": n_valid,
        "n_missing_windows": n_missing,
        "n_synthetic_fixture_windows": len(fixture_t_rows),
        "n_unlabeled_valid_windows": len(unlabeled_valid_rows),
        "n_contradictory_label_windows": len(contradictory_label_rows),
        "skip_rate": round(skip_rate, 4),
        "max_skip_rate": max_skip_rate,
        "missingness_by_reason": missingness_by_reason,
        "missing_records": missing_records,
        "n_total_subjects": len(all_subject_ids),
        "n_complete_subjects": len(complete_subjects),
        "n_partial_subjects": len(partial_subjects),
        "n_failed_subjects": len(failed_subjects),
        "complete_subjects": complete_subjects,
        "partial_subjects": partial_subjects,
        "failed_subjects": failed_subjects,
        "conditions_detected": unique_conditions,
        "n_paired_subjects": len(paired_subjects),
        "paired_subjects": paired_subjects,
        "unpaired_subjects": unpaired_subjects,
        "min_paired_subjects": min_paired_subjects,
        "missing_expected_subjects": missing_expected_subjects,
        "subject_details": subject_details,
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
    cohort_missingness_report: dict | None = None,
) -> dict[str, str]:
    """`null_gate_report`/`group_significance_report`/`phase_based_topology_report`/
    `connectivity_report`/`spatial_topology_report`/`microstate_report`/
    `ml_decoding_report`/`cohort_missingness_report` are optional (default None,
    writing nothing extra) so existing callers that don't pass them keep getting
    exactly the same output files as before.
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
    if cohort_missingness_report is not None:
        paths["cohort_missingness_report.json"] = base / "cohort_missingness_report.json"

    with paths["features_t.csv"].open("w", encoding="utf-8", newline="") as f:
        writer = None
        for r in rows:
            d = asdict(r)
            if writer is None:
                writer = csv.DictWriter(f, fieldnames=list(d.keys()))
                writer.writeheader()
            row_dict = {}
            for k, v in d.items():
                if v is None:
                    row_dict[k] = ""
                elif isinstance(v, (dict, list)):
                    row_dict[k] = json.dumps(v)
                else:
                    row_dict[k] = v
            writer.writerow(row_dict)

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
    if cohort_missingness_report is not None:
        paths["cohort_missingness_report.json"].write_text(
            json.dumps(cohort_missingness_report, indent=2, allow_nan=False), encoding="utf-8"
        )

    report_lines = [
        f"# {dataset_id.upper()} Local Signal-Reader Level T Topology Extraction",
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
        report_lines += ["## Null gate report (phase-randomization surrogate comparison)", f"- {null_gate_report}"]
    if group_significance_report is not None:
        report_lines += ["## Group comparison report (permutation tests)", f"- {group_significance_report}"]
    if phase_based_topology_report is not None:
        report_lines += ["## Phase-based topology report (Hilbert-phase metrics from returned samples)", f"- {phase_based_topology_report}"]
    if connectivity_report is not None:
        report_lines += ["## Connectivity report (PLV/PLI/wPLI, optional Granger prediction statistic)", f"- {connectivity_report}"]
    if spatial_topology_report is not None:
        report_lines += ["## Optional spatial-topology output", f"- {spatial_topology_report}"]
    if microstate_report is not None:
        report_lines += ["## Optional microstate output", f"- {microstate_report}"]
    if ml_decoding_report is not None:
        report_lines += ["## ML group-decoding output (configured classifier evaluation)", f"- {ml_decoding_report}"]
    if cohort_missingness_report is not None:
        report_lines += [
            "## Cohort missingness audit report",
            f"- verdict: {cohort_missingness_report.get('verdict')}",
            f"- gate_passed: {cohort_missingness_report.get('gate_passed')}",
            f"- skip_rate: {cohort_missingness_report.get('skip_rate')}",
            f"- n_valid_windows: {cohort_missingness_report.get('n_valid_windows')}",
            f"- n_missing_windows: {cohort_missingness_report.get('n_missing_windows')}",
            f"- n_paired_subjects: {cohort_missingness_report.get('n_paired_subjects')}",
            f"- reason: {cohort_missingness_report.get('verdict_reason')}",
        ]
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
