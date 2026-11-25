"""Deterministic artifact generator for the migration-wave pack."""
from __future__ import annotations

import json
import os
import platform
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.benchmarking.pipeline_efficiency.telemetry import dumps, json_safe
from tools.benchmarking.migration_wave.harness import run_all
from tools.benchmarking.migration_wave.schema import (
    EVIDENCE_CLASS,
    OWNED_PATH_PREFIXES,
    REQUIRED_OUTPUT_FILES,
    SCHEMA_VERSION,
    TARGET_NAMES,
    VARIANT_NAMES,
)
from tools.benchmarking.migration_wave.validator import validate_root


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
        "No clinical claims. No ontology-layer claims. No proof claims. "
        "No remote dataset access. No production algorithm edits."
    )


def render_summary(report: Dict[str, Any]) -> str:
    ranking = (report.get("bottleneck_ranking") or [])[:12]
    opt = report.get("optimization_candidates") or []
    regs = report.get("regressions") or []
    lines = [
        "# Migration-wave benchmark summary",
        "",
        _guardrail_block(),
        "",
        f"- Schema: `{report.get('schema')}`",
        f"- Results: `{report.get('num_results')}`",
        f"- Summary: `{json.dumps(report.get('summary') or {}, sort_keys=True)}`",
        f"- Max workers: `{(report.get('config') or {}).get('max_workers')}`",
        "",
        "## Comparison matrix (runtime_best_s)",
        "",
    ]
    matrix = (report.get("comparison_matrix") or {}).get("cells") or {}
    variants = (report.get("comparison_matrix") or {}).get("variants") or []
    columns = ["target", *variants]
    table_rows = []
    for target in sorted(matrix):
        row = {"target": target}
        for name in variants:
            cell = (matrix.get(target) or {}).get(name) or {}
            row[name] = cell.get("runtime_best_s") if cell.get("status") == "ok" else cell.get("status")
        table_rows.append(row)
    lines.extend([_md_table(table_rows, columns), "", "## Bottleneck ranking (top 12)", "", _md_table(
        ranking,
        ["rank", "variant", "target", "status", "runtime_best_s", "tracemalloc_peak_bytes", "disk_bytes"],
    ), "", "## Regressions", ""])
    if not regs:
        lines.append("No same-surface correctness or advisory runtime regressions vs current_main.")
    else:
        for item in regs:
            lines.append(
                f"- `{item.get('variant')}` / `{item.get('target')}` / `{item.get('kind')}`: {item.get('detail')}"
            )
    lines.extend(["", "## Measured optimization candidates", ""])
    if not opt:
        lines.append("No production change is recommended. Ratios did not exceed evidence floors.")
    else:
        for item in opt:
            lines.append(
                f"- `{item.get('variant')}` `{item.get('target')}` / `{item.get('metric')}` "
                f"(ratio `{item.get('ratio')}`): {item.get('recommendation')}"
            )
    lines.extend(["", "## Limitations", ""])
    for note in report.get("notes") or []:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def generate(
    out: str | Path,
    *,
    seed: int = 0,
    size: int = 64,
    repetitions: int = 1,
    isolated: bool = False,
    harness_root: Optional[str | Path] = None,
    variant_roots: Optional[Dict[str, str]] = None,
    variants: Optional[list[str]] = None,
) -> Dict[str, Any]:
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    report = run_all(
        seed=seed,
        size=size,
        repetitions=repetitions,
        isolated=isolated,
        harness_root=harness_root,
        variant_roots=variant_roots,
        variants=variants,
    )
    write_json(root / "migration_wave_report.json", report)
    _write_atomic(root / "migration_wave_summary.md", render_summary(report))
    write_json(
        root / "generation_manifest.json",
        {
            "schema": SCHEMA_VERSION,
            "evidence_class": EVIDENCE_CLASS,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": list(REQUIRED_OUTPUT_FILES),
            "synthetic": True,
        },
    )
    write_json(root / "target_inventory.json", {"targets": sorted(TARGET_NAMES), "evidence_class": EVIDENCE_CLASS})
    write_json(root / "variant_inventory.json", report.get("variant_inventory"))
    write_json(root / "comparison_matrix.json", report.get("comparison_matrix"))
    write_json(root / "bottleneck_ranking.json", report.get("bottleneck_ranking"))
    write_json(root / "optimization_candidates.json", {"candidates": report.get("optimization_candidates"), "production_modified": False})
    write_json(
        root / "checksum_ledger.json",
        [
            {
                "variant": row.get("variant"),
                "target": row.get("target"),
                "status": row.get("status"),
                "checksum": (row.get("deterministic") or {}).get("checksum"),
                "surface": (row.get("deterministic") or {}).get("surface"),
            }
            for row in report.get("results") or []
        ],
    )
    write_json(
        root / "budget_verdicts.json",
        [
            {
                "variant": row.get("variant"),
                "target": row.get("target"),
                "budget": (row.get("deterministic") or {}).get("budget"),
            }
            for row in report.get("results") or []
        ],
    )
    write_json(
        root / "capability_probe.json",
        {
            "variants": report.get("variant_inventory"),
            "network_used": False,
            "remote_data_accessed": False,
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
        },
    )
    write_json(
        root / "governance_check.json",
        {
            "owned_paths": list(OWNED_PATH_PREFIXES),
            "evidence_class": EVIDENCE_CLASS,
            "production_modified": False,
        },
    )
    write_json(
        root / "telemetry_environment.json",
        {"platform": platform.system().lower(), "python_version": platform.python_version()},
    )
    vault = root / "obsidian"
    vault.mkdir(parents=True, exist_ok=True)
    index = ["# Migration wave", "", _guardrail_block(), "", "## Notes", ""]
    for spec in report.get("variant_inventory") or []:
        name = spec["variant"]
        dest = vault / f"{name}.md"
        dest.write_text(
            f"# {name}\n\n{_guardrail_block()}\n\n- PR: `{spec.get('pr')}`\n- SHA: `{spec.get('sha')}`\n- State: `{spec.get('pr_state')}`\n- Available: `{spec.get('available')}`\n",
            encoding="utf-8",
        )
        index.append(f"- [[{name}]]")
    for target in sorted(TARGET_NAMES):
        dest = vault / f"{target}.md"
        dest.write_text(f"# {target}\n\n{_guardrail_block()}\n", encoding="utf-8")
        index.append(f"- [[{target}]]")
    extra = {
        "Optimization_Candidates": "# Optimization candidates\n\n" + _guardrail_block() + "\n\n"
        + "\n".join(f"- {item.get('recommendation')}" for item in (report.get("optimization_candidates") or [{"recommendation": "none measured"}]))
        + "\n",
        "Measurement_Limitations": "# Measurement limitations\n\n" + _guardrail_block() + "\n\n"
        + "\n".join(f"- {n}" for n in (report.get("notes") or []))
        + "\n",
        "Guardrails": "# Guardrails\n\n" + _guardrail_block() + "\n",
        "Comparison_Matrix": "# Comparison matrix\n\n" + _guardrail_block() + "\n",
    }
    for name, text in extra.items():
        (vault / f"{name}.md").write_text(text, encoding="utf-8")
        index.append(f"- [[{name}]]")
    (vault / "Migration_Wave_Index.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    cc = root / "command_center"
    cc.mkdir(parents=True, exist_ok=True)
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
        "max_workers": 1,
    }
    write_json(cc / "status.json", {**base, "summary": report.get("summary")})
    write_json(cc / "checksum_gate.json", {**base, "ledger": "checksum_ledger.json"})
    write_json(cc / "optimization_queue.json", {**base, "candidates": report.get("optimization_candidates")})
    write_json(cc / "bottleneck_board.json", {**base, "ranking": report.get("bottleneck_ranking")})
    write_json(cc / "comparison_board.json", {**base, "matrix": report.get("comparison_matrix")})
    write_json(cc / "regression_gate.json", {**base, "regressions": report.get("regressions")})
    write_json(cc / "capability_board.json", {**base, "variants": report.get("variant_inventory")})
    write_json(root / "command_center_sync_result.json", {"ok": True, "n": 7})
    write_json(root / "obsidian_sync_result.json", {"ok": True, "vault": str(vault)})
    rag = root / "rag_pack"
    rag.mkdir(parents=True, exist_ok=True)
    chunks = render_summary(report)
    (rag / "chunks.md").write_text(chunks, encoding="utf-8")
    write_json(rag / "rag_pack.json", {"evidence_class": EVIDENCE_CLASS, "synthetic": True, "n_chunks": 1})
    validation = validate_root(root)
    write_json(root / "validation.json", validation)
    report["validation"] = validation
    return report
