from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

BANNED_PHRASES = (
    "proves consciousness", "consciousness proven", "soul proven", "afterlife proven",
    "liberation detected", "ontology solved", "ultimate reality", "q equals self", "q equals soul",
    "q_abs equals suffering", "f_dress equals karma", "sedated implies no_experience",
    "unresponsive implies unconscious", "topology proves liberation", "eeg proves consciousness",
)
SAFE_CLAIM = "MNE extraction outputs were converted into canonical signal-block artifacts for downstream Level M and Level T processing without inferring labels or targets."
STRICT_JOIN_KEYS = ["dataset_id", "row_id", "source_file", "window_id", "window_start_s", "window_end_s", "sample_start", "sample_end"]


def _validate_safe_text(text: str) -> None:
    lower = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lower:
            raise ValueError(f"Banned phrase detected: {phrase}")


@dataclass
class CanonicalSignalBlockWindow:
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
    conversion_status: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class MNESignalBlockConversionResult:
    dataset_id: str
    source_file: str
    input_extraction_status: str
    conversion_status: str
    n_input_windows: int
    n_converted_windows: int
    n_rejected_windows: int
    windows: list[dict]
    rejected_windows: list[dict]
    signal_block_inventory: dict
    reader_alignment_report: dict
    ready_for_level_m_signal: bool
    ready_for_level_t_signal: bool
    conversion_blockers: list[str]
    omega_event: dict
    safe_claim: str
    forbidden_claims: list[str]
    warnings: list[str]


