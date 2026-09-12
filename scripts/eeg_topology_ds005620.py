"""Cohort EEG PLV and persistent-H1 analysis for OpenNeuro ds005620.

The script uses the OpenNeuro GraphQL API only to inventory a pinned snapshot.
The deprecated ``--download`` switch is rejected. It never fabricates missing
subjects: only subject pairs for which both task-awake and task-sed2 recordings
are present are analysed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping
from urllib.request import Request, urlopen

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import numpy as np
from scipy.signal import hilbert
from scipy.stats import wilcoxon

from tools.data_access.chunk_cache import ChunkRange
from tools.fetch_ds000245 import BoundedObjectRequest


GRAPHQL_URL = "https://openneuro.org/crn/graphql"
DATASET = "ds005620"


class DataAccessBlocked(RuntimeError):
    """Raised when metadata or data access is not explicitly authorized."""


def openneuro_file_inventory(
    dataset: str, snapshot: str, *, allow_network: bool = False
) -> list[dict[str, Any]]:
    """Query only pinned snapshot metadata through GraphQL.

    Metadata access is opt-in as well.  No object body is read by this
    function, and ``allow_network=False`` fails before opening a socket.
    """
    if not allow_network:
        raise DataAccessBlocked("OpenNeuro metadata access is disabled; pass allow_network=True explicitly")
    query = """query SnapshotFiles($dataset: ID!, $tag: String!) {
      snapshot(datasetId: $dataset, tag: $tag) {
        files(recursive: true) { id filename size directory annexed }
      }
    }"""
    body = json.dumps({"query": query, "variables": {"dataset": dataset, "tag": snapshot}}).encode("utf-8")
    request = Request(GRAPHQL_URL, data=body, headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    with urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(f"OpenNeuro GraphQL error: {payload['errors']}")
    files = payload.get("data", {}).get("snapshot", {}).get("files")
    if not isinstance(files, list):
        raise RuntimeError("OpenNeuro API returned no snapshot file tree")
    return [item for item in files if isinstance(item, dict) and not item.get("directory")]


def ensure_dataset(
    data_root: Path,
    dataset: str,
    snapshot: str,
    download: bool = False,
    *,
    allow_network: bool = False,
) -> list[dict[str, Any]]:
    """Load a local manifest or perform an explicit metadata-only inventory.

    The old ``download`` switch is retained only to fail loudly for callers
    that still request whole-dataset materialization.  It never invokes a
    downloader.
    """
    if download:
        raise DataAccessBlocked(
            "full OpenNeuro dataset downloads are rejected; provide bounded manifest windows"
        )
    inventory_path = data_root / "openneuro_inventory.json"
    if inventory_path.exists():
        payload = json.loads(inventory_path.read_text(encoding="utf-8"))
        if payload.get("dataset") != dataset or payload.get("snapshot") != snapshot:
            raise DataAccessBlocked("local OpenNeuro manifest identity does not match requested dataset/snapshot")
        inventory = payload.get("files")
        if not isinstance(inventory, list):
            raise DataAccessBlocked("local OpenNeuro manifest has no valid file list")
    else:
        inventory = openneuro_file_inventory(dataset, snapshot, allow_network=allow_network)
    data_root.mkdir(parents=True, exist_ok=True)
    if not inventory_path.exists():
        inventory_path.write_text(
            json.dumps({"dataset": dataset, "snapshot": snapshot, "files": inventory}, indent=2, allow_nan=False)
            + "\n",
            encoding="utf-8",
        )
    return inventory


def plan_bounded_windows(
    inventory: Iterable[Mapping[str, Any]],
    *,
    dataset: str,
    cache_root: Path,
    output_root: Path,
    max_cache_bytes: int,
    windows: Mapping[str, Mapping[str, Any]],
    allow_network: bool = False,
    final_consumer: str,
    eviction_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a canonical zero-network plan for explicitly requested ranges.

    ``windows`` maps a BIDS relative path to ``start_byte``/``end_byte``.
    Inventory rows must provide size and a source SHA-256; neither is inferred.
    """
    by_path = {str(item.get("filename", item.get("bids_path", ""))): item for item in inventory}
    bounded_requests: list[BoundedObjectRequest] = []
    for bids_path in sorted(windows):
        row = by_path.get(bids_path)
        if row is None:
            raise DataAccessBlocked(f"requested BIDS path is absent from manifest: {bids_path}")
        size = row.get("size")
        checksum = row.get("sha256") or row.get("source_sha256") or row.get("checksum")
        source_uri = row.get("source_uri") or row.get("download_url")
        if not isinstance(size, int) or size <= 0:
            raise DataAccessBlocked(f"manifest size is missing or invalid for {bids_path}")
        if not isinstance(checksum, str):
            raise DataAccessBlocked(f"manifest SHA-256 is missing for {bids_path}; provenance cannot be fabricated")
        if not isinstance(source_uri, str) or not source_uri:
            raise DataAccessBlocked(f"manifest source URI is missing for {bids_path}")
        bounds = windows[bids_path]
        bounded_requests.append(
            BoundedObjectRequest(
                dataset_id=dataset,
                bids_path=bids_path,
                source_uri=source_uri,
                expected_size_bytes=size,
                source_sha256=checksum,
                cache_root=cache_root,
                output_root=output_root,
                max_cache_bytes=max_cache_bytes,
                chunk_range=ChunkRange(
                    int(bounds["start_byte"]),
                    int(bounds["end_byte"]),
                    total_file_size=size,
                ),
                final_consumer=final_consumer,
                eviction_metadata=eviction_metadata,
                allow_network=allow_network,
            )
        )
    return {"requests": [request.to_dict() for request in bounded_requests], "network_accessed": False}


