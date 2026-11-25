"""Chunked OpenNeuro stimulus-onset sweep through the approved bounded-range adapter.

Every EEG byte is requested through ``ApprovedAcquisitionAdapter`` as one bounded byte
range per epoch: a TMS epoch, or a matched control window at a time with no stimulus
nearby. Each chunk is read, reduced to a transition-index vector, acknowledged with
``consume()``, and deleted by the adapter's ``delete_on_final_consumer`` policy before the
next chunk is requested. Only small sidecar files (BrainVision header and marker file,
events table, dataset description) are fetched whole, under a hard byte cap, because the
adapter's contract rejects whole-object requests by design.

Scientific status: the transition index is an operational definition written for the
stimulus-onset sweep criterion (see ``TRANSITION_INDEX_DEFINITION``). Its outputs are
empirical observations on the recordings processed. A verdict on the stated criterion is
not confirmation of the causal claim the criterion was written to test.
"""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np
from scipy.spatial import Delaunay
from scipy.stats import rankdata

S3_BASE_URL = "https://s3.amazonaws.com/openneuro.org"
METADATA_CAP_BYTES = 1024 * 1024
PRE_MS = 500.0
POST_MS = 600.0
LAG_MS = 10
WINDOW_HALF_MS = 5.0
ARTIFACT_MS = (0.0, 15.0)
CONTROL_EXCLUSION_MS = 1000.0
ALPHA_BAND = {"alpha": (8.0, 13.0)}
CONSUMER_ID = "transition_index"
MONTAGE = "colin27_1005"
# Stimulus task per dataset. Only datasets whose stimulus events are confirmed are listed.
# ds002094: single-pulse TMS-EEG; 'tmseeg1' recordings carry R128 response markers at ~5 s spacing.
TASK_BY_DATASET = {"ds002094": "tmseeg1"}
TRANSITION_INDEX_DEFINITION = (
    "For each epoch: linear interpolation of the TMS artifact window [0, 15) ms per channel; "
    "alpha-band (8-13 Hz) analytic phase; geometry-aware phase-grid Qabs (repository "
    "phase_grid_topology_from_band on the colin27_1005 montage triangulation) averaged over a "
    "10 ms window centred at each offset tau; transition index(tau) = |Qabs(tau) - Qabs(tau - 10 ms)|, "
    "snapped to the 1/51 grid of integer window sums (float residue removed; off-grid values raise). "
    "Offsets in [0, 50) ms are not evaluated (artifact exclusion)."
)


class ChunkAcquisitionError(RuntimeError):
    """A bounded chunk could not be acquired or verified through the approved adapter."""


class MetadataCapError(ValueError):
    """A sidecar metadata object exceeded the hard byte cap or has an unusable size."""


# ── BrainVision header and events ────────────────────────────────────────────

_BV_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9]*)=(.*)$")
_BV_DTYPES = {"IEEE_FLOAT_32": "<f4", "INT_16": "<i2"}


@dataclass(frozen=True)
class BrainVisionHeader:
    data_file: str
    orientation: str
    binary_format: str
    channel_names: tuple[str, ...]
    sampling_interval_us: float

    @property
    def n_channels(self) -> int:
        return len(self.channel_names)

    @property
    def sfreq(self) -> float:
        return 1e6 / self.sampling_interval_us

    @property
    def dtype(self) -> str:
        return _BV_DTYPES[self.binary_format]

    @property
    def bytes_per_sample(self) -> int:
        return int(np.dtype(self.dtype).itemsize)

    @property
    def frame_bytes(self) -> int:
        """Bytes for one multiplexed time point across all channels."""
        return self.n_channels * self.bytes_per_sample


