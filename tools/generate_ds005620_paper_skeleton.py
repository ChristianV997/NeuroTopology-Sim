"""
Generate DS005620 paper skeleton with reviewer checklist (P18.2 / O4).

Reads the evidence packet and optional ontology evaluation to produce:
- paper_skeleton.md          — structured paper template
- reviewer_checklist.md      — peer review checklist
- negative_space_disclaimers.md — explicit negative-space statements

Usage:
  python tools/generate_ds005620_paper_skeleton.py \\
    --evidence outputs/btc_icft/ds005620_real_benchmark_execution_mock/evidence_packet.json \\
    --out outputs/btc_icft/ds005620_real_benchmark_execution_mock \\
    --ontology-root outputs/btc_icft/ds005620_ontology_evaluation_mock
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure repo root is on sys.path when running as a script from tools/.
sys.path.insert(0, str(Path(__file__).parent.parent))

from sciencer_d.btc_icft.ontology.artifact_reader import (
    load_claim_scope_matrix,
    summarize_ontology_for_packet,
)


_SAFE_CLAIM = (
    "DS005620 paper skeleton generated from engineering evidence packet. "
    "Template only — no empirical claims are made in this artifact."
)

_DEFAULT_ONTOLOGY_ROOT = "outputs/btc_icft/ds005620_ontology_evaluation_mock"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _build_ontology_claim_scope_section(ontology_root: Path) -> str:
    summary = summarize_ontology_for_packet(ontology_root)
    scope_matrix = load_claim_scope_matrix(ontology_root)

    lines = [
        "## Ontology and Claim Scope",
        "",
        "### Claim Scope Matrix",
        "",
    ]
    if scope_matrix:
        for scope, info in scope_matrix.items():
            allowed = info.get("allowed", False)
            max_state = info.get("max_state", "unknown")
            lines.append(f"- `{scope}`: allowed={allowed}, max_state=`{max_state}`")
            for b in info.get("blockers", []):
                lines.append(f"  - blocker: {b}")
    else:
        lines.append(
            "- Claim scope matrix not yet generated. "
            "Run `make ds005620-ontology-eval-mock`."
        )

    lines += [
        "",
        "### Bridge Claim Status",
        "",
        f"- Current promotion state: `{summary.get('promotion_state', 'engineering_validated')}`",
        f"- Max claim scope: `{summary.get('max_claim_scope', 'engineering_runtime')}`",
        f"- Ontology claim status: `{summary.get('ontology_claim_status', 'ontology_quarantined')}`",
    ]

    counts = summary.get("bridge_status_counts", {})
    if counts:
        lines.append("")
        for status, n in sorted(counts.items()):
            lines.append(f"- Bridge status `{status}`: {n}")

    lines += [
        "",
        "### Falsifiers",
        "",
        (
            "All declared bridge falsifiers must be evaluated before empirical promotion. "
            "Current status: `not_evaluated` (mock E2E run only). "
            "See `falsifier_status.json` in the ontology evaluation output."
        ),
        "",
        "### Alternative Explanations",
        "",
        (
            "All declared alternative explanations must be addressed before promotion. "
            "Current status: `not_evaluated`. "
            "See `alternative_explanations.json` in the ontology evaluation output."
        ),
        "",
        "### Current Promotion State",
        "",
        f"- **{summary.get('promotion_state', 'engineering_validated')}**",
        "",
        "### What the Current Artifact Set Can Support",
        "",
        "- Engineering runtime validation (mock E2E chain completed).",
        "- Publication of the benchmark protocol for peer review.",
        "- Description of the claim-scope gate for reviewer evaluation.",
        "",
        "### What Remains Blocked",
        "",
    ]
    blocked = summary.get("blocked_claims", [])
    if blocked:
        for c in blocked:
            lines.append(f"- `{c}` (requires real execution, controls, and review)")
    else:
        lines.append(
            "- Level M empirical promotion (requires real execution + reviewed labels + controls)."
        )
        lines.append(
            "- Level T topology residual promotion (requires real execution + controls)."
        )

    lines += [
        "",
        "### What Remains Quarantined",
        "",
        "- Substrate mechanism candidates: require independent biophysical evidence.",
        "- Theory candidates: remain at theory-consistency scope only.",
        "- Ontology candidates: permanently quarantined pending independent evidence.",
        "",
    ]
    return "\n".join(lines)


def _build_paper_skeleton(evidence: dict, ontology_root: Path) -> str:
    mode = evidence.get("mode", "unknown")
    benchmark_completed = evidence.get("benchmark_completed", False)
    p11_ok = evidence.get("stage_outcomes", {}).get("p11_succeeded", False)

    ontology_section = _build_ontology_claim_scope_section(ontology_root)

    lines = [
        "# DS005620 Benchmark Study — Paper Skeleton",
        "",
        "> **Status:** TEMPLATE ONLY — requires independent peer review before any empirical claims",
        "",
        "## Abstract (placeholder)",
        "",
        (
            "We applied a controlled labeled-residual benchmark to EEG signal windows "
            "from DS005620, using human-reviewed external label contracts (P17.1) "
            "and explicit target injection (P13). The engineering chain (P12 → P13 → P11) "
            "ran end-to-end in guarded mode. This skeleton records the protocol and "
            "placeholder slots for results pending independent peer review."
        ),
        "",
        "## 1. Introduction",
        "",
        "_(Background on DS005620 dataset and research question — to be written by authors.)_",
        "",
        "## 2. Methods",
        "",
        "### 2.1 Dataset",
        "",
        "- Dataset: DS005620",
        "- Source: OpenNeuro (or local mirror)",
        "- Label provenance: Human-reviewed external contract (P17.1 artifact)",
        "",
        "### 2.2 Label Contract",
        "",
        "- Contract status: `active_reviewed_external_contract`",
        "- Explicit label column: as declared in `p12_external_contract.json`",
        "- Positive/negative values: as declared in `p12_external_contract.json`",
        "- No labels inferred from filenames, topology, or EEG artifacts",
        "",
        "### 2.3 Feature Extraction",
        "",
        "- Level M (signal features): P9 pipeline",
        "- Level T (topology features): P10 pipeline",
        "- Join keys: 8 strict keys (dataset_id, row_id, source_file, window_id, ...)",
        "",
        "### 2.4 Benchmark",
        "",
        "- Label alignment: P12 (`align_eeg_labels --external-contract`)",
        "- Target injection: P13 (`inject_eeg_targets`)",
        "- M+T benchmark: P11 (`run_eeg_signal_mt`)",
        "- P11 consumed P13 labeled file — not raw Level M",
        "",
        f"### 2.5 Execution Mode",
        "",
        f"- Mode used for this skeleton: `{mode}`",
        f"- Benchmark completed: {benchmark_completed}",
        f"- P11 succeeded: {p11_ok}",
        "",
        "## 3. Results (placeholder)",
        "",
        "_(Insert `metrics_signal_mt.json` results here after independent review.)_",
        "",
        "| Metric | Value | Notes |",
        "|---|---|---|",
        "| (placeholder) | (placeholder) | (placeholder) |",
        "",
        "## 4. Discussion",
        "",
        "_(Authors: discuss results in the context of the declared hypothesis.)_",
        "",
        "## 5. Limitations",
        "",
        "- Mock E2E uses synthetic fixtures, not real patient data",
        "- Results require independent statistical review",
        "- No null distribution computed in this skeleton",
        "- No ablation set included",
        "",
        "## 6. Negative Space (see negative_space_disclaimers.md)",
        "",
        (
            "This study makes no assertions about internal states, awareness, or any "
            "metaphysical or soteriological properties of any biological or computational system. "
            "See `negative_space_disclaimers.md` for the full explicit negative-space statement."
        ),
        "",
        ontology_section,
        "",
        "## References",
        "",
        "_(To be filled in by authors.)_",
        "",
        "---",
        "",
        f"_Generated by P18.2 / O4 paper skeleton tool — {datetime.now(timezone.utc).isoformat()}_",
        f"_Safe claim: {_SAFE_CLAIM}_",
    ]
    return "\n".join(lines)


def _build_reviewer_checklist(evidence: dict, ontology_root: Path) -> str:
    omega = evidence.get("omega_invariants", {})
    summary = summarize_ontology_for_packet(ontology_root)

    lines = [
        "# DS005620 Paper Reviewer Checklist",
        "",
        "Use this checklist when reviewing the DS005620 paper skeleton.",
        "",
        "## Engineering Integrity",
        "",
        "- [ ] `benchmark_completed` is `true` in execution artifact",
        "- [ ] All three stages (P12, P13, P11) succeeded",
        "- [ ] P11 consumed `features_m_signal_labeled.csv` (from P13), not raw Level M",
        "- [ ] All omega invariants are `false`:",
    ]
    for k in [
        "labels_inferred", "targets_fabricated", "source_contracts_modified",
        "legacy_mt_real_modified", "contracts_activated_by_executor",
        "p11_promotion_gate_modified", "consciousness_claims_made",
    ]:
        v = omega.get(k, "NOT FOUND")
        lines.append(f"  - [ ] `{k}`: {v} (must be false)")
    lines += [
        "",
        "## Label Contract Review",
        "",
        "- [ ] `p12_external_contract.json` reviewed and `contract_status` is `active_reviewed_external_contract`",
        "- [ ] `explicit_label_column` matches actual metadata column",
        "- [ ] `positive_values` and `negative_values` are non-overlapping and non-empty",
        "- [ ] No sedated/unresponsive shortcut mappings in contract",
        "- [ ] Join keys match strict 8-key set",
        "",
        "## Statistical Review",
        "",
        "- [ ] Results in `metrics_signal_mt.json` are reported with full provenance",
        "- [ ] Null distribution or permutation test included (or explicitly noted as future work)",
        "- [ ] ROI and statistical thresholds preregistered or justified",
        "- [ ] Effect sizes reported",
        "",
        "## Negative Space",
        "",
        "- [ ] Paper does not make assertions about internal states or awareness",
        "- [ ] Paper does not make metaphysical or soteriological claims",
        "- [ ] `negative_space_disclaimers.md` is cited or appended",
        "",
        "## Ontology Review Checklist",
        "",
        f"- **Current claim scope:** `{summary.get('max_claim_scope', 'engineering_runtime')}`",
        f"- **Current promotion state:** `{summary.get('promotion_state', 'engineering_validated')}`",
        f"- **Ontology claim status:** `{summary.get('ontology_claim_status', 'ontology_quarantined')}`",
        "",
        "- [ ] Claim scope matrix reviewed (see `claim_scope_matrix.json`)",
        "- [ ] Bridge claim status reviewed (see `bridge_claim_status.json`)",
        "- [ ] Falsifiers reviewed (see `falsifier_status.json`)",
        "- [ ] Alternative explanations reviewed (see `alternative_explanations.json`)",
        "- [ ] Level M / T claims require real execution and controls before promotion",
        "- [ ] Substrate / mechanism claims require independent biophysical evidence",
        "- [ ] Theory candidates remain at theory-consistency scope only",
        "- [ ] Ontology candidates remain quarantined",
        "- [ ] No metric-to-ontology shortcut present in manuscript",
        "- [ ] No state-label shortcut present in manuscript",
        "- [ ] No direct equivalence claim between benchmark metrics and any experiential property",
        "",
        "---",
        "_P18.2 / O4 reviewer checklist — template only._",
    ]
    return "\n".join(lines)


def _build_negative_space_disclaimers(ontology_root: Path) -> str:
    summary = summarize_ontology_for_packet(ontology_root)

    lines = [
        "# DS005620 Negative Space Disclaimers",
        "",
        "This document records what the DS005620 benchmark study does NOT claim.",
        "",
        "## Engineering Scope",
        "",
        (
            "The DS005620 benchmark chain (P12 → P13 → P11) is an engineering "
            "pipeline that aligns human-reviewed external labels, injects explicit "
            "targets, and computes signal and topology features. It is NOT a "
            "measurement or proof of any experiential, metaphysical, soteriological, "
            "or ontological property."
        ),
        "",
        "## Explicit Non-Claims",
        "",
        "This study makes NO assertions about:",
        "",
        "- Internal subjective experience of any kind",
        "- Awareness, sentience, or any related property",
        "- The self, personal identity, or soul",
        "- Liberation, enlightenment, or soteriological states",
        "- Afterlife, continuity of any kind beyond the physical",
        "- Whether EEG topology relates to any experiential state",
        "- Whether any metric in `metrics_signal_mt.json` indicates experiential states",
        "- Whether any biological state (sedated, anesthetized, unresponsive) implies any experiential state",
        "",
        "## Ontology Quarantine Disclaimer",
        "",
        (
            "The ontology evaluation layer (O1-O4) assigns all ontology-candidate "
            "claims to `ontology_quarantined` status. This is the permanent default "
            "for the current artifact set. Quarantine is not lifted by benchmark "
            "results alone."
        ),
        "",
        f"- Current ontology claim status: `{summary.get('ontology_claim_status', 'ontology_quarantined')}`",
        f"- Current max claim scope: `{summary.get('max_claim_scope', 'engineering_runtime')}`",
        "",
        "## Mock E2E Scope Disclaimer",
        "",
        (
            "The mock E2E run does not support empirical promotion of any Level M "
            "or Level T claim. Real execution, reviewed labels, and controls are "
            "required before empirical promotion. The current artifact set "
            "supports engineering runtime validation only."
        ),
        "",
        "## Real Execution Scope Disclaimer",
        "",
        (
            "Real execution without controls does not support topology-residual "
            "promotion. Controls (nulls, ablations, leakage report, artifact report) "
            "are required for Level T claims."
        ),
        "",
        "## Mechanism Candidate Disclaimer",
        "",
        (
            "Mechanism candidates require independent biophysical evidence beyond "
            "EEG benchmark performance. Benchmark results alone do not establish "
            "a substrate mechanism."
        ),
        "",
        "## Label Provenance Statement",
        "",
        (
            "All labels were sourced from a human-reviewed external contract (P17.1). "
            "No labels were inferred from filenames, EEG topology, signal artifacts, "
            "or any automated heuristic."
        ),
        "",
        "## Target Provenance Statement",
        "",
        (
            "All targets were injected by P13 from the P12 label alignment output. "
            "No targets were fabricated, imputed, or derived from model predictions."
        ),
        "",
        "---",
        "_P18.2 / O4 negative space disclaimers — required attachment for all DS005620 paper submissions._",
    ]
    return "\n".join(lines)


def generate_paper_skeleton(
    evidence_path: str,
    out_dir: str,
    *,
    ontology_root: str | None = None,
    require_ontology: bool = False,
) -> dict[str, str]:
    evidence = _load_json(Path(evidence_path))
    _ontology_root = Path(ontology_root) if ontology_root else Path(_DEFAULT_ONTOLOGY_ROOT)

    if require_ontology:
        summary = summarize_ontology_for_packet(_ontology_root)
        if not summary["ontology_available"]:
            raise SystemExit(
                f"--require-ontology is set but ontology evaluation not found at {_ontology_root}"
            )

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    skeleton_path = out / "paper_skeleton.md"
    skeleton_path.write_text(_build_paper_skeleton(evidence, _ontology_root), encoding="utf-8")

    checklist_path = out / "reviewer_checklist.md"
    checklist_path.write_text(_build_reviewer_checklist(evidence, _ontology_root), encoding="utf-8")

    disclaimers_path = out / "negative_space_disclaimers.md"
    disclaimers_path.write_text(_build_negative_space_disclaimers(_ontology_root), encoding="utf-8")

    return {
        "paper_skeleton.md": str(skeleton_path),
        "reviewer_checklist.md": str(checklist_path),
        "negative_space_disclaimers.md": str(disclaimers_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate DS005620 paper skeleton (P18.2 / O4)")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument(
        "--ontology-root",
        default=_DEFAULT_ONTOLOGY_ROOT,
        help="Path to ontology evaluation output directory",
    )
    parser.add_argument(
        "--require-ontology",
        action="store_true",
        default=False,
        help="Exit nonzero if ontology evaluation is absent",
    )
    args = parser.parse_args(argv)

    out_dir = args.out or str(Path(args.evidence).parent)
    artifacts = generate_paper_skeleton(
        args.evidence,
        out_dir,
        ontology_root=args.ontology_root,
        require_ontology=args.require_ontology,
    )
    for name, path in artifacts.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
