"""
DS005620 real/local preflight check (P18.2).
Inspects all prerequisites for a live P18.1 real/local execution.
Does NOT execute any pipeline stage, download data, or activate contracts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_REQUIRED_METADATA_EXTENSIONS = {".tsv", ".csv", ".json"}
_REQUIRED_SIGNAL_FILES = {
    "signal_block_inventory.json",
    "window_inventory.csv",
    "window_signal_values.json",
    "reader_alignment_report.json",
}
_STRICT_JOIN_KEYS = [
    "dataset_id", "row_id", "source_file", "window_id",
    "window_start_s", "window_end_s", "sample_start", "sample_end",
]
_LEVEL_M_CSV = "features_m_signal.csv"
_LEVEL_T_CSV = "features_t_signal.csv"

_SAFE_CLAIM = (
    "DS005620 real/local preflight inspected all required inputs for a live benchmark run "
    "without executing pipeline stages, downloading data, or activating contracts."
)


@dataclass
class PreflightInputStatus:
    name: str
    path: str
    exists: bool
    ready: bool
    blockers: list[str]


@dataclass
class DS005620RealLocalPreflightResult:
    dataset_id: str
    all_ready: bool
    next_action: str
    input_statuses: list[PreflightInputStatus]
    blockers: list[str]
    warnings: list[str]
    safe_claim: str
    ts: str


def _check_contract(path: Optional[str]) -> PreflightInputStatus:
    if not path:
        return PreflightInputStatus(
            name="reviewed_contract",
            path="(not provided)",
            exists=False,
            ready=False,
            blockers=["reviewed_contract path not provided"],
        )
    p = Path(path)
    if not p.exists():
        return PreflightInputStatus(
            name="reviewed_contract",
            path=str(path),
            exists=False,
            ready=False,
            blockers=[f"reviewed_contract not found: {path}"],
        )
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return PreflightInputStatus(
            name="reviewed_contract",
            path=str(path),
            exists=True,
            ready=False,
            blockers=[f"reviewed_contract parse error: {exc}"],
        )
    blockers = []
    status = payload.get("contract_status", "")
    if status != "active_reviewed_external_contract":
        blockers.append(
            f"contract_status is '{status}' expected 'active_reviewed_external_contract'"
        )
    jk = payload.get("join_keys", [])
    if jk != _STRICT_JOIN_KEYS:
        blockers.append("join_keys do not match strict required join keys")
    return PreflightInputStatus(
        name="reviewed_contract",
        path=str(path),
        exists=True,
        ready=len(blockers) == 0,
        blockers=blockers,
    )


def _check_metadata(path: Optional[str]) -> PreflightInputStatus:
    if not path:
        return PreflightInputStatus(
            name="metadata",
            path="(not provided)",
            exists=False,
            ready=False,
            blockers=["metadata path not provided"],
        )
    p = Path(path)
    if not p.exists():
        return PreflightInputStatus(
            name="metadata",
            path=str(path),
            exists=False,
            ready=False,
            blockers=[f"metadata file not found: {path}"],
        )
    if p.suffix.lower() not in _REQUIRED_METADATA_EXTENSIONS:
        return PreflightInputStatus(
            name="metadata",
            path=str(path),
            exists=True,
            ready=False,
            blockers=[f"metadata extension '{p.suffix}' not in {sorted(_REQUIRED_METADATA_EXTENSIONS)}"],
        )
    return PreflightInputStatus(
        name="metadata", path=str(path), exists=True, ready=True, blockers=[]
    )


def _check_signal_blocks(path: Optional[str]) -> PreflightInputStatus:
    if not path:
        return PreflightInputStatus(
            name="canonical_signal_blocks",
            path="(not provided)",
            exists=False,
            ready=False,
            blockers=["canonical_signal_blocks path not provided"],
        )
    p = Path(path)
    if not p.exists() or not p.is_dir():
        return PreflightInputStatus(
            name="canonical_signal_blocks",
            path=str(path),
            exists=False,
            ready=False,
            blockers=[f"canonical_signal_blocks directory not found: {path}"],
        )
    blockers = []
    for fname in _REQUIRED_SIGNAL_FILES:
        if not (p / fname).exists():
            blockers.append(f"missing required signal file: {fname}")
    return PreflightInputStatus(
        name="canonical_signal_blocks",
        path=str(path),
        exists=True,
        ready=len(blockers) == 0,
        blockers=blockers,
    )


def _check_level_csv(name: str, dir_path: Optional[str], csv_name: str) -> PreflightInputStatus:
    if not dir_path:
        return PreflightInputStatus(
            name=name,
            path="(not provided)",
            exists=False,
            ready=False,
            blockers=[f"{name} path not provided"],
        )
    p = Path(dir_path) / csv_name
    if not p.exists():
        return PreflightInputStatus(
            name=name,
            path=str(p),
            exists=False,
            ready=False,
            blockers=[f"{name} file not found: {p}"],
        )
    return PreflightInputStatus(
        name=name, path=str(p), exists=True, ready=True, blockers=[]
    )


def _determine_next_action(statuses: list[PreflightInputStatus]) -> str:
    by_name = {s.name: s for s in statuses}
    if not by_name.get("metadata", PreflightInputStatus("", "", False, False, [])).ready:
        return "provide_metadata"
    if not by_name.get("reviewed_contract", PreflightInputStatus("", "", False, False, [])).ready:
        return "run_p17_1_to_materialize_reviewed_contract"
    if not by_name.get("canonical_signal_blocks", PreflightInputStatus("", "", False, False, [])).ready:
        return "run_p19_2_canonical_signal_block_conversion"
    if not by_name.get("level_m_features", PreflightInputStatus("", "", False, False, [])).ready:
        return "run_p9_level_m_feature_extraction"
    if not by_name.get("level_t_features", PreflightInputStatus("", "", False, False, [])).ready:
        return "run_p10_level_t_topology_extraction"
    return "run_p18_1_real_local_execute"


def run_real_local_preflight(
    dataset_id: str,
    reviewed_contract: Optional[str] = None,
    metadata: Optional[str] = None,
    signal_blocks: Optional[str] = None,
    level_m: Optional[str] = None,
    level_t: Optional[str] = None,
) -> DS005620RealLocalPreflightResult:
    statuses = [
        _check_contract(reviewed_contract),
        _check_metadata(metadata),
        _check_signal_blocks(signal_blocks),
        _check_level_csv("level_m_features", level_m, _LEVEL_M_CSV),
        _check_level_csv("level_t_features", level_t, _LEVEL_T_CSV),
    ]
    all_blockers = [b for s in statuses for b in s.blockers]
    all_ready = all(s.ready for s in statuses)
    next_action = _determine_next_action(statuses)

    return DS005620RealLocalPreflightResult(
        dataset_id=dataset_id,
        all_ready=all_ready,
        next_action=next_action,
        input_statuses=statuses,
        blockers=all_blockers,
        warnings=[],
        safe_claim=_SAFE_CLAIM,
        ts=datetime.now(timezone.utc).isoformat(),
    )


def write_preflight_outputs(result: DS005620RealLocalPreflightResult, out_dir: str) -> dict[str, str]:
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)

    statuses_serializable = [
        {
            "name": s.name,
            "path": s.path,
            "exists": s.exists,
            "ready": s.ready,
            "blockers": s.blockers,
        }
        for s in result.input_statuses
    ]

    report_json = {
        "dataset_id": result.dataset_id,
        "all_ready": result.all_ready,
        "next_action": result.next_action,
        "blocker_count": len(result.blockers),
        "blockers": result.blockers,
        "warnings": result.warnings,
        "safe_claim": result.safe_claim,
        "ts": result.ts,
        "input_statuses": statuses_serializable,
    }
    # Write canonical name + spec-required alias
    json_path = p / "preflight_report.json"
    json_path.write_text(json.dumps(report_json, indent=2), encoding="utf-8")
    alias_json_path = p / "real_local_preflight.json"
    alias_json_path.write_text(json.dumps(report_json, indent=2), encoding="utf-8")

    # Write next-actions file required by Phase 3 spec
    next_actions = {
        "next_action": result.next_action,
        "all_ready": result.all_ready,
        "ready_for_p18_1_execute": result.all_ready,
        "blocker_count": len(result.blockers),
        "next_command": (
            "python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark "
            "--execute --peer-reviewed-contract-confirmed --out <out>"
            if result.all_ready
            else f"# First resolve: {result.next_action}"
        ),
    }
    next_actions_path = p / "real_local_next_actions.json"
    next_actions_path.write_text(json.dumps(next_actions, indent=2), encoding="utf-8")

    lines = [
        "# DS005620 Real/Local Preflight Report",
        "",
        f"**Dataset:** {result.dataset_id}",
        f"**All ready:** {result.all_ready}",
        f"**Next action:** `{result.next_action}`",
        f"**Blocker count:** {len(result.blockers)}",
        "",
        "## Input Statuses",
        "",
    ]
    for s in result.input_statuses:
        status_str = "READY" if s.ready else "BLOCKED"
        lines.append(f"- **{s.name}**: {status_str} (`{s.path}`)")
        for b in s.blockers:
            lines.append(f"  - BLOCKER: {b}")
    lines += [
        "",
        "## Safe Claim",
        "",
        result.safe_claim,
        "",
        "---",
        "",
        "_P18.2 preflight — no pipelines executed, no data downloaded, no contracts activated._",
    ]

    md_path = p / "preflight_report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    # Write report.md alias required by spec
    report_md_path = p / "report.md"
    report_md_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "preflight_report.json": str(json_path),
        "real_local_preflight.json": str(alias_json_path),
        "real_local_next_actions.json": str(next_actions_path),
        "preflight_report.md": str(md_path),
        "report.md": str(report_md_path),
    }