def parse_brainvision_header(text: str) -> BrainVisionHeader:
    """Parse a BrainVision ``.vhdr``. Fails closed on layouts this reader does not support."""
    fields: dict[str, str] = {}
    channels: dict[int, str] = {}
    section = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        match = _BV_LINE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if section == "Channel Infos" and re.fullmatch(r"Ch\d+", key):
            channels[int(key[2:])] = value.split(",")[0].strip()
        else:
            fields.setdefault(key, value)
    for required in ("DataFile", "DataOrientation", "BinaryFormat", "SamplingInterval"):
        if required not in fields:
            raise ValueError(f"BrainVision header is missing {required}")
    orientation = fields["DataOrientation"].upper()
    if orientation != "MULTIPLEXED":
        raise ValueError(f"unsupported DataOrientation {orientation!r}: only MULTIPLEXED is supported")
    binary_format = fields["BinaryFormat"].upper()
    if binary_format not in _BV_DTYPES:
        raise ValueError(f"unsupported BinaryFormat {binary_format!r}")
    names = tuple(channels[i] for i in sorted(channels))
    if not names or len(set(names)) != len(names):
        raise ValueError("BrainVision channel names are missing or duplicated")
    if "NumberOfChannels" in fields and int(fields["NumberOfChannels"]) != len(names):
        raise ValueError("NumberOfChannels disagrees with the channel table")
    interval = float(fields["SamplingInterval"])
    if not np.isfinite(interval) or interval <= 0:
        raise ValueError("SamplingInterval must be a positive finite number of microseconds")
    data_file = fields["DataFile"]
    if "/" in data_file or "\\" in data_file or data_file in {"", ".", ".."}:
        raise ValueError("DataFile must be a bare file name in the same folder as the header")
    return BrainVisionHeader(
        data_file=data_file,
        orientation=orientation,
        binary_format=binary_format,
        channel_names=names,
        sampling_interval_us=interval,
    )


def tms_onset_samples(events_tsv: str, *, event_type: str = "Response", value: str = "R128") -> np.ndarray:
    """Return zero-based stimulus sample indices from a BIDS events table.

    BIDS ``sample`` is one-based (the BrainVision marker position), so the index is ``sample - 1``.
    """
    reader = csv.DictReader(io.StringIO(events_tsv), delimiter="\t")
    columns = set(reader.fieldnames or [])
    if not {"type", "value", "sample"} <= columns:
        raise ValueError("events table must contain type, value and sample columns")
    samples = sorted({int(row["sample"]) - 1 for row in reader if row["type"] == event_type and row["value"] == value})
    if not samples:
        raise ValueError(f"no stimulus events of type {event_type!r} value {value!r}")
    return np.asarray(samples, dtype=np.int64)


# ── network: listing, capped sidecars, licence ───────────────────────────────

def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def list_prefix(base_url: str, prefix: str, *, delimiter: Optional[str] = None, timeout: float = 60.0) -> tuple[dict[str, int], list[str]]:
    """List keys (with sizes) and common prefixes under ``prefix`` via the S3 ListObjectsV2 API.

    Listing returns object names and sizes only; it never transfers object content.
    """
    keys: dict[str, int] = {}
    common: list[str] = []
    token: Optional[str] = None
    while True:
        params: dict[str, str] = {"list-type": "2", "prefix": prefix}
        if delimiter:
            params["delimiter"] = delimiter
        if token:
            params["continuation-token"] = token
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            root = ET.fromstring(resp.read())
        truncated = False
        token = None
        for child in list(root):
            name = _local_name(child.tag)
            if name == "Contents":
                key = size = None
                for item in child:
                    if _local_name(item.tag) == "Key":
                        key = item.text
                    elif _local_name(item.tag) == "Size":
                        size = int(item.text or 0)
                if key is not None:
                    keys[key] = int(size or 0)
            elif name == "CommonPrefixes":
                for item in child:
                    if _local_name(item.tag) == "Prefix" and item.text:
                        common.append(item.text)
            elif name == "IsTruncated":
                truncated = (child.text or "").strip().lower() == "true"
            elif name == "NextContinuationToken":
                token = child.text
        if not truncated or not token:
            break
    return keys, sorted(set(common))


def fetch_small_object(url: str, *, cap_bytes: int = METADATA_CAP_BYTES, timeout: float = 60.0) -> bytes:
    """Fetch a whole sidecar file whose size is known and at most ``cap_bytes``.

    This path is for metadata sidecars only. EEG data is never fetched through it.
    """
    head = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(head, timeout=timeout) as resp:
        size = int(resp.headers.get("Content-Length") or -1)
    if size < 0 or size > cap_bytes:
        raise MetadataCapError(f"metadata object size {size} is outside the 0..{cap_bytes} byte cap")
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        body = resp.read(cap_bytes + 1)
    if len(body) != size:
        raise IOError(f"incomplete metadata transfer: {len(body)} != {size}")
    return body


