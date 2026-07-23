from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .generator import GUARDRAIL_FLAGS, TOE_CONSTRUCTS


REQUIRED_FILES = [
    "toe_literature_priority_matrix.json",
    "source_to_construct_map.json",
    "construct_to_equation_map.json",
    "constraint_to_falsifier_map.json",
    "topology_telemetry_upgrade_digest.md",
    "active_inference_allostasis_digest.md",
    "computational_psychiatry_digest.md",
    "bioelectric_basal_cognition_digest.md",
    "cosmology_constraint_matrix.json",
    "gravitational_wave_constraint_matrix.json",
    "consciousness_theory_adversarial_matrix.json",
    "equation_candidate_registry.json",
    "toe_falsifier_watchlist.json",
    "toe_theory_integration_digest.md",
    "toe_literature_bridge_report.md",
    "generation_manifest.json",
]

CONTENT_REQUIREMENTS = {
    "toe_theory_integration_digest.md": [term.lower() for term in TOE_CONSTRUCTS],
    "topology_telemetry_upgrade_digest.md": [
        "hodge", "persistent local laplacian", "sheaf", "causal topology",
        "local-global mismatch", "qabs", "fdress",
    ],
    "active_inference_allostasis_digest.md": [
        "precision weighting",
        "allostatic cost",
        "interoceptive/exteroceptive arbitration",
        "recalibration latency",
    ],
    "computational_psychiatry_digest.md": [
        "latent parameters", "attractor dwell", "recovery latency",
        "threat precision", "self-model recurrence",
    ],
    "bioelectric_basal_cognition_digest.md": [
        "adaptive boundary regulation", "multiscale autonomy",
        "non-neural anticipation", "substrate-independent regulation",
    ],
    "cosmology_constraint_matrix.json": [
        "desi",
        "cmb",
        "sne",
        "euclid",
        "hubble tension",
    ],
    "gravitational_wave_constraint_matrix.json": [
        "kerr ringdown", "black-hole spectroscopy", "area theorem", "gr reduction limit",
    ],
    "consciousness_theory_adversarial_matrix.json": [
        "global workspace theory", "integrated information theory",
        "recurrent processing theory", "active inference", "orch-or", "higher-order theories",
    ],
}

FORBIDDEN_CLAIM_PATTERNS = [
    r"\b(?:this|the)\s+(?:framework|model|result|evidence|toe)\s+proves?\s+consciousness\b",
    r"\b(?:this|the)\s+(?:framework|model|result|evidence|toe)\s+proves?\s+(?:a\s+)?soul\b",
    r"\btoe\s+(?:is\s+)?validated\b",
    r"\btoe\s+(?:is\s+)?proven\b",
    r"\b(?:is|provides)\s+the\s+final\s+theory\b",
    r"\bis\s+a\s+final\s+theory\b",
    r"\bconsciousness\s+(?:is\s+)?solved\b",
    r"\b(?:proves?|proof of)\s+(?:the\s+)?(?:soul|afterlife|nibbāna)\b",
    r"\b(?:soul|afterlife|nibbāna|nibbana)\s+proof\b",
    r"\bq(?:abs)?\s+proves?\b",
    r"\bfdress\s+proves?\b",
    r"\b(?:diagnoses|treats|cures)\b",
    (
        r"\b(?:provides?|offers?|performs?|enables?)\s+"
        r"(?:clinical\s+)?(?:diagnosis|treatment|cure)\b"
    ),
    r"\bclinical efficacy\b",
    r"\bontology promotion (?:is )?allowed\b",
]

DISALLOWED_TRUE_FLAGS = set(GUARDRAIL_FLAGS)

FALSIFIER_FIELDS = {
    "id",
    "claim_affected",
    "affected_subsystems",
    "observable_required",
    "failure_condition",
    "claim_demotion_action",
    "next_experiment_or_simulation",
    "priority",
}


def _load_json(path: Path, violations: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        violations.append(f"invalid_json:{path.name}:{exc}")
        return None


def _check_flags(value: Any, source: str, violations: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in DISALLOWED_TRUE_FLAGS and child is not False:
                violations.append(f"unsafe_flag:{source}:{key}={child!r}")
            _check_flags(child, source, violations)
    elif isinstance(value, list):
        for child in value:
            _check_flags(child, source, violations)


def validate(root: str | Path) -> dict:
    root_path = Path(root)
    violations: list[str] = []
    checked_files: list[str] = []

    for name in REQUIRED_FILES:
        path = root_path / name
        if not path.is_file():
            violations.append(f"missing:{name}")
        else:
            checked_files.append(name)

    texts: dict[str, str] = {}
    json_values: dict[str, Any] = {}
    for name in checked_files:
        path = root_path / name
        if path.suffix == ".json":
            value = _load_json(path, violations)
            json_values[name] = value
            texts[name] = (
                "" if value is None else json.dumps(value, ensure_ascii=False).lower()
            )
        else:
            texts[name] = path.read_text(
                encoding="utf-8", errors="replace"
            ).lower()

    for name, required_terms in CONTENT_REQUIREMENTS.items():
        text = texts.get(name, "")
        for term in required_terms:
            if term not in text:
                violations.append(f"missing_content:{name}:{term}")

    combined_text = "\n".join(texts.values())
    for pattern in FORBIDDEN_CLAIM_PATTERNS:
        if re.search(pattern, combined_text, flags=re.IGNORECASE):
            violations.append(f"forbidden_claim:{pattern}")
    if re.search(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b", combined_text):
        violations.append("api_key_exposure:openai_key_pattern")

    for name, value in json_values.items():
        if value is not None:
            _check_flags(value, name, violations)

    if "generation_manifest.json" in json_values:
        manifest = json_values["generation_manifest.json"]
        guardrails = manifest.get("guardrails", {}) if isinstance(manifest, dict) else {}
        for flag in sorted(DISALLOWED_TRUE_FLAGS):
            if guardrails.get(flag) is not False:
                violations.append(f"missing_safe_guardrail:generation_manifest.json:{flag}")

    if "toe_falsifier_watchlist.json" in json_values:
        falsifiers = json_values["toe_falsifier_watchlist.json"]
        if not isinstance(falsifiers, list):
            violations.append("invalid_registry:toe_falsifier_watchlist.json")
        else:
            by_id = {row.get("id"): row for row in falsifiers if isinstance(row, dict)}
            for expected_id in (f"F{i}" for i in range(1, 11)):
                row = by_id.get(expected_id)
                if row is None:
                    violations.append(f"missing_falsifier:{expected_id}")
                    continue
                missing_fields = sorted(FALSIFIER_FIELDS - set(row))
                if missing_fields:
                    violations.append(
                        f"missing_falsifier_fields:{expected_id}:{','.join(missing_fields)}"
                    )
                if any(value == "x" for value in row.values()):
                    violations.append(f"placeholder_falsifier:{expected_id}")

    if "equation_candidate_registry.json" in json_values:
        equations = json_values["equation_candidate_registry.json"]
        ids = (
            {row.get("equation_id") for row in equations if isinstance(row, dict)}
            if isinstance(equations, list)
            else set()
        )
        for expected_id in (f"EQ-{i:03d}" for i in range(1, 11)):
            if expected_id not in ids:
                violations.append(f"missing_equation:{expected_id}")

    return {
        "ok": not violations,
        "validator": "toe_literature_bridge",
        "checked_files": checked_files,
        "violations": violations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--json-out", required=True)
    args = parser.parse_args(argv)
    result = validate(args.root)
    output = Path(args.json_out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
