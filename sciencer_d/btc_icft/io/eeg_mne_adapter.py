from __future__ import annotations

import csv
import hashlib
import importlib
import importlib.util
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

SUPPORTED_EXTENSIONS = {
    ".edf", ".bdf", ".gdf", ".set", ".fdt",
    ".vhdr", ".vmrk", ".eeg", ".cnt", ".fif", ".fif.gz",
}
BANNED_PHRASES = (
    "proves consciousness", "consciousness proven", "soul proven", "afterlife proven",
    "liberation detected", "ontology solved", "ultimate reality", "q equals self", "q equals soul",
    "q_abs equals suffering", "f_dress equals karma", "sedated implies no_experience",
    "unresponsive implies unconscious", "topology proves liberation", "eeg proves consciousness",
)
SAFE_CLAIM = "Local EEG data were extracted through an optional MNE adapter into fixed signal windows without inferring labels or targets."


@dataclass
class MNESignalChunk:
    """Descriptor and data payload for a memory-bounded streaming EEG/MEG chunk."""
    chunk_index: int
    chunk_start_s: float
    chunk_end_s: float
    sample_start: int
    sample_end: int
    sfreq: float
    n_channels: int
    n_samples: int
    channel_names: list[str]
    channel_types: list[str]
    units: dict[str, str]
    data: Any
    annotations: list[dict]
    source_file: str
    source_sha256: str
    montage_coordinates: dict[str, list[float]]
    montage_source: str
    unmatched_channels: list[str]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        if hasattr(self.data, "tolist"):
            d["data"] = self.data.tolist()
        return d


@dataclass
class MNESignalExtractionWindow:
    dataset_id: str
    row_id: str
    source_file: str
    window_id: str
    window_start_s: float
    window_end_s: float
    sample_start: int
    sample_end: int
    sample_rate_hz: float
    n_channels: int
    n_samples: int
    channel_names: list[str]
    signal_values: list[list[float]]
    extraction_status: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class MNESignalExtractionResult:
    dataset_id: str
    source_file: str
    mne_available: bool
    mne_version: str | None
    supported_file: bool
    file_format: str
    sample_rate_hz: float | None
    n_channels: int
    channel_names: list[str]
    duration_s: float | None
    n_windows: int
    windows: list[dict]
    extraction_status: str
    extraction_blockers: list[str]
    output_contract: dict
    omega_event: dict
    safe_claim: str
    forbidden_claims: list[str]
    warnings: list[str]


def _validate_safe_text(text: str) -> None:
    t = text.lower()
    for p in BANNED_PHRASES:
        if p in t:
            raise ValueError(f"Banned phrase detected: {p}")


def check_mne_available() -> dict:
    available = importlib.util.find_spec("mne") is not None
    ver = None
    if available:
        try:
            ver = getattr(importlib.import_module("mne"), "__version__", None)
        except Exception:
            ver = None
    return {"installed": available, "version": ver}


