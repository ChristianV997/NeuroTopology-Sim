#!/usr/bin/env python3
"""Stream ds005620 (propofol sedation EEG) through PITNN empirical falsification.

Why this tool exists
--------------------
`scripts/run_empirical_falsification.py` already implements the PITNN two-condition
falsification contract, and `scripts/eeg_topology_ds005620.py` already implements the
correct PLV + persistent-H1 topology for THIS dataset (5000 Hz, beta/gamma band,
ripser). What was missing was a way to feed them the REAL cohort: the prior cohort run
found only ONE paired subject because the full dataset is 83 GB and was never fetched.

This driver closes that gap without duplicating any analysis code:

  * subject/recording discovery ....... base_runner.list_s3_subjects + S3 listing
  * bounded ranged download .......... base_runner.sync_s3_subject's byte-range idea,
                                       narrowed here to the TWO recordings we need
  * resume / checkpoint / delete ...... base_runner.run_streaming_loop
  * BrainVision read + montage ........ shared.data_loaders.eeg_bids_loader.read_local_raw
  * graph persistence (H1) ............ topo_monitor.graph_persistence.analyze_adjacency
  * spatial charge .................... topo_monitor.spatial_phase.sensor_spatial_charge
  * PITNN falsification ............... scripts.run_empirical_falsification

Efficiency
----------
ds005620 is 83 GB of `.eeg` across 202 recordings (mean 411 MB, 65 ch @ 5000 Hz,
IEEE_FLOAT_32 MULTIPLEXED). We never download a whole recording. BrainVision binary
is a flat multiplexed array with no length field in the `.vhdr`, so a byte-range
prefix of the `.eeg` is itself a valid, shorter recording that MNE reads normally.
Fetching `--download-seconds` of each of two recordings per subject reduces the
transfer from 83 GB to roughly 2 GB, and `run_streaming_loop` deletes each subject's
raw bytes before the next one, so peak disk stays near one subject's worth.

Pairing rule (explicit, no label inference)
-------------------------------------------
awake   := task-awake_acq-EC          (eyes-closed rest; exactly one per subject)
sedated := task-sed_acq-rest_run-<lowest>, falling back to task-sed2_acq-rest

`acq-tms` recordings are excluded on purpose: TMS-evoked activity is a different
regime and would confound a resting-state contrast. The registry
(configs/btc_icft/dataset_onboarding_registry.json) maps both `sed` and `sed2` to the
`sedated` state; the previous cohort script globbed only `task-sed2`, which silently
dropped most sedation recordings.

Usage
-----
    python tools/stream_pitnn_cohort_ds005620.py \\
        --out outputs/pitnn_cohort/ds005620 --work-root data/ds005620_stream
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.streaming import base_runner

_BUCKET = "openneuro.org"
_DATASET = "ds005620"

# Native acquisition parameters, confirmed by direct S3 header inspection:
# NumberOfChannels=65, SamplingInterval=200.0 us (5000 Hz), BinaryFormat=IEEE_FLOAT_32.
_NATIVE_RATE_HZ = 5000.0


# --------------------------------------------------------------------------- #
# Recording selection
# --------------------------------------------------------------------------- #

def _s3_client():
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    return boto3.client(
        "s3",
        config=Config(
            signature_version=UNSIGNED,
            max_pool_connections=16,
            connect_timeout=20,
            read_timeout=120,
            retries={"max_attempts": 5, "mode": "adaptive"},
        ),
    )


def list_recording_keys(client, dataset_id: str = _DATASET) -> dict[str, dict[str, str]]:
    """Map subject -> {"awake": vhdr_key, "sedated": vhdr_key} for paired subjects only.

    Selection is deterministic and documented in the module docstring. A subject
    missing either side is omitted (never substituted), so the cohort n reflects real
    paired availability rather than an inferred pairing.
    """
    keys: list[str] = []
    for page in client.get_paginator("list_objects_v2").paginate(
        Bucket=_BUCKET, Prefix=f"{dataset_id}/sub-"
    ):
        keys.extend(obj["Key"] for obj in page.get("Contents", []) if obj["Key"].endswith(".vhdr"))

    by_subject: dict[str, dict[str, str]] = {}
    run_re = re.compile(r"run-(\d+)")
    for subject in sorted({k.split("/")[1] for k in keys}):
        mine = [k for k in keys if k.split("/")[1] == subject]
        awake = [k for k in mine if "task-awake_acq-EC" in k]
        sed = sorted(
            (k for k in mine if "task-sed_acq-rest" in k),
            key=lambda k: int(run_re.search(k).group(1)) if run_re.search(k) else 0,
        )
        sed2 = sorted(
            (k for k in mine if "task-sed2_acq-rest" in k),
            key=lambda k: int(run_re.search(k).group(1)) if run_re.search(k) else 0,
        )
        sedated = sed or sed2
        if awake and sedated:
            by_subject[subject] = {"awake": awake[0], "sedated": sedated[0]}
    return by_subject


# --------------------------------------------------------------------------- #
# Bounded ranged download
# --------------------------------------------------------------------------- #

def _eeg_prefix_bytes(vhdr_text: str, duration_seconds: float, full_size: int) -> int:
    """Bytes of a MULTIPLEXED BrainVision `.eeg` holding `duration_seconds` of data.

    Mirrors `base_runner.sync_s3_subject._required_eeg_bytes`. Truncating on a whole
    -sample boundary is what keeps the prefix a valid recording.
    """
    channels = int(re.search(r"^NumberOfChannels=(\d+)", vhdr_text, re.MULTILINE).group(1))
    interval_us = float(re.search(r"^SamplingInterval=([0-9.]+)", vhdr_text, re.MULTILINE).group(1))
    fmt = re.search(r"^BinaryFormat=(.+)$", vhdr_text, re.MULTILINE)
    bytes_per_sample = 4 if "32" in (fmt.group(1) if fmt else "") else 2
    samples = int(duration_seconds * 1_000_000 / interval_us + 0.999999)
    return min(full_size, channels * samples * bytes_per_sample)


def fetch_recording(client, vhdr_key: str, dest_dir: Path, duration_seconds: float) -> Path:
    """Download one recording's `.vhdr`, `.vmrk` and a ranged `.eeg` prefix.

    The header must land before the range can be computed, so it is fetched first
    rather than concurrently -- the same ordering dependency `sync_s3_subject`
    documents for its metadata/EEG phases.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(vhdr_key).name[: -len(".vhdr")]

    vhdr_text = client.get_object(Bucket=_BUCKET, Key=vhdr_key)["Body"].read().decode("utf-8", "replace")
    vhdr_path = dest_dir / f"{stem}.vhdr"
    vhdr_path.write_text(vhdr_text, encoding="utf-8")

    vmrk_key = vhdr_key[: -len(".vhdr")] + ".vmrk"
    try:
        vmrk = client.get_object(Bucket=_BUCKET, Key=vmrk_key)["Body"].read()
        (dest_dir / f"{stem}.vmrk").write_bytes(vmrk)
    except Exception:
        pass  # markers are optional for a resting-state amplitude read

    eeg_key = vhdr_key[: -len(".vhdr")] + ".eeg"
    full_size = client.head_object(Bucket=_BUCKET, Key=eeg_key)["ContentLength"]
    want = _eeg_prefix_bytes(vhdr_text, duration_seconds, full_size)

    eeg_path = dest_dir / f"{stem}.eeg"
    partial = eeg_path.with_suffix(".eeg.part")
    body = client.get_object(Bucket=_BUCKET, Key=eeg_key, Range=f"bytes=0-{want - 1}")["Body"]
    with partial.open("wb") as out:
        while True:
            block = body.read(8 * 1024 * 1024)
            if not block:
                break
            out.write(block)
    if partial.stat().st_size != want:
        partial.unlink(missing_ok=True)
        raise IOError(f"incomplete ranged download for {eeg_key}: {partial.stat().st_size} != {want}")
    partial.replace(eeg_path)
    return vhdr_path


