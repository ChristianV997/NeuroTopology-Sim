from __future__ import annotations

import csv
import importlib.util
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

BANNED_PHRASES = (
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
    "sedated implies no_experience",
    "unresponsive implies unconscious",
)

SAFE_CLAIM = (
    "Local EEG files were scanned for reader capability and extraction readiness "
    "without parsing binary signals or inferring labels."
)

TEXT_EXTS = {".csv", ".tsv", ".txt"}
MNE_EXTS = {".edf", ".bdf", ".gdf", ".set", ".fdt", ".vhdr", ".vmrk", ".eeg", ".cnt", ".fif"}
WFDB_EXTS = {".hea", ".dat"}
SCIPY_EXTS = {".mat"}


@dataclass
class EEGReaderCapability:
    reader_name: str
    optional_package: str | None
    installed: bool
    supported_extensions: list[str]
    status: str
    notes: list[str]


@dataclass
class EEGFileManifestRow:
    dataset_id: str
    file_path: str
    file_name: str
    extension: str
    detected_format: str
    file_size_bytes: int
    reader_status: str
    recommended_reader: str | None
    optional_package_required: str | None
    readable_now: bool
    blocked_reason: str | None
    warnings: list[str] = field(default_factory=list)


@dataclass
class EEGReaderPreflightResult:
    dataset_id: str
    n_files_scanned: int
    n_readable_now: int
    n_dependency_gated: int
    n_unsupported: int
    n_unknown: int
    reader_capabilities: list[dict]
    file_manifest: list[dict]
    format_counts: dict
    status_counts: dict
    extraction_ready: bool
    extraction_blockers: list[str]
    next_adapter_actions: list[str]
    omega_event: dict
    safe_claim: str
    forbidden_claims: list[str]
    warnings: list[str]


def _validate_safe_text(text: str) -> None:
    lower = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lower:
            raise ValueError(f"Banned phrase detected: {phrase}")


def detect_file_format(path: str) -> dict:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in TEXT_EXTS:
        return {"extension": ext, "detected_format": ext.lstrip('.'), "reader": "text_fixture_reader", "package": None, "status": "readable_text_fixture", "readable_now": True}
    if ext in MNE_EXTS:
        return {"extension": ext, "detected_format": "mne_binary", "reader": "mne_reader_candidate", "package": "mne", "status": "dependency_gated", "readable_now": False}
    if ext in WFDB_EXTS:
        return {"extension": ext, "detected_format": "wfdb_record", "reader": "wfdb_reader_candidate", "package": "wfdb", "status": "dependency_gated", "readable_now": False}
    if ext in SCIPY_EXTS:
        return {"extension": ext, "detected_format": "scipy_mat", "reader": "scipy_mat_candidate", "package": "scipy", "status": "dependency_gated", "readable_now": False}
    if ext == "":
        return {"extension": "", "detected_format": "unknown", "reader": None, "package": None, "status": "unknown_format", "readable_now": False}
    return {"extension": ext, "detected_format": "unsupported", "reader": None, "package": None, "status": "unsupported_extension", "readable_now": False}


def check_optional_reader_capabilities() -> list[EEGReaderCapability]:
    mne = importlib.util.find_spec("mne") is not None
    wfdb = importlib.util.find_spec("wfdb") is not None
    scipy = importlib.util.find_spec("scipy") is not None
    _ = importlib.util.find_spec("numpy") is not None
    return [
        EEGReaderCapability("text_fixture_reader", None, True, sorted(TEXT_EXTS), "stdlib_text_ready", ["Fixture-like text EEG inputs are readable now."]),
        EEGReaderCapability("mne_reader_candidate", "mne", mne, sorted(MNE_EXTS), "available" if mne else "missing_optional_dependency", []),
        EEGReaderCapability("wfdb_reader_candidate", "wfdb", wfdb, sorted(WFDB_EXTS), "available" if wfdb else "missing_optional_dependency", []),
        EEGReaderCapability("scipy_mat_candidate", "scipy", scipy, sorted(SCIPY_EXTS), "available" if scipy else "missing_optional_dependency", []),
    ]


def scan_eeg_dataset_files(root: str, dataset_id: str, max_files: int | None = None) -> list[EEGFileManifestRow]:
    rows = []
    root_path = Path(root)
    if not root_path.exists():
        return rows
    files = [p for p in sorted(root_path.rglob("*")) if p.is_file()]
    if max_files is not None:
        files = files[:max_files]
    installed = {c.optional_package: c.installed for c in check_optional_reader_capabilities() if c.optional_package}
    for f in files:
        det = detect_file_format(str(f))
        st = det["status"]
        blocked = None
        if st == "dependency_gated":
            pkg = det["package"]
            if not installed.get(pkg, False):
                st = "dependency_missing"
                blocked = f"optional_dependency_missing:{pkg}"
            else:
                st = "dependency_available_not_extracted"
                blocked = "binary_reader_not_implemented"
        elif st == "unsupported_extension":
            blocked = "unsupported_extension"
        elif st == "unknown_format":
            blocked = "unknown_format"
        rows.append(EEGFileManifestRow(dataset_id, str(f), f.name, det["extension"], det["detected_format"], f.stat().st_size, st, det["reader"], det["package"], st == "readable_text_fixture", blocked, []))
    return rows