def compute_file_sha256(path: str | Path, block_size: int = 65536) -> str:
    """Compute SHA-256 checksum of a file for provenance tracking."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(block_size):
            h.update(chunk)
    return h.hexdigest()


def detect_mne_supported_file(path: str) -> dict:
    p = Path(path)
    name_lower = p.name.lower()
    if name_lower.endswith(".fif.gz"):
        ext = ".fif.gz"
    else:
        ext = p.suffix.lower()
    return {"supported": ext in SUPPORTED_EXTENSIONS, "extension": ext, "file_format": ext.lstrip(".") if ext else "unknown"}


def resolve_montage_coordinates(
    raw,
    fallback_montages: tuple[str, ...] = ("standard_1020", "standard_1005"),
) -> dict:
    """Extract sensor coordinates from raw or resolve against standard montages.

    Preserves SI units (meters) for electrode coordinates.
    """
    coordinates: dict[str, list[float]] = {}
    matched: list[str] = []
    unmatched: list[str] = []
    warnings: list[str] = []
    montage_source = "none"

    ch_names = list(raw.ch_names)

    # 1. Check if raw info already contains sensor positions
    has_raw_coords = False
    if hasattr(raw, "info") and "chs" in raw.info:
        for ch_info in raw.info["chs"]:
            name = ch_info.get("ch_name")
            loc = ch_info.get("loc")
            if loc is not None and len(loc) >= 3:
                pos = [float(loc[0]), float(loc[1]), float(loc[2])]
                if any(x != 0.0 and not math.isnan(x) for x in pos):
                    coordinates[name] = pos
                    matched.append(name)
                    has_raw_coords = True

    if has_raw_coords and len(matched) > 0:
        montage_source = "raw_montage"
        for ch in ch_names:
            if ch not in coordinates:
                unmatched.append(ch)
                warnings.append(f"Channel {ch!r} missing sensor coordinates in raw montage.")
        return {
            "coordinates": coordinates,
            "matched_channels": matched,
            "unmatched_channels": unmatched,
            "montage_source": montage_source,
            "warnings": warnings,
        }

    # 2. Fallback to standard montages (standard_1020, standard_1005)
    mne_mod = None
    try:
        mne_mod = importlib.import_module("mne")
    except Exception:
        pass

    if mne_mod is not None and hasattr(mne_mod, "channels"):
        for mont_name in fallback_montages:
            try:
                std_mont = mne_mod.channels.make_standard_montage(mont_name)
                pos_dict = std_mont.get_positions().get("ch_pos", {})
                norm_pos = {k.strip().upper(): (k, [float(c) for c in v]) for k, v in pos_dict.items()}

                cur_coords: dict[str, list[float]] = {}
                cur_matched: list[str] = []
                cur_unmatched: list[str] = []

                for ch in ch_names:
                    ch_clean = ch.strip().upper()
                    if ch_clean.startswith("EEG "):
                        ch_clean = ch_clean[4:].strip()
                    elif ch_clean.startswith("EEG-"):
                        ch_clean = ch_clean[4:].strip()

                    if ch_clean in norm_pos:
                        cur_coords[ch] = norm_pos[ch_clean][1]
                        cur_matched.append(ch)
                    else:
                        cur_unmatched.append(ch)

                if cur_matched:
                    coordinates = cur_coords
                    matched = cur_matched
                    unmatched = cur_unmatched
                    montage_source = mont_name
                    for un in unmatched:
                        warnings.append(f"Channel {un!r} unmatched in standard montage {mont_name}.")
                    break
            except Exception as e:
                warnings.append(f"Failed loading fallback montage {mont_name}: {e}")

    if not coordinates:
        montage_source = "none"
        unmatched = list(ch_names)
        warnings.append("No 3D sensor coordinates resolved from raw or standard montages.")

    return {
        "coordinates": coordinates,
        "matched_channels": matched,
        "unmatched_channels": unmatched,
        "montage_source": montage_source,
        "warnings": warnings,
    }


def _init_result(dataset_id: str, path: str, status: str, blockers: list[str], supported: bool, fmt: str, mne_meta: dict) -> MNESignalExtractionResult:
    res = MNESignalExtractionResult(dataset_id, str(path), mne_meta["installed"], mne_meta.get("version"), supported, fmt, None, 0, [], None, 0, [], status, blockers, {}, {}, SAFE_CLAIM, [], [])
    res.output_contract = {"artifacts": ["mne_signal_metadata.json", "mne_signal_windows.csv", "mne_signal_window_values.json", "mne_extraction_report.json", "omega_event.json", "report.md"]}
    res.omega_event = build_mne_adapter_omega_event(res)
    return res


def _load_raw(path: str):
    mne = importlib.import_module("mne")
    p = Path(path)
    name_lower = p.name.lower()
    if name_lower.endswith((".fif", ".fif.gz")):
        return mne.io.read_raw_fif(path, preload=False, verbose="ERROR")
    ext = p.suffix.lower()
    if ext == ".edf":
        return mne.io.read_raw_edf(path, preload=False, verbose="ERROR")
    if ext == ".bdf":
        return mne.io.read_raw_bdf(path, preload=False, verbose="ERROR")
    if ext == ".gdf":
        if hasattr(mne.io, "read_raw_gdf"):
            return mne.io.read_raw_gdf(path, preload=False, verbose="ERROR")
        return mne.io.read_raw_edf(path, preload=False, verbose="ERROR")
    if ext in {".set", ".fdt"}:
        return mne.io.read_raw_eeglab(path, preload=False, verbose="ERROR")
    if ext in {".vhdr", ".vmrk", ".eeg"}:
        return mne.io.read_raw_brainvision(path, preload=False, verbose="ERROR")
    if ext == ".cnt":
        return mne.io.read_raw_cnt(path, preload=False, verbose="ERROR")
    raise ValueError(f"unsupported extension: {ext}")


def iter_mne_signal_chunks(
    path: str | Path,
    chunk_seconds: float = 2.0,
    picks: list[str] | None = None,
    start_s: float | None = None,
    stop_s: float | None = None,
    return_dict: bool = False,
    fallback_montages: tuple[str, ...] = ("standard_1020", "standard_1005"),
) -> Iterator[MNESignalChunk | dict]:
    """Stream EEG/MEG signal data chunk-by-chunk with bounded memory and provenance tracking.

    Parameters
    ----------
    path : str | Path
        Path to the recording file.
    chunk_seconds : float
        Length of each chunk in seconds (default: 2.0).
    picks : list[str] | None
        Channel names to pick. If None, all channels are extracted.
    start_s : float | None
        Start time in seconds. If None, begins at 0.0.
    stop_s : float | None
        Stop time in seconds. If None, streams until end of recording.
    return_dict : bool
        If True, yields dict; otherwise yields MNESignalChunk dataclass.
    fallback_montages : tuple[str, ...]
        Montages to try if raw has no sensor locations.

    Yields
    ------
    chunk : MNESignalChunk | dict
        Yields chunks with shape (n_channels, n_samples) and metadata.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Recording file not found: {path}")

    det = detect_mne_supported_file(str(p))
    if not det["supported"]:
        raise ValueError(f"Unsupported file format for MNE streaming: {det.get('extension')}")

    cap = check_mne_available()
    if not cap["installed"]:
        raise ImportError("mne package is required for iter_mne_signal_chunks but is not installed.")

    import numpy as np

    source_sha256 = compute_file_sha256(p)
    raw = _load_raw(str(p))

    # Enforce memory-bounded guarantee: raw must not be preloaded
    if getattr(raw, "preload", False) is True:
        raw.preload = False

    sfreq = float(raw.info.get("sfreq", 0.0))
    if sfreq <= 0:
        raise ValueError(f"Invalid sampling rate in recording: {sfreq}")

    all_ch_names = list(raw.ch_names)
    if picks is not None:
        indices = [i for i, ch in enumerate(all_ch_names) if ch in picks]
        if not indices:
            raise ValueError(f"None of the requested picks {picks} were found in channels {all_ch_names}")
        ch_names = [all_ch_names[i] for i in indices]
    else:
        indices = list(range(len(all_ch_names)))
        ch_names = all_ch_names

    try:
        ch_types = [raw.get_channel_types(picks=[i])[0] for i in indices]
    except Exception:
        ch_types = ["eeg"] * len(indices)

    units: dict[str, str] = {}
    for ch, t in zip(ch_names, ch_types):
        t_l = t.lower()
        if t_l in {"eeg", "seeg", "ecog"}:
            units[ch] = "V"
        elif t_l == "mag":
            units[ch] = "T"
        elif t_l == "grad":
            units[ch] = "T/m"
        else:
            units[ch] = "arbitrary"

    montage_info = resolve_montage_coordinates(raw, fallback_montages=fallback_montages)
    picked_coords = {ch: montage_info["coordinates"][ch] for ch in ch_names if ch in montage_info["coordinates"]}
    picked_matched = [ch for ch in ch_names if ch in montage_info["matched_channels"]]
    picked_unmatched = [ch for ch in ch_names if ch in montage_info["unmatched_channels"]]

    n_total = int(raw.n_times)
    s_start = max(0, int(round(start_s * sfreq))) if start_s is not None else 0
    s_stop = min(n_total, int(round(stop_s * sfreq))) if stop_s is not None else n_total

    if s_start >= s_stop:
        return

    chunk_samples = max(1, int(round(chunk_seconds * sfreq)))
    chunk_idx = 0
    curr_sample = s_start

    raw_annots = getattr(raw, "annotations", None)

    while curr_sample < s_stop:
        c_end_sample = min(curr_sample + chunk_samples, s_stop)
        c_start_s = curr_sample / sfreq
        c_end_s = c_end_sample / sfreq

        data_slice = raw.get_data(picks=indices, start=curr_sample, stop=c_end_sample)
        data_arr = np.asarray(data_slice, dtype=float)

        warnings: list[str] = list(montage_info.get("warnings", []))
        if not np.all(np.isfinite(data_arr)):
            warnings.append("non_finite_values_detected_in_chunk")
            data_arr = np.nan_to_num(data_arr, nan=0.0, posinf=0.0, neginf=0.0)

        chunk_annots: list[dict] = []
        if raw_annots is not None and len(raw_annots) > 0:
            for annot in raw_annots:
                onset = float(annot.get("onset", 0.0))
                dur = float(annot.get("duration", 0.0))
                desc = str(annot.get("description", ""))
                if onset <= c_end_s and (onset + dur) >= c_start_s:
                    chunk_annots.append({"onset": onset, "duration": dur, "description": desc})

        chunk = MNESignalChunk(
            chunk_index=chunk_idx,
            chunk_start_s=c_start_s,
            chunk_end_s=c_end_s,
            sample_start=curr_sample,
            sample_end=c_end_sample,
            sfreq=sfreq,
            n_channels=len(ch_names),
            n_samples=data_arr.shape[1],
            channel_names=ch_names,
            channel_types=ch_types,
            units=units,
            data=data_arr,
            annotations=chunk_annots,
            source_file=str(p),
            source_sha256=source_sha256,
            montage_coordinates=picked_coords,
            montage_source=montage_info["montage_source"],
            unmatched_channels=picked_unmatched,
            warnings=sorted(set(warnings)),
        )

        yield chunk.to_dict() if return_dict else chunk
        curr_sample = c_end_sample
        chunk_idx += 1