# --------------------------------------------------------------------------- #
# Read + condition matrix
# --------------------------------------------------------------------------- #

def read_condition(
    vhdr_path: Path, *, skip_seconds: float, analyze_seconds: float, target_rate_hz: float
) -> tuple[np.ndarray, float, np.ndarray | None]:
    """Return `(samples, channels)` decimated EEG plus rate and montage coordinates.

    Decimation is anti-aliased (`scipy.signal.decimate`, zero-phase FIR). 5000 Hz is far
    above what a <=80 Hz analysis needs; decimating to `target_rate_hz` cuts the
    downstream Hilbert/PLV cost by the same factor without touching the passband.
    """
    from scipy.signal import decimate

    from shared.data_loaders.eeg_bids_loader import read_local_raw

    stream = read_local_raw(vhdr_path, preload=False)
    raw = stream.raw
    rate = float(raw.info["sfreq"])

    picks = [i for i, kind in enumerate(raw.get_channel_types()) if kind == "eeg"]
    if len(picks) < 8:
        raise ValueError(f"{vhdr_path.name}: only {len(picks)} EEG channels")

    start = int(round(skip_seconds * rate))
    stop = min(int(raw.n_times), start + int(round(analyze_seconds * rate)))
    if stop - start < int(round(2.0 * rate)):
        raise ValueError(f"{vhdr_path.name}: fewer than 2 s of usable data after skip")

    data = np.asarray(raw.get_data(start=start, stop=stop, picks=picks), float)  # (ch, samples)
    if not np.all(np.isfinite(data)):
        raise ValueError(f"{vhdr_path.name}: non-finite samples")

    factor = int(round(rate / target_rate_hz))
    if factor > 1:
        data = decimate(data, factor, axis=1, ftype="fir", zero_phase=True)
        rate = rate / factor

    montage = stream.metadata.montage_coordinates
    if montage is not None:
        montage = np.asarray(montage, float)[picks]

    # Drop any channel that decimation or acquisition left constant: PITNN's
    # `_normalize` rejects zero-variance channels outright, and a flat channel
    # carries no phase information for PLV either.
    keep = np.std(data, axis=1) > np.finfo(float).eps
    data = data[keep]
    if montage is not None:
        montage = montage[keep]
    if data.shape[0] < 8:
        raise ValueError(f"{vhdr_path.name}: fewer than 8 non-degenerate channels")

    return data.T, float(rate), montage


