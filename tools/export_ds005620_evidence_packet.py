"""
Export DS005620 evidence packet for peer review (P18.2).

Reads the artifact manifest, execution summary, and omega event to produce:
- evidence_packet.json  — structured evidence record
- evidence_packet.md    — human-readable summary
- notion_import_payload.json — Notion-compatible import payload

Usage:
  python tools/export_ds005620_evidence_packet.py \\
    --manifest outputs/btc_icft/ds005620_real_benchmark_execution_mock/artifact_manifest.json \\
    --out outputs/btc_icft/ds005620_real_benchmark_execution_mock
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


_SAFE_CLAIM = (
    "DS005620 evidence packet exported from engineering benchmark artifacts. "
    "Contains only engineering results. Makes no metaphysical, soteriological, "
    "or experiential claims about any subject."
)

_PROMOTION_DECISION = "engineering_runtime_validated_only"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_evidence_packet(manifest_path: str, out_dir: str) -> dict[str, str]:
    manifest_p = Path(manifest_path)
    manifest = _load_json(manifest_p)
    root = Path(manifest.get("artifact_root", manifest_p.parent))

    execution = _load_json(root / "ds005620_real_benchmark_execution.json")
    omega = _load_json(root / "omega_event.json")
    stage_results = _load_json(root / "stage_results.json")

    benchmark_completed = execution.get("benchmark_completed", False)
    mode = execution.get("mode", "unknown")
    p12_ok = execution.get("p12_succeeded", False)
    p13_ok = execution.get("p13_succeeded", False)
    p11_ok = execution.get("p11_succeeded", False)

    omega_invariants = {
        "labels_inferred": omega.get("labels_inferred", False),
        "targets_fabricated": omega.get("targets_fabricated", False),
        "source_contracts_modified": omega.get("source_contracts_modified", False),
        "legacy_mt_real_modified": omega.get("legacy_mt_real_modified", False),
        "contracts_activated_by_executor": omega.get("contracts_activated_by_executor", False),
        "p11_promotion_gate_modified": omega.get("p11_promotion_gate_modified", False),
        "consciousness_claims_made": omega.get("consciousness_claims_made", False),
    }
    all_invariants_false = all(not v for v in omega_invariants.values())

    packet = {
        "dataset_id": "DS005620",
        "evidence_type": "engineering_benchmark_execution",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_completed": benchmark_completed,
        "mode": mode,
        "stage_outcomes": {
            "p12_succeeded": p12_ok,
            "p13_succeeded": p13_ok,
            "p11_succeeded": p11_ok,
        },
        "omega_invariants": omega_invariants,
        "all_omega_invariants_false": all_invariants_false,
        "promotion_decision": _PROMOTION_DECISION,
        "artifact_count": manifest.get("artifact_count", 0),
        "safe_claim": _SAFE_CLAIM,
        "source_manifest": str(manifest_p),
    }

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    packet_path = out / "evidence_packet.json"
    packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")

    md_lines = [
        "# DS005620 Evidence Packet",
        "",
        f"**Dataset:** DS005620",
        f"**Mode:** {mode}",
        f"**Benchmark completed:** {benchmark_completed}",
        f"**Promotion decision:** `{_PROMOTION_DECISION}`",
        "",
        "## Stage Outcomes",
        "",
        f"- P12 label alignment: {p12_ok}",
        f"- P13 target injection: {p13_ok}",
        f"- P11 M+T benchmark: {p11_ok}",
        "",
        "## Omega Invariants (all must be false)",
        "",
    ]
    for k, v in omega_invariants.items():
        md_lines.append(f"- `{k}`: {v}")
    md_lines += [
        "",
        "## Safe Claim",
        "",
        _SAFE_CLAIM,
        "",
        "## What This Is Not",
        "",
        (
            "This evidence packet records engineering execution results only. "
            "It makes no assertions about internal states, awareness, or any "
            "metaphysical properties of any biological or computational system."
        ),
        "",
        "---",
        "",
        "_P18.2 evidence export — no pipeline stages executed during this export._",
    ]
    md_path = out / "evidence_packet.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    notion_payload = {
        "title": "DS005620 Evidence Packet",
        "properties": {
            "Dataset": "DS005620",
            "Mode": mode,
            "Benchmark Completed": benchmark_completed,
            "Promotion Decision": _PROMOTION_DECISION,
            "All Omega Invariants False": all_invariants_false,
            "P12 Succeeded": p12_ok,
            "P13 Succeeded": p13_ok,
            "P11 Succeeded": p11_ok,
        },
        "content_md": "\n".join(md_lines),
    }
    notion_path = out / "notion_import_payload.json"
    notion_path.write_text(json.dumps(notion_payload, indent=2), encoding="utf-8")

    return {
        "evidence_packet.json": str(packet_path),
        "evidence_packet.md": str(md_path),
        "notion_import_payload.json": str(notion_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export DS005620 evidence packet (P18.2)")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    out_dir = args.out or str(Path(args.manifest).parent)
    artifacts = build_evidence_packet(args.manifest, out_dir)
    for name, path in artifacts.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
