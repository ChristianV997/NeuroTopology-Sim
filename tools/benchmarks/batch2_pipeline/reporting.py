"""Deterministic artifact generator: inventory, reports, Obsidian, command-center, RAG."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .harness import TOOLING_AVAILABILITY, run_all
from .schema import (
    EVIDENCE_CLASS,
    OWNED_PATH_PREFIXES,
    REQUIRED_OUTPUT_FILES,
    SCHEMA_VERSION,
)
from .telemetry import dumps, json_safe
from .workloads import TARGETS


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
            os.unlink(tmp)


def write_json(path: Path, obj: Any) -> None:
    _write_atomic(path, dumps(obj) + "\n")


def _md_table(rows: List[Dict[str, Any]], columns: List[str]) -> str:
    head = "| " + " | ".join(columns) + " |\n|" + "|".join(["---"] * len(columns)) + "|"
    body = [
        "| " + " | ".join("" if r.get(c) is None else str(r.get(c)) for c in columns) + " |"
        for r in rows
    ]
    return "\n".join([head, *body])


def _guardrail_block() -> str:
    return (
        "Evidence class: `performance_only`. Synthetic local fixtures only. "
        "No clinical claims. No ontology-layer claims. No proof claims. No remote "
        "dataset access. No Awareness Studio import. No production algorithm edits. "
        "Results are not scientific evidence."
    )


def render_summary(report: Dict[str, Any]) -> str:
    ranking = report.get("bottleneck_ranking") or []
    opt = report.get("optimization_candidates") or []
    lines = [
        "# Batch-2 pipeline benchmark summary",
        "",
        _guardrail_block(),
        "",
        f"- Schema: `{report.get('schema')}`",
        f"- Targets: `{report.get('num_targets')}`",
        f"- Summary: `{json.dumps(report.get('summary') or {}, sort_keys=True)}`",
        f"- All equivalent: `{report.get('all_equivalent')}`",
        f"- All within budget: `{report.get('all_within_budget')}`",
        f"- Max workers: `{(report.get('config') or {}).get('max_workers')}`",
        "",
        "## Bottleneck ranking (baseline waste signals)",
        "",
        _md_table(
            ranking,
            [
                "rank",
                "target",
                "status",
                "baseline_read_counts",
                "baseline_preprocess_calls",
                "baseline_fsync_calls",
                "baseline_runtime_best_s",
                "runtime_ratio_advisory",
            ],
        ),
        "",
        "## Measured optimization candidates",
        "",
    ]
    if not opt:
        lines.append(
            "No production change is recommended. Counter deltas / ratios did not "
            "exceed evidence thresholds, or metrics were null."
        )
    else:
        for item in opt:
            lines.append(
                f"- `{item.get('target')}` / `{item.get('metric')}`: {item.get('recommendation')}"
            )
    lines.extend(["", "## Per-target checksums", ""])
    for rec in report.get("results") or []:
        det = rec.get("deterministic") or {}
        lines.append(
            f"- `{rec.get('target')}`: status=`{rec.get('status')}` "
            f"match=`{det.get('checksum_match')}` "
            f"baseline=`{det.get('checksum_baseline')}` "
            f"candidate=`{det.get('checksum_candidate')}`"
        )
    lines.extend(["", "## Limitations", ""])
    for note in report.get("notes") or []:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def _obsidian_notes(report: Dict[str, Any], vault: Path) -> List[str]:
    vault.mkdir(parents=True, exist_ok=True)
    written: List[str] = []
    index_lines = [
        "# Batch-2 pipeline benchmarks",
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
                f"- Counter deltas: `{json.dumps(rec.get('counter_deltas'), default=str)}`",
                f"- Candidate runtime_best_s: `{(tel.get('candidate') or {}).get('runtime_best_s')}`",
                f"- Candidate tracemalloc_peak_bytes: `{(tel.get('candidate') or {}).get('tracemalloc_peak_bytes')}`",
                f"- Candidate rss_after_bytes: `{(tel.get('candidate') or {}).get('rss_after_bytes')}`",
                f"- Candidate disk_bytes: `{(tel.get('candidate') or {}).get('disk_bytes')}`",
                f"- Worker count: `{tel.get('worker_count')}`",
                "",
                "## Recommendations",
                "",
            ]
            + [f"- {item}" for item in (rec.get("recommendations") or ["none"])]
            + ["", "## Optimization candidates", ""]
            + [
                f"- {item.get('recommendation')}"
                for item in (rec.get("optimization_candidates") or [{"recommendation": "none measured"}])
            ]
            + [""]
        )
        dest.write_text(body, encoding="utf-8")
        written.append(str(dest))
        index_lines.append(f"- [[{name}]]")
    for name, text in {
        "Optimization_Candidates": "# Optimization candidates\n\n"
        + _guardrail_block()
        + "\n\n"
        + "\n".join(
            f"- `{item.get('target')}`: {item.get('recommendation')}"
            for item in (
                report.get("optimization_candidates")
                or [{"target": "none", "recommendation": "no measured bottleneck exceeded thresholds"}]
            )
        )
        + "\n",
        "Measurement_Limitations": "# Measurement limitations\n\n"
        + _guardrail_block()
        + "\n\n"
        + "\n".join(f"- {n}" for n in (report.get("notes") or []))
        + "\n",
        "Guardrails": "# Guardrails\n\n"
        + _guardrail_block()
        + "\n\n- Owned paths: "
        + ", ".join(f"`{p}`" for p in OWNED_PATH_PREFIXES)
        + "\n",
    }.items():
        dest = vault / f"{name}.md"
        dest.write_text(text, encoding="utf-8")
        written.append(str(dest))
        index_lines.append(f"- [[{name}]]")
    index = vault / "Batch2_Pipeline_Index.md"
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
        "diagnosis_claims_allowed": False,
        "treatment_claims_allowed": False,
        "ontology_promotion_allowed": False,
        "proof_claims_allowed": False,
        "real_data_auto_execution_allowed": False,
        "max_workers": (report.get("config") or {}).get("max_workers", 1),
    }
    payloads = {
        "batch2_pipeline_status.json": {
            **base,
            "summary": report.get("summary"),
            "all_equivalent": report.get("all_equivalent"),
            "all_within_budget": report.get("all_within_budget"),
        },
        "bottleneck_board.json": {**base, "ranking": report.get("bottleneck_ranking")},
        "optimization_queue.json": {
            **base,
            "candidates": report.get("optimization_candidates"),
        },
        "budget_gate.json": {
            **base,
            "budgets": report.get("budgets"),
            "all_within_budget": report.get("all_within_budget"),
        },
        "checksum_gate.json": {
            **base,
            "all_equivalent": report.get("all_equivalent"),
            "ledger": [
                {
                    "target": r.get("target"),
                    "checksum_baseline": (r.get("deterministic") or {}).get("checksum_baseline"),
                    "checksum_candidate": (r.get("deterministic") or {}).get("checksum_candidate"),
                    "checksum_match": (r.get("deterministic") or {}).get("checksum_match"),
                }
                for r in report.get("results") or []
            ],
        },
        "tooling_status.json": {**base, "tooling_availability": report.get("tooling_availability")},
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
                    f"Not scientific evidence."
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
    lines = ["# Batch-2 pipeline RAG chunks", "", _guardrail_block(), ""]
    for chunk in chunks:
        lines.extend([f"## {chunk['id']}", "", chunk["text"], ""])
    (out / "chunks.md").write_text("\n".join(lines), encoding="utf-8")


def generate(
    out_dir: str | Path,
    *,
    seed: int = 0,
    size: Optional[int] = None,
    repetitions: int = 1,
    report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the campaign (unless ``report`` is provided) and write the artifact pack."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    if report is None:
        report = run_all(seed=seed, size=size, repetitions=repetitions)
    write_json(root / "batch2_pipeline_report.json", report)
    (root / "batch2_pipeline_summary.md").write_text(render_summary(report), encoding="utf-8")
    write_json(
        root / "generation_manifest.json",
        {
            "schema": SCHEMA_VERSION,
            "evidence_class": EVIDENCE_CLASS,
            "synthetic": True,
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
                {
                    "name": spec.name,
                    "path_family": spec.path_family,
                    "default_size": spec.default_size,
                }
                for spec in (TARGETS[k] for k in sorted(TARGETS))
            ],
            "evidence_class": EVIDENCE_CLASS,
        },
    )
    write_json(
        root / "bottleneck_ranking.json",
        {"ranking": report.get("bottleneck_ranking"), "evidence_class": EVIDENCE_CLASS},
    )
    write_json(
        root / "optimization_candidates.json",
        {
            "candidates": report.get("optimization_candidates"),
            "evidence_class": EVIDENCE_CLASS,
            "production_modified": False,
        },
    )
    write_json(root / "telemetry_environment.json", report.get("telemetry_environment"))
    write_json(
        root / "checksum_ledger.json",
        {
            "all_equivalent": report.get("all_equivalent"),
            "entries": [
                {
                    "target": r.get("target"),
                    "checksum_baseline": (r.get("deterministic") or {}).get("checksum_baseline"),
                    "checksum_candidate": (r.get("deterministic") or {}).get("checksum_candidate"),
                    "checksum_match": (r.get("deterministic") or {}).get("checksum_match"),
                }
                for r in report.get("results") or []
            ],
        },
    )
    write_json(
        root / "budget_verdicts.json",
        {
            "all_within_budget": report.get("all_within_budget"),
            "entries": [
                {"target": r.get("target"), "budget": (r.get("deterministic") or {}).get("budget")}
                for r in report.get("results") or []
            ],
        },
    )
    write_json(
        root / "counter_comparison.json",
        {
            "evidence_class": EVIDENCE_CLASS,
            "entries": [
                {
                    "target": r.get("target"),
                    "counter_deltas": r.get("counter_deltas"),
                    "baseline_counters": ((r.get("telemetry") or {}).get("baseline") or {}).get("counters"),
                    "candidate_counters": ((r.get("telemetry") or {}).get("candidate") or {}).get("counters"),
                }
                for r in report.get("results") or []
            ],
        },
    )
    write_json(
        root / "measurement_limitations.json",
        {
            "evidence_class": EVIDENCE_CLASS,
            "notes": report.get("notes"),
            "rss_may_be_null": True,
            "runtime_is_advisory": True,
            "missing_metrics_are_null": True,
            "not_scientific_evidence": True,
        },
    )
    write_json(
        root / "governance_check.json",
        {
            "evidence_class": EVIDENCE_CLASS,
            "denylist_enforced": True,
            "denylist_echoed": False,
            "owned_paths": list(OWNED_PATH_PREFIXES),
            "network_required": False,
            "remote_data": False,
        },
    )
    write_json(
        root / "tooling_availability.json",
        {
            "evidence_class": EVIDENCE_CLASS,
            "tooling_availability": report.get("tooling_availability") or TOOLING_AVAILABILITY,
            "rea": "REA_UNAVAILABLE",
        },
    )
    obsidian_written = _obsidian_notes(report, root / "obsidian")
    cc_written = _command_center(report, root / "command_center")
    _rag_pack(report, root / "rag_pack")
    write_json(
        root / "obsidian_sync_result.json",
        {"written": obsidian_written, "evidence_class": EVIDENCE_CLASS},
    )
    write_json(
        root / "command_center_sync_result.json",
        {"written": cc_written, "evidence_class": EVIDENCE_CLASS},
    )
    from .validator import validate_root

    validation = validate_root(root)
    write_json(root / "validation.json", validation)
    return report