# --------------------------------------------------------------------------- #
# Topology (PLV -> persistent H1) per window
# --------------------------------------------------------------------------- #

def _plv_matrix(phase: np.ndarray) -> np.ndarray:
    """Phase-locking value matrix from `(channels, samples)` phase.

    Uses the identity `mean_t exp(i(phi_a - phi_b)) = (z @ z^H)/N` with
    `z = exp(i*phi)`, avoiding the `(C, C, N)` intermediate the older scripts
    materialise -- at 65 channels x 5000 samples that difference is ~170 MB per window.
    """
    z = np.exp(1j * phase)
    plv = np.abs(z @ z.conj().T) / phase.shape[1]
    np.fill_diagonal(plv, 0.0)
    return np.clip((plv + plv.T) / 2.0, 0.0, 1.0)


def window_topology(
    data: np.ndarray,
    rate_hz: float,
    montage: np.ndarray | None,
    *,
    band: tuple[float, float],
    window_seconds: float,
    plv_threshold: float,
    landscape_layers: int,
    export_cubical_persistence: bool = False,
) -> tuple[list[dict[str, Any]], np.ndarray]:
    """Per-window PLV persistence + spatial charge for one condition.

    `data` is `(samples, channels)`. Band-limited analytic phase matches the discipline
    in `scripts/eeg_topology_ds005620.py` (a broadband Hilbert phase is not a
    meaningful oscillatory phase). Returns `(rows, phase)` -- the caller needs the
    band-filtered phase array itself (not just the summaries) to build the spatial
    defect snapshot from the same last window these rows already describe, rather
    than recomputing the filter.

    `export_cubical_persistence`, when set, additionally computes GUDHI sub-level
    cubical persistence on the raw PLV *matrix itself* via
    `core.topology.export_persistence_json`. This is a genuinely different summary
    from the ripser Vietoris-Rips diagram `analyze_adjacency` already computes on
    `1 - PLV`: cubical persistence sweeps every PLV threshold on the matrix as a
    2D grid, so it captures amplitude structure the graph-distance view discards.
    `core/persistence_export.py` was built and unit-tested in isolation but never
    exercised on real data before this call.
    """
    import mne
    from scipy.signal import hilbert

    from topo_monitor.graph_persistence import analyze_adjacency
    from topo_monitor.spatial_phase import sensor_spatial_charge

    x = np.asarray(data, float).T  # (channels, samples)
    x = x - x.mean(axis=1, keepdims=True)
    x = x / np.where(np.std(x, axis=1, keepdims=True) > 0, np.std(x, axis=1, keepdims=True), 1.0)
    filtered = mne.filter.filter_data(x, rate_hz, band[0], band[1], method="iir", verbose="ERROR")
    phase = np.angle(hilbert(filtered, axis=1))

    span = int(round(window_seconds * rate_hz))
    out: list[dict[str, Any]] = []
    for index, start in enumerate(range(0, phase.shape[1] - span + 1, span)):
        chunk = phase[:, start : start + span]
        plv = _plv_matrix(chunk)
        result = analyze_adjacency(plv, threshold=plv_threshold, n_layers=landscape_layers)
        charge = None
        if montage is not None:
            try:
                charge = sensor_spatial_charge(chunk[:, -1], montage)
            except Exception:
                # Delaunay can also raise QhullError on degenerate sensor layouts;
                # a missing charge is recorded as null rather than fabricated.
                charge = None
        row: dict[str, Any] = {
            "window": index,
            "start_s": float(start / rate_hz),
            "channels": int(chunk.shape[0]),
            "beta1": int(np.max(result.beta_curve)) if result.beta_curve.size else 0,
            "filtration_beta1_max": int(np.max(result.sweep_beta1)) if result.sweep_beta1 is not None else 0,
            "integrated_landscape_area": float(result.integrated_landscape_area),
            "mean_plv": float(plv[np.triu_indices_from(plv, k=1)].mean()),
            "q_spatial": charge,
        }
        if export_cubical_persistence:
            from core.topology import export_persistence_json

            row["cubical_persistence"] = export_persistence_json(plv, max_dimension=1)
        out.append(row)
    return out, phase


