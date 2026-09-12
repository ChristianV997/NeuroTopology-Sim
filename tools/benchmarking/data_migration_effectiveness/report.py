"""Markdown + finite JSON writers, Obsidian mirror, command-center, RAG pack."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from tools.benchmarking.data_migration_effectiveness.harness import run_all
from tools.benchmarking.data_migration_effectiveness.schema import (
    EVIDENCE_CLASS,
    OWNED_PATH_PREFIXES,
    REQUIRED_OUTPUT_FILES,
    SCHEMA_VERSION,
)
from tools.benchmarking.data_migration_effectiveness.telemetry import dumps, json_safe
from tools.benchmarking.data_migration_effectiveness.validator import validate_report, validate_root
from tools.benchmarking.data_migration_effectiveness.workloads import TARGETS

PathLike = Union[str, Path]


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def write_json(path: Path, obj: Any) -> None:
    _write_atomic(path, dumps(obj) + "\n")


def _opt_text(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("recommendation") or json.dumps(item, sort_keys=True, default=str))
    return str(item)


def _guardrail_block() -> str:
    return (
        "Evidence class: `performance_only`. Synthetic local fixtures only. "
        "No clinical claims. No ontology-layer claims. No proof claims. "
        "No scientific improvement claim. No OpenNeuro/AWS/DANDI access. "
        "No production data-access or streaming edits."
    )


def render_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Data-Migration Effectiveness Report",
        "",
        _guardrail_block(),
        "",
        f"- schema: `{payload.get('schema')}`",
        f"- evidence_class: `{payload.get('evidence_class')}`",
        f"- synthetic: `{payload.get('synthetic')}`",
        f"- scientific_improvement_claimed: `{payload.get('scientific_improvement_claimed')}`",
        f"- network_accessed: `{payload.get('network_accessed')}`",
        f"- all_checksums_match: `{payload.get('all_checksums_match')}`",
        "",
        "## Decision / status summary",
        "",
    ]
    for key, value in sorted((payload.get("summary") or {}).items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Targets",
            "",
            "| target | status | checksum_match | runtime_ratio | tm_ratio |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in payload.get("results") or []:
        tel = row.get("telemetry") or {}
        det = row.get("deterministic") or {}
        lines.append(
            f"| `{row.get('target')}` | `{row.get('status')}` | `{det.get('checksum_match')}` | "
            f"`{tel.get('runtime_ratio_candidate_over_baseline_advisory')}` | "
            f"`{tel.get('tracemalloc_peak_ratio_candidate_over_baseline')}` |"
        )
    lines.extend(["", "## Measured optimization candidates", ""])
    opts = payload.get("optimization_candidates") or []
    if not opts:
        lines.append("- none (no measured ratio exceeded advisory thresholds)")
    else:
        for item in opts:
            lines.append(f"- {_opt_text(item)}")
    lines.extend(["", "## Limitations", ""])
    for lim in payload.get("limitations") or []:
        lines.append(f"- {lim}")
    lines.append("")
    return "\n".join(lines)


def write_reports(payload: Dict[str, Any], output_dir: PathLike) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    jp = out / "data_migration_effectiveness.json"
    mp = out / "data_migration_effectiveness.md"
    write_json(jp, payload)
    _write_atomic(mp, render_markdown(payload))
    return {"json": str(jp), "markdown": str(mp)}


def _obsidian_notes(report: Dict[str, Any], vault: Path) -> List[str]:
    vault.mkdir(parents=True, exist_ok=True)
    written: List[str] = []
    index_lines = [
        "# Data-migration effectiveness",
        "",
        _guardrail_block(),
        "",
        "## Notes",
        "",
    ]
    for rec in report.get("results") or []:
        name = rec["target"]
        dest = vault / f"{name}.md"
        det = rec.get("deterministic") or {}
        tel = rec.get("telemetry") or {}
        cand = tel.get("candidate") or {}
        body = "\n".join(
            [
                f"# {name}",
                "",
                _guardrail_block(),
                "",
                f"- Path family: `{rec.get('path_family')}`",
                f"- Status: `{rec.get('status')}`",
                f"- Checksum match: `{det.get('checksum_match')}`",
                f"- Feature count: `{det.get('feature_count')}`",
                f"- Rejected full object: `{det.get('rejected_full_object')}`",
                f"- Candidate runtime_best_s: `{cand.get('runtime_best_s')}`",
                f"- Candidate planning_latency_s: `{cand.get('planning_latency_s')}`",
                f"- Candidate tracemalloc_peak_bytes: `{cand.get('tracemalloc_peak_bytes')}`",
                f"- Candidate rss_after_bytes: `{cand.get('rss_after_bytes')}`",
                f"- Candidate disk_bytes: `{cand.get('disk_bytes')}`",
                f"- Candidate cache_occupancy_bytes: `{cand.get('cache_occupancy_bytes')}`",
                f"- Candidate evicted_bytes: `{cand.get('evicted_bytes')}`",
                f"- Candidate retry_attempts: `{cand.get('retry_attempts')}`",
                "",
                "## Optimization candidates",
                "",
            ]
            + [f"- {_opt_text(item)}" for item in (rec.get("optimization_candidates") or ["none measured"])]
            + [""]
        )
        dest.write_text(body, encoding="utf-8")
        written.append(str(dest))
        index_lines.append(f"- [[{name}]]")
    extras = {
        "Optimization_Candidates": "# Optimization candidates\n\n"
        + _guardrail_block()
        + "\n\n"
        + "\n".join(
            f"- {_opt_text(item)}"
            for item in (report.get("optimization_candidates") or ["no measured bottleneck exceeded thresholds"])
        )
        + "\n",
        "Measurement_Limitations": "# Measurement limitations\n\n"
        + _guardrail_block()
        + "\n\n"
        + "\n".join(f"- {n}" for n in (report.get("limitations") or []))
        + "\n",
        "Guardrails": "# Guardrails\n\n"
        + _guardrail_block()
        + "\n\n- Owned paths: "
        + ", ".join(f"`{p}`" for p in OWNED_PATH_PREFIXES)
        + "\n",
        "Correctness_Vs_Performance": "# Correctness vs performance\n\n"
        + _guardrail_block()
        + "\n\nChecksums are the correctness gate. Runtime, RSS, tracemalloc, "
        + "disk, occupancy, eviction, and retry counts are telemetry and may be null.\n",
    }
    for name, text in extras.items():
        dest = vault / f"{name}.md"
        dest.write_text(text, encoding="utf-8")
        written.append(str(dest))
        index_lines.append(f"- [[{name}]]")
    index = vault / "Data_Migration_Effectiveness_Index.md"
    index.write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    written.append(str(index))
    return written


def _command_center(report: Dict[str, Any], out: Path) -> List[str]:
    out.mkdir(parents=True, exist_ok=True)
    written: List[str] = []
    base = {
        "ok": True,
        "evidence_class": EVIDENCE_CLASS,
        "synthetic": True,
        "schema": SCHEMA_VERSION,
        "network_required": False,
        "api_keys_required": False,
        "scientific_improvement_claimed": False,
        "diagnosis_claims_allowed": False,
        "treatment_claims_allowed": False,
        "ontology_promotion_allowed": False,
        "proof_claims_allowed": False,
        "real_data_auto_execution_allowed": False,
        "max_workers": (report.get("config") or {}).get("max_workers", 1),
    }
    payloads = {
        "status.json": {
            **base,
            "summary": report.get("summary"),
            "all_checksums_match": report.get("all_checksums_match"),
            "regressions": report.get("regressions"),
            "network_accessed": report.get("network_accessed"),
        },
        "checksum_gate.json": {
            **base,
            "all_checksums_match": report.get("all_checksums_match"),
            "ledger": [
                {
                    "target": r.get("target"),
                    "checksum_baseline": (r.get("deterministic") or {}).get("checksum_baseline"),
                    "checksum_candidate": (r.get("deterministic") or {}).get("checksum_candidate"),
                    "checksum_match": (r.get("deterministic") or {}).get("checksum_match"),
                    "status": r.get("status"),
                }
                for r in report.get("results") or []
            ],
        },
        "optimization_queue.json": {
            **base,
            "candidates": report.get("optimization_candidates"),
        },
        "telemetry_board.json": {
            **base,
            "results": [
                {
                    "target": r.get("target"),
                    "status": r.get("status"),
                    "telemetry": r.get("telemetry"),
                }
                for r in report.get("results") or []
            ],
        },
        "production_availability.json": {
            **base,
            "production_available": report.get("production_available"),
        },
        "limitations.json": {
            **base,
            "limitations": report.get("limitations"),
        },
    }
    for name, payload in payloads.items():
        path = out / name
        write_json(path, payload)
        written.append(str(path))
    return written


def _rag_pack(report: Dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    chunks = []
    for rec in report.get("results") or []:
        chunks.append(
            {
                "id": rec.get("target"),
                "text": (
                    f"Target {rec.get('target')} status {rec.get('status')} "
                    f"checksum_match {(rec.get('deterministic') or {}).get('checksum_match')} "
                    f"path_family {rec.get('path_family')} evidence_class {EVIDENCE_CLASS}. "
                    "Performance-only synthetic measurement; not scientific evidence."
                ),
                "evidence_class": EVIDENCE_CLASS,
                "synthetic": True,
                "claim_scope": "performance_engineering",
            }
        )
    write_json(
        out / "rag_pack.json",
        {
            "safe_only": True,
            "evidence_class": EVIDENCE_CLASS,
            "items": chunks,
            "redaction_rules": ["mask_api_keys", "drop_secrets", "strip_credentials"],
        },
    )
    lines = ["# Data-migration effectiveness RAG chunks", "", _guardrail_block(), ""]
    for chunk in chunks:
        lines.extend([f"## {chunk['id']}", "", chunk["text"], ""])
    (out / "chunks.md").write_text("\n".join(lines), encoding="utf-8")


def generate(
    out_dir: str | Path,
    *,
    seed: int = 0,
    size: int = 64,
    repetitions: int = 1,
    report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    if report is None:
        report = run_all(seed=seed, size=size, repetitions=repetitions)
    write_reports(report, root)
    write_json(
        root / "generation_manifest.json",
        {
            "schema": SCHEMA_VERSION,
            "evidence_class": EVIDENCE_CLASS,
            "synthetic": True,
            "scientific_improvement_claimed": False,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "owned_paths": list(OWNED_PATH_PREFIXES),
            "required_files": list(REQUIRED_OUTPUT_FILES),
            "config": report.get("config"),
        },
    )
    write_json(
        root / "target_inventory.json",
        {
            "targets": [
                {"name": spec.name, "path_family": spec.path_family, "default_size": spec.default_size}
                for spec in (TARGETS[k] for k in sorted(TARGETS))
            ],
            "evidence_class": EVIDENCE_CLASS,
        },
    )
    _obsidian_notes(report, root / "obsidian")
    _command_center(report, root / "command_center")
    _rag_pack(report, root / "rag")
    validation = validate_report(report)
    write_json(root / "validation.json", validation)
    packed = json.loads((root / "data_migration_effectiveness.json").read_text(encoding="utf-8"))
    packed["_pack_validation"] = validation
    return json_safe(report)


def validate(root: str | Path) -> Dict[str, Any]:
    return validate_root(root)