def _head_size(url: str, *, timeout: float = 60.0) -> int:
    """Size in bytes from a HEAD request. No object content is transferred."""
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        length = resp.headers.get("Content-Length")
    if not length or int(length) < 0:
        raise IOError(f"HEAD returned no usable Content-Length for {url}")
    return int(length)


def license_state_from_description(text: str) -> str:
    """Map a BIDS ``License`` string onto the adapter's licence states. Unknown licences stay blocked."""
    try:
        license_text = str(json.loads(text).get("License", ""))
    except (ValueError, AttributeError):
        return "unknown_blocked"
    normalized = re.sub(r"[\s\-_]", "", license_text).lower()
    if normalized.startswith("cc0"):
        return "open_cc0"
    if normalized.startswith("ccby") and "nc" not in normalized and "nd" not in normalized:
        return "open_cc_by"
    return "unknown_blocked"


# ── chunk acquisition through the approved adapter ───────────────────────────

@dataclass
class ChunkRecord:
    chunk_index: int
    object_path: str
    start_byte: int
    end_byte: int
    bytes_transferred: int
    evicted: bool
    checksum_verified: bool


class ApprovedChunkReader:
    """Reads one bounded byte range per call and deletes it after consumption."""

    def __init__(
        self,
        adapter: Any,
        *,
        dataset_id: str,
        base_url: str,
        allow_network: bool,
        license_state: str,
    ) -> None:
        self.adapter = adapter
        self.dataset_id = dataset_id
        self.base_url = base_url.rstrip("/")
        self.allow_network = bool(allow_network)
        self.license_state = license_state
        self.records: list[ChunkRecord] = []

    def url(self, key: str) -> str:
        return f"{self.base_url}/{self.dataset_id}/{key}"

    def read_range(self, *, key: str, expected_size: int, start_byte: int, end_byte: int, chunk_index: int) -> bytes:
        from tools.data_access.approved_adapter import (
            BoundedAcquisitionRequest,
            ChecksumPolicy,
            EvictionPolicy,
            SourceCatalogType,
        )

        request = BoundedAcquisitionRequest(
            dataset_id=self.dataset_id,
            object_path=key,
            source_uri=self.url(key),
            expected_size_bytes=int(expected_size),
            start_byte=int(start_byte),
            end_byte=int(end_byte),
            catalog_type=SourceCatalogType.OPENNEURO.value,
            checksum_policy=ChecksumPolicy.SHA256_IF_AVAILABLE.value,
            expected_checksum=None,
            eviction_policy=EvictionPolicy.DELETE_ON_FINAL_CONSUMER.value,
            allow_network=self.allow_network,
            license_state=self.license_state,
            declared_consumers=[CONSUMER_ID],
        )
        result = self.adapter.acquire(request, chunk_index=chunk_index)
        if not result.success or not result.cached_path:
            raise ChunkAcquisitionError(f"{result.error_code}: {result.error_message}")
        data = b""
        try:
            data = Path(result.cached_path).read_bytes()
        finally:
            ack = self.adapter.consume(self.dataset_id, key, CONSUMER_ID, chunk_index=chunk_index)
            self.records.append(
                ChunkRecord(
                    chunk_index=int(chunk_index),
                    object_path=key,
                    start_byte=int(start_byte),
                    end_byte=int(end_byte),
                    bytes_transferred=int(result.bytes_transferred),
                    evicted=bool(ack.get("evicted")) and not Path(result.cached_path).exists(),
                    checksum_verified=bool(result.checksum_verified),
                )
            )
        expected_length = int(end_byte) - int(start_byte) + 1
        if len(data) != expected_length:
            raise ChunkAcquisitionError(f"chunk length {len(data)} != requested {expected_length}")
        return data


# ── transition index ─────────────────────────────────────────────────────────

def _geometry(channel_names: Sequence[str], sfreq: float) -> tuple[list[str], np.ndarray, np.ndarray, list[int]]:
    """Montage positions, triangulation and header indices of the channels that have positions."""
    import mne

    from validation.montage_topology import get_channel_xy

    names = list(channel_names)
    info = mne.create_info(names, sfreq, ch_types="eeg")
    raw = mne.io.RawArray(np.zeros((len(names), 1)), info, verbose=False)
    with mne.utils.use_log_level("ERROR"):
        raw.set_montage(MONTAGE, on_missing="ignore", match_case=False)
        used, xy = get_channel_xy(raw, montage=MONTAGE)
    index = [names.index(name) for name in used]
    triangles = Delaunay(xy).simplices
    return list(used), np.asarray(xy, dtype=float), np.asarray(triangles, dtype=int), index