def _recordings(data_root: Path, task: str) -> dict[str, Path]:
    """Find one local BrainVision/EDF/FIF recording per subject and task."""
    found: dict[str, Path] = {}
    patterns = (f"*task-{task}*_eeg.vhdr", f"*task-{task}*_eeg.edf", f"*task-{task}*_eeg.fif", f"*task-{task}*_meg.fif")
    for pattern in patterns:
        for path in sorted(data_root.rglob(pattern)):
            match = re.search(r"(?:^|[/\\])(sub-[^/\\]+)", str(path))
            if match:
                found.setdefault(match.group(1), path)
    return found


def _read_window(path: Path, sample_rate_hz: float, window_s: float, beta_low_hz: float, beta_high_hz: float, max_samples: int) -> tuple[np.ndarray, float]:
    """Read one bounded EEG window and extract analytic beta-band phases."""
    import mne
    suffix = path.suffix.lower()
    if suffix == ".vhdr":
        raw = mne.io.read_raw_brainvision(path, preload=False, verbose="ERROR")
    elif suffix == ".edf":
        raw = mne.io.read_raw_edf(path, preload=False, verbose="ERROR")
    elif suffix == ".fif":
        raw = mne.io.read_raw_fif(path, preload=False, verbose="ERROR")
    else:
        raise ValueError(f"unsupported EEG file: {path}")
    actual_rate = float(raw.info["sfreq"])
    if sample_rate_hz > 0 and not np.isclose(actual_rate, sample_rate_hz, rtol=1e-3):
        raise ValueError(f"sampling-rate mismatch for {path}: file={actual_rate}, requested={sample_rate_hz}")
    count = min(int(round(window_s * actual_rate)), int(raw.n_times), max_samples)
    if count < 32:
        raise ValueError(f"recording window is too short for topology: {path}")
    data = raw.get_data(start=0, stop=count, reject_by_annotation="omit")
    if not np.all(np.isfinite(data)):
        raise ValueError(f"non-finite EEG values in {path}")
    data -= np.mean(data, axis=1, keepdims=True)
    scale = np.std(data, axis=1, keepdims=True)
    data /= np.where(scale > 0, scale, 1.0)
    filtered = mne.filter.filter_data(data, actual_rate, beta_low_hz, beta_high_hz, method="iir", verbose="ERROR")
    return np.unwrap(np.angle(hilbert(filtered, axis=1)), axis=1), actual_rate


def _plv(phases: np.ndarray) -> np.ndarray:
    """Compute the C-by-C phase-locking value matrix."""
    differences = phases[:, None, :] - phases[None, :, :]
    result = np.abs(np.mean(np.exp(1j * differences), axis=2))
    np.fill_diagonal(result, 0.0)
    return np.asarray((result + result.T) / 2.0, float)


def _persistent_features(plv: np.ndarray, filtration: np.ndarray) -> dict[str, Any]:
    """Compute H1 persistence and beta1 curves from PLV-derived distances."""
    try:
        from ripser import ripser
    except ImportError as exc:
        raise RuntimeError("ripser is required for persistent H1 analysis") from exc
    distance = np.clip(1.0 - plv, 0.0, 1.0)
    diagrams = ripser(distance, distance_matrix=True, maxdim=1, thresh=float(np.max(filtration)))['dgms'][1]
    finite = diagrams[np.isfinite(diagrams[:, 1])] if diagrams.size else np.empty((0, 2))
    betti = [int(np.sum((finite[:, 0] <= threshold) & (threshold < finite[:, 1]))) for threshold in filtration]
    persistence = np.maximum(0.0, finite[:, 1] - finite[:, 0]) if finite.size else np.empty(0)
    return {"betti1_curve": betti, "landscape_area_proxy": float(np.sum(persistence * persistence) / 2.0), "h1_intervals": finite.tolist(), "mean_betti1": float(np.mean(betti))}