def load_mne_raw_metadata(path: str) -> dict:
    if not Path(path).exists():
        raise FileNotFoundError(path)
    det = detect_mne_supported_file(path)
    cap = check_mne_available()
    if not det["supported"] or not cap["installed"]:
        return {"sample_rate_hz": None, "n_channels": 0, "channel_names": [], "duration_s": None, "warnings": []}
    raw = _load_raw(path)
    sfreq = float(raw.info.get("sfreq", 0.0))
    ch = list(raw.ch_names)
    dur = float(raw.n_times / sfreq) if sfreq > 0 else None
    return {"sample_rate_hz": sfreq, "n_channels": len(ch), "channel_names": ch, "duration_s": dur, "warnings": []}


def extract_mne_signal_windows(path: str, dataset_id: str, window_seconds: float = 2.0, max_windows: int | None = None, picks: list[str] | None = None) -> MNESignalExtractionResult:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    det = detect_mne_supported_file(path)
    cap = check_mne_available()
    if not det["supported"]:
        return _init_result(dataset_id, path, "unsupported_extension", ["unsupported_extension"], False, det["file_format"], cap)
    if not cap["installed"]:
        return _init_result(dataset_id, path, "dependency_missing", ["optional_dependency_missing:mne"], True, det["file_format"], cap)
    try:
        raw = _load_raw(path)
    except Exception as e:
        r = _init_result(dataset_id, path, "read_error", ["mne_read_error"], True, det["file_format"], cap)
        r.warnings.append(str(e))
        return r
    sfreq = float(raw.info.get("sfreq", 0.0))
    ch_names = list(raw.ch_names)
    indices = list(range(len(ch_names)))
    if picks:
        sel = [i for i, n in enumerate(ch_names) if n in picks]
        if sel:
            indices = sel
            ch_names = [ch_names[i] for i in indices]
    n_total = int(raw.n_times)
    win_samples = max(1, int(sfreq * window_seconds)) if sfreq > 0 else 1
    n_windows = n_total // win_samples
    if max_windows is not None:
        n_windows = min(n_windows, max_windows)
    windows = []
    for i in range(n_windows):
        s0 = i * win_samples
        s1 = s0 + win_samples
        data = raw.get_data(picks=indices, start=s0, stop=s1)
        vals = []
        warn = []
        for row in data:
            conv = []
            for x in row.tolist():
                v = float(x)
                if math.isnan(v) or math.isinf(v):
                    warn.append("non_finite_replaced")
                    v = 0.0
                conv.append(v)
            vals.append(conv)
        w = MNESignalExtractionWindow(dataset_id, f"{p.stem}__win_{i}", str(p), f"win-{i:03d}", s0 / sfreq, s1 / sfreq, s0, s1, sfreq, len(indices), win_samples, ch_names, vals, "extracted", sorted(set(warn)))
        windows.append(asdict(w))
    r = MNESignalExtractionResult(dataset_id, str(p), True, cap.get("version"), True, det["file_format"], sfreq, len(indices), ch_names, (n_total / sfreq if sfreq else None), len(windows), windows, "extracted" if windows else "no_windows", [] if windows else ["no_complete_windows"], {}, {}, SAFE_CLAIM, [], [])
    r.output_contract = {"artifacts": ["mne_signal_metadata.json", "mne_signal_windows.csv", "mne_signal_window_values.json", "mne_extraction_report.json", "omega_event.json", "report.md"]}
    r.omega_event = build_mne_adapter_omega_event(r)
    return r


