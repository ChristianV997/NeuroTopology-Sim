from __future__ import annotations

import argparse
import json
from pathlib import Path


TOE_PRIMITIVES = [
    "boundary",
    "constraint",
    "field",
    "topology",
    "information",
    "symmetry",
    "phase transition",
    "observer/interiority",
    "viability",
    "allostatic cost",
    "precision weighting",
    "recalibration latency",
    "local-global consistency",
    "causal topology",
    "cosmological field constraint",
    "GR/Kerr reduction limit",
]

BTC_ICFT_CONSTRUCTS = [
    "Q",
    "Qabs",
    "fdress",
    "phase field",
    "defects",
    "coherence",
    "fragmentation",
    "anesthesia wedge",
    "M-only vs M+T residual value",
]

TOL_CONSTRUCTS = [
    "dukkha",
    "taṇhā",
    "upādāna",
    "anattā",
    "sati",
    "samādhi",
    "paññā",
    "vimutti",
    "exit cost",
    "recovery latency",
    "affordance field",
    "allostatic load",
    "rumination",
    "craving",
    "flexibility",
]

PHYSICS_CONSTRAINTS = [
    "ΛCDM",
    "BAO",
    "CMB",
    "SNe",
    "Euclid lensing",
    "DESI constraints",
    "Kerr ringdown",
    "GR reduction limit",
    "black-hole area theorem",
]

TOE_CONSTRUCTS = (
    TOE_PRIMITIVES + BTC_ICFT_CONSTRUCTS + TOL_CONSTRUCTS + PHYSICS_CONSTRAINTS
)

SOURCE_TO_CONSTRUCT_MAP = {
    "sources": [
        {
            "source_id": "SRC-TOPOLOGY",
            "constructs": [
                "topology",
                "local-global consistency",
                "causal topology",
                *BTC_ICFT_CONSTRUCTS,
            ],
        },
        {
            "source_id": "SRC-ACTIVE-INFERENCE",
            "constructs": [
                "precision weighting",
                "allostatic cost",
                "recalibration latency",
            ],
        },
        {
            "source_id": "SRC-COMP-PSY",
            "constructs": [
                "viability",
                "observer/interiority",
                "information",
                *TOL_CONSTRUCTS,
            ],
        },
        {
            "source_id": "SRC-BIOELECTRIC",
            "constructs": ["boundary", "field", "phase transition"],
        },
        {
            "source_id": "SRC-PHYSICS",
            "constructs": [
                "constraint",
                "symmetry",
                "cosmological field constraint",
                "GR/Kerr reduction limit",
                *PHYSICS_CONSTRAINTS,
            ],
        },
    ]
}

CONSTRUCT_TO_EQUATION_MAP = {
    "constructs": [
        {
            "construct": "topology",
            "equation_ids": ["EQ-001", "EQ-002", "EQ-003", "EQ-004"],
        },
        {"construct": "precision weighting", "equation_ids": ["EQ-005"]},
        {"construct": "allostatic cost", "equation_ids": ["EQ-006"]},
        {"construct": "recalibration latency", "equation_ids": ["EQ-007"]},
        {
            "construct": "cosmological field constraint",
            "equation_ids": ["EQ-008", "EQ-009"],
        },
        {"construct": "GR/Kerr reduction limit", "equation_ids": ["EQ-010"]},
    ]
}

CONSTRAINT_TO_FALSIFIER_MAP = {
    "mappings": [
        {"constraint_id": "BTC-001", "falsifier_id": "F1"},
        {"constraint_id": "EEG-001", "falsifier_id": "F2"},
        {"constraint_id": "EEG-002", "falsifier_id": "F3"},
        {"constraint_id": "TOP-001", "falsifier_id": "F4"},
        {"constraint_id": "TOP-002", "falsifier_id": "F5"},
        {"constraint_id": "TOL-001", "falsifier_id": "F6"},
        {"constraint_id": "COS-001", "falsifier_id": "F7"},
        {"constraint_id": "GW-001", "falsifier_id": "F8"},
        {"constraint_id": "BIO-001", "falsifier_id": "F9"},
        {"constraint_id": "MECH-001", "falsifier_id": "F10"},
    ]
}

GUARDRAIL_FLAGS = [
    "toe_validation_claims_allowed",
    "final_theory_claims_allowed",
    "consciousness_proof_claims_allowed",
    "soul_proof_claims_allowed",
    "afterlife_proof_claims_allowed",
    "nibbana_proof_claims_allowed",
    "q_qabs_fdress_proof_claims_allowed",
    "clinical_claims_allowed",
    "ontology_promotion_allowed",
    "empirical_claims_from_fixtures_allowed",
    "real_data_auto_execution_allowed",
    "live_api_calls_allowed",
    "api_key_exposure_allowed",
    "openai_calls_allowed",
    "dataset_downloads_allowed",
    "label_inference_allowed",
    "target_fabrication_allowed",
]


def generate(roots: list[str], out_dir: str | Path, strict: bool = False) -> tuple[dict, int]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    availability = {root: Path(root).exists() for root in roots}
    missing = [root for root, available in availability.items() if not available]

    priority = {
        "inputs": availability,
        "status": {
            root: "available" if available else "not_available"
            for root, available in availability.items()
        },
        "toe_constructs": TOE_CONSTRUCTS,
        "claim_scope": "research_hypothesis",
        "evidence_state": "conceptual_mapping",
        "warnings": [f"Missing upstream artifact root: {root}" for root in missing],
    }
    (out / "toe_literature_priority_matrix.json").write_text(
        json.dumps(priority, indent=2), encoding="utf-8"
    )

    integration = "# TOE Theory Integration Digest\n\n" + "\n".join(
        f"- {construct}" for construct in TOE_CONSTRUCTS
    )
    integration += (
        "\n\nThese are provisional research constructs and constraints. "
        "No subjective-experience, clinical, or ontology conclusion follows from this mapping.\n"
    )
    (out / "toe_theory_integration_digest.md").write_text(integration, encoding="utf-8")
    (out / "toe_literature_bridge_report.md").write_text(
        "# P40 Summary\n\nRun the reporting module after all registries are generated.\n",
        encoding="utf-8",
    )

    manifest = {
        "ok": not (strict and missing),
        "strict": strict,
        "missing_upstream_roots": missing,
        "guardrails": {flag: False for flag in GUARDRAIL_FLAGS},
    }
    (out / "generation_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    for name, payload in (
        ("source_to_construct_map.json", SOURCE_TO_CONSTRUCT_MAP),
        ("construct_to_equation_map.json", CONSTRUCT_TO_EQUATION_MAP),
        ("constraint_to_falsifier_map.json", CONSTRAINT_TO_FALSIFIER_MAP),
    ):
        (out / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest, 1 if strict and missing else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roots", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    _, return_code = generate(args.roots, args.out, args.strict)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
