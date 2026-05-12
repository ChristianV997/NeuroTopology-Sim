"""P18.0 — DS005620 real benchmark readiness gate and dry-run planner.

Inspects whether all required real/local DS005620 benchmark inputs exist and
are compatible before allowing a future P18.1 real target-aware benchmark run.

Does NOT run P9/P10/P11.
Does NOT infer labels.
Does NOT fabricate targets.
Does NOT activate contracts.
Does NOT mutate P12 source contracts.

Public API
----------
DS005620BenchmarkInputStatus
DS005620BenchmarkReadinessResult
load_json_if_exists(path)
inspect_reviewed_contract(path)
inspect_metadata_file(path)
inspect_canonical_signal_blocks(path)
inspect_level_m_features(path)
inspect_level_t_features(path)
build_ds005620_benchmark_readiness(inputs)
build_dry_run_command_plan(result)
build_p18_readiness_omega_event(result)
write_p18_readiness_outputs(result, out_dir)
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

_SAFE_CLAIM = (
    "DS005620 real benchmark readiness was evaluated from reviewed contract and "
    "local artifact paths without running benchmarks or inferring labels."
)

_STRICT_JOIN_KEYS: list[str] = [
    "dataset_id",
    "row_id",
    "source_file",
    "window_id",
    "window_start_s",
    "window_end_s",
    "sample_start",
    "sample_end",
]

_REQUIRED_SIGNAL_BLOCK_FILES: list[str] = [
    "signal_block_inventory.json",
    "window_inventory.csv",
    "window_signal_values.json",
    "reader_alignment_report.json",
]

_BANNED_PHRASES: tuple[str, ...] = (
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
    "topology proves liberation",
    "eeg proves consciousness",
)

_FORBIDDEN_CLAIMS: list[str] = [
    "No consciousness proof.",
    "No self or soul claim.",
    "No liberation or enlightenment claim.",
    "No afterlife claim.",
    "No ontology proof.",
    "No label inference.",
    "No target fabrication.",
    "No automatic contract activation.",
    "No sedated/no_experience shortcut.",
    "No unresponsive/unconscious shortcut.",
    "No automatic P11 execution.",
    "No P9/P10/P11 run.",
]

_P19_2_CLI_MODULE = "sciencer_d.btc_icft.pipelines.convert_mne_to_signal_blocks"

_VALID_METADATA_EXTENSIONS = {".csv", ".tsv", ".json"}


def _validate_safe_text(text: str) -> None:
    lower = text.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            raise ValueError(f"Banned phrase detected: {phrase!r}")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DS005620BenchmarkInputStatus:
    name: str
    path: str | None
    exists: bool
    status: str
    ready: bool
    blockers: list[str]
    warnings: list[str]
    summary: dict


@dataclass
class DS005620BenchmarkReadinessResult:
    dataset_id: str
    ready_for_real_benchmark: bool
    ready_for_p12_alignment: bool
    ready_for_p13_target_injection: bool
    ready_for_p11_target_aware_benchmark: bool
    input_statuses: list[dict]
    strict_join_keys: list[str]
    execution_blockers: list[str]
    dry_run_command_plan: list[dict]
    required_next_steps: list[str]
    omega_event: dict
    safe_claim: str
    forbidden_claims: list[str]
    warnings: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json_if_exists(path: str) -> dict | None:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_csv_header(path: Path) -> list[str]:
    try:
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, [])
        return [h.strip() for h in header]
    except Exception:
        return []


def _p19_2_cli_exists() -> bool:
    return importlib.util.find_spec(_P19_2_CLI_MODULE) is not None


# ---------------------------------------------------------------------------
# Inspectors
# ---------------------------------------------------------------------------

def inspect_reviewed_contract(path: str) -> DS005620BenchmarkInputStatus:
    blockers: list[str] = []
    warnings: list[str] = []
    summary: dict = {}

    if not path:
        return DS005620BenchmarkInputStatus(
            name="reviewed_contract",
            path=None,
            exists=False,
            status="missing",
            ready=False,
            blockers=["reviewed_contract path not provided"],
            warnings=[],
            summary={},
        )

    p = Path(path)
    if not p.is_file():
        return DS005620BenchmarkInputStatus(
            name="reviewed_contract",
            path=path,
            exists=False,
            status="missing",
            ready=False,
            blockers=[f"reviewed_contract not found: {path}"],
            warnings=[],
            summary={},
        )

    data = load_json_if_exists(path) or {}
    summary = {
        "dataset_id": data.get("dataset_id"),
        "contract_status": data.get("contract_status"),
        "explicit_label_column": data.get("explicit_label_column"),
    }

    if data.get("dataset_id") != "DS005620":
        blockers.append(
            f"reviewed_contract dataset_id is {data.get('dataset_id')!r}, expected 'DS005620'"
        )

    contract_status = data.get("contract_status")
    if contract_status != "active_reviewed_external_contract":
        blockers.append(
            f"reviewed_contract contract_status is {contract_status!r}, "
            "expected 'active_reviewed_external_contract'"
        )

    if not data.get("explicit_label_column"):
        blockers.append("reviewed_contract explicit_label_column is missing or empty")

    if not data.get("positive_values"):
        blockers.append("reviewed_contract positive_values is missing or empty")

    if not data.get("negative_values"):
        blockers.append("reviewed_contract negative_values is missing or empty")

    contract_keys = set(data.get("join_keys") or [])
    missing_keys = [k for k in _STRICT_JOIN_KEYS if k not in contract_keys]
    if missing_keys:
        blockers.append(f"reviewed_contract join_keys missing strict keys: {missing_keys}")

    if not data.get("guardrails"):
        warnings.append("reviewed_contract guardrails field is missing or empty")

    ready = len(blockers) == 0
    status = "ready" if ready else "blocked"
    return DS005620BenchmarkInputStatus(
        name="reviewed_contract",
        path=path,
        exists=True,
        status=status,
        ready=ready,
        blockers=blockers,
        warnings=warnings,
        summary=summary,
    )


def inspect_metadata_file(path: str | None) -> DS005620BenchmarkInputStatus:
    if not path:
        return DS005620BenchmarkInputStatus(
            name="metadata_file",
            path=None,
            exists=False,
            status="missing",
            ready=False,
            blockers=["metadata_file path not provided"],
            warnings=[],
            summary={},
        )

    p = Path(path)
    if not p.is_file():
        return DS005620BenchmarkInputStatus(
            name="metadata_file",
            path=path,
            exists=False,
            status="missing",
            ready=False,
            blockers=[f"metadata_file not found: {path}"],
            warnings=[],
            summary={},
        )

    blockers: list[str] = []
    warnings: list[str] = []

    ext = p.suffix.lower()
    if ext not in _VALID_METADATA_EXTENSIONS:
        blockers.append(
            f"metadata_file extension {ext!r} not supported; "
            f"expected one of {sorted(_VALID_METADATA_EXTENSIONS)}"
        )

    summary = {"path": path, "extension": ext, "size_bytes": p.stat().st_size}

    ready = len(blockers) == 0
    status = "ready" if ready else "blocked"
    return DS005620BenchmarkInputStatus(
        name="metadata_file",
        path=path,
        exists=True,
        status=status,
        ready=ready,
        blockers=blockers,
        warnings=warnings,
        summary=summary,
    )


def inspect_canonical_signal_blocks(path: str) -> DS005620BenchmarkInputStatus:
    if not path:
        return DS005620BenchmarkInputStatus(
            name="canonical_signal_blocks",
            path=None,
            exists=False,
            status="missing",
            ready=False,
            blockers=["canonical_signal_blocks path not provided"],
            warnings=[],
            summary={},
        )

    d = Path(path)
    if not d.is_dir():
        return DS005620BenchmarkInputStatus(
            name="canonical_signal_blocks",
            path=path,
            exists=False,
            status="missing",
            ready=False,
            blockers=[f"canonical_signal_blocks directory not found: {path}"],
            warnings=[],
            summary={},
        )

    blockers: list[str] = []
    warnings: list[str] = []
    found_files: list[str] = []

    for fname in _REQUIRED_SIGNAL_BLOCK_FILES:
        fp = d / fname
        if fp.is_file():
            found_files.append(fname)
        else:
            blockers.append(f"canonical_signal_blocks missing required file: {fname}")

    # Check reader_alignment_report for level M/T readiness
    ra_path = d / "reader_alignment_report.json"
    if ra_path.is_file():
        ra = load_json_if_exists(str(ra_path)) or {}
        level_m_ready = ra.get("ready_for_p9_level_m_signal") or ra.get("ready_for_level_m_signal")
        level_t_ready = ra.get("ready_for_p10_level_t_signal") or ra.get("ready_for_level_t_signal")
        if not level_m_ready:
            blockers.append(
                "reader_alignment_report does not set ready_for_p9_level_m_signal or "
                "ready_for_level_m_signal to true"
            )
        if not level_t_ready:
            blockers.append(
                "reader_alignment_report does not set ready_for_p10_level_t_signal or "
                "ready_for_level_t_signal to true"
            )

    # Check window_inventory.csv for strict join keys
    wi_path = d / "window_inventory.csv"
    if wi_path.is_file():
        header = _read_csv_header(wi_path)
        missing_keys = [k for k in _STRICT_JOIN_KEYS if k not in header]
        if missing_keys:
            blockers.append(
                f"window_inventory.csv header missing strict join keys: {missing_keys}"
            )

    summary = {
        "path": path,
        "found_files": found_files,
        "missing_files": [
            f for f in _REQUIRED_SIGNAL_BLOCK_FILES if f not in found_files
        ],
    }

    ready = len(blockers) == 0
    status = "ready" if ready else "blocked"
    return DS005620BenchmarkInputStatus(
        name="canonical_signal_blocks",
        path=path,
        exists=True,
        status=status,
        ready=ready,
        blockers=blockers,
        warnings=warnings,
        summary=summary,
    )


def inspect_level_m_features(path: str | None) -> DS005620BenchmarkInputStatus:
    if not path:
        return DS005620BenchmarkInputStatus(
            name="level_m_features",
            path=None,
            exists=False,
            status="optional_missing",
            ready=False,
            blockers=[],
            warnings=["level_m_features path not provided (optional for P18.0)"],
            summary={},
        )

    features_file = Path(path) / "features_m_signal.csv"
    if not features_file.is_file():
        return DS005620BenchmarkInputStatus(
            name="level_m_features",
            path=path,
            exists=False,
            status="optional_missing",
            ready=False,
            blockers=[],
            warnings=[f"level_m_features features_m_signal.csv not found in {path}"],
            summary={},
        )

    blockers: list[str] = []
    header = _read_csv_header(features_file)
    missing_keys = [k for k in _STRICT_JOIN_KEYS if k not in header]
    if missing_keys:
        blockers.append(
            f"features_m_signal.csv missing strict join keys: {missing_keys}"
        )

    summary = {"path": str(features_file), "header_keys": header[:10]}
    ready = len(blockers) == 0
    status = "ready" if ready else "blocked"
    return DS005620BenchmarkInputStatus(
        name="level_m_features",
        path=path,
        exists=True,
        status=status,
        ready=ready,
        blockers=blockers,
        warnings=[],
        summary=summary,
    )


def inspect_level_t_features(path: str | None) -> DS005620BenchmarkInputStatus:
    if not path:
        return DS005620BenchmarkInputStatus(
            name="level_t_features",
            path=None,
            exists=False,
            status="optional_missing",
            ready=False,
            blockers=[],
            warnings=["level_t_features path not provided (optional for P18.0)"],
            summary={},
        )

    features_file = Path(path) / "features_t_signal.csv"
    if not features_file.is_file():
        return DS005620BenchmarkInputStatus(
            name="level_t_features",
            path=path,
            exists=False,
            status="optional_missing",
            ready=False,
            blockers=[],
            warnings=[f"level_t_features features_t_signal.csv not found in {path}"],
            summary={},
        )

    blockers: list[str] = []
    header = _read_csv_header(features_file)
    missing_keys = [k for k in _STRICT_JOIN_KEYS if k not in header]
    if missing_keys:
        blockers.append(
            f"features_t_signal.csv missing strict join keys: {missing_keys}"
        )

    summary = {"path": str(features_file), "header_keys": header[:10]}
    ready = len(blockers) == 0
    status = "ready" if ready else "blocked"
    return DS005620BenchmarkInputStatus(
        name="level_t_features",
        path=path,
        exists=True,
        status=status,
        ready=ready,
        blockers=blockers,
        warnings=[],
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def build_ds005620_benchmark_readiness(
    inputs: dict,
) -> DS005620BenchmarkReadinessResult:
    """Evaluate readiness of all required real/local DS005620 benchmark inputs.

    inputs dict keys:
      reviewed_contract: str | None
      metadata: str | None
      signal_blocks: str | None
      level_m: str | None
      level_t: str | None
    """
    contract_status = inspect_reviewed_contract(inputs.get("reviewed_contract") or "")
    metadata_status = inspect_metadata_file(inputs.get("metadata"))
    signal_blocks_status = inspect_canonical_signal_blocks(
        inputs.get("signal_blocks") or ""
    )
    level_m_status = inspect_level_m_features(inputs.get("level_m"))
    level_t_status = inspect_level_t_features(inputs.get("level_t"))

    all_statuses = [
        contract_status,
        metadata_status,
        signal_blocks_status,
        level_m_status,
        level_t_status,
    ]

    # P12 alignment readiness: requires reviewed contract + metadata + signal blocks
    ready_for_p12 = (
        contract_status.ready
        and metadata_status.ready
        and signal_blocks_status.ready
    )

    # P13 readiness: requires P12 alignment output (label_alignment.csv);
    # for P18.0 this is not yet available unless explicitly provided
    ready_for_p13 = False

    # P11 readiness: requires Level M, Level T, and target-injected features;
    # for P18.0 this is not yet available unless all provided
    ready_for_p11 = (
        level_m_status.ready
        and level_t_status.ready
        and ready_for_p12
    )

    ready_for_real_benchmark = ready_for_p11

    # Collect all blockers
    execution_blockers: list[str] = []
    for s in all_statuses:
        execution_blockers.extend(s.blockers)

    warnings: list[str] = []
    for s in all_statuses:
        warnings.extend(s.warnings)

    required_next_steps: list[str] = []
    if not contract_status.ready:
        required_next_steps.append(
            "Materialize reviewed external contract (P17.1) before proceeding."
        )
    if not metadata_status.ready:
        required_next_steps.append(
            "Provide real/local DS005620 metadata file (events.tsv or equivalent)."
        )
    if not signal_blocks_status.ready:
        required_next_steps.append(
            "Run P19.1 MNE extraction and P19.2 canonical conversion to produce "
            "signal block inventory with strict join keys."
        )
    if not level_m_status.ready:
        required_next_steps.append(
            "Run P9 Level M signal extraction after signal blocks are ready."
        )
    if not level_t_status.ready:
        required_next_steps.append(
            "Run P10 Level T signal topology after signal blocks are ready."
        )
    if not ready_for_p13:
        required_next_steps.append(
            "Run P12 label alignment with reviewed external contract to produce "
            "label_alignment.csv, then run P13 target injection."
        )

    if not required_next_steps:
        required_next_steps.append(
            "All required benchmark inputs are ready. "
            "Open a P18.1 PR after peer review of p12_external_contract.json."
        )

    dry_run_plan = build_dry_run_command_plan_from_statuses(
        contract_status=contract_status,
        metadata_status=metadata_status,
        signal_blocks_status=signal_blocks_status,
        level_m_status=level_m_status,
        level_t_status=level_t_status,
        inputs=inputs,
    )

    omega = build_p18_readiness_omega_event_from(ready_for_real_benchmark)

    return DS005620BenchmarkReadinessResult(
        dataset_id="DS005620",
        ready_for_real_benchmark=ready_for_real_benchmark,
        ready_for_p12_alignment=ready_for_p12,
        ready_for_p13_target_injection=ready_for_p13,
        ready_for_p11_target_aware_benchmark=ready_for_p11,
        input_statuses=[asdict(s) for s in all_statuses],
        strict_join_keys=_STRICT_JOIN_KEYS[:],
        execution_blockers=execution_blockers,
        dry_run_command_plan=dry_run_plan,
        required_next_steps=required_next_steps,
        omega_event=omega,
        safe_claim=_SAFE_CLAIM,
        forbidden_claims=_FORBIDDEN_CLAIMS[:],
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Dry-run command plan
# ---------------------------------------------------------------------------

def build_dry_run_command_plan_from_statuses(
    contract_status: DS005620BenchmarkInputStatus,
    metadata_status: DS005620BenchmarkInputStatus,
    signal_blocks_status: DS005620BenchmarkInputStatus,
    level_m_status: DS005620BenchmarkInputStatus,
    level_t_status: DS005620BenchmarkInputStatus,
    inputs: dict,
) -> list[dict]:
    p19_2_exists = _p19_2_cli_exists()

    reviewed_contract_out = (
        inputs.get("reviewed_contract")
        or "outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json"
    )
    signal_blocks_out = (
        inputs.get("signal_blocks")
        or "outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620"
    )
    level_m_out = inputs.get("level_m") or "outputs/btc_icft/eeg_level_m/DS005620"
    level_t_out = inputs.get("level_t") or "outputs/btc_icft/eeg_level_t/DS005620"

    commands: list[dict] = []

    # Step 1: P17.1 — materialize reviewed contract
    commands.append({
        "stage": "P17.1",
        "command": (
            "python -m sciencer_d.btc_icft.pipelines.materialize_ds005620_reviewed_contract "
            "--declaration data/DS005620/ds005620_activation_declaration.json "
            "--out outputs/btc_icft/ds005620_reviewed_contract"
        ),
        "ready_to_run": not contract_status.ready,
        "requires": ["ds005620_activation_declaration.json"],
        "expected_outputs": [
            "outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json",
            "outputs/btc_icft/ds005620_reviewed_contract/reviewed_contract.json",
        ],
        "blockers": contract_status.blockers if not contract_status.ready else [],
    })

    # Step 2: P19.1 — MNE extraction
    commands.append({
        "stage": "P19.1",
        "command": (
            "python -m sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks "
            "--dataset-id DS005620 "
            "--input data/DS005620/<subject>.edf "
            "--out outputs/btc_icft/eeg_mne_extract/DS005620"
        ),
        "ready_to_run": not signal_blocks_status.ready,
        "requires": ["local DS005620 EEG file (.edf or equivalent)"],
        "expected_outputs": [
            "outputs/btc_icft/eeg_mne_extract/DS005620/signal_windows.json",
        ],
        "blockers": [],
    })

    # Step 3: P19.2 — canonical signal-block conversion
    if p19_2_exists:
        commands.append({
            "stage": "P19.2",
            "command": (
                "python -m sciencer_d.btc_icft.pipelines.convert_mne_to_signal_blocks "
                "--dataset-id DS005620 "
                "--mne-extract outputs/btc_icft/eeg_mne_extract/DS005620 "
                f"--out {signal_blocks_out}"
            ),
            "ready_to_run": not signal_blocks_status.ready,
            "requires": ["P19.1 MNE extract outputs"],
            "expected_outputs": [
                f"{signal_blocks_out}/signal_block_inventory.json",
                f"{signal_blocks_out}/window_inventory.csv",
                f"{signal_blocks_out}/window_signal_values.json",
                f"{signal_blocks_out}/reader_alignment_report.json",
            ],
            "blockers": [],
        })
    else:
        commands.append({
            "stage": "P19.2",
            "command": "# P19.2 CLI not yet implemented",
            "ready_to_run": False,
            "requires": ["P19.2 canonical signal-block converter (not yet implemented)"],
            "expected_outputs": [
                f"{signal_blocks_out}/signal_block_inventory.json",
                f"{signal_blocks_out}/window_inventory.csv",
                f"{signal_blocks_out}/window_signal_values.json",
                f"{signal_blocks_out}/reader_alignment_report.json",
            ],
            "blockers": ["blocked_missing_p19_2_converter"],
        })

    # Step 4: P9 — Level M signal extraction
    commands.append({
        "stage": "P9",
        "command": (
            "python -m sciencer_d.btc_icft.pipelines.run_eeg_level_m_signal "
            "--dataset-id DS005620 "
            f"--signal-blocks {signal_blocks_out} "
            f"--out {level_m_out}"
        ),
        "ready_to_run": signal_blocks_status.ready and not level_m_status.ready,
        "requires": [f"{signal_blocks_out}/window_inventory.csv"],
        "expected_outputs": [f"{level_m_out}/features_m_signal.csv"],
        "blockers": signal_blocks_status.blockers if not signal_blocks_status.ready else [],
    })

    # Step 5: P10 — Level T signal topology
    commands.append({
        "stage": "P10",
        "command": (
            "python -m sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal "
            "--dataset-id DS005620 "
            f"--signal-blocks {signal_blocks_out} "
            f"--out {level_t_out}"
        ),
        "ready_to_run": signal_blocks_status.ready and not level_t_status.ready,
        "requires": [f"{signal_blocks_out}/window_inventory.csv"],
        "expected_outputs": [f"{level_t_out}/features_t_signal.csv"],
        "blockers": signal_blocks_status.blockers if not signal_blocks_status.ready else [],
    })

    # Step 6: P12 — label alignment with reviewed external contract
    p12_cli_supports_external = _check_p12_supports_external_contract()
    p12_blockers = []
    if not p12_cli_supports_external:
        p12_blockers = ["blocked_p12_external_contract_handshake_missing"]
    elif not contract_status.ready:
        p12_blockers = ["P17.1 reviewed contract not ready"]

    commands.append({
        "stage": "P12",
        "command": (
            "python -m sciencer_d.btc_icft.pipelines.align_eeg_labels "
            "--dataset-id DS005620 "
            f"--signal-features {level_m_out}/features_m_signal.csv "
            "--metadata data/DS005620/events.tsv "
            "--external-contract "
            f"{reviewed_contract_out} "
            "--out outputs/btc_icft/eeg_labels/DS005620_reviewed"
        ),
        "ready_to_run": (
            contract_status.ready
            and level_m_status.ready
            and p12_cli_supports_external
            and not p12_blockers
        ),
        "requires": [
            reviewed_contract_out,
            f"{level_m_out}/features_m_signal.csv",
            "data/DS005620/events.tsv",
        ],
        "expected_outputs": [
            "outputs/btc_icft/eeg_labels/DS005620_reviewed/label_alignment.csv",
        ],
        "blockers": p12_blockers,
    })

    # Step 7: P13 — target injection
    commands.append({
        "stage": "P13",
        "command": (
            "python -m sciencer_d.btc_icft.pipelines.inject_eeg_targets "
            "--dataset-id DS005620 "
            "--label-alignment outputs/btc_icft/eeg_labels/DS005620_reviewed/label_alignment.csv "
            f"--m-features {level_m_out}/features_m_signal.csv "
            "--out outputs/btc_icft/eeg_targets/DS005620_reviewed"
        ),
        "ready_to_run": False,
        "requires": [
            "outputs/btc_icft/eeg_labels/DS005620_reviewed/label_alignment.csv",
            f"{level_m_out}/features_m_signal.csv",
        ],
        "expected_outputs": [
            "outputs/btc_icft/eeg_targets/DS005620_reviewed/features_m_signal_labeled.csv",
        ],
        "blockers": ["P12 label alignment must complete first"],
    })

    # Step 8: P11 — target-aware signal M+T benchmark
    commands.append({
        "stage": "P11",
        "command": (
            "python -m sciencer_d.btc_icft.pipelines.run_eeg_signal_mt "
            "--dataset-id DS005620 "
            f"--m-features {level_m_out}/features_m_signal.csv "
            f"--t-features {level_t_out}/features_t_signal.csv "
            "--out outputs/btc_icft/eeg_signal_mt/DS005620_reviewed"
        ),
        "ready_to_run": False,
        "requires": [
            f"{level_m_out}/features_m_signal.csv",
            f"{level_t_out}/features_t_signal.csv",
            "outputs/btc_icft/eeg_targets/DS005620_reviewed/features_m_signal_labeled.csv",
        ],
        "expected_outputs": [
            "outputs/btc_icft/eeg_signal_mt/DS005620_reviewed/metrics_signal_mt.json",
        ],
        "blockers": ["P12/P13 must complete first; this is future P18.1 scope"],
    })

    return commands


def build_dry_run_command_plan(
    result: DS005620BenchmarkReadinessResult,
) -> list[dict]:
    return result.dry_run_command_plan


def _check_p12_supports_external_contract() -> bool:
    """Check if align_eeg_labels CLI accepts --external-contract flag."""
    try:
        import sciencer_d.btc_icft.pipelines.align_eeg_labels as m  # noqa: F401
        import inspect
        src = inspect.getsource(m)
        return "--external-contract" in src or "external_contract" in src
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Omega event
# ---------------------------------------------------------------------------

def build_p18_readiness_omega_event_from(
    ready_for_real_benchmark: bool,
    dataset_id: str = "DS005620",
) -> dict:
    _validate_safe_text(_SAFE_CLAIM)
    payload = f"p18_0:{dataset_id}:{ready_for_real_benchmark}:{_SAFE_CLAIM}"
    return {
        "event_id": hashlib.sha256(payload.encode()).hexdigest()[:16],
        "event_type": "ds005620_real_benchmark_readiness_gate",
        "dataset_id": dataset_id,
        "ready_for_real_benchmark": ready_for_real_benchmark,
        "benchmarks_run": False,
        "labels_inferred": False,
        "targets_fabricated": False,
        "contracts_activated": False,
        "safe_claim": _SAFE_CLAIM,
        "forbidden_claims": _FORBIDDEN_CLAIMS[:],
    }


def build_p18_readiness_omega_event(
    result: DS005620BenchmarkReadinessResult,
) -> dict:
    return result.omega_event


# ---------------------------------------------------------------------------
# Output writer
# ---------------------------------------------------------------------------

def write_p18_readiness_outputs(
    result: DS005620BenchmarkReadinessResult,
    out_dir: str,
) -> dict[str, str]:
    """Write exactly 6 output files."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}

    # 1. ds005620_benchmark_readiness.json
    readiness_data = {
        "dataset_id": result.dataset_id,
        "ready_for_real_benchmark": result.ready_for_real_benchmark,
        "ready_for_p12_alignment": result.ready_for_p12_alignment,
        "ready_for_p13_target_injection": result.ready_for_p13_target_injection,
        "ready_for_p11_target_aware_benchmark": result.ready_for_p11_target_aware_benchmark,
        "strict_join_keys": result.strict_join_keys,
        "execution_blockers": result.execution_blockers,
        "required_next_steps": result.required_next_steps,
        "warnings": result.warnings,
    }
    p = out / "ds005620_benchmark_readiness.json"
    p.write_text(json.dumps(readiness_data, indent=2), encoding="utf-8")
    outputs["ds005620_benchmark_readiness"] = str(p)

    # 2. benchmark_input_statuses.json
    p = out / "benchmark_input_statuses.json"
    p.write_text(
        json.dumps({"input_statuses": result.input_statuses}, indent=2),
        encoding="utf-8",
    )
    outputs["benchmark_input_statuses"] = str(p)

    # 3. dry_run_command_plan.json
    p = out / "dry_run_command_plan.json"
    p.write_text(
        json.dumps({"commands": result.dry_run_command_plan}, indent=2),
        encoding="utf-8",
    )
    outputs["dry_run_command_plan"] = str(p)

    # 4. execution_blockers.json
    blocker_counts = len(result.execution_blockers)
    next_unblocked = next(
        (
            cmd["stage"]
            for cmd in result.dry_run_command_plan
            if cmd.get("ready_to_run") and not cmd.get("blockers")
        ),
        "none",
    )
    p = out / "execution_blockers.json"
    p.write_text(
        json.dumps(
            {
                "blockers": result.execution_blockers,
                "blocker_counts": blocker_counts,
                "next_unblocked_action": next_unblocked,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    outputs["execution_blockers"] = str(p)

    # 5. omega_event.json
    p = out / "omega_event.json"
    p.write_text(json.dumps(result.omega_event, indent=2), encoding="utf-8")
    outputs["omega_event"] = str(p)

    # 6. report.md
    report_lines = [
        "# DS005620 Real Benchmark Readiness Gate",
        "",
        "## Stage",
        "",
        "P18.0 — DS005620 readiness gate and dry-run planner. "
        "Inspects reviewed external contract and local artifact paths "
        "without running benchmarks or inferring labels.",
        "",
        "## Dataset",
        "",
        f"- dataset_id: {result.dataset_id}",
        f"- ready_for_real_benchmark: {result.ready_for_real_benchmark}",
        f"- ready_for_p12_alignment: {result.ready_for_p12_alignment}",
        f"- ready_for_p13_target_injection: {result.ready_for_p13_target_injection}",
        f"- ready_for_p11_target_aware_benchmark: {result.ready_for_p11_target_aware_benchmark}",
        "",
        "## Inputs inspected",
        "",
    ]
    for s in result.input_statuses:
        report_lines.append(
            f"- {s['name']}: {s['status']} "
            f"(ready={s['ready']}, path={s['path']})"
        )

    report_lines += [
        "",
        "## Readiness summary",
        "",
        "| Input | Status | Ready |",
        "|---|---|---|",
    ]
    for s in result.input_statuses:
        report_lines.append(f"| {s['name']} | {s['status']} | {s['ready']} |")

    report_lines += [
        "",
        "## Execution blockers",
        "",
    ]
    if result.execution_blockers:
        for b in result.execution_blockers:
            report_lines.append(f"- {b}")
    else:
        report_lines.append("None — all required inputs are ready.")

    report_lines += [
        "",
        "## Dry-run command plan",
        "",
        "The following commands should be run in order. "
        "None are executed automatically.",
        "",
    ]
    for cmd in result.dry_run_command_plan:
        report_lines += [
            f"### Stage {cmd['stage']}",
            "",
            f"```bash",
            f"{cmd['command']}",
            f"```",
            "",
            f"- ready_to_run: {cmd['ready_to_run']}",
        ]
        if cmd.get("blockers"):
            for b in cmd["blockers"]:
                report_lines.append(f"- BLOCKER: {b}")
        report_lines.append("")

    report_lines += [
        "## Safe claim",
        "",
        result.safe_claim,
        "",
        "## Forbidden claims",
        "",
    ]
    for fc in result.forbidden_claims:
        report_lines.append(f"- {fc}")

    report_lines += [
        "",
        "## Next required step",
        "",
        "Resolve blockers, then run P18.1 only after reviewed contract, "
        "metadata, canonical signal blocks, Level M/T features, and explicit "
        "targets are available.",
    ]

    report_text = "\n".join(report_lines) + "\n"
    _validate_safe_text(report_text)
    p = out / "report.md"
    p.write_text(report_text, encoding="utf-8")
    outputs["report"] = str(p)

    return outputs