def load_mne_signal_metadata(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_mne_signal_windows(path: str) -> list[dict]:
    rows = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for k in ["window_start_s", "window_end_s", "sample_rate_hz"]:
                row[k] = float(row[k])
            for k in ["sample_start", "sample_end", "n_channels", "n_samples"]:
                row[k] = int(float(row[k]))
            row["channel_names"] = [c for c in row.get("channel_names", "").split("|") if c]
            row["warnings"] = [w for w in row.get("warnings", "").split("|") if w]
            rows.append(row)
    return rows


def load_mne_signal_window_values(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def convert_mne_windows_to_canonical_blocks(metadata: dict, windows: list[dict], values: dict, dataset_id: str) -> MNESignalBlockConversionResult:
    extraction_status = metadata.get("extraction_status", "unknown")
    source_file = metadata.get("source_file", values.get("source_file", "unknown"))
    blockers, warnings, out_windows, rejected = [], [], [], []
    if extraction_status != "extracted":
        blockers.append("input_not_extracted")
        status = "blocked_input_not_extracted"
    elif not windows:
        blockers.append("no_windows")
        status = "blocked_no_windows"
    else:
        status = "converted"

    values_by_row = {w.get("row_id"): w for w in values.get("windows", [])}
    values_by_win = {w.get("window_id"): w for w in values.get("windows", [])}

    for idx, w in enumerate(windows):
        row_id = w.get("row_id") or f"{Path(source_file).stem}__win_{idx}"
        found = values_by_row.get(row_id) or values_by_win.get(w.get("window_id"))
        local_warn = []
        reject_reason = None
        if found is None:
            reject_reason = "missing_signal_values"
        else:
            channel_names = w.get("channel_names", [])
            v_channels = found.get("channel_names", [])
            signal_values = found.get("signal_values", [])
            if channel_names != v_channels:
                reject_reason = "channel_names_mismatch"
            elif len(signal_values) != int(w.get("n_channels", 0)):
                reject_reason = "n_channels_mismatch"
            elif any(not isinstance(ch, list) for ch in signal_values):
                reject_reason = "invalid_signal_shape"
            elif any(len(ch) != int(w.get("n_samples", 0)) for ch in signal_values):
                reject_reason = "n_samples_mismatch"
            else:
                bad = False
                for ch in signal_values:
                    for x in ch:
                        if not isinstance(x, (int, float)) or math.isnan(float(x)) or math.isinf(float(x)):
                            bad = True
                            break
                    if bad:
                        break
                if bad:
                    reject_reason = "non_numeric_or_non_finite"
            if reject_reason is None:
                c = CanonicalSignalBlockWindow(dataset_id=dataset_id, row_id=row_id, source_file=w.get("source_file", source_file), window_id=w["window_id"], window_start_s=float(w["window_start_s"]), window_end_s=float(w["window_end_s"]), sample_start=int(w["sample_start"]), sample_end=int(w["sample_end"]), sample_rate_hz=float(w["sample_rate_hz"]), n_channels=int(w["n_channels"]), n_samples=int(w["n_samples"]), channel_names=channel_names, signal_values=signal_values, conversion_status="converted", warnings=local_warn)
                out_windows.append(asdict(c))
        if reject_reason is not None:
            rejected.append({"row_id": row_id, "window_id": w.get("window_id"), "reason": reject_reason})

    if extraction_status == "extracted" and windows and not out_windows:
        status = "blocked_all_windows_rejected"
        blockers.append("all_windows_rejected")
    ready = status == "converted" and len(out_windows) > 0

    result = MNESignalBlockConversionResult(dataset_id=dataset_id, source_file=source_file, input_extraction_status=extraction_status, conversion_status=status, n_input_windows=len(windows), n_converted_windows=len(out_windows), n_rejected_windows=len(rejected), windows=out_windows, rejected_windows=rejected, signal_block_inventory={}, reader_alignment_report={}, ready_for_level_m_signal=ready, ready_for_level_t_signal=ready, conversion_blockers=blockers, omega_event={}, safe_claim=SAFE_CLAIM, forbidden_claims=[], warnings=warnings)
    result.signal_block_inventory = build_signal_block_inventory(result)
    result.reader_alignment_report = build_reader_alignment_report(result)
    result.omega_event = build_mne_conversion_omega_event(result)
    return result


def build_signal_block_inventory(result: MNESignalBlockConversionResult) -> dict:
    return {"dataset_id": result.dataset_id, "source_file": result.source_file, "input_extraction_status": result.input_extraction_status, "conversion_status": result.conversion_status, "n_input_windows": result.n_input_windows, "n_converted_windows": result.n_converted_windows, "n_rejected_windows": result.n_rejected_windows, "ready_for_level_m_signal": result.ready_for_level_m_signal, "ready_for_level_t_signal": result.ready_for_level_t_signal, "conversion_blockers": result.conversion_blockers, "warnings": result.warnings}


def build_reader_alignment_report(result: MNESignalBlockConversionResult) -> dict:
    return {"dataset_id": result.dataset_id, "source_file": result.source_file, "p19_1_source": True, "p8_2_compatible": result.conversion_status == "converted", "ready_for_p9_level_m_signal": result.ready_for_level_m_signal, "ready_for_p10_level_t_signal": result.ready_for_level_t_signal, "strict_join_keys": STRICT_JOIN_KEYS, "warnings": result.warnings}


def build_mne_conversion_omega_event(result: MNESignalBlockConversionResult) -> dict:
    _validate_safe_text(result.safe_claim)
    return {"event_type": "mne_to_canonical_signal_block_conversion", "dataset_id": result.dataset_id, "source_file": result.source_file, "conversion_status": result.conversion_status, "n_converted_windows": result.n_converted_windows, "safe_claim": result.safe_claim, "forbidden_claims": result.forbidden_claims}


def write_mne_signal_block_outputs(result: MNESignalBlockConversionResult, out_dir: str) -> dict[str, str]:
    _validate_safe_text(result.safe_claim)
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    files = {}
    p = out / "signal_block_inventory.json"; p.write_text(json.dumps(result.signal_block_inventory, indent=2), encoding="utf-8"); files[p.name]=str(p)
    p = out / "window_inventory.csv"
    cols = ["dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end","sample_rate_hz","n_channels","n_samples","channel_names","conversion_status","warnings"]
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for row in result.windows:
            row2 = {k: row.get(k) for k in cols}; row2["channel_names"] = "|".join(row.get("channel_names", [])); row2["warnings"] = "|".join(row.get("warnings", [])); w.writerow(row2)
    files[p.name]=str(p)
    p = out / "window_signal_values.json"; p.write_text(json.dumps({"dataset_id": result.dataset_id, "source_file": result.source_file, "windows": [{"row_id": w["row_id"], "window_id": w["window_id"], "channel_names": w["channel_names"], "signal_values": w["signal_values"]} for w in result.windows]}, indent=2), encoding="utf-8"); files[p.name]=str(p)
    p = out / "reader_alignment_report.json"; p.write_text(json.dumps(result.reader_alignment_report, indent=2), encoding="utf-8"); files[p.name]=str(p)
    counts = {}
    for r in result.rejected_windows: counts[r["reason"]] = counts.get(r["reason"], 0) + 1
    p = out / "rejected_windows.json"; p.write_text(json.dumps({"rejected_windows": result.rejected_windows, "rejection_counts": counts}, indent=2), encoding="utf-8"); files[p.name]=str(p)
    p = out / "omega_event.json"; p.write_text(json.dumps(result.omega_event, indent=2), encoding="utf-8"); files[p.name]=str(p)
    report = "\n".join(["# MNE to Canonical Signal-Block Conversion","","## Stage","P19.2 canonical signal-block conversion.","","## Dataset",result.dataset_id,"","## Source file",result.source_file,"","## Input extraction status",result.input_extraction_status,"","## Conversion status",result.conversion_status,"","## Window summary",f"input: {result.n_input_windows}, converted: {result.n_converted_windows}, rejected: {result.n_rejected_windows}","","## Rejected windows",json.dumps(counts),"","## Readiness for Level M/T",f"readiness for Level M and Level T: {result.ready_for_level_m_signal and result.ready_for_level_t_signal}","","## Safe claim",result.safe_claim,"","## Forbidden claims","- None","","## Next required step","Run Level M and Level T signal pipelines on the canonical signal-block outputs only after verifying local EEG provenance and conversion quality.","","This conversion produces canonical signal-block artifacts without inferring labels or targets."])
    _validate_safe_text(report)
    p = out / "report.md"; p.write_text(report, encoding="utf-8"); files[p.name]=str(p)
    return files
