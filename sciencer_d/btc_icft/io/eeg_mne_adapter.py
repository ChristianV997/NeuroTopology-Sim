from __future__ import annotations

import csv
import importlib
import importlib.util
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

SUPPORTED_EXTENSIONS = {".edf", ".bdf", ".gdf", ".set", ".fdt", ".vhdr", ".vmrk", ".eeg", ".cnt", ".fif"}
BANNED_PHRASES = (
    "proves consciousness", "consciousness proven", "soul proven", "afterlife proven",
    "liberation detected", "ontology solved", "ultimate reality", "q equals self", "q equals soul",
    "q_abs equals suffering", "f_dress equals karma", "sedated implies no_experience",
    "unresponsive implies unconscious", "topology proves liberation", "eeg proves consciousness",
)
SAFE_CLAIM = "Local EEG data were extracted through an optional MNE adapter into fixed signal windows without inferring labels or targets."


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


def detect_mne_supported_file(path: str) -> dict:
    ext = Path(path).suffix.lower()
    return {"supported": ext in SUPPORTED_EXTENSIONS, "extension": ext, "file_format": ext.lstrip(".") if ext else "unknown"}


def _init_result(dataset_id: str, path: str, status: str, blockers: list[str], supported: bool, fmt: str, mne_meta: dict) -> MNESignalExtractionResult:
    res = MNESignalExtractionResult(dataset_id, str(path), mne_meta["installed"], mne_meta.get("version"), supported, fmt, None, 0, [], None, 0, [], status, blockers, {}, {}, SAFE_CLAIM, [], [])
    res.output_contract = {"artifacts": ["mne_signal_metadata.json", "mne_signal_windows.csv", "mne_signal_window_values.json", "mne_extraction_report.json", "omega_event.json", "report.md"]}
    res.omega_event = build_mne_adapter_omega_event(res)
    return res


def _load_raw(path: str):
    mne = importlib.import_module("mne")
    ext = Path(path).suffix.lower()
    if ext in {".edf", ".gdf"}: return mne.io.read_raw_edf(path, preload=False, verbose="ERROR")
    if ext == ".bdf": return mne.io.read_raw_bdf(path, preload=False, verbose="ERROR")
    if ext == ".fif": return mne.io.read_raw_fif(path, preload=False, verbose="ERROR")
    if ext in {".set", ".fdt"}: return mne.io.read_raw_eeglab(path, preload=False, verbose="ERROR")
    if ext in {".vhdr", ".vmrk", ".eeg"}: return mne.io.read_raw_brainvision(path, preload=False, verbose="ERROR")
    if ext == ".cnt": return mne.io.read_raw_cnt(path, preload=False, verbose="ERROR")
    raise ValueError("unsupported extension")


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
