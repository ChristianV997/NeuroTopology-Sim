"""Phase 4 retrofit inventory reports (engineering evidence only).

Builds six deterministic JSON reports from an ``InventorySnapshot`` and
the offline tool-source registry. No network, no MarketOS, no dataset
downloads, no credentials.

Inventory is **not scientific evidence**. ``scientific_claim_status`` is
always ``not_evidence``. Reports never emit scientific ``PASS``. An
``empirical`` artifact label is a heuristic, not a scientific pass.
The K>100 / scientific PASS gate is out of scope for this subsystem.

Clock: pass ``_now`` or ``generated_at`` for a frozen timestamp. Default
is UTC ISO-8601. Tests must inject a frozen clock.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from .models import (
    ARTIFACT_LABEL_EMPIRICAL,
    ARTIFACT_LABEL_VALUES,
    INVENTORY_SCHEMA_VERSION,
    InventorySnapshot,
)
from .scanner import (
    GitUnavailableError,
    build_inventory_snapshot,
    snapshot_to_json,
)
from .tool_sources import (
    load_tool_sources,
    resolve_tool_sources_path,
    summarize_tool_sources,
)
from .validators import (
    EXPECTED_REAL_TOOL_SOURCE_COUNT,
    FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES,
    INVENTORY_CLAIM_STATUS_NOT_EVIDENCE,
    empirical_label_is_scientific_pass,
    inventory_claim_record,
    inventory_is_scientific_evidence,
    inventory_scientific_claim_status,
    validate_duplicate_ownership,
    validate_inventory_snapshot,
    validate_no_network_imports,
    validate_no_scientific_pass,
    validate_tool_source_registry,
)

Pathish = Union[str, Path]
Clockish = Union[str, datetime]

REPORT_SCHEMA_VERSION = "0.1"
REPORT_SCHEMA_RELATIVE = "configs/retrofit_inventory/report_schema.json"
DEFAULT_OUTPUT_RELATIVE = "artifacts/retrofit_inventory"
GENERATED_BY = "tools.retrofit_inventory.reporting"

REPORT_KIND_REPOSITORY = "repository_inventory"
REPORT_KIND_ARTIFACT = "artifact_inventory"
REPORT_KIND_TOOL_ADMISSION = "tool_admission_inventory"
REPORT_KIND_OWNERSHIP = "ownership_collision_report"
REPORT_KIND_PRIORITY = "retrofit_priority_report"
REPORT_KIND_SCIENCE_RISK = "scientific_claim_risk_report"

REPORT_KINDS: Sequence[str] = (
    REPORT_KIND_REPOSITORY,
    REPORT_KIND_ARTIFACT,
    REPORT_KIND_TOOL_ADMISSION,
    REPORT_KIND_OWNERSHIP,
    REPORT_KIND_PRIORITY,
    REPORT_KIND_SCIENCE_RISK,
)
REPORT_FILENAMES: Sequence[str] = tuple(f"{kind}.json" for kind in REPORT_KINDS)

STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_INCOMPLETE = "incomplete"
STATUS_VALUES = frozenset({STATUS_OK, STATUS_ERROR, STATUS_INCOMPLETE})

INVENTORY_NOT_EVIDENCE_LIMITATION = (
    "Inventory is not scientific evidence. These reports do not validate "
    "topology metrics, consciousness, or a theory of everything."
)
EMPIRICAL_NOT_PASS_LIMITATION = (
    "Artifact labels (synthetic | empirical | unknown) are heuristics only. "
    "An empirical label is not a scientific PASS."
)
PASS_GATE_OUT_OF_SCOPE_LIMITATION = (
    "The K>100 / scientific PASS gate is out of scope for this subsystem. "
    "scientific_claim_status is always not_evidence. Reports never emit PASS."
)
NOT_LAUNCH_AUTHORITY_LIMITATION = (
    "These reports are an engineering inventory, not launch authority, "
    "not a license opinion, and not an ontology promotion."
)

_ADOPTION_PRIORITY = {
    "consider": 0,
    "experimental_only": 1,
    "defer": 2,
    "reject": 3,
}
_OFFLINE_PRIORITY = {
    "fully_offline": 0,
    "offline_with_local_data": 1,
    "unknown": 2,
    "requires_network": 3,
}
_RISK_PRIORITY = {"none": 0, "low": 1, "medium": 2, "high": 3}

_PACKAGE_DIR = Path(__file__).resolve().parent
_REPORTING_PATH = Path(__file__).resolve()


def dump_json(payload: Any) -> str:
    """Deterministic JSON text (``sort_keys=True``, trailing newline)."""

    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def format_timestamp(
    _now: Optional[Clockish] = None,
    generated_at: Optional[Clockish] = None,
) -> str:
    """Return an ISO-8601 timestamp. Tests must inject ``_now`` / ``generated_at``."""

    value = generated_at if generated_at is not None else _now
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def common_limitations() -> List[str]:
    """Fixed limitations present on every report envelope."""

    return [
        INVENTORY_NOT_EVIDENCE_LIMITATION,
        EMPIRICAL_NOT_PASS_LIMITATION,
        PASS_GATE_OUT_OF_SCOPE_LIMITATION,
        NOT_LAUNCH_AUTHORITY_LIMITATION,
    ]


def common_next_actions(*, has_errors: bool, incomplete: bool) -> List[str]:
    actions: List[str] = []
    if has_errors:
        actions.append(
            "Resolve validation errors listed in errors before treating "
            "this inventory as a complete engineering record."
        )
    if incomplete:
        actions.append(
            "Supply a complete InventorySnapshot and tool-source registry, "
            "then regenerate the six reports."
        )
    actions.extend(
        [
            "Do not treat this inventory as scientific evidence or a PASS.",
            "Integration Phase 5: add scripts/build_retrofit_inventory.py to "
            f"emit these six files under {DEFAULT_OUTPUT_RELATIVE}/.",
            "Do not run a K>100 / scientific PASS gate from these reports.",
        ]
    )
    return actions


def snapshot_digest(snapshot: Optional[InventorySnapshot]) -> Optional[str]:
    if snapshot is None:
        return None
    return sha256_text(snapshot_to_json(snapshot))


def _schema_path(repo_root: Optional[Pathish] = None) -> Path:
    if repo_root is not None:
        candidate = Path(repo_root) / REPORT_SCHEMA_RELATIVE
        if candidate.is_file():
            return candidate
    packaged = _PACKAGE_DIR.parents[1] / REPORT_SCHEMA_RELATIVE
    return packaged


def _hash_file_if_present(path: Optional[Path]) -> Optional[str]:
    if path is None or not path.is_file():
        return None
    return sha256_bytes(path.read_bytes())


def build_source_hashes(
    snapshot: Optional[InventorySnapshot],
    *,
    tool_sources_yaml_hash: Optional[str] = None,
    tool_rows: Optional[Sequence[Mapping[str, Any]]] = None,
    repo_root: Optional[Pathish] = None,
) -> Dict[str, Any]:
    """Content hashes of key inputs (snapshot digest, YAML, schema version)."""

    yaml_hash = tool_sources_yaml_hash
    if yaml_hash is None and tool_rows:
        yaml_hash = sha256_text(json.dumps(list(tool_rows), sort_keys=True, ensure_ascii=True))
    schema_hash = _hash_file_if_present(_schema_path(repo_root))
    return {
        "inventory_schema_version": (
            snapshot.schema_version if snapshot is not None else INVENTORY_SCHEMA_VERSION
        ),
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "report_schema": schema_hash,
        "snapshot_digest": snapshot_digest(snapshot),
        "tool_sources_yaml": yaml_hash,
    }


def _envelope(
    *,
    report_kind: str,
    timestamp: str,
    repository_commit: str,
    source_hashes: Mapping[str, Any],
    status: str,
    warnings: Sequence[str],
    errors: Sequence[str],
    limitations: Optional[Sequence[str]] = None,
    next_actions: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    if status not in STATUS_VALUES:
        raise ValueError(f"status must be one of {sorted(STATUS_VALUES)}, got {status!r}")
    return {
        "errors": list(errors),
        "limitations": list(limitations if limitations is not None else common_limitations()),
        "next_actions": list(
            next_actions
            if next_actions is not None
            else common_next_actions(
                has_errors=bool(errors),
                incomplete=status == STATUS_INCOMPLETE,
            )
        ),
        "report_kind": report_kind,
        "repository_commit": repository_commit,
        "schema_version": REPORT_SCHEMA_VERSION,
        "source_hashes": dict(source_hashes),
        "status": status,
        "timestamp": timestamp,
        "warnings": list(warnings),
    }


def _snapshot_payload(snapshot: Optional[InventorySnapshot]) -> Dict[str, Any]:
    if snapshot is None:
        return {
            "files": [],
            "worktrees_and_branches": [],
            "artifacts": [],
            "governance_files": [],
            "dependencies": [],
            "overlaps": [],
            "report_fields": {},
        }
    return snapshot.to_dict()


def build_repository_inventory(
    snapshot: Optional[InventorySnapshot],
    *,
    timestamp: str,
    source_hashes: Mapping[str, Any],
    status: str,
    warnings: Sequence[str],
    errors: Sequence[str],
    next_actions: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    payload = _snapshot_payload(snapshot)
    commit = snapshot.commit_sha if snapshot is not None else ""
    report = _envelope(
        report_kind=REPORT_KIND_REPOSITORY,
        timestamp=timestamp,
        repository_commit=commit,
        source_hashes=source_hashes,
        status=status,
        warnings=warnings,
        errors=errors,
        next_actions=next_actions,
    )
    report.update(
        {
            "dependencies": list(payload.get("dependencies") or []),
            "files": list(payload.get("files") or []),
            "governance": list(payload.get("governance_files") or []),
            "overlaps": list(payload.get("overlaps") or []),
            "worktrees_and_branches": list(payload.get("worktrees_and_branches") or []),
        }
    )
    return report


def build_artifact_inventory(
    snapshot: Optional[InventorySnapshot],
    *,
    timestamp: str,
    source_hashes: Mapping[str, Any],
    status: str,
    warnings: Sequence[str],
    errors: Sequence[str],
    next_actions: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    payload = _snapshot_payload(snapshot)
    artifacts = list(payload.get("artifacts") or [])
    counts = {label: 0 for label in ARTIFACT_LABEL_VALUES}
    for row in artifacts:
        label = row.get("label")
        if label in counts:
            counts[label] += 1
    commit = snapshot.commit_sha if snapshot is not None else ""
    report = _envelope(
        report_kind=REPORT_KIND_ARTIFACT,
        timestamp=timestamp,
        repository_commit=commit,
        source_hashes=source_hashes,
        status=status,
        warnings=warnings,
        errors=errors,
        next_actions=next_actions,
    )
    report.update(
        {
            "artifacts": artifacts,
            "empirical_label_is_pass": False,
            "label_counts": counts,
            "label_policy": (
                "heuristic only (synthetic | empirical | unknown); "
                "empirical is not a scientific PASS"
            ),
        }
    )
    return report


def build_tool_admission_inventory(
    snapshot: Optional[InventorySnapshot],
    tool_rows: Sequence[Mapping[str, Any]],
    *,
    timestamp: str,
    source_hashes: Mapping[str, Any],
    status: str,
    warnings: Sequence[str],
    errors: Sequence[str],
    next_actions: Optional[Sequence[str]] = None,
    loaded_from_real_yaml: bool = False,
) -> Dict[str, Any]:
    rows = [dict(row) for row in tool_rows]
    rows.sort(key=lambda row: str(row.get("id") or ""))
    summary = summarize_tool_sources(entries=rows) if rows else {
        "count": 0,
        "by_adoption_recommendation": {},
        "by_integration_mode": {},
    }
    commit = snapshot.commit_sha if snapshot is not None else ""
    report = _envelope(
        report_kind=REPORT_KIND_TOOL_ADMISSION,
        timestamp=timestamp,
        repository_commit=commit,
        source_hashes=source_hashes,
        status=status,
        warnings=warnings,
        errors=errors,
        next_actions=next_actions,
    )
    report.update(
        {
            "admission_summary": summary,
            "expected_real_tool_source_count": EXPECTED_REAL_TOOL_SOURCE_COUNT,
            "loaded_from_real_yaml": loaded_from_real_yaml,
            "tools": rows,
        }
    )
    return report


def build_ownership_collision_report(
    snapshot: Optional[InventorySnapshot],
    tool_rows: Optional[Sequence[Mapping[str, Any]]],
    *,
    timestamp: str,
    source_hashes: Mapping[str, Any],
    status: str,
    warnings: Sequence[str],
    errors: Sequence[str],
    next_actions: Optional[Sequence[str]] = None,
    duplicate_ownership_errors: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    payload = _snapshot_payload(snapshot)
    claimed = payload.get("report_fields", {}).get("claimed_owners")
    if not isinstance(claimed, list):
        claimed = []
    commit = snapshot.commit_sha if snapshot is not None else ""
    dups = list(duplicate_ownership_errors or [])
    if duplicate_ownership_errors is None and snapshot is not None:
        dups = validate_duplicate_ownership(snapshot, tool_rows)
    report = _envelope(
        report_kind=REPORT_KIND_OWNERSHIP,
        timestamp=timestamp,
        repository_commit=commit,
        source_hashes=source_hashes,
        status=status,
        warnings=warnings,
        errors=errors,
        next_actions=next_actions,
    )
    report.update(
        {
            "claimed_owners": list(claimed),
            "duplicate_ownership_findings": dups,
            "overlaps": list(payload.get("overlaps") or []),
        }
    )
    return report


def _engineering_priority_tuple(row: Mapping[str, Any]) -> tuple:
    adoption = str(row.get("adoption_recommendation") or "")
    offline = str(row.get("offline_behavior") or "")
    network = str(row.get("network_risk") or "")
    privacy = str(row.get("privacy_risk") or "")
    return (
        _ADOPTION_PRIORITY.get(adoption, 9),
        _OFFLINE_PRIORITY.get(offline, 9),
        max(_RISK_PRIORITY.get(network, 9), _RISK_PRIORITY.get(privacy, 9)),
        str(row.get("id") or ""),
    )


def build_retrofit_priority_report(
    snapshot: Optional[InventorySnapshot],
    tool_rows: Sequence[Mapping[str, Any]],
    *,
    timestamp: str,
    source_hashes: Mapping[str, Any],
    status: str,
    warnings: Sequence[str],
    errors: Sequence[str],
    next_actions: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Engineering priority only. Not a scientific ranking."""

    ranked: List[Dict[str, Any]] = []
    for row in tool_rows:
        key = _engineering_priority_tuple(row)
        ranked.append(
            {
                "adoption_recommendation": row.get("adoption_recommendation"),
                "engineering_priority_key": list(key),
                "id": row.get("id"),
                "integration_mode": row.get("integration_mode"),
                "name": row.get("name"),
                "network_risk": row.get("network_risk"),
                "offline_behavior": row.get("offline_behavior"),
                "privacy_risk": row.get("privacy_risk"),
                "ranking_kind": "engineering_only",
            }
        )
    ranked.sort(key=lambda item: tuple(item["engineering_priority_key"]))
    for index, item in enumerate(ranked, start=1):
        item["engineering_priority"] = index
    commit = snapshot.commit_sha if snapshot is not None else ""
    extra_actions = list(
        next_actions
        if next_actions is not None
        else common_next_actions(
            has_errors=bool(errors),
            incomplete=status == STATUS_INCOMPLETE,
        )
    )
    if "Review consider-ranked optional adapters as engineering work only." not in extra_actions:
        extra_actions.append(
            "Review consider-ranked optional adapters as engineering work only."
        )
    report = _envelope(
        report_kind=REPORT_KIND_PRIORITY,
        timestamp=timestamp,
        repository_commit=commit,
        source_hashes=source_hashes,
        status=status,
        warnings=warnings,
        errors=errors,
        next_actions=extra_actions,
    )
    report.update(
        {
            "candidates": ranked,
            "ranking_disclaimer": (
                "Engineering priority from adoption_recommendation plus "
                "offline / network / privacy risk. NOT a scientific ranking, "
                "NOT evidence, NOT a PASS."
            ),
            "ranking_kind": "engineering_only",
        }
    )
    return report


