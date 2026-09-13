"""Fail-closed promotion evaluator. Calls evaluate_claim(); never confirms science."""

from __future__ import annotations

import math
from typing import Any

from tools.evidence_promotion_gate.adapters import LoadedCase, claim_payload_from_case
from tools.evidence_promotion_gate.schema import (
    ALLOWED_EVIDENCE_CLASSES,
    DECISION_TO_ALLOWED_CLASS,
    DOWNSTREAM_KINDS,
    FORMAL_METHOD_TOKENS,
    LITERATURE_CLAIM_KINDS,
    LITERATURE_EVIDENCE_CLASSES,
    PROMOTION_DECISIONS,
    PROXY_METHOD_TOKENS,
    SCHEMA_VERSION,
    SYNTHETIC_TOKENS,
    UNSAFE_EVIDENCE_LABELS,
    PromotionResult,
    Reason,
)
from tools.research_claim_gate.gate import evaluate_claim

_BLOCKING = 0
_SYNTHETIC = 1
_LITERATURE = 2
_PROXY = 3
_PROVENANCE = 4
_INCONCLUSIVE = 5
_ENGINEERING = 6
_DESCRIPTIVE = 7

_DECISION_RANK = {
    "BLOCK_PROMOTION": _BLOCKING,
    "HOLD_SYNTHETIC_ONLY": _SYNTHETIC,
    "HOLD_LITERATURE_HYPOTHESIS": _LITERATURE,
    "HOLD_PROXY_ONLY": _PROXY,
    "HOLD_INCOMPLETE_PROVENANCE": _PROVENANCE,
    "HOLD_INCONCLUSIVE": _INCONCLUSIVE,
    "ADMISSIBLE_FOR_ENGINEERING_REPORT": _ENGINEERING,
    "ADMISSIBLE_FOR_DESCRIPTIVE_REVIEW": _DESCRIPTIVE,
}


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _reason(code: str, severity: str, message: str) -> Reason:
    return Reason(code=code, severity=severity, message=message)


def _is_synthetic_token(value: str | None) -> bool:
    return _norm(value) in SYNTHETIC_TOKENS


def _is_proxy_token(value: str | None) -> bool:
    token = _norm(value).replace("-", "_").replace(" ", "_")
    return token in PROXY_METHOD_TOKENS or any(part in PROXY_METHOD_TOKENS for part in token.split("_") if part)


def _is_formal_token(value: str | None) -> bool:
    return _norm(value).replace("-", "_").replace(" ", "_") in FORMAL_METHOD_TOKENS


def _is_unsafe_evidence(value: str | None) -> bool:
    if value is None:
        return False
    raw = str(value).strip()
    return raw in UNSAFE_EVIDENCE_LABELS or _norm(raw) in {"empirical", "confirmed"}


def _is_pass_verdict(value: str | None) -> bool:
    return _norm(value) == "pass"


def _finite_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def _provenance_status(provenance: dict[str, Any] | None) -> str:
    if not provenance:
        return "missing"
    required = ("source_id", "checksum", "acquisition", "dataset_version")
    present = []
    for key in required:
        alt = {"source_id": provenance.get("source_id") or provenance.get("dataset_id")}
        if key == "source_id":
            value = alt["source_id"] or provenance.get("source_uri")
        elif key == "checksum":
            value = provenance.get("checksum") or provenance.get("checksum_sha256")
        elif key == "acquisition":
            value = provenance.get("acquisition") or provenance.get("acquisition_source")
        else:
            value = provenance.get("dataset_version") or provenance.get("version")
        if value:
            present.append(key)
    if not present:
        return "missing"
    if len(present) < len(required):
        return "incomplete"
    checksum = str(provenance.get("checksum") or provenance.get("checksum_sha256") or "")
    if checksum and len(checksum) != 64:
        return "invalid"
    return "complete"


