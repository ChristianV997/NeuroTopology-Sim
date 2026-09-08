#!/usr/bin/env python3
"""CLI validation runner for directed-hypergraph feature contract integration.

Validates:
- Hyperedge normalization and duplicate-free canonical ordering
- Finite weights, bounded hyperedge counts, and declared units
- Feature extraction conformity with transitions.features canonical namespace
- Strict mathematical separation of beta-1 and spatial phase charge
- Non-causal guardrails (blocks causal terminology without causal design metadata)
- Evaluates 4 null controls: label permutation, temporal block shift, common driver, matched variance
- Emits strict null-safe JSON (allow_nan=False) or terminal summary
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add repository root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.higher_order_integration.hypergraph_adapter import (
    HypergraphFeatureAdapter,
    HypergraphValidationConfig,
)
from topo_monitor.higher_order.hypergraph import SparseDirectedHypergraph
from topo_monitor.higher_order.hypergraph_types import DirectedHyperedge


def build_demo_fixture_hyperedges() -> list[DirectedHyperedge]:
    """Create a standard benchmark suite of directed hyperedges across modalities."""
    return [
        DirectedHyperedge(
            source_nodes=("EEG_theta", "ECG_hrv_low"),
            target_nodes=("Respiration_apnea",),
            weight=2.4,
            confidence=0.92,
            window=(1.0, 3.5),
            context_variables={"state": "pre_apnea"},
            provenance="synthetic_multimodal_fixture",
        ),
        DirectedHyperedge(
            source_nodes=("Respiration_apnea",),
            target_nodes=("EEG_delta_burst", "ECG_tachycardia"),
            weight=3.1,
            confidence=0.88,
            window=(3.5, 6.0),
            context_variables={"state": "apnea_recovery"},
            provenance="synthetic_multimodal_fixture",
        ),
        DirectedHyperedge(
            source_nodes=("Frontal_pole", "Anterior_cingulate"),
            target_nodes=("Insula",),
            weight=1.7,
            confidence=0.95,
            window=(0.0, 2.0),
            context_variables={"task": "transition_switch"},
            provenance="synthetic_triadic_fixture",
        ),
        DirectedHyperedge(
            source_nodes=("Parietal_alpha",),
            target_nodes=("Occipital_alpha",),
            weight=1.1,
            confidence=0.99,
            window=(2.0, 4.0),
            context_variables={"task": "visual_idle"},
            provenance="synthetic_eeg_fixture",
        ),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate directed-hypergraph outputs against forecasting and canonical-feature contracts."
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Path to JSON file containing directed hyperedges or hypergraph report (default: uses standard demo fixture).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to save validated HypergraphFeaturePayload JSON.",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["summary", "json"],
        default="summary",
        help="Output display format (default: summary).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any validation error is encountered.",
    )
    parser.add_argument(
        "--max-hyperedges",
        type=int,
        default=500,
        help="Maximum allowed hyperedge count (default: 500).",
    )
    parser.add_argument(
        "--skip-null-controls",
        action="store_true",
        help="Skip evaluation of the 4 null controls.",
    )
    return parser.parse_args()


def format_terminal_summary(payload: Any) -> str:
    """Format HypergraphFeaturePayload into a clean CLI summary table."""
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("      DIRECTED-HYPERGRAPH FEATURE CONTRACT VALIDATION REPORT")
    lines.append("=" * 78)
    lines.append(f"Timestamp (UTC)    : {payload.created_at_utc}")
    lines.append(f"Schema Version     : {payload.schema_version}")
    lines.append(f"Feature Family     : {payload.feature_family}")
    lines.append(f"Contract Validation: {'PASSED (VALID)' if payload.is_valid else 'FAILED (INVALID)'}")
    lines.append(f"Hyperedges Stored  : {len(payload.normalized_hyperedges)}")
    lines.append(f"Checksum (SHA-256) : {payload.deterministic_checksum[:16]}...")
    lines.append("-" * 78)

    # 1. Validation Issues
    lines.append("\n[1] VALIDATION RULES CHECK")
    if not payload.validation_issues:
        lines.append("  No validation issues detected (100% compliant).")
    else:
        for issue in payload.validation_issues:
            lines.append(f"  [{issue.issue_type.upper()}] {issue.field}: {issue.message}")

    # 2. Canonical Transition Features
    lines.append("\n[2] CANONICAL TRANSITION FEATURES (transitions.features compliant)")
    lines.append(f"{'Feature Name':<42} {'Value':<16} {'Unit'}")
    lines.append("-" * 74)
    units_map = payload.feature_metadata.get("units", {})
    for feat_name, feat_val in sorted(payload.features.items()):
        unit = units_map.get(feat_name, "dimensionless")
        lines.append(f"{feat_name:<42} {feat_val:<16.4f} {unit}")

    # 3. Null Controls
    lines.append("\n[3] RIGOROUS NULL CONTROLS")
    nc = payload.null_controls
    z_perm = f"{nc.label_permutation_z_score:.2f}" if nc.label_permutation_z_score is not None else "N/A"
    p_perm = f"{nc.label_permutation_p_value:.4f}" if nc.label_permutation_p_value is not None else "N/A"
    lines.append(f"  1. Label Permutation Null     : z={z_perm}, empirical p={p_perm}")
    t_shift = (
        f"{nc.temporal_block_shift_preserved_ratio * 100:.1f}%"
        if nc.temporal_block_shift_preserved_ratio is not None
        else "N/A"
    )
    lines.append(f"  2. Temporal Block Shift       : {t_shift} temporal coherence preserved")
    c_frac = (
        f"{nc.common_driver_confounding_fraction * 100:.1f}%"
        if nc.common_driver_confounding_fraction is not None
        else "N/A"
    )
    lines.append(f"  3. Common Driver Confounding  : {c_frac} shared driver overlap")
    z_var = f"{nc.matched_variance_z_score:.2f}" if nc.matched_variance_z_score is not None else "N/A"
    lines.append(f"  4. Matched Variance Control   : z={z_var}")

    # 4. Separation & Guardrails
    lines.append("\n[4] MATHEMATICAL SEPARATION & NON-CAUSAL GUARDRAIL")
    for k, v in payload.distinct_from_topology.items():
        lines.append(f"  - {k}: {v}")
    lines.append("-" * 78)
    lines.append("SCIENTIFIC DISCLAIMER:")
    lines.append(f"  {payload.scientific_disclaimer}")
    lines.append("=" * 78)
    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    # Ingest records
    if args.input:
        in_path = Path(args.input)
        if not in_path.exists():
            print(f"Error: Input file '{args.input}' not found.", file=sys.stderr)
            return 1
        raw_data = json.loads(in_path.read_text(encoding="utf-8"))
        if isinstance(raw_data, dict) and "hyperedges" in raw_data:
            records = raw_data["hyperedges"]
        elif isinstance(raw_data, list):
            records = raw_data
        else:
            records = [raw_data]
    else:
        records = build_demo_fixture_hyperedges()

    config = HypergraphValidationConfig(max_hyperedges=args.max_hyperedges)
    adapter = HypergraphFeatureAdapter(config=config)

    payload = adapter.build_feature_payload(
        records,
        run_null_controls=not args.skip_null_controls,
    )

    if args.format == "json":
        sys.stdout.write(payload.to_json(indent=2) + "\n")
    else:
        sys.stdout.write(format_terminal_summary(payload) + "\n")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload.to_json(indent=2), encoding="utf-8")

    if args.strict and not payload.is_valid:
        print("Strict validation failed: Payload contains validation errors.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