def build_scientific_claim_risk_report(
    snapshot: Optional[InventorySnapshot],
    *,
    timestamp: str,
    source_hashes: Mapping[str, Any],
    status: str,
    warnings: Sequence[str],
    errors: Sequence[str],
    next_actions: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Always ``not_evidence``. Never PASS. Empirical labels ≠ PASS."""

    claim = inventory_claim_record(snapshot)
    status_value = inventory_scientific_claim_status(snapshot)
    if status_value in FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES:
        # Fail closed: never copy a forbidden status into the report body.
        status_value = INVENTORY_CLAIM_STATUS_NOT_EVIDENCE
    empirical_pass = False
    if snapshot is not None:
        for artifact in snapshot.artifacts:
            if artifact.label == ARTIFACT_LABEL_EMPIRICAL:
                empirical_pass = empirical_pass or empirical_label_is_scientific_pass(
                    artifact.label
                )
    commit = snapshot.commit_sha if snapshot is not None else ""
    extra_actions = list(
        next_actions
        if next_actions is not None
        else common_next_actions(
            has_errors=bool(errors),
            incomplete=status == STATUS_INCOMPLETE,
        )
    )
    extra_actions.append(
        "K>100 / scientific PASS gate remains out of scope for this subsystem."
    )
    report = _envelope(
        report_kind=REPORT_KIND_SCIENCE_RISK,
        timestamp=timestamp,
        repository_commit=commit,
        source_hashes=source_hashes,
        status=status,
        warnings=warnings,
        errors=errors,
        next_actions=extra_actions,
    )
    report.update(
        {
            "claim_record": claim,
            "empirical_label_is_pass": False,
            "forbidden_scientific_claim_statuses": sorted(
                FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES
            ),
            "inventory_is_evidence": inventory_is_scientific_evidence(snapshot),
            "k_gt_100_gate": "out_of_scope",
            "scientific_assertions": {
                "empirical_label_is_pass": False,
                "inventory_is_evidence": False,
                "k_gt_100_gate": "out_of_scope",
                "never_pass": True,
                "scientific_claim_status": INVENTORY_CLAIM_STATUS_NOT_EVIDENCE,
                "scientific_pass_gate": "out_of_scope",
            },
            "scientific_claim_status": status_value,
            "scientific_pass_gate": "out_of_scope",
            "statements": [
                "Inventory is not evidence.",
                "scientific_claim_status is always not_evidence.",
                "Reports never emit scientific PASS.",
                "Empirical labels are not a scientific PASS.",
                "K>100 / scientific PASS gate is out of scope for this subsystem.",
            ],
        }
    )
    _ = empirical_pass  # validator contract: always False
    return report


def _unique(items: Sequence[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _collect_validation(
    snapshot: Optional[InventorySnapshot],
    tool_rows: Sequence[Mapping[str, Any]],
    *,
    repo_root: Optional[Pathish],
    scan_text_contents: bool,
    loaded_from_real_yaml: bool,
) -> List[str]:
    errors: List[str] = []
    if snapshot is not None:
        errors.extend(
            validate_inventory_snapshot(
                snapshot,
                repo_root=repo_root if repo_root is not None else snapshot.repo_root,
                scan_text_contents=scan_text_contents,
                tool_sources=list(tool_rows) if tool_rows else None,
            )
        )
        errors.extend(validate_no_scientific_pass(snapshot))
        errors.extend(validate_duplicate_ownership(snapshot, tool_rows or None))
    if tool_rows:
        expect = EXPECTED_REAL_TOOL_SOURCE_COUNT if loaded_from_real_yaml else None
        require_nb = True if loaded_from_real_yaml else None
        errors.extend(
            validate_tool_source_registry(
                tool_rows,
                expect_count=expect,
                require_notebooklm=require_nb,
            )
        )
    errors.extend(validate_no_network_imports(extra_paths=[_REPORTING_PATH]))
    return _unique(errors)


def _load_tool_rows(
    repo_root: Pathish,
    *,
    tool_rows: Optional[Sequence[Mapping[str, Any]]],
    tool_sources_root: Optional[Pathish],
) -> tuple[List[Dict[str, Any]], Optional[str], bool, List[str], List[str]]:
    """Return rows, yaml hash, loaded_from_real_yaml, errors, warnings.

    On load failure, rows stay empty — do not invent a clean registry.
    """

    errors: List[str] = []
    warnings: List[str] = []
    if tool_rows is not None:
        rows = [dict(row) for row in tool_rows]
        rows.sort(key=lambda row: str(row.get("id") or ""))
        yaml_hash = None
        load_root = tool_sources_root if tool_sources_root is not None else repo_root
        try:
            yaml_hash = _hash_file_if_present(resolve_tool_sources_path(load_root))
        except FileNotFoundError:
            yaml_hash = None
        return rows, yaml_hash, False, errors, warnings

    load_root = tool_sources_root if tool_sources_root is not None else repo_root
    try:
        path = resolve_tool_sources_path(load_root)
        yaml_hash = _hash_file_if_present(path)
        rows = load_tool_sources(load_root)
        return rows, yaml_hash, True, errors, warnings
    except FileNotFoundError as exc:
        errors.append(f"tool sources YAML not found: {exc}")
        return [], None, False, errors, warnings
    except ValueError as exc:
        errors.append(f"tool sources YAML failed validation: {exc}")
        return [], None, False, errors, warnings
    except OSError as exc:
        errors.append(f"tool sources YAML could not be read: {exc}")
        return [], None, False, errors, warnings


def _scan_or_use_snapshot(
    repo_root: Pathish,
    snapshot: Optional[InventorySnapshot],
) -> tuple[Optional[InventorySnapshot], List[str]]:
    if snapshot is not None:
        return snapshot, []
    try:
        return build_inventory_snapshot(repo_root), []
    except FileNotFoundError as exc:
        return None, [f"repo_root does not exist: {exc}"]
    except GitUnavailableError as exc:
        return None, [f"git unavailable (fail closed): {exc}"]
    except OSError as exc:
        return None, [f"inventory scan failed: {exc}"]


def resolve_bundle_status(
    *,
    errors: Sequence[str],
    snapshot: Optional[InventorySnapshot],
    tool_rows: Sequence[Mapping[str, Any]],
    loaded_from_real_yaml: bool,
) -> str:
    if errors:
        return STATUS_ERROR
    if snapshot is None:
        return STATUS_INCOMPLETE
    if not tool_rows:
        return STATUS_INCOMPLETE
    if loaded_from_real_yaml and len(tool_rows) != EXPECTED_REAL_TOOL_SOURCE_COUNT:
        return STATUS_INCOMPLETE
    return STATUS_OK


def build_report_bundle(
    repo_root: Pathish,
    *,
    output_dir: Optional[Pathish] = None,
    offline: bool = True,
    _now: Optional[Clockish] = None,
    generated_at: Optional[Clockish] = None,
    snapshot: Optional[InventorySnapshot] = None,
    tool_rows: Optional[Sequence[Mapping[str, Any]]] = None,
    tool_sources_root: Optional[Pathish] = None,
    scan_text_contents: Optional[bool] = None,
) -> Dict[str, Any]:
    """Build the six-report bundle. Optionally write it under ``output_dir``.

    ``_now`` / ``generated_at`` freeze the envelope timestamp for tests.
    Validation errors set ``status=error`` and populate ``errors``. Failed
    loads leave lists empty — this function does not invent clean data.

    ``offline`` is accepted for the public API. Reporting stays offline
    even if ``offline=False`` (warning, no network).
    """

    warnings: List[str] = []
    if not offline:
        warnings.append(
            "offline=False is ignored; reporting is offline-only and makes "
            "no network calls."
        )

    snapshot_obj, scan_errors = _scan_or_use_snapshot(repo_root, snapshot)
    rows, yaml_hash, loaded_from_real_yaml, load_errors, load_warnings = _load_tool_rows(
        repo_root,
        tool_rows=tool_rows,
        tool_sources_root=tool_sources_root,
    )
    warnings.extend(load_warnings)

    if scan_text_contents is None:
        scan_text_contents = snapshot is None

    validation_errors = _collect_validation(
        snapshot_obj,
        rows,
        repo_root=repo_root,
        scan_text_contents=bool(scan_text_contents),
        loaded_from_real_yaml=loaded_from_real_yaml,
    )
    errors = _unique([*scan_errors, *load_errors, *validation_errors])

    status = resolve_bundle_status(
        errors=errors,
        snapshot=snapshot_obj,
        tool_rows=rows,
        loaded_from_real_yaml=loaded_from_real_yaml,
    )
    timestamp = format_timestamp(_now=_now, generated_at=generated_at)
    hashes = build_source_hashes(
        snapshot_obj,
        tool_sources_yaml_hash=yaml_hash,
        tool_rows=rows,
        repo_root=repo_root,
    )
    commit = snapshot_obj.commit_sha if snapshot_obj is not None else ""
    actions = common_next_actions(
        has_errors=bool(errors),
        incomplete=status == STATUS_INCOMPLETE,
    )
    dup_errors = (
        validate_duplicate_ownership(snapshot_obj, rows or None)
        if snapshot_obj is not None
        else []
    )

    reports = {
        f"{REPORT_KIND_REPOSITORY}.json": build_repository_inventory(
            snapshot_obj,
            timestamp=timestamp,
            source_hashes=hashes,
            status=status,
            warnings=warnings,
            errors=errors,
            next_actions=actions,
        ),
        f"{REPORT_KIND_ARTIFACT}.json": build_artifact_inventory(
            snapshot_obj,
            timestamp=timestamp,
            source_hashes=hashes,
            status=status,
            warnings=warnings,
            errors=errors,
            next_actions=actions,
        ),
        f"{REPORT_KIND_TOOL_ADMISSION}.json": build_tool_admission_inventory(
            snapshot_obj,
            rows,
            timestamp=timestamp,
            source_hashes=hashes,
            status=status,
            warnings=warnings,
            errors=errors,
            next_actions=actions,
            loaded_from_real_yaml=loaded_from_real_yaml,
        ),
        f"{REPORT_KIND_OWNERSHIP}.json": build_ownership_collision_report(
            snapshot_obj,
            rows,
            timestamp=timestamp,
            source_hashes=hashes,
            status=status,
            warnings=warnings,
            errors=errors,
            next_actions=actions,
            duplicate_ownership_errors=dup_errors,
        ),
        f"{REPORT_KIND_PRIORITY}.json": build_retrofit_priority_report(
            snapshot_obj,
            rows,
            timestamp=timestamp,
            source_hashes=hashes,
            status=status,
            warnings=warnings,
            errors=errors,
            next_actions=actions,
        ),
        f"{REPORT_KIND_SCIENCE_RISK}.json": build_scientific_claim_risk_report(
            snapshot_obj,
            timestamp=timestamp,
            source_hashes=hashes,
            status=status,
            warnings=warnings,
            errors=errors,
            next_actions=actions,
        ),
    }

    bundle: Dict[str, Any] = {
        "errors": list(errors),
        "generated_by": GENERATED_BY,
        "limitations": common_limitations(),
        "next_actions": actions,
        "report_filenames": list(REPORT_FILENAMES),
        "reports": reports,
        "repository_commit": commit,
        "schema_version": REPORT_SCHEMA_VERSION,
        "source_hashes": hashes,
        "status": status,
        "timestamp": timestamp,
        "warnings": list(warnings),
    }
    if output_dir is not None:
        write_report_bundle(bundle, output_dir)
    return bundle


def write_report_bundle(bundle: Mapping[str, Any], output_dir: Pathish) -> List[Path]:
    """Write the six report files only under ``output_dir``."""

    reports = bundle.get("reports")
    if not isinstance(reports, Mapping):
        raise ValueError("bundle.reports must be a mapping of the six report files")
    missing = [name for name in REPORT_FILENAMES if name not in reports]
    if missing:
        raise ValueError(f"bundle.reports missing: {', '.join(missing)}")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for name in REPORT_FILENAMES:
        path = out / name
        path.write_text(dump_json(reports[name]), encoding="utf-8")
        written.append(path)
    return written


__all__ = [
    "DEFAULT_OUTPUT_RELATIVE",
    "GENERATED_BY",
    "REPORT_FILENAMES",
    "REPORT_KINDS",
    "REPORT_SCHEMA_RELATIVE",
    "REPORT_SCHEMA_VERSION",
    "STATUS_ERROR",
    "STATUS_INCOMPLETE",
    "STATUS_OK",
    "build_artifact_inventory",
    "build_ownership_collision_report",
    "build_report_bundle",
    "build_repository_inventory",
    "build_retrofit_priority_report",
    "build_scientific_claim_risk_report",
    "build_source_hashes",
    "build_tool_admission_inventory",
    "common_limitations",
    "dump_json",
    "format_timestamp",
    "snapshot_digest",
    "write_report_bundle",
]
