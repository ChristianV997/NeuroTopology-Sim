"""DS005620 Level T signal topology extraction scaffold.

Consumes P8.2 signal-block window inventory and emits operational topology
telemetry candidates for future M+T signal residual testing.

Does NOT:
- download data
- add hard dependencies (stdlib-only)
- extract Level M features
- run residual promotion
- implement Level O/C/Q
- claim EEG/topology/Q/Q_abs/f_dress/BTC/ICFT proves consciousness, self,
  soul, liberation, afterlife, enlightenment, ultimate reality, or ontology
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

from sciencer_d.btc_icft.io.eeg_signal_blocks import parse_fixture_signal_file


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
    "Readable local EEG-like signal windows were mapped into operational "
    "Level T topology telemetry candidates for future residual testing."
)

_REQUIRED_WINDOW_COLUMNS = {
    "file_path",
    "row_id",
    "window_id",
    "window_start_s",
    "window_end_s",
    "sample_start",
    "sample_end",
    "n_channels",
    "n_samples",
    "sample_rate_hz",
    "status",
}

_SIMILARITY_THRESHOLD = 0.1


def _validate_safe_text(text: str) -> None:
    """Raise ValueError if text contains any banned phrase."""
    lower = text.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            raise ValueError(f"Banned phrase detected: {phrase!r}")


@dataclass
class EEGLevelTSignalTopologyRow:
    """Topology telemetry for a single signal window."""
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
    q_net: float
    q_abs: float
    f_dress: float
    defect_density: float
    n_triangles: int
    n_valid_triangles: int
    topology_quality: float
    topology_status: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class EEGLevelTSignalTopologyResult:
    """Aggregate Level T signal topology extraction result."""
    dataset_id: str
    n_windows: int
    n_topology_rows: int
    n_skipped_windows: int
    topology_rows: list[dict] = field(default_factory=list)
    skipped_windows: list[dict] = field(default_factory=list)
    topology_quality_report: dict = field(default_factory=dict)
    artifact_report: dict = field(default_factory=dict)
    omega_event: dict = field(default_factory=dict)
    safe_claim: str = _SAFE_CLAIM
    forbidden_claims: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_signal_window_inventory(signal_blocks_dir: str) -> list[dict]:
    """Load window_inventory.csv from a signal blocks output directory.

    Args:
        signal_blocks_dir: Path to directory containing window_inventory.csv.

    Returns:
        List of window dicts parsed from CSV.

    Raises:
        FileNotFoundError: If window_inventory.csv is missing.
        ValueError: If required columns are absent.
    """
    inv_path = Path(signal_blocks_dir) / "window_inventory.csv"
    if not inv_path.exists():
        raise FileNotFoundError(
            f"Signal block window inventory is required. "
            f"Run probe_eeg_signal_blocks first or use --mock-fixture. "
            f"(looked for: {inv_path})"
        )

    with open(inv_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        header = set(reader.fieldnames or [])

    missing = _REQUIRED_WINDOW_COLUMNS - header
    if missing:
        raise ValueError(
            f"window_inventory.csv is missing required columns: {sorted(missing)}"
        )

    return rows


# ---------------------------------------------------------------------------
# Topology computation (stdlib-only)
# ---------------------------------------------------------------------------

def _channel_mean(channel: list[float]) -> float:
    if not channel:
        return 0.0
    return sum(channel) / len(channel)


def _channel_variance(channel: list[float], mean: float) -> float:
    if len(channel) < 2:
        return 0.0
    return sum((x - mean) ** 2 for x in channel) / len(channel)


def _pearson_proxy(a: list[float], b: list[float]) -> float:
    """Stdlib-only Pearson correlation approximation between two equal-length lists."""
    n = len(a)
    if n < 2:
        return 0.0
    ma = _channel_mean(a)
    mb = _channel_mean(b)
    va = _channel_variance(a, ma)
    vb = _channel_variance(b, mb)
    denom = math.sqrt(va * vb)
    if denom < 1e-12:
        return 0.0
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / n
    return max(-1.0, min(1.0, cov / denom))


def _compute_topology_from_channels(
    channel_data: list[list[float]],
) -> tuple[float, float, float, float, int, int, float]:
    """Compute deterministic topology proxies from multi-channel signal data.

    Args:
        channel_data: List of per-channel sample lists (equal length).

    Returns:
        (q_net, q_abs, f_dress, defect_density, n_triangles, n_valid_triangles, topology_quality)
    """
    n_ch = len(channel_data)
    if n_ch == 0:
        return 0.0, 0.0, 0.0, 0.0, 0, 0, 0.0

    # Channel means → use as proxy "charges"
    means = [_channel_mean(ch) for ch in channel_data]

    # q_net: signed sum of alternating mean differences (winding proxy)
    # Treat sorted means as a closed ring; sum signed plaquette differences
    sorted_means = sorted(means)
    n = len(sorted_means)
    q_net = 0.0
    for i in range(n):
        diff = sorted_means[(i + 1) % n] - sorted_means[i]
        q_net += diff if i % 2 == 0 else -diff

    # q_abs: sum of absolute pairwise mean differences across all ordered pairs
    q_abs = 0.0
    for i in range(n_ch):
        for j in range(i + 1, n_ch):
            q_abs += abs(means[i] - means[j])
    # Normalize to [0, n_ch-1] range
    n_pairs = n_ch * (n_ch - 1) / 2
    q_abs = q_abs / n_pairs if n_pairs > 0 else 0.0

    # f_dress = max(q_abs - abs(q_net), 0)
    q_net_norm = q_net / max(n_ch, 1)
    f_dress = max(q_abs - abs(q_net_norm), 0.0)

    # Triangles: n choose 3
    n_triangles = (n_ch * (n_ch - 1) * (n_ch - 2)) // 6 if n_ch >= 3 else 0

    # Valid triangles: triples where mean pairwise correlation > threshold
    n_valid_triangles = 0
    if n_ch >= 3:
        n_samples = len(channel_data[0]) if channel_data else 0
        if n_samples >= 2:
            # Precompute each ordered pair's absolute correlation exactly once
            # into a symmetric matrix, then read it in the triangle loop. The
            # previous triple loop recomputed each pair's `_pearson_proxy`
            # (an O(n_samples) pure-Python pass) up to (n_ch-2) times -- for
            # n_ch=8 that is 168 pearson evaluations where only 28 distinct
            # pairs exist (~6x redundant, and each evaluation walks a full
            # ~1000s-of-samples window). Caching is byte-identical: the same
            # `_pearson_proxy` result feeds the same `(|r_ij|+|r_ik|+|r_jk|)/3`
            # comparison, just computed once per pair.
            abs_corr = [[0.0] * n_ch for _ in range(n_ch)]
            for i in range(n_ch):
                for j in range(i + 1, n_ch):
                    c = abs(_pearson_proxy(channel_data[i], channel_data[j]))
                    abs_corr[i][j] = c
                    abs_corr[j][i] = c
            for i in range(n_ch):
                for j in range(i + 1, n_ch):
                    for k in range(j + 1, n_ch):
                        avg_corr = (abs_corr[i][j] + abs_corr[i][k] + abs_corr[j][k]) / 3.0
                        if avg_corr > _SIMILARITY_THRESHOLD:
                            n_valid_triangles += 1

    defect_density = q_abs / max(n_valid_triangles, 1)
    topology_quality = n_valid_triangles / max(n_triangles, 1) if n_triangles > 0 else 0.0

    # Ensure all values are finite
    for v in (q_net, q_abs, f_dress, defect_density, topology_quality):
        if not math.isfinite(v):
            return 0.0, 0.0, 0.0, 0.0, n_triangles, 0, 0.0

    return (
        q_net_norm,
        q_abs,
        f_dress,
        defect_density,
        n_triangles,
        n_valid_triangles,
        topology_quality,
    )


# Public alias: this is real, signal-derived topology (channel means/correlations),
# deliberately reused by other Level T implementations (e.g. ds005620_real_topology.py)
# instead of each dataset reimplementing its own — or worse, fabricating one from a
# metadata hash, as ds005620_real_topology.py's fixture path used to.
compute_topology_from_channels = _compute_topology_from_channels


# ---------------------------------------------------------------------------
# Per-window topology extraction
# ---------------------------------------------------------------------------

def compute_signal_topology_for_window(
    dataset_id: str,
    window: dict,
) -> EEGLevelTSignalTopologyRow:
    """Compute topology telemetry for a single signal window.

    Loads the source file, slices the specified sample range, and computes
    deterministic topology proxies.

    Args:
        dataset_id: Dataset identifier string.
        window: Dict with window metadata (from window_inventory.csv).

    Returns:
        EEGLevelTSignalTopologyRow with computed topology metrics.
    """
    row_id = window.get("row_id", "")
    source_file = window.get("file_path", "")
    window_id = window.get("window_id", "")
    warnings: list[str] = []

    def _make_skipped(status: str, reason: str) -> EEGLevelTSignalTopologyRow:
        return EEGLevelTSignalTopologyRow(
            dataset_id=dataset_id,
            row_id=row_id,
            source_file=source_file,
            window_id=window_id,
            window_start_s=float(window.get("window_start_s", 0.0) or 0.0),
            window_end_s=float(window.get("window_end_s", 0.0) or 0.0),
            sample_start=int(window.get("sample_start", 0) or 0),
            sample_end=int(window.get("sample_end", 0) or 0),
            n_channels=int(window.get("n_channels", 0) or 0),
            n_samples=int(window.get("n_samples", 0) or 0),
            sample_rate_hz=float(window.get("sample_rate_hz", 0.0) or 0.0),
            q_net=0.0,
            q_abs=0.0,
            f_dress=0.0,
            defect_density=0.0,
            n_triangles=0,
            n_valid_triangles=0,
            topology_quality=0.0,
            topology_status=status,
            warnings=[reason],
        )

    # Validate sample range
    try:
        sample_start = int(window.get("sample_start", 0) or 0)
        sample_end = int(window.get("sample_end", 0) or 0)
        n_channels = int(window.get("n_channels", 0) or 0)
        n_samples_w = int(window.get("n_samples", 0) or 0)
        sample_rate_hz = float(window.get("sample_rate_hz", 0.0) or 0.0)
        window_start_s = float(window.get("window_start_s", 0.0) or 0.0)
        window_end_s = float(window.get("window_end_s", 0.0) or 0.0)
    except (ValueError, TypeError) as e:
        return _make_skipped("skipped_invalid_window", f"Invalid window fields: {e}")

    if sample_end <= sample_start:
        return _make_skipped("skipped_invalid_window", f"sample_end ({sample_end}) <= sample_start ({sample_start})")

    if n_channels < 1:
        return _make_skipped("insufficient_channels", f"n_channels={n_channels} < 1")

    if n_channels < 3:
        warnings.append(f"n_channels={n_channels} < 3; n_triangles will be 0")

    # Load source file
    if not source_file or not Path(source_file).exists():
        return _make_skipped("skipped_unreadable_source", f"Source file not found: {source_file!r}")

    try:
        sig = parse_fixture_signal_file(source_file)
    except Exception as e:
        return _make_skipped("skipped_parse_error", f"Parse error: {e}")

    if not sig.readable or not sig.samples:
        return _make_skipped("skipped_unreadable_source", f"Source file not readable: {source_file!r}")

    # Slice samples
    actual_end = min(sample_end, sig.n_samples or 0)
    actual_start = min(sample_start, actual_end)
    sliced_rows = sig.samples[actual_start:actual_end]

    if not sliced_rows:
        return _make_skipped("skipped_no_samples", "No samples in specified range")

    n_actual_samples = len(sliced_rows)
    if n_actual_samples < n_samples_w // 2:
        warnings.append(
            f"Window has {n_actual_samples} samples; expected {n_samples_w}"
        )

    # Transpose: rows of samples → list per channel
    row_width = len(sliced_rows[0]) if sliced_rows else 0
    if row_width == 0:
        return _make_skipped("skipped_no_samples", "Zero-width sample rows")

    actual_channels = min(n_channels, row_width)
    channel_data: list[list[float]] = [
        [row[ch_idx] for row in sliced_rows]
        for ch_idx in range(actual_channels)
    ]

    if actual_channels < n_channels:
        warnings.append(f"Source has {actual_channels} channels; window expected {n_channels}")

    # Determine topology status
    window_status = window.get("status", "ok")
    if window_status == "short_window":
        topo_status = "short_window"
    elif actual_channels < 3:
        topo_status = "insufficient_channels"
    else:
        topo_status = "ok"

    # Compute topology
    (
        q_net, q_abs, f_dress, defect_density,
        n_triangles, n_valid_triangles, topology_quality,
    ) = _compute_topology_from_channels(channel_data)

    return EEGLevelTSignalTopologyRow(
        dataset_id=dataset_id,
        row_id=row_id,
        source_file=source_file,
        window_id=window_id,
        window_start_s=window_start_s,
        window_end_s=window_end_s,
        sample_start=sample_start,
        sample_end=sample_end,
        n_channels=actual_channels,
        n_samples=n_actual_samples,
        sample_rate_hz=sample_rate_hz,
        q_net=q_net,
        q_abs=q_abs,
        f_dress=f_dress,
        defect_density=defect_density,
        n_triangles=n_triangles,
        n_valid_triangles=n_valid_triangles,
        topology_quality=topology_quality,
        topology_status=topo_status,
        warnings=warnings,
    )


def compute_signal_topology_rows(
    dataset_id: str,
    windows: list[dict],
) -> tuple[list[EEGLevelTSignalTopologyRow], list[dict]]:
    """Compute topology rows for all windows; collect skipped records separately.

    Args:
        dataset_id: Dataset identifier.
        windows: List of window dicts from window_inventory.csv.

    Returns:
        (topology_rows, skipped_windows) tuple.
    """
    rows: list[EEGLevelTSignalTopologyRow] = []
    skipped: list[dict] = []

    _SKIPPED_STATUSES = {
        "skipped_no_samples",
        "skipped_invalid_window",
        "skipped_unreadable_source",
        "skipped_parse_error",
    }

    for w in windows:
        row = compute_signal_topology_for_window(dataset_id, w)
        if row.topology_status in _SKIPPED_STATUSES:
            skipped.append({
                "row_id": row.row_id,
                "source_file": row.source_file,
                "window_id": row.window_id,
                "reason": row.topology_status,
                "warnings": row.warnings,
            })
        else:
            rows.append(row)

    return rows, skipped


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def build_topology_quality_report(
    rows: list[EEGLevelTSignalTopologyRow],
    skipped_windows: list[dict],
) -> dict:
    """Build topology quality report.

    Args:
        rows: Topology rows.
        skipped_windows: Skipped window records.

    Returns:
        Dict with quality statistics.
    """
    n_rows = len(rows)
    n_skipped = len(skipped_windows)
    n_windows = n_rows + n_skipped

    finite_rows = [r for r in rows if math.isfinite(r.topology_quality)]
    n_finite = len(finite_rows)

    mean_quality = (
        sum(r.topology_quality for r in finite_rows) / n_finite if n_finite > 0 else 0.0
    )
    low_quality = sum(1 for r in finite_rows if r.topology_quality < 0.25)

    # artifact dominance: mean_quality < 0.25 OR >half rows have quality < 0.25
    artifact_dominance = (
        mean_quality < 0.25 or
        (n_finite > 0 and low_quality > n_finite / 2)
    )

    quality_passed = (
        n_rows > 0 and
        n_finite == n_rows and
        not artifact_dominance
    )

    return {
        "dataset_id": rows[0].dataset_id if rows else "",
        "n_windows": n_windows,
        "n_topology_rows": n_rows,
        "n_skipped_windows": n_skipped,
        "mean_topology_quality": round(mean_quality, 6),
        "low_quality_windows": low_quality,
        "finite_topology_rows": n_finite,
        "quality_passed": quality_passed,
    }


def build_signal_topology_artifact_report(
    rows: list[EEGLevelTSignalTopologyRow],
) -> dict:
    """Build artifact report for topology extraction run.

    Args:
        rows: Topology rows.

    Returns:
        Dict with artifact statistics.
    """
    dataset_id = rows[0].dataset_id if rows else ""
    n_rows = len(rows)

    qualities = [r.topology_quality for r in rows if math.isfinite(r.topology_quality)]
    mean_q = sum(qualities) / len(qualities) if qualities else 0.0
    min_q = min(qualities) if qualities else 0.0
    low_quality = sum(1 for q in qualities if q < 0.25)
    insuff_ch = sum(1 for r in rows if r.topology_status == "insufficient_channels")

    artifact_dominance = (
        mean_q < 0.25 or
        (len(qualities) > 0 and low_quality > len(qualities) / 2)
    )

    return {
        "dataset_id": dataset_id,
        "n_topology_rows": n_rows,
        "mean_topology_quality": round(mean_q, 6),
        "min_topology_quality": round(min_q, 6),
        "low_quality_windows": low_quality,
        "insufficient_channel_windows": insuff_ch,
        "topology_artifact_dominance": artifact_dominance,
    }


def build_level_t_signal_omega_event(result: EEGLevelTSignalTopologyResult) -> dict:
    """Build omega event record for the topology extraction run."""
    _validate_safe_text(result.safe_claim)
    payload = (
        f"level_t_signal:{result.dataset_id}:{result.n_topology_rows}:"
        f"{result.n_windows}:{result.safe_claim}"
    )
    event_id = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return {
        "event_id": event_id,
        "event_type": "level_t_signal_topology",
        "dataset_id": result.dataset_id,
        "n_windows": result.n_windows,
        "n_topology_rows": result.n_topology_rows,
        "n_skipped_windows": result.n_skipped_windows,
        "safe_claim": result.safe_claim,
        "forbidden_claims": result.forbidden_claims,
        "warnings": result.warnings[:20],
    }


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------

def write_level_t_signal_outputs(
    result: EEGLevelTSignalTopologyResult,
    out_dir: str,
) -> dict[str, str]:
    """Write Level T signal topology outputs.

    Artifacts:
        features_t_signal.csv
        topology_quality_report.json
        artifact_report.json
        skipped_windows.json
        omega_event.json
        report.md

    Args:
        result: Aggregate topology extraction result.
        out_dir: Output directory path.

    Returns:
        Dict mapping artifact names to file paths written.
    """
    _validate_safe_text(result.safe_claim)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}

    # 1. features_t_signal.csv
    feat_file = out_path / "features_t_signal.csv"
    _FEAT_COLS = [
        "dataset_id", "row_id", "source_file", "window_id",
        "window_start_s", "window_end_s", "sample_start", "sample_end",
        "n_channels", "n_samples", "sample_rate_hz",
        "q_net", "q_abs", "f_dress", "defect_density",
        "n_triangles", "n_valid_triangles", "topology_quality",
        "topology_status", "warnings",
    ]
    import csv as _csv
    with open(feat_file, "w", newline="") as f:
        writer = _csv.writer(f)
        writer.writerow(_FEAT_COLS)
        for row_dict in result.topology_rows:
            writer.writerow([
                row_dict.get("dataset_id", ""),
                row_dict.get("row_id", ""),
                row_dict.get("source_file", ""),
                row_dict.get("window_id", ""),
                row_dict.get("window_start_s", ""),
                row_dict.get("window_end_s", ""),
                row_dict.get("sample_start", ""),
                row_dict.get("sample_end", ""),
                row_dict.get("n_channels", ""),
                row_dict.get("n_samples", ""),
                row_dict.get("sample_rate_hz", ""),
                row_dict.get("q_net", ""),
                row_dict.get("q_abs", ""),
                row_dict.get("f_dress", ""),
                row_dict.get("defect_density", ""),
                row_dict.get("n_triangles", ""),
                row_dict.get("n_valid_triangles", ""),
                row_dict.get("topology_quality", ""),
                row_dict.get("topology_status", ""),
                "|".join(row_dict.get("warnings", [])),
            ])
    outputs["features_t_signal"] = str(feat_file)

    # 2. topology_quality_report.json
    tqr_file = out_path / "topology_quality_report.json"
    with open(tqr_file, "w") as f:
        json.dump(result.topology_quality_report, f, indent=2)
    outputs["topology_quality_report"] = str(tqr_file)

    # 3. artifact_report.json
    ar_file = out_path / "artifact_report.json"
    with open(ar_file, "w") as f:
        json.dump(result.artifact_report, f, indent=2)
    outputs["artifact_report"] = str(ar_file)

    # 4. skipped_windows.json
    sw_file = out_path / "skipped_windows.json"
    with open(sw_file, "w") as f:
        json.dump({"skipped": result.skipped_windows}, f, indent=2)
    outputs["skipped_windows"] = str(sw_file)

    # 5. omega_event.json
    omega_file = out_path / "omega_event.json"
    with open(omega_file, "w") as f:
        json.dump(result.omega_event, f, indent=2)
    outputs["omega_event"] = str(omega_file)

    # 6. report.md
    md = _build_markdown_report(result)
    md_file = out_path / "report.md"
    with open(md_file, "w") as f:
        f.write(md)
    outputs["report"] = str(md_file)

    return outputs


def _build_markdown_report(result: EEGLevelTSignalTopologyResult) -> str:
    """Build Markdown summary report."""
    _validate_safe_text(result.safe_claim)

    md = "# EEG Level T Signal Topology Extraction\n\n"

    md += "## Stage\n\n"
    md += (
        "P10 — Level T signal topology scaffold. Consumes P8.2 signal-block "
        "window inventory and emits operational Level T topology telemetry "
        "candidates. Does NOT extract Level M features, run residual promotion, "
        "or implement Level O/C/Q.\n\n"
    )

    md += f"## Dataset\n\n`{result.dataset_id}`\n\n"

    md += "## Input Signal Windows\n\n"
    md += f"- Total windows: {result.n_windows}\n"
    md += f"- Topology rows computed: {result.n_topology_rows}\n"
    md += f"- Skipped windows: {result.n_skipped_windows}\n\n"

    tqr = result.topology_quality_report
    md += "## Topology Quality\n\n"
    md += f"- Mean topology quality: {tqr.get('mean_topology_quality', 0.0):.4f}\n"
    md += f"- Low quality windows: {tqr.get('low_quality_windows', 0)}\n"
    md += f"- Finite topology rows: {tqr.get('finite_topology_rows', 0)}\n"
    md += f"- Quality passed: {tqr.get('quality_passed', False)}\n\n"

    ar = result.artifact_report
    md += "## Artifact Report\n\n"
    md += f"- Mean topology quality: {ar.get('mean_topology_quality', 0.0):.4f}\n"
    md += f"- Min topology quality: {ar.get('min_topology_quality', 0.0):.4f}\n"
    md += f"- Insufficient channel windows: {ar.get('insufficient_channel_windows', 0)}\n"
    md += f"- Topology artifact dominance: {ar.get('topology_artifact_dominance', False)}\n\n"

    md += "## Skipped Windows\n\n"
    if result.skipped_windows:
        for sw in result.skipped_windows[:10]:
            md += f"- {sw.get('row_id', '')}: {sw.get('reason', '')}\n"
    else:
        md += "_No windows skipped._\n"
    md += "\n"

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
        "Join Level M signal features and Level T signal topology telemetry "
        "in a future signal-level residual benchmark.\n\n"
    )

    md += "---\n"
    md += (
        "**Guardrail:** This signal topology telemetry does not validate "
        "cognition, affect, physiology, or any metaphysical property.\n"
    )
    return md