def build_reader_preflight_report(dataset_id: str, rows: list[EEGFileManifestRow], capabilities: list[EEGReaderCapability]) -> EEGReaderPreflightResult:
    format_counts, status_counts = {}, {}
    for r in rows:
        format_counts[r.detected_format] = format_counts.get(r.detected_format, 0) + 1
        status_counts[r.reader_status] = status_counts.get(r.reader_status, 0) + 1
    n_readable_now = sum(1 for r in rows if r.readable_now)
    n_dep = sum(1 for r in rows if r.reader_status in {"dependency_missing", "dependency_available_not_extracted"})
    n_unsupported = status_counts.get("unsupported_extension", 0)
    n_unknown = status_counts.get("unknown_format", 0)
    blockers = []
    if not rows:
        blockers.append("no_files_found")
    if n_dep > 0:
        blockers.append("binary_reader_not_implemented")
    for cap in capabilities:
        if cap.optional_package and not cap.installed:
            blockers.append(f"optional_dependency_missing:{cap.optional_package}")
    if n_unsupported > 0:
        blockers.append("unsupported_formats_present")
    if n_readable_now == 0:
        blockers.append("no_readable_files")
    next_actions = [
        "Select a single binary EEG backend (mne/wfdb/scipy) for first real extractor.",
        "Add local fixture tests for dependency-gated formats before enabling extraction.",
        "Implement dependency-gated real EEG extraction only after selecting a specific reader backend and adding tests with local fixtures.",
    ]
    extraction_ready = n_readable_now > 0 and "scan_error" not in status_counts and any(r.extension in TEXT_EXTS for r in rows)
    result = EEGReaderPreflightResult(dataset_id, len(rows), n_readable_now, n_dep, n_unsupported, n_unknown, [asdict(c) for c in capabilities], [asdict(r) for r in rows], format_counts, status_counts, extraction_ready, blockers, next_actions, {}, SAFE_CLAIM, [], [])
    result.omega_event = build_reader_preflight_omega_event(result)
    return result


def build_reader_preflight_omega_event(result: EEGReaderPreflightResult) -> dict:
    _validate_safe_text(result.safe_claim)
    return {
        "event_type": "eeg_reader_preflight",
        "dataset_id": result.dataset_id,
        "n_files_scanned": result.n_files_scanned,
        "safe_claim": result.safe_claim,
        "forbidden_claims": result.forbidden_claims,
    }


def write_reader_preflight_outputs(result: EEGReaderPreflightResult, out_dir: str) -> dict[str, str]:
    _validate_safe_text(result.safe_claim)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    man = out / "eeg_file_manifest.csv"
    with man.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["dataset_id","file_path","file_name","extension","detected_format","file_size_bytes","reader_status","recommended_reader","optional_package_required","readable_now","blocked_reason","warnings"])
        w.writeheader(); [w.writerow({**row, "warnings": "|".join(row["warnings"])}) for row in result.file_manifest]
    files["eeg_file_manifest.csv"] = str(man)
    cap = out / "reader_capability_report.json"
    cap.write_text(json.dumps({"capabilities": result.reader_capabilities, "optional_dependencies": [c["optional_package"] for c in result.reader_capabilities if c["optional_package"]], "stdlib_text_ready": True, "notes": ["Optional dependencies are detected but never required."]}, indent=2), encoding="utf-8")
    files["reader_capability_report.json"] = str(cap)
    summ = out / "reader_preflight_summary.json"
    summ.write_text(json.dumps({k: getattr(result, k) for k in ["dataset_id","n_files_scanned","n_readable_now","n_dependency_gated","n_unsupported","n_unknown","format_counts","status_counts","extraction_ready","extraction_blockers","next_adapter_actions","warnings"]}, indent=2), encoding="utf-8")
    files["reader_preflight_summary.json"] = str(summ)
    blk = out / "extraction_blockers.json"; blk.write_text(json.dumps({"extraction_blockers": result.extraction_blockers}, indent=2), encoding="utf-8"); files["extraction_blockers.json"] = str(blk)
    omg = out / "omega_event.json"; omg.write_text(json.dumps(result.omega_event, indent=2), encoding="utf-8"); files["omega_event.json"] = str(omg)
    rep = out / "report.md"
    rep.write_text("\n".join([
        "# EEG Reader Capability Preflight","","## Stage","P19.0 local EEG reader capability preflight.","","## Dataset",result.dataset_id,"","## Files scanned",str(result.n_files_scanned),"","## Reader capabilities",json.dumps(result.reader_capabilities, indent=2),"","## Format summary",json.dumps(result.format_counts, indent=2),"","## Extraction readiness",str(result.extraction_ready),"","## Blockers",json.dumps(result.extraction_blockers, indent=2),"","## Next adapter actions",* [f"- {x}" for x in result.next_adapter_actions],"","## Safe claim",result.safe_claim,"","## Forbidden claims","- None","","## Next required step","Implement dependency-gated real EEG extraction only after selecting a specific reader backend and adding tests with local fixtures.",
    ]), encoding="utf-8")
    files["report.md"] = str(rep)
    _validate_safe_text(rep.read_text(encoding="utf-8"))
    return files