def _condition_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    charges = [r["q_spatial"] for r in rows if r["q_spatial"] is not None]
    return {
        "windows": len(rows),
        "mean_beta1": float(np.mean([r["filtration_beta1_max"] for r in rows])) if rows else None,
        "mean_landscape_area": float(np.mean([r["integrated_landscape_area"] for r in rows])) if rows else None,
        "mean_plv": float(np.mean([r["mean_plv"] for r in rows])) if rows else None,
        "mean_q_spatial": float(np.mean(charges)) if charges else None,
    }


# --------------------------------------------------------------------------- #
# Spatial defect snapshot (closes the command-center `spatial_artifact` gap)
# --------------------------------------------------------------------------- #

def spatial_defect_snapshot(phase: np.ndarray, montage: np.ndarray | None, beta1: int | None = None) -> dict[str, Any] | None:
    """Real channel-coordinate defect map from one condition's final window.

    Reuses `validation.montage_topology.signed_defect_map` unmodified -- the same
    tested function `dual_engine/anesthesia_signed_winding_pipeline.py` already
    runs on this dataset for its channel-mean report. `montage` is the `(n, 3)`
    array `read_condition` already extracted; its first two columns are the same
    xy plane `validation.montage_topology.get_channel_xy` would return, since both
    derive from the raw's `standard_1020` fallback montage set in
    `shared.data_loaders.eeg_bids_loader.read_local_raw`.

    Returns `None` (not a fabricated zero-filled record) when there is no montage,
    fewer than three finite positions, or fewer than three triangles survive
    triangulation -- callers must treat absence as absence.
    """
    from validation.montage_topology import signed_defect_map, triangulate_xy

    if montage is None:
        return None
    xy = np.asarray(montage, float)[:, :2]
    finite = np.all(np.isfinite(xy), axis=1)
    if int(np.count_nonzero(finite)) < 3:
        return None
    xy = xy[finite]
    phase_last = np.asarray(phase, float)[finite, -1]
    amp_last = None  # only the phase snapshot is retained; amplitude masking is skipped, not faked

    try:
        triangles = triangulate_xy(xy)
        defects = signed_defect_map(phase_last, xy, triangles, amp_vec=amp_last, amp_quantile=None)
    except Exception:
        return None

    return {
        "channel_coordinates": xy.tolist(),
        "coordinate_frame": "sensor_2d_projection_of_standard_1020_montage",
        "phase": phase_last.tolist(),
        "beta1": beta1,
        "defects": {
            "triangle_indices": defects["triangle_indices"].tolist(),
            "signed_winding": defects["signed_winding"].tolist(),
            "centroid_xy": defects["centroid_xy"].tolist(),
            "chirality": defects["chirality"].tolist(),
            "n_valid_triangles": defects["n_valid_triangles"],
        },
        "wave_vectors": None,
        "wave_vectors_note": "not implemented anywhere in this repo; reported null rather than fabricated",
        "quality_control": {
            "n_channels": int(xy.shape[0]),
            "n_channels_finite_position": int(np.count_nonzero(finite)),
            "n_valid_triangles": defects["n_valid_triangles"],
            "all_finite": bool(np.all(np.isfinite(defects["signed_winding"])) and np.all(np.isfinite(defects["centroid_xy"]))),
        },
    }