def _interpolate_artifact(signal: np.ndarray, start: int, stop: int) -> None:
    """Linear interpolation across [start, stop) per channel, in place."""
    if stop <= start or start < 1 or stop >= signal.shape[1]:
        return
    left = signal[:, start - 1]
    right = signal[:, stop]
    steps = np.arange(1, stop - start + 1) / (stop - start + 1)
    signal[:, start:stop] = left[:, None] + (right - left)[:, None] * steps[None, :]


def transition_index_vector(
    samples: np.ndarray,
    *,
    sfreq: float,
    xy: np.ndarray,
    triangles: np.ndarray,
    onset_index: int,
    offsets_ms: Sequence[int],
) -> np.ndarray:
    """Transition index at each offset, for one epoch (channels x time, already in geometry order)."""
    from validation.analytic_phase import analytic_phases_by_band
    from validation.montage_topology import phase_grid_topology_from_band

    signal = np.array(samples, dtype=float, copy=True)
    art_start = onset_index + int(round(ARTIFACT_MS[0] * sfreq / 1000.0))
    art_stop = onset_index + int(round(ARTIFACT_MS[1] * sfreq / 1000.0))
    _interpolate_artifact(signal, art_start, art_stop)
    phases = analytic_phases_by_band(signal, sfreq, ALPHA_BAND)["alpha"]
    half = int(round(WINDOW_HALF_MS * sfreq / 1000.0))
    centres = sorted({int(t) for t in offsets_ms} | {int(t) - LAG_MS for t in offsets_ms})
    qabs: dict[int, float] = {}
    for tau in centres:
        centre = onset_index + int(round(tau * sfreq / 1000.0))
        window = phases[:, centre - half: centre + half + 1]
        qabs[tau] = float(phase_grid_topology_from_band(window, xy, triangles)["Qabs"])
    # Each window mean is an integer sum of per-sample windings over (2*half+1) samples, so every
    # difference lies on the grid k / (2*half+1). Float residue (~1e-16) is removed by snapping to that
    # grid; a value that is off the grid by more than 1e-6 means the readout is not quantized, so fail.
    grid = float(2 * half + 1)
    steps = np.asarray([abs(qabs[int(t)] - qabs[int(t) - LAG_MS]) * grid for t in offsets_ms], dtype=float)
    if not np.all(np.isfinite(steps)) or float(np.max(np.abs(steps - np.round(steps)))) > 1e-6:
        raise ValueError("transition-index windows are off the integer-winding grid; the phase readout is not quantized")
    return np.round(steps) / grid


# ── statistics: AUC, leave-one-recording-out held-out AUC, label-shuffle null ─