def evaluate_case(case: LoadedCase) -> PromotionResult:
    reasons: list[Reason] = []
    candidates: list[str] = []

    reasons.append(
        _reason(
            "SCIENTIFIC_PASS_NOT_EMITTED",
            "info",
            "this gate never emits a scientific PASS or empirical confirmation",
        )
    )

    if case.load_errors:
        if any(error == "EMPTY_INPUT" for error in case.load_errors):
            reasons.append(_reason("EMPTY_INPUT", "error", "case directory contained no local JSON or Markdown inputs"))
        else:
            reasons.append(_reason("MALFORMED_INPUT", "error", "; ".join(case.load_errors)))
        candidates.append("HOLD_INCONCLUSIVE")

    declared_classes: list[str] = []
    data_modes: list[str] = []
    methods: list[str] = []
    claim_kinds: list[str] = []
    claim_classes: list[str] = []
    n_tests_values: list[int | None] = []
    n_tests_declared = False
    multiplicity_values: list[str | None] = []
    multiplicity_declared = False
    controls_present = False
    controls_declared = False
    provenance_states: list[str] = []
    synthetic = False
    performance_only = False
    fixture_token = False
    null_surrogate = False
    network_requested = False
    proxy = False
    literature = False
    unsafe_downstream_pass = False
    unsafe_downstream_empirical = False
    declared_empirical = False
    declared_k: float | None = None
    formal_method = False
    engineering = False
    descriptive = False
    kinds: list[str] = []

    for artifact in case.artifacts:
        kinds.append(artifact.kind)
        if artifact.evidence_class:
            declared_classes.append(artifact.evidence_class)
        if artifact.data_mode:
            data_modes.append(artifact.data_mode)
        if artifact.evidence_method:
            methods.append(artifact.evidence_method)
        if artifact.claim_kind:
            claim_kinds.append(artifact.claim_kind)
        if artifact.claim_class:
            claim_classes.append(artifact.claim_class)
        payload = artifact.payload if isinstance(artifact.payload, dict) else {}
        if "n_tests" in payload or "number_of_tests" in payload or artifact.n_tests is not None:
            n_tests_declared = True
            n_tests_values.append(artifact.n_tests)
        if (
            "multiplicity_correction" in payload
            or "multiplicity_status" in payload
            or artifact.multiplicity_correction is not None
        ):
            multiplicity_declared = True
            multiplicity_values.append(artifact.multiplicity_correction)
        if artifact.kind in {"claim", "run_record"}:
            if "null_controls" in payload or "controls" in payload:
                controls_declared = True
        if artifact.null_controls:
            controls_present = True
            controls_declared = True
        if artifact.provenance is not None:
            provenance_states.append(_provenance_status(artifact.provenance))
        if artifact.network_access_requested:
            network_requested = True
        if artifact.declared_k is not None:
            declared_k = artifact.declared_k
        if artifact.synthetic_flag is True:
            synthetic = True
        if _is_synthetic_token(artifact.data_mode) or _is_synthetic_token(artifact.evidence_class):
            synthetic = True
        if _norm(artifact.data_mode) == "performance_only" or _norm(artifact.evidence_class) == "performance_only":
            performance_only = True
            synthetic = True
        if _norm(artifact.data_mode) == "fixture" or _is_synthetic_token(artifact.data_mode) and _norm(artifact.data_mode) == "fixture":
            fixture_token = True
        if _norm(artifact.data_mode) in {"fixture"}:
            fixture_token = True
            synthetic = True
        if _norm(artifact.data_mode) in {"null", "surrogate", "null_control", "surrogate_baseline"}:
            null_surrogate = True
            synthetic = True
        if _is_proxy_token(artifact.evidence_method) or _is_proxy_token(artifact.proxy_status) or _is_proxy_token(artifact.evidence_class):
            proxy = True
        if _is_formal_token(artifact.evidence_method):
            formal_method = True
        if artifact.kind == "literature" or (
            artifact.claim_kind and _norm(artifact.claim_kind) in LITERATURE_CLAIM_KINDS
        ):
            literature = True
        if artifact.evidence_class and _norm(artifact.evidence_class) in LITERATURE_EVIDENCE_CLASSES and artifact.kind == "literature":
            literature = True
        if artifact.kind in DOWNSTREAM_KINDS and _is_pass_verdict(artifact.verdict):
            unsafe_downstream_pass = True
        if artifact.kind in DOWNSTREAM_KINDS and _is_unsafe_evidence(artifact.evidence_class):
            unsafe_downstream_empirical = True
        if _is_unsafe_evidence(artifact.evidence_class):
            declared_empirical = True
        if _norm(artifact.claim_class) in {"engineering_fact", "benchmark_result"} or _norm(artifact.evidence_class) in {
            "engineering_fact",
            "benchmark_result",
        }:
            engineering = True
        if _norm(artifact.claim_class) == "descriptive_empirical" or _norm(artifact.evidence_class) == "descriptive_empirical":
            descriptive = True
        if isinstance(artifact.payload, dict):
            metrics = artifact.payload.get("metrics")
            if isinstance(metrics, dict):
                metric_keys = " ".join(str(key).lower() for key in metrics)
                if any(token in metric_keys for token in ("aic", "aicc", "bic", "rss", "proxy_k", "proxy_bayes")):
                    proxy = True
            if _is_proxy_token(str(artifact.payload.get("proxy_bayes_factor", "") if artifact.payload.get("proxy_bayes_factor") not in (None, "") else "")):
                proxy = True
            if artifact.payload.get("proxy_bayes_factor") not in (None, ""):
                proxy = True

    claim_gate_dict: dict[str, Any] | None = None
    for artifact in case.of_kind("claim_gate_result"):
        if isinstance(artifact.payload, dict):
            claim_gate_dict = dict(artifact.payload)
            break

    claim_payload = claim_payload_from_case(case)
    if claim_payload is not None:
        # Map EMPIRICAL out of claim_class so evaluate_claim sees a closed vocab
        # while declared_evidence_class remains the original label.
        mapped = dict(claim_payload)
        for key in ("claim_class", "evidence_class"):
            if _is_unsafe_evidence(str(mapped.get(key))):
                mapped[key] = "unsupported_claim"
        result = evaluate_claim(mapped)
        claim_gate_dict = result.to_dict()
        decision = result.decision
        codes = set(result.reason_codes)
        if decision == "CLAIM_SYNTHETIC_ONLY" or "SYNTHETIC_NOT_EMPIRICAL" in codes:
            synthetic = True
            reasons.append(_reason("CLAIM_GATE_SYNTHETIC_ONLY", "error", "claim gate classified the record as synthetic-only"))
        if decision == "CLAIM_REJECTED":
            hard_block = codes & {
                "NETWORK_ACCESS_NOT_APPROVED",
                "SUBJECT_SESSION_OVERLAP",
                "FUTURE_PAST_LEAKAGE",
                "SYNTHETIC_NOT_BIOLOGICAL",
                "UNSUPPORTED_CLAIM_CLASS",
            }
            if hard_block:
                reasons.append(_reason("CLAIM_GATE_REJECTED", "error", "claim gate rejected the record; promotion is blocked"))
                candidates.append("BLOCK_PROMOTION")
            else:
                reasons.append(_reason("CLAIM_GATE_REJECTED", "error", "claim gate rejected the record; held without promotion"))
                candidates.append("HOLD_INCONCLUSIVE")
        if decision == "CLAIM_REQUIRES_REVIEW":
            reasons.append(_reason("CLAIM_GATE_REVIEW", "warning", "claim gate requires review; not treated as clean"))
            candidates.append("HOLD_INCONCLUSIVE")
        if decision == "CLAIM_PROVENANCE_INVALID" or codes & {"MISSING_PROVENANCE", "INCOMPLETE_PROVENANCE", "INVALID_PROVENANCE"}:
            reasons.append(_reason("CLAIM_GATE_PROVENANCE_INVALID", "error", "claim gate reported invalid or incomplete provenance"))
            candidates.append("HOLD_INCOMPLETE_PROVENANCE")
        if codes & {"PROXY_NOT_FORMAL_BAYESIAN", "PROXY_NOT_CAUSAL", "PROXY_NOT_MECHANISTIC"}:
            proxy = True
            reasons.append(_reason("CLAIM_GATE_DOWNGRADED", "warning", "claim gate downgraded a proxy or overreaching method"))
        elif decision == "CLAIM_DOWNGRADED":
            reasons.append(_reason("CLAIM_GATE_DOWNGRADED", "warning", "claim gate downgraded the declared method; promotion is still refused"))
            candidates.append("HOLD_INCONCLUSIVE")
        if decision == "CLAIM_INCOMPLETE":
            reasons.append(_reason("CLAIM_GATE_INCOMPLETE", "error", "claim gate could not represent the input"))
            candidates.append("HOLD_INCONCLUSIVE")
        if "UNKNOWN_N_TESTS" in codes:
            n_tests_values.append(None)
        if "MISSING_MULTIPLICITY_CORRECTION" in codes:
            multiplicity_values.append(None)
        if "MISSING_NULL_CONTROLS" in codes:
            controls_declared = True
            controls_present = False
        if "NETWORK_ACCESS_NOT_APPROVED" in codes:
            network_requested = True

    if network_requested:
        reasons.append(_reason("NETWORK_ACCESS_NOT_APPROVED", "critical", "network access was requested; this gate made no network call"))
        candidates.append("BLOCK_PROMOTION")

    if declared_empirical:
        reasons.append(_reason("EMPIRICAL_PROMOTION_REFUSED", "critical", "declared EMPIRICAL/confirmed class cannot be promoted by this gate"))
        candidates.append("BLOCK_PROMOTION")
    if unsafe_downstream_pass:
        reasons.append(_reason("DOWNSTREAM_UNSAFE_PASS", "critical", "downstream payload would display verdict PASS without surviving this gate"))
        candidates.append("BLOCK_PROMOTION")
    if unsafe_downstream_empirical:
        reasons.append(_reason("DOWNSTREAM_UNSAFE_EMPIRICAL", "critical", "downstream payload would display evidence_class EMPIRICAL without surviving this gate"))
        candidates.append("BLOCK_PROMOTION")

    if synthetic:
        if performance_only:
            reasons.append(_reason("PERFORMANCE_ONLY_NOT_EMPIRICAL", "error", "performance_only records cannot become empirical"))
        if fixture_token:
            reasons.append(_reason("FIXTURE_NOT_EMPIRICAL", "error", "fixture records cannot become empirical"))
        if null_surrogate:
            reasons.append(_reason("NULL_SURROGATE_NOT_EMPIRICAL", "error", "null/surrogate records cannot become empirical"))
        reasons.append(_reason("SYNTHETIC_NOT_EMPIRICAL", "error", "synthetic/demo output cannot support empirical promotion"))
        reasons.append(_reason("SYNTHETIC_DEMO_ONLY", "warning", "record is held as a synthetic demonstration only"))
        if declared_empirical or unsafe_downstream_pass or unsafe_downstream_empirical:
            candidates.append("BLOCK_PROMOTION")
        else:
            candidates.append("HOLD_SYNTHETIC_ONLY")

    if literature:
        if any(_norm(kind) == "review_required" for kind in claim_kinds) or any(
            _norm(cls) == "review_required" for cls in declared_classes
        ):
            reasons.append(_reason("LITERATURE_REVIEW_REQUIRED", "warning", "literature review_required cannot be treated as empirical"))
        reasons.append(_reason("LITERATURE_HYPOTHESIS_NOT_EMPIRICAL", "error", "literature hypothesis cannot be promoted to empirical"))
        candidates.append("HOLD_LITERATURE_HYPOTHESIS")

    if proxy:
        reasons.append(_reason("PROXY_NOT_FORMAL_BAYESIAN", "error", "proxy AIC/AICc/BIC/RSS/K is not formal Bayesian evidence"))
        reasons.append(_reason("PROXY_K_NOT_EMPIRICAL", "error", "proxy K cannot be promoted to empirical evidence"))
        candidates.append("HOLD_PROXY_ONLY")

    if formal_method:
        reasons.append(
            _reason(
                "FORMAL_BAYES_FACTOR_NOT_CONFIRMATION",
                "warning",
                "a declared formal method is recorded but does not confirm or promote the claim",
            )
        )
        if declared_k is not None and declared_k == 100:
            reasons.append(_reason("K_EQUALS_100_NOT_PASS", "warning", "K == 100 is not a PASS"))
        candidates.append("HOLD_INCONCLUSIVE")

    provenance_needed = descriptive or declared_empirical or any(
        _norm(cls) in {"descriptive_empirical", "proxy_inference", "formal_statistical_evidence", "benchmark_result"}
        for cls in declared_classes + claim_classes
    )
    if provenance_needed or provenance_states:
        if not provenance_states or "missing" in provenance_states:
            reasons.append(_reason("MISSING_PROVENANCE", "error", "evidence-bearing records require declared provenance"))
            candidates.append("HOLD_INCOMPLETE_PROVENANCE")
        elif "invalid" in provenance_states:
            reasons.append(_reason("INVALID_PROVENANCE", "error", "declared provenance checksum or fields are invalid"))
            candidates.append("HOLD_INCOMPLETE_PROVENANCE")
        elif "incomplete" in provenance_states:
            reasons.append(_reason("INCOMPLETE_PROVENANCE", "error", "provenance is incomplete and is not treated as clean"))
            candidates.append("HOLD_INCOMPLETE_PROVENANCE")

    review_needed = descriptive or declared_empirical or any(
        _norm(cls) in {"descriptive_empirical", "proxy_inference", "formal_statistical_evidence", "benchmark_result"}
        for cls in declared_classes + claim_classes
    )
    if review_needed:
        unknown_n = (not n_tests_declared) or any(value is None for value in n_tests_values)
        if unknown_n:
            reasons.append(_reason("UNKNOWN_N_TESTS", "warning", "unknown n_tests is never treated as one test"))
            candidates.append("HOLD_INCONCLUSIVE")
        unknown_multiplicity = (not multiplicity_declared) or any(
            value is None or _norm(value) in {"", "unknown", "none"} for value in multiplicity_values
        )
        multiple = any(isinstance(value, int) and value > 1 for value in n_tests_values)
        if unknown_multiplicity or (multiple and unknown_multiplicity):
            reasons.append(_reason("UNKNOWN_MULTIPLICITY", "warning", "unknown multiplicity is not treated as a single clean test"))
            candidates.append("HOLD_INCONCLUSIVE")
        if not controls_present:
            reasons.append(_reason("MISSING_NULL_CONTROLS", "warning", "missing null controls are not implied to have passed"))
            candidates.append("HOLD_INCONCLUSIVE")

    if engineering and not synthetic and not literature and not proxy and not declared_empirical:
        candidates.append("ADMISSIBLE_FOR_ENGINEERING_REPORT")
    if (
        descriptive
        and not synthetic
        and not literature
        and not proxy
        and not declared_empirical
        and provenance_states
        and all(state == "complete" for state in provenance_states)
        and n_tests_values
        and all(isinstance(value, int) and value >= 1 for value in n_tests_values)
        and controls_present
        and multiplicity_values
    ):
        candidates.append("ADMISSIBLE_FOR_DESCRIPTIVE_REVIEW")

    if not candidates:
        reasons.append(_reason("MALFORMED_INPUT", "warning", "no promotion-admissible class was established; held inconclusive"))
        candidates.append("HOLD_INCONCLUSIVE")

    ranked = sorted(candidates, key=lambda name: _DECISION_RANK[name])
    decision = ranked[0]
    if decision not in PROMOTION_DECISIONS:
        decision = "HOLD_INCONCLUSIVE"

    declared = declared_classes[0] if declared_classes else None
    allowed = DECISION_TO_ALLOWED_CLASS[decision]
    if engineering and decision == "ADMISSIBLE_FOR_ENGINEERING_REPORT":
        for cls in claim_classes + declared_classes:
            if _norm(cls) == "benchmark_result":
                allowed = "benchmark_result"
                break
    if allowed not in ALLOWED_EVIDENCE_CLASSES:
        allowed = "unsupported_claim"

    data_mode = data_modes[0] if data_modes else ("synthetic" if synthetic else None)
    if performance_only:
        data_mode = data_mode or "performance_only"

    formal_bayes_factor = None
    if formal_method and declared_k is not None:
        # Record declared K only; it is not confirmation and never yields PASS.
        formal_bayes_factor = declared_k

    # Deduplicate reason codes while preserving order.
    seen: set[str] = set()
    ordered_reasons: list[Reason] = []
    for reason in reasons:
        if reason.code in seen:
            continue
        seen.add(reason.code)
        ordered_reasons.append(reason)

    return PromotionResult(
        schema_version=SCHEMA_VERSION,
        case_id=case.case_id,
        promotion_decision=decision,
        reason_codes=tuple(reason.code for reason in ordered_reasons),
        reasons=tuple(ordered_reasons),
        declared_evidence_class=declared,
        allowed_evidence_class=allowed,
        synthetic_demo=synthetic,
        scientific_pass=False,
        scientific_eligibility=decision in {
            "ADMISSIBLE_FOR_DESCRIPTIVE_REVIEW",
            "ADMISSIBLE_FOR_ENGINEERING_REPORT",
        },
        formal_bayes_factor=formal_bayes_factor if formal_method and not proxy else None,
        declared_formal_bayes_factor=declared_k if formal_method else None,
        claim_gate=claim_gate_dict,
        input_fingerprints=case.fingerprints(),
        artifact_kinds=tuple(kinds),
        data_mode=data_mode,
    )


def evaluate_path(input_path: Any) -> list[PromotionResult]:
    from pathlib import Path

    from tools.evidence_promotion_gate.adapters import discover_cases

    cases = discover_cases(Path(input_path))
    return [evaluate_case(case) for case in cases]