# --------------------------------------------------------------------------- #
# Per-subject processing
# --------------------------------------------------------------------------- #

def process_subject(subject_root: Path, subject: str, out_dir: Path, cfg: argparse.Namespace) -> dict[str, Any]:
    """Build the paired condition bundle, run PITNN falsification, summarise topology."""
    conditions: dict[str, dict[str, Any]] = {}
    arrays: dict[str, np.ndarray] = {}
    rate_hz: float | None = None

    for label, state_key in (("awake", "state_a"), ("sedated", "state_b")):
        vhdr = next(iter(sorted((subject_root / label).glob("*.vhdr"))), None)
        if vhdr is None:
            raise FileNotFoundError(f"{subject}: no {label} header fetched")
        data, rate, montage = read_condition(
            vhdr,
            skip_seconds=cfg.skip_seconds,
            analyze_seconds=cfg.analyze_seconds,
            target_rate_hz=cfg.target_rate_hz,
        )
        # Both conditions must share a sampling rate: PITNN takes a single
        # `sample_rate_hz` for the concatenated pair, so a silent mismatch would
        # mis-scale one condition's spectrum.
        if rate_hz is not None and abs(rate - rate_hz) > 1e-9:
            raise ValueError(f"{subject}: condition sample rates differ ({rate_hz} vs {rate})")
        rate_hz = rate
        arrays[state_key] = data
        rows, phase = window_topology(
            data,
            rate,
            montage,
            band=(cfg.band_low_hz, cfg.band_high_hz),
            window_seconds=cfg.window_seconds,
            plv_threshold=cfg.plv_threshold,
            landscape_layers=cfg.landscape_layers,
            export_cubical_persistence=cfg.export_persistence,
        )
        last_beta1 = rows[-1]["filtration_beta1_max"] if rows else None
        spatial = spatial_defect_snapshot(phase, montage, beta1=last_beta1) if cfg.export_spatial else None
        conditions[label] = {
            "source_file": vhdr.name,
            "windows": rows,
            "summary": _condition_summary(rows),
            "spatial": spatial,
        }

    # PITNN consumes a two-condition NPZ (`state_a` / `state_b`, samples x channels)
    # through `sim.pitnn.ingest_empirical.ingest_conditions`. Both conditions must
    # share a channel count for a like-for-like comparison. Truncating to the
    # narrower one only aligns positions, so record when a drop actually happened:
    # a subject whose two recordings lost different channels is comparing
    # different sensors under the same index and must be visible, not silent.
    widths = (arrays["state_a"].shape[1], arrays["state_b"].shape[1])
    width = min(widths)
    channel_mismatch = widths[0] != widths[1]
    bundle_dir = out_dir / "bundles"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle = bundle_dir / f"{subject}_conditions.npz"
    np.savez_compressed(bundle, state_a=arrays["state_a"][:, :width], state_b=arrays["state_b"][:, :width])

    from scripts.run_empirical_falsification import run_empirical_falsification

    report = run_empirical_falsification(
        input_file=bundle,
        condition_a_label="awake",
        condition_b_label="sedated",
        sample_rate_hz=float(rate_hz),
        output_dir=out_dir / "falsification" / subject,
        fast_tda=cfg.fast_tda,
        seed=cfg.seed,
        rg_block_size=0,
    )

    bottleneck = None
    if cfg.export_persistence:
        try:
            from core.persistence_export import bottleneck_distance, deserialize_diagram

            awake_h1 = deserialize_diagram(
                conditions["awake"]["windows"][-1]["cubical_persistence"]["diagrams"]["1"]
            )
            sedated_h1 = deserialize_diagram(
                conditions["sedated"]["windows"][-1]["cubical_persistence"]["diagrams"]["1"]
            )
            bottleneck = bottleneck_distance(awake_h1, sedated_h1)
        except Exception:
            bottleneck = None  # a missing/degenerate diagram is reported as null, not zero

    record = {
        "subject": subject,
        "sample_rate_hz": float(rate_hz),
        "n_channels": int(width),
        "n_channels_per_condition": {"awake": int(widths[0]), "sedated": int(widths[1])},
        "channel_count_mismatch": bool(channel_mismatch),
        "n_samples_per_condition": int(min(arrays["state_a"].shape[0], arrays["state_b"].shape[0])),
        "band_hz": [cfg.band_low_hz, cfg.band_high_hz],
        "topology": {label: conditions[label]["summary"] for label in conditions},
        "topology_windows": {label: conditions[label]["windows"] for label in conditions},
        "source_files": {label: conditions[label]["source_file"] for label in conditions},
        "spatial": {label: conditions[label]["spatial"] for label in conditions},
        "cubical_h1_bottleneck_distance_last_window": bottleneck,
        "pitnn": {
            "bayes_factor": float(report["bayes_factor"]),
            "delta_aicc": float(report["delta_aicc"]),
            "verdict": report["verdict"],
            "awake": report["conditions"]["awake"]["topology"],
            "sedated": report["conditions"]["sedated"]["topology"],
            "awake_inversion": report["conditions"]["awake"]["inversion"],
            "sedated_inversion": report["conditions"]["sedated"]["inversion"],
        },
    }
    (out_dir / "subjects").mkdir(parents=True, exist_ok=True)
    (out_dir / "subjects" / f"{subject}.json").write_text(
        json.dumps(record, indent=2, sort_keys=True, default=float), encoding="utf-8"
    )
    return {
        "verdict": record["pitnn"]["verdict"],
        "bayes_factor": record["pitnn"]["bayes_factor"],
        "awake_landscape": record["topology"]["awake"]["mean_landscape_area"],
        "sedated_landscape": record["topology"]["sedated"]["mean_landscape_area"],
    }


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=_REPO_ROOT / "outputs" / "pitnn_cohort" / "ds005620")
    p.add_argument("--work-root", type=Path, default=_REPO_ROOT / "data" / "ds005620_stream")
    p.add_argument("--download-seconds", type=float, default=40.0, help="ranged .eeg prefix per recording")
    p.add_argument("--skip-seconds", type=float, default=5.0, help="discard recording onset (settling/artefact)")
    p.add_argument("--analyze-seconds", type=float, default=30.0)
    p.add_argument("--target-rate-hz", type=float, default=500.0, help="decimate from the native 5000 Hz")
    p.add_argument("--window-seconds", type=float, default=10.0)
    p.add_argument("--band-low-hz", type=float, default=30.0)
    p.add_argument("--band-high-hz", type=float, default=80.0)
    p.add_argument("--plv-threshold", type=float, default=0.5)
    p.add_argument("--landscape-layers", type=int, default=3)
    p.add_argument("--fast-tda", action="store_true")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--limit", type=int, default=None, help="bound subjects processed this invocation")
    p.add_argument("--keep-raw", action="store_true")
    p.add_argument(
        "--export-spatial", action="store_true",
        help="save a real channel-coordinate defect map per condition (closes the "
             "command-center spatial_artifact gap); adds one Delaunay triangulation "
             "per condition per subject, negligible cost",
    )
    p.add_argument(
        "--export-persistence", action="store_true",
        help="save GUDHI cubical persistence (H0/H1) of the last window's PLV matrix "
             "per condition, plus the awake-vs-sedated H1 bottleneck distance; "
             "requires the optional gudhi dependency",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    cfg = parser().parse_args(argv)
    if cfg.download_seconds < cfg.skip_seconds + cfg.analyze_seconds:
        parser().error("--download-seconds must cover --skip-seconds + --analyze-seconds")
    if cfg.target_rate_hz <= 2.0 * cfg.band_high_hz:
        parser().error("--target-rate-hz must exceed twice --band-high-hz (Nyquist)")

    client = _s3_client()
    pairs = list_recording_keys(client)
    cfg.out.mkdir(parents=True, exist_ok=True)
    (cfg.out / "pairing.json").write_text(json.dumps(pairs, indent=2, sort_keys=True), encoding="utf-8")
    print(f"{len(pairs)} paired subjects discovered on S3.")

    def sync_subject_fn(subject: str, work_path: Path) -> Path:
        root = work_path / subject
        for label in ("awake", "sedated"):
            fetch_recording(client, pairs[subject][label], root / label, cfg.download_seconds)
        return root

    def process_fn(subject_root: Path, subject: str, out_path: Path) -> dict:
        return process_subject(subject_root, subject, out_path, cfg)

    manifest = base_runner.run_streaming_loop(
        sorted(pairs),
        cfg.out,
        cfg.work_root,
        sync_subject_fn,
        process_fn,
        limit=cfg.limit,
        keep_raw=cfg.keep_raw,
    )
    print(
        json.dumps(
            {
                "processed": len(manifest["processed_subjects"]),
                "failed": len(manifest["failed_subjects"]),
                "out": str(cfg.out),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