def auc_score(labels: Sequence[int], scores: Sequence[float]) -> float:
    """Mann-Whitney AUC with average ranks for ties."""
    y = np.asarray(labels, dtype=int)
    s = np.asarray(scores, dtype=float)
    n_pos = int(np.sum(y == 1))
    n_neg = int(y.size - n_pos)
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = rankdata(s)
    return float((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def loso_heldout(recordings: Sequence[tuple[np.ndarray, np.ndarray]]) -> dict[str, Any]:
    """Leave-one-recording-out selection of the sweep offset, scored on the held-out recording.

    ``recordings`` is a list of ``(scores, labels)`` with ``scores`` shaped (epochs, offsets).
    The offset is chosen by training AUC on the other recordings; the held-out AUC is computed
    on the pooled out-of-fold scores.
    """
    if len(recordings) < 3:
        raise ValueError("held-out evaluation needs at least 3 recordings")
    n_offsets = recordings[0][0].shape[1]
    fold_scores: list[np.ndarray] = []
    fold_labels: list[np.ndarray] = []
    selected: list[int] = []
    for held in range(len(recordings)):
        train = [rec for i, rec in enumerate(recordings) if i != held]
        train_scores = np.vstack([s for s, _ in train])
        train_labels = np.concatenate([y for _, y in train])
        train_auc = np.asarray([auc_score(train_labels, train_scores[:, j]) for j in range(n_offsets)])
        best = int(np.nanargmax(train_auc))
        selected.append(best)
        held_scores, held_labels = recordings[held]
        fold_scores.append(held_scores[:, best])
        fold_labels.append(held_labels)
    pooled = auc_score(np.concatenate(fold_labels), np.concatenate(fold_scores))
    return {"heldout_auc": pooled, "selected_offset_index": selected}


def label_shuffle_null(recordings: Sequence[tuple[np.ndarray, np.ndarray]], *, n_shuffles: int, seed: int) -> np.ndarray:
    """Held-out AUC under within-recording label permutations, repeating the full offset selection."""
    rng = np.random.default_rng(seed)
    null = np.empty(int(n_shuffles), dtype=float)
    for b in range(int(n_shuffles)):
        permuted = [(scores, rng.permutation(labels)) for scores, labels in recordings]
        null[b] = loso_heldout(permuted)["heldout_auc"]
    return null


def permutation_p_value(observed: float, null: np.ndarray) -> float:
    """One-sided add-one p-value: P(null >= observed)."""
    return float((1.0 + np.sum(null >= observed)) / (1.0 + null.size))


# ── recording discovery and processing ───────────────────────────────────────

@dataclass(frozen=True)
class RecordingRef:
    subject: str
    header_key: str
    events_key: str
    listing: Mapping[str, int] = field(repr=False)


def discover_recordings(
    base_url: str,
    dataset_id: str,
    *,
    task: str,
    max_recordings: int,
) -> list[RecordingRef]:
    """Subjects in sorted order that have header, events and data for ``task``. Listing only."""
    _, subjects = list_prefix(base_url.rstrip("/"), f"{dataset_id}/", delimiter="/")
    found: list[RecordingRef] = []
    for prefix in subjects:
        subject = prefix.rstrip("/").rsplit("/", 1)[-1]
        if not subject.startswith("sub-"):
            continue
        bucket_listing, _ = list_prefix(base_url.rstrip("/"), f"{dataset_id}/{subject}/eeg/")
        # Listing keys are bucket-relative; everything below uses dataset-relative BIDS paths.
        listing = {key[len(dataset_id) + 1:]: size for key, size in bucket_listing.items()}
        header = [k for k in listing if k.endswith(f"_task-{task}_eeg.vhdr")]
        events = [k for k in listing if k.endswith(f"_task-{task}_events.tsv")]
        if not header or not events:
            continue
        found.append(RecordingRef(subject=subject, header_key=sorted(header)[0], events_key=sorted(events)[0], listing=listing))
        if len(found) >= max_recordings:
            break
    return found


@dataclass
class RecordingResult:
    subject: str
    scores: np.ndarray
    labels: np.ndarray
    kinds: list[str]
    onset_samples: list[int]
    chunks: list[ChunkRecord]
    skipped_edge: int
    channels_used: list[str]
    sfreq: float


def _choose_evenly(values: np.ndarray, k: int) -> np.ndarray:
    if values.size <= k:
        return values
    picks = np.linspace(0, values.size - 1, k).round().astype(int)
    return values[np.unique(picks)]


def _control_onsets(rng: np.random.Generator, n: int, lo: int, hi: int, stimuli: np.ndarray, exclusion: int) -> np.ndarray:
    """``n`` control samples in [lo, hi), each at least ``exclusion`` samples from every stimulus and every other control."""
    chosen: list[int] = []
    attempts = 0
    limit = 200 * max(n, 1) + 10_000
    while len(chosen) < n:
        attempts += 1
        if attempts > limit:
            raise ValueError("could not place enough control windows away from stimuli")
        candidate = int(rng.integers(lo, hi))
        if stimuli.size and float(np.min(np.abs(stimuli - candidate))) < exclusion:
            continue
        if chosen and float(np.min(np.abs(np.asarray(chosen) - candidate))) < exclusion:
            continue
        chosen.append(candidate)
    return np.asarray(chosen, dtype=np.int64)


def process_recording(
    reader: ApprovedChunkReader,
    ref: RecordingRef,
    *,
    task: str,
    max_epochs: int,
    seed: int,
    sweep_offsets_ms: Sequence[int],
) -> RecordingResult:
    header_text = fetch_small_object(reader.url(ref.header_key)).decode("utf-8", errors="replace")
    header = parse_brainvision_header(header_text)
    events = fetch_small_object(reader.url(ref.events_key)).decode("utf-8", errors="replace")
    stimuli = tms_onset_samples(events)

    data_key = ref.header_key.rsplit("/", 1)[0] + "/" + header.data_file
    if data_key not in ref.listing:
        raise ValueError(f"data file {header.data_file} is not listed next to the header")
    size = int(ref.listing[data_key])
    head_size = _head_size(reader.url(data_key))
    if head_size != size:
        raise ValueError(f"listed size {size} disagrees with HEAD size {head_size} for {data_key}")
    if size % header.frame_bytes != 0:
        raise ValueError("data size is not a whole number of multiplexed frames")
    n_samples = size // header.frame_bytes
    sfreq = header.sfreq
    pre = int(round(PRE_MS * sfreq / 1000.0))
    post = int(round(POST_MS * sfreq / 1000.0))
    exclusion = int(round(CONTROL_EXCLUSION_MS * sfreq / 1000.0))

    valid = stimuli[(stimuli - pre >= 0) & (stimuli + post <= n_samples)]
    skipped_edge = int(stimuli.size - valid.size)
    if valid.size == 0:
        raise ValueError("no stimulus has a complete epoch inside the recording")
    tms = _choose_evenly(valid, max_epochs)
    rng = np.random.default_rng(seed)
    controls = _control_onsets(rng, tms.size, pre, n_samples - post, stimuli, exclusion)

    xy_names, xy, triangles, channel_index = _geometry(header.channel_names, sfreq)
    offsets = [int(t) for t in sweep_offsets_ms]
    scores = np.zeros((tms.size + controls.size, len(offsets)), dtype=float)
    labels = np.concatenate([np.ones(tms.size, dtype=int), np.zeros(controls.size, dtype=int)])
    kinds = ["tms"] * tms.size + ["control"] * controls.size
    chunks: list[ChunkRecord] = []
    centres = list(tms) + list(controls)
    for index, centre in enumerate(centres):
        start = int(centre) - pre
        stop = int(centre) + post
        raw = reader.read_range(
            key=data_key,
            expected_size=size,
            start_byte=start * header.frame_bytes,
            end_byte=stop * header.frame_bytes - 1,
            chunk_index=index,
        )
        frames = np.frombuffer(raw, dtype=header.dtype).reshape(stop - start, header.n_channels)
        samples = frames.T.astype(float)[channel_index, :]
        scores[index, :] = transition_index_vector(
            samples,
            sfreq=sfreq,
            xy=xy,
            triangles=triangles,
            onset_index=pre,
            offsets_ms=offsets,
        )
        chunks.append(reader.records[-1])
    return RecordingResult(
        subject=ref.subject,
        scores=scores,
        labels=labels,
        kinds=kinds,
        onset_samples=[int(s) for s in tms],
        chunks=chunks,
        skipped_edge=skipped_edge,
        channels_used=list(xy_names),
        sfreq=sfreq,
    )


# ── top-level run ────────────────────────────────────────────────────────────

@dataclass
class StimulusSweepResult:
    metrics: dict[str, Any]
    epoch_rows: list[dict[str, Any]]
    chunk_rows: list[dict[str, Any]]
    scope: dict[str, Any]
    null_auc: np.ndarray


def sweep_offsets(sweep_range_ms: Sequence[int], step_ms: int, excluded_ms: Sequence[int]) -> list[int]:
    lo, hi = int(sweep_range_ms[0]), int(sweep_range_ms[1])
    step = int(step_ms)
    if step <= 0 or step != step_ms:
        raise ValueError("step_ms must be a positive integer number of milliseconds")
    excl_lo, excl_hi = int(excluded_ms[0]), int(excluded_ms[1])
    return [t for t in range(lo, hi + 1, step) if not (excl_lo <= t < excl_hi)]


def run_stimulus_sweep(
    *,
    adapter: Any,
    dataset_id: str,
    task: str = "tmseeg1",
    base_url: str = S3_BASE_URL,
    allow_network: bool,
    max_recordings: int,
    max_epochs_per_recording: int,
    n_shuffles: int,
    seed: int = 0,
    sweep_range_ms: Sequence[int] = (-200, 400),
    step_ms: int = 10,
    excluded_ms: Sequence[int] = (0, 50),
) -> StimulusSweepResult:
    if not allow_network:
        raise PermissionError("network access to OpenNeuro is not approved for this run")
    license_text = fetch_small_object(f"{base_url.rstrip('/')}/{dataset_id}/dataset_description.json").decode("utf-8", errors="replace")
    license_state = license_state_from_description(license_text)
    reader = ApprovedChunkReader(
        adapter,
        dataset_id=dataset_id,
        base_url=base_url,
        allow_network=allow_network,
        license_state=license_state,
    )
    offsets = sweep_offsets(sweep_range_ms, step_ms, excluded_ms)
    refs = discover_recordings(base_url, dataset_id, task=task, max_recordings=max_recordings)
    if len(refs) < 3:
        raise ValueError(f"found {len(refs)} recordings for task {task!r}; at least 3 are needed")
    results = []
    for index, ref in enumerate(refs):
        result = process_recording(
            reader,
            ref,
            task=task,
            max_epochs=max_epochs_per_recording,
            seed=int(seed) + index,
            sweep_offsets_ms=offsets,
        )
        results.append(result)
        transferred = sum(c.bytes_transferred for c in result.chunks)
        print(f"[openneuro] {ref.subject}: {len(result.chunks)} chunks, {transferred} bytes transferred, "
              f"{int(result.labels.sum())} TMS + {int((1 - result.labels).sum())} control epochs", flush=True)
    recordings = [(r.scores, r.labels) for r in results]
    held = loso_heldout(recordings)
    null = label_shuffle_null(recordings, n_shuffles=n_shuffles, seed=int(seed) + 10_000)
    p_value = permutation_p_value(held["heldout_auc"], null)
    fold_offsets = [offsets[i] for i in held["selected_offset_index"]]
    epoch_rows: list[dict[str, Any]] = []
    for result in results:
        for row_index, (kind, label) in enumerate(zip(result.kinds, result.labels)):
            epoch_rows.append({
                "subject": result.subject,
                "kind": kind,
                "label": int(label),
                **{f"TI_{t}ms": float(result.scores[row_index, j]) for j, t in enumerate(offsets)},
            })
    chunk_rows = [
        {"subject": r.subject, **vars(c)} for r in results for c in r.chunks
    ]
    residual = residual_cache_files(getattr(adapter, "cache_root", None))
    metrics = {
        "heldout_auc": float(held["heldout_auc"]),
        "p_value": float(p_value),
        "n_shuffles": int(n_shuffles),
        "n_recordings": int(len(results)),
        "n_epochs_tms": int(sum(int(r.labels.sum()) for r in results)),
        "n_epochs_control": int(sum(int((1 - r.labels).sum()) for r in results)),
        "bytes_transferred": int(sum(c["bytes_transferred"] for c in chunk_rows)),
        "chunks_consumed": int(len(chunk_rows)),
        "chunks_evicted": int(sum(1 for c in chunk_rows if c["evicted"])),
        "residual_cache_files": int(len(residual)),
        "best_offset_ms_per_fold": [int(t) for t in fold_offsets],
    }
    nonzero = np.mean(np.concatenate([r.scores for r in results]) > 0, axis=0)
    scope = {
        "dataset_id": dataset_id,
        "transition_index_nonzero_fraction_mean": float(np.mean(nonzero)),
        "transition_index_nonzero_fraction_by_offset": [float(v) for v in nonzero],
        "task": task,
        "license_state": license_state,
        "subjects": [r.subject for r in results],
        "skipped_stimuli_at_edges": {r.subject: r.skipped_edge for r in results},
        "channels_used": results[0].channels_used,
        "sfreq_hz": results[0].sfreq,
        "sweep_offsets_ms": offsets,
        "transition_index_definition": TRANSITION_INDEX_DEFINITION,
    }
    return StimulusSweepResult(metrics=metrics, epoch_rows=epoch_rows, chunk_rows=chunk_rows, scope=scope, null_auc=null)


def residual_cache_files(cache_root: Optional[object]) -> list[str]:
    """Files left under the cache root after consumption, excluding the adapter's JSON manifests."""
    if cache_root is None:
        return []
    root = Path(str(cache_root))
    if not root.exists():
        return []
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p.suffix != ".json")