def analyze_recording(path: Path, sample_rate_hz: float, window_s: float, beta_low_hz: float, beta_high_hz: float, filtration: np.ndarray, max_samples: int) -> dict[str, Any]:
    """Process a single bounded recording window."""
    phases, actual_rate = _read_window(path, sample_rate_hz, window_s, beta_low_hz, beta_high_hz, max_samples)
    plv = _plv(phases)
    feature = _persistent_features(plv, filtration)
    return {"path": str(path), "channels": int(phases.shape[0]), "samples": int(phases.shape[1]), "sample_rate_hz": actual_rate, "mean_plv": float(np.mean(plv)), **feature}


def run(data_root: Path, output: Path, snapshot: str, download: bool, sample_rate_hz: float, window_s: float, beta_low_hz: float, beta_high_hz: float, max_samples: int, *, allow_network: bool = False) -> dict[str, Any]:
    """Run paired awake/sedated analysis and a paired Wilcoxon test."""
    inventory = ensure_dataset(data_root, DATASET, snapshot, download, allow_network=allow_network)
    awake = _recordings(data_root, "awake")
    sedated = _recordings(data_root, "sed2")
    subjects = sorted(set(awake) & set(sedated))
    filtration = np.linspace(0.1, 0.9, 17)
    records = []
    for subject in subjects:
        records.append({"subject": subject, "awake": analyze_recording(awake[subject], sample_rate_hz, window_s, beta_low_hz, beta_high_hz, filtration, max_samples), "sedated": analyze_recording(sedated[subject], sample_rate_hz, window_s, beta_low_hz, beta_high_hz, filtration, max_samples)})
    awake_values = np.asarray([record["awake"]["landscape_area_proxy"] for record in records], float)
    sedated_values = np.asarray([record["sedated"]["landscape_area_proxy"] for record in records], float)
    if len(records) >= 2 and not np.allclose(awake_values, sedated_values):
        statistic, pvalue = wilcoxon(awake_values, sedated_values, alternative="two-sided", method="auto")
        test = {"status": "computed", "statistic": float(statistic), "pvalue": float(pvalue), "n_pairs": len(records)}
    else:
        test = {"status": "insufficient_paired_subjects_or_zero_difference", "statistic": None, "pvalue": None, "n_pairs": len(records)}
    payload = {"schema": "ScienceR-Dsim.ds005620EEGTopology.v1", "dataset": DATASET, "snapshot": snapshot, "inventory_files": len(inventory), "paired_subjects": len(records), "records": records, "wilcoxon_landscape_area": test, "filtration_thresholds": filtration.tolist(), "beta_band_hz": [beta_low_hz, beta_high_hz], "scientific_note": "PLV and H1 persistence are descriptive EEG network measures; a paired p-value does not establish consciousness mechanisms or quantum biology."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data/ds005620"))
    parser.add_argument("--snapshot", default="1.0.0")
    parser.add_argument("--download", action="store_true", help="Deprecated and rejected: full-dataset downloads are not supported")
    parser.add_argument("--allow-network", action="store_true", help="Explicitly allow metadata inventory access")
    parser.add_argument("--sample-rate-hz", type=float, default=5000.0)
    parser.add_argument("--window-s", type=float, default=10.0)
    parser.add_argument("--beta-low-hz", type=float, default=13.0)
    parser.add_argument("--beta-high-hz", type=float, default=20.0)
    parser.add_argument("--max-samples", type=int, default=50000)
    parser.add_argument("--output", type=Path, default=Path("artifacts/topology_monitoring/ds005620/cohort_topology.json"))
    args = parser.parse_args()
    if args.sample_rate_hz <= 2.0 * args.beta_high_hz or args.window_s <= 0 or args.max_samples < 32:
        parser.error("sampling rate must satisfy Nyquist and window/max-samples must be positive")
    try:
        run(args.data_root, args.output, args.snapshot, args.download, args.sample_rate_hz, args.window_s, args.beta_low_hz, args.beta_high_hz, args.max_samples, allow_network=args.allow_network)
    except DataAccessBlocked as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