def build_mne_adapter_omega_event(result: MNESignalExtractionResult) -> dict:
    _validate_safe_text(result.safe_claim)
    return {"event_type": "eeg_mne_adapter", "dataset_id": result.dataset_id, "source_file": result.source_file, "extraction_status": result.extraction_status, "n_windows": result.n_windows, "safe_claim": result.safe_claim, "forbidden_claims": result.forbidden_claims}


def write_mne_signal_outputs(result: MNESignalExtractionResult, out_dir: str) -> dict[str, str]:
    _validate_safe_text(result.safe_claim)
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    files = {}
    meta = out / "mne_signal_metadata.json"; meta.write_text(json.dumps({"dataset_id": result.dataset_id, "source_file": result.source_file, "file_format": result.file_format, "mne_available": result.mne_available, "mne_version": result.mne_version, "sample_rate_hz": result.sample_rate_hz, "n_channels": result.n_channels, "channel_names": result.channel_names, "duration_s": result.duration_s, "extraction_status": result.extraction_status, "warnings": result.warnings}, indent=2)); files[meta.name]=str(meta)
    csvf = out / "mne_signal_windows.csv"
    cols=["dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end","sample_rate_hz","n_channels","n_samples","channel_names","extraction_status","warnings"]
    with csvf.open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for row in result.windows:
            row2={k:row.get(k) for k in cols}; row2["channel_names"]="|".join(row.get("channel_names",[])); row2["warnings"]="|".join(row.get("warnings",[])); w.writerow(row2)
    files[csvf.name]=str(csvf)
    vals = out/"mne_signal_window_values.json"; vals.write_text(json.dumps({"dataset_id":result.dataset_id,"source_file":result.source_file,"windows":[{"row_id":w["row_id"],"window_id":w["window_id"],"signal_values":w.get("signal_values",[]),"channel_names":w.get("channel_names",[])} for w in result.windows]},indent=2)); files[vals.name]=str(vals)
    repj = out/"mne_extraction_report.json"; repj.write_text(json.dumps({"dataset_id":result.dataset_id,"source_file":result.source_file,"supported_file":result.supported_file,"mne_available":result.mne_available,"extraction_status":result.extraction_status,"extraction_blockers":result.extraction_blockers,"n_windows":result.n_windows,"output_contract":result.output_contract,"ready_for_signal_block_conversion":result.extraction_status=="extracted" and result.n_windows>0,"warnings":result.warnings}, indent=2)); files[repj.name]=str(repj)
    omg = out/"omega_event.json"; omg.write_text(json.dumps(result.omega_event, indent=2)); files[omg.name]=str(omg)
    md = out/"report.md"; md.write_text("\n".join(["# MNE EEG Signal Extraction Prototype","","## Stage","P19.1 optional MNE adapter reader prototype.","","## Dataset",result.dataset_id,"","## Source file",result.source_file,"","## Dependency status",f"mne_available: {result.mne_available}","","## Extraction status",result.extraction_status,"","## Window summary",f"n_windows: {result.n_windows}","","## Blockers",json.dumps(result.extraction_blockers),"","## Safe claim",result.safe_claim,"","## Forbidden claims","- None","","## Next required step","Convert extracted windows into the canonical P8.2/P9 signal-block path only after validating local file provenance and extraction quality.","","This optional MNE adapter exports fixed signal windows without inferring labels or targets."]), encoding="utf-8")
    _validate_safe_text(md.read_text())
    files[md.name]=str(md)
    return files
