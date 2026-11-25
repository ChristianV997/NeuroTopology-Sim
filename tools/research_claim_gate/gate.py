"""Pure, deterministic gate for scientific claim reporting.

The gate is deliberately narrower than a scientific analysis.  It checks the
declared metadata and claim language, then returns a decision and reason
codes.  No decision is a scientific confirmation and the module never emits a
Bayes factor or a scientific ``PASS`` inferred from metadata.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "NeuroTopology.ResearchClaimGate.v1"

CLAIM_CLASSES: tuple[str, ...] = (
    "engineering_fact",
    "benchmark_result",
    "synthetic_demonstration",
    "descriptive_empirical",
    "proxy_inference",
    "formal_statistical_evidence",
    "hypothesis",
    "speculation",
    "unsupported_claim",
)

DECISION_STATES: tuple[str, ...] = (
    "CLAIM_ADMISSIBLE",
    "CLAIM_REQUIRES_REVIEW",
    "CLAIM_DOWNGRADED",
    "CLAIM_REJECTED",
    "CLAIM_INCOMPLETE",
    "CLAIM_SYNTHETIC_ONLY",
    "CLAIM_PROVENANCE_INVALID",
    "CLAIM_NOT_COMPARABLE",
)

SEVERITIES: tuple[str, ...] = ("info", "warning", "error", "critical")

REASON_CODES: tuple[str, ...] = (
    "INPUT_NOT_OBJECT",
    "MALFORMED_INPUT",
    "UNKNOWN_CLAIM_CLASS",
    "UNKNOWN_EVIDENCE_CLASS",
    "MISSING_CLAIM_TEXT",
    "MISSING_PROVENANCE",
    "INCOMPLETE_PROVENANCE",
    "INVALID_PROVENANCE",
    "SYNTHETIC_NOT_EMPIRICAL",
    "SYNTHETIC_NOT_BIOLOGICAL",
    "PROXY_NOT_CAUSAL",
    "PROXY_NOT_MECHANISTIC",
    "PROXY_NOT_FORMAL_BAYESIAN",
    "FORMAL_METHOD_NOT_VALIDATED",
    "UNKNOWN_N_TESTS",
    "MISSING_MULTIPLICITY_CORRECTION",
    "UNVERIFIED_LABELS",
    "SUBJECT_SESSION_OVERLAP",
    "FUTURE_PAST_LEAKAGE",
    "MISSING_NULL_CONTROLS",
    "MISSING_UNCERTAINTY",
    "MISSING_EFFECT_SIZE",
    "TRIADIC_NOT_CAUSAL",
    "GRAPH_BETA1_NOT_SPATIAL_CHARGE",
    "PARASYMPATHETIC_NOT_EQUANIMITY",
    "CLEAN_AUDIT_NOT_CONFIRMATION",
    "COMPARISON_NOT_COMPARABLE",
    "UNSUPPORTED_CLAIM_CLASS",
    "NETWORK_ACCESS_NOT_APPROVED",
    "FORMAL_BAYES_FACTOR_NOT_EMITTED",
)

_PROMOTED_CLASSES = frozenset(
    {"benchmark_result", "descriptive_empirical", "proxy_inference", "formal_statistical_evidence"}
)
_EVIDENCE_REQUIRING_PROVENANCE = _PROMOTED_CLASSES
_REVIEW_CLASSES = _PROMOTED_CLASSES
_FORMAL_METHODS = frozenset(
    {"formal", "formal_bayes_factor", "marginal_likelihood", "validated_likelihood"}
)
_PROXY_METHODS = frozenset(
    {"proxy", "aic", "aicc", "bic", "aicc_ratio", "bic_ratio", "rss", "regression_proxy"}
)


class ClaimInputError(ValueError):
    """Raised internally when a claim cannot be represented safely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _finite(value: Any, path: str = "$") -> None:
    """Reject non-finite values without relying on permissive JSON behavior."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ClaimInputError("MALFORMED_INPUT", f"non-finite value at {path}")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _finite(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _finite(item, f"{path}[{index}]")
        return
    raise ClaimInputError("MALFORMED_INPUT", f"unsupported value type at {path}: {type(value).__name__}")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ClaimInputError("MALFORMED_INPUT", "text fields must be strings")
    value = value.strip()
    return value or None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise ClaimInputError("MALFORMED_INPUT", "boolean metadata must be true, false, or null")


def _names(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    raise ClaimInputError("MALFORMED_INPUT", "subject/session identifiers must be strings or arrays")


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ClaimInputError("MALFORMED_INPUT", f"{field_name} must be an object")
    return value


@dataclass(frozen=True)
class ProvenanceRecord:
    """Declared source metadata; completeness is validated, never inferred."""

    source_id: str | None = None
    source_uri: str | None = None
    checksum: str | None = None
    acquisition: str | None = None
    dataset_version: str | None = None
    subject_ids: tuple[str, ...] = ()
    session_ids: tuple[str, ...] = ()
    labels_verified: bool | None = None

    @classmethod
    def from_value(cls, value: Any) -> "ProvenanceRecord":
        if value is None or value == "":
            return cls()
        if isinstance(value, str):
            return cls(source_id=value.strip() or None)
        data = _mapping(value, "provenance")
        return cls(
            source_id=_text(data.get("source_id", data.get("dataset_id"))),
            source_uri=_text(data.get("source_uri", data.get("uri"))),
            checksum=_text(data.get("checksum", data.get("checksum_sha256"))),
            acquisition=_text(data.get("acquisition", data.get("acquisition_source"))),
            dataset_version=_text(data.get("dataset_version", data.get("version"))),
            subject_ids=_names(data.get("subject_ids", data.get("subjects"))),
            session_ids=_names(data.get("session_ids", data.get("sessions"))),
            labels_verified=_optional_bool(data.get("labels_verified")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "subject_ids": list(self.subject_ids),
            "session_ids": list(self.session_ids),
        }


@dataclass(frozen=True)
class ProvenanceValidation:
    status: str
    missing_fields: tuple[str, ...] = ()
    reason_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "missing_fields": list(self.missing_fields),
            "reason_code": self.reason_code,
        }


def validate_provenance(provenance: ProvenanceRecord | Mapping[str, Any] | str | None) -> ProvenanceValidation:
    """Return explicit provenance status for an input record.

    Evidence-bearing classes require source identity, a checksum, acquisition
    information, and a dataset/version identifier.  A source string alone is
    intentionally not complete provenance.
    """
    try:
        record = provenance if isinstance(provenance, ProvenanceRecord) else ProvenanceRecord.from_value(provenance)
    except ClaimInputError:
        return ProvenanceValidation("invalid", reason_code="INVALID_PROVENANCE")
    if not any((record.source_id, record.source_uri, record.checksum, record.acquisition, record.dataset_version)):
        return ProvenanceValidation("missing", ("source_id", "checksum", "acquisition", "dataset_version"), "MISSING_PROVENANCE")
    required = {
        "source_id": record.source_id or record.source_uri,
        "checksum": record.checksum,
        "acquisition": record.acquisition,
        "dataset_version": record.dataset_version,
    }
    missing = tuple(name for name, value in required.items() if not value)
    if missing:
        return ProvenanceValidation("incomplete", missing, "INCOMPLETE_PROVENANCE")
    if record.checksum and not re.fullmatch(r"[0-9a-fA-F]{64}", record.checksum):
        return ProvenanceValidation("invalid", ("checksum",), "INVALID_PROVENANCE")
    return ProvenanceValidation("complete")


@dataclass(frozen=True)
class ClaimRecord:
    """Typed normalized claim input accepted by the gate."""

    claim_id: str
    text: str
    claim_class: str
    evidence_class: str
    data_mode: str
    evidence_method: str | None
    proxy_status: str | None
    provenance: ProvenanceRecord
    n_tests: int | None
    multiplicity_correction: str | None
    labels_verified: bool | None
    null_controls: tuple[str, ...]
    uncertainty_present: bool
    effect_size_present: bool
    train_subjects: tuple[str, ...]
    test_subjects: tuple[str, ...]
    train_sessions: tuple[str, ...]
    test_sessions: tuple[str, ...]
    future_to_past_leakage: bool | None
    network_access_requested: bool
    network_policy_approved: bool
    compared_metric: str | None
    relation: str | None
    comparison_comparable: bool | None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ClaimRecord":
        if not isinstance(raw, Mapping):
            raise ClaimInputError("INPUT_NOT_OBJECT", "claim record must be a JSON object")
        _finite(raw)
        claim_id = _text(raw.get("claim_id", raw.get("id")))
        text = _text(raw.get("text", raw.get("claim")))
        if not claim_id:
            raise ClaimInputError("MALFORMED_INPUT", "claim_id is required")
        if not text:
            raise ClaimInputError("MISSING_CLAIM_TEXT", "claim text is required")

        claim_class = raw.get("claim_class", raw.get("claim_category"))
        evidence_class = raw.get("evidence_class", raw.get("evidence_category", claim_class))
        if not isinstance(claim_class, str):
            raise ClaimInputError("UNKNOWN_CLAIM_CLASS", "claim_class is required")
        if not isinstance(evidence_class, str):
            raise ClaimInputError("UNKNOWN_EVIDENCE_CLASS", "evidence_class must be a string")

        data_mode = raw.get("data_mode", raw.get("empirical_synthetic_status"))
        if data_mode is None and isinstance(raw.get("synthetic"), bool):
            data_mode = "synthetic" if raw["synthetic"] else "empirical"
        if not isinstance(data_mode, str):
            data_mode = "unknown"
        data_mode = data_mode.lower().strip()

        provenance = ProvenanceRecord.from_value(raw.get("provenance", raw.get("provenance_reference")))
        controls = raw.get("null_controls", raw.get("controls"))
        if isinstance(controls, Mapping):
            controls = [key for key, value in controls.items() if value not in (None, False, "")]
        null_controls = _names(controls)
        uncertainty = raw.get("uncertainty", raw.get("uncertainty_metadata"))
        effect_size = raw.get("effect_size", raw.get("effect_size_metadata"))
        labels_verified = raw.get("labels_verified", raw.get("condition_labels_verified", provenance.labels_verified))
        labels_verified = _optional_bool(labels_verified)
        n_tests = raw.get("n_tests", raw.get("number_of_tests"))
        if n_tests is not None:
            if isinstance(n_tests, bool) or not isinstance(n_tests, int) or n_tests < 1:
                raise ClaimInputError("MALFORMED_INPUT", "n_tests must be a positive integer or null")
        correction = raw.get("multiplicity_correction", raw.get("multiple_comparison_correction"))
        if isinstance(correction, bool):
            correction = "declared" if correction else None
        if correction is not None and not isinstance(correction, str):
            raise ClaimInputError("MALFORMED_INPUT", "multiplicity_correction must be a string, boolean, or null")
        network_requested = _optional_bool(raw.get("network_access_requested"))
        network_approved = _optional_bool(raw.get("network_policy_approved"))

        return cls(
            claim_id=claim_id,
            text=text,
            claim_class=claim_class.strip(),
            evidence_class=evidence_class.strip(),
            data_mode=data_mode,
            evidence_method=_text(raw.get("evidence_method", raw.get("likelihood_method"))),
            proxy_status=_text(raw.get("proxy_status", raw.get("proxy_formal_status"))),
            provenance=provenance,
            n_tests=n_tests,
            multiplicity_correction=correction.strip() if isinstance(correction, str) and correction.strip() else None,
            labels_verified=labels_verified,
            null_controls=null_controls,
            uncertainty_present=uncertainty is not None and uncertainty is not False and uncertainty != {},
            effect_size_present=effect_size is not None and effect_size is not False and effect_size != {},
            train_subjects=_names(raw.get("train_subjects")),
            test_subjects=_names(raw.get("test_subjects")),
            train_sessions=_names(raw.get("train_sessions")),
            test_sessions=_names(raw.get("test_sessions")),
            future_to_past_leakage=_optional_bool(raw.get("future_to_past_leakage", raw.get("temporal_leakage"))),
            network_access_requested=network_requested is True,
            network_policy_approved=network_approved is True,
            compared_metric=_text(raw.get("compared_metric", raw.get("metric"))),
            relation=_text(raw.get("relation", raw.get("interpretation"))),
            comparison_comparable=_optional_bool(raw.get("comparable")) if "comparable" in raw else (
                False if str(raw.get("comparison_status", "")).lower() in {"not_comparable", "incompatible"} else None
            ),
        )


@dataclass(frozen=True)
class Reason:
    code: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity, "message": self.message}


@dataclass(frozen=True)
class ClaimGateResult:
    """Stable output contract; no numeric evidence is generated by the gate."""

    schema_version: str
    claim_id: str | None
    decision: str
    severity: str
    claim_class: str | None
    evidence_class: str | None
    data_mode: str | None
    provenance_status: str
    recommended_downgrade_class: str | None
    scientific_eligibility: bool
    scientific_pass: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    reasons: tuple[Reason, ...] = field(default_factory=tuple)
    network_access_performed: bool = False
    formal_bayes_factor: None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "claim_id": self.claim_id,
            "decision": self.decision,
            "severity": self.severity,
            "claim_class": self.claim_class,
            "evidence_class": self.evidence_class,
            "data_mode": self.data_mode,
            "provenance_status": self.provenance_status,
            "recommended_downgrade_class": self.recommended_downgrade_class,
            "scientific_eligibility": self.scientific_eligibility,
            "scientific_pass": self.scientific_pass,
            "reason_codes": list(self.reason_codes),
            "reasons": [reason.to_dict() for reason in self.reasons],
            "network_access_performed": self.network_access_performed,
            "formal_bayes_factor": None,
        }


def _reason(code: str, severity: str, message: str) -> Reason:
    if code not in REASON_CODES:
        raise AssertionError(f"unregistered reason code: {code}")
    if severity not in SEVERITIES:
        raise AssertionError(f"unregistered severity: {severity}")
    return Reason(code, severity, message)


def _text_has(text: str, phrases: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in phrases)


def _evaluate_valid(record: ClaimRecord) -> ClaimGateResult:
    reasons: list[Reason] = []
    provenance = validate_provenance(record.provenance)
    claim_class = record.claim_class
    evidence_class = record.evidence_class

    if claim_class not in CLAIM_CLASSES:
        reasons.append(_reason("UNKNOWN_CLAIM_CLASS", "critical", "claim class is outside the closed gate vocabulary"))
    if evidence_class not in CLAIM_CLASSES:
        reasons.append(_reason("UNKNOWN_EVIDENCE_CLASS", "critical", "evidence class is outside the closed gate vocabulary"))

    if record.network_access_requested and not record.network_policy_approved:
        reasons.append(_reason("NETWORK_ACCESS_NOT_APPROVED", "critical", "network access was requested without an approved policy; no network call was made"))

    if record.comparison_comparable is False:
        reasons.append(_reason("COMPARISON_NOT_COMPARABLE", "error", "the supplied feature families or estimands are explicitly not comparable"))

    if claim_class == "unsupported_claim":
        reasons.append(_reason("UNSUPPORTED_CLAIM_CLASS", "critical", "unsupported_claim is not admissible as evidence"))

    synthetic = record.data_mode in {"synthetic", "synthetic_demo", "synthetic_demonstration"}
    empirical_claim = claim_class in {"descriptive_empirical", "formal_statistical_evidence"} or evidence_class in {"descriptive_empirical", "formal_statistical_evidence"}
    if synthetic and empirical_claim:
        reasons.append(_reason("SYNTHETIC_NOT_EMPIRICAL", "error", "synthetic output cannot support empirical or formal evidence"))
    if synthetic and _text_has(record.text, ("biological", "human", "consciousness", "equanimity", "nonattachment")):
        reasons.append(_reason("SYNTHETIC_NOT_BIOLOGICAL", "error", "synthetic output cannot support biological or mental-state claims"))

    proxy = (record.proxy_status or "").lower() in {"proxy", "aicc", "bic", "aic", "rss"} or (record.evidence_method or "").lower() in _PROXY_METHODS
    causal = _text_has(record.text, ("causal", "causally", "causes", "causation", "influence")) or (record.relation or "").lower() in {"causal", "causal_influence"}
    mechanistic = _text_has(record.text, ("mechanistic", "mechanism", "biological process"))
    formal_language = _text_has(record.text, ("formal bayes factor", "formal bayesian", "formal statistical evidence", "bayes factor"))
    if proxy and causal:
        reasons.append(_reason("PROXY_NOT_CAUSAL", "error", "proxy metrics cannot be labeled causal or causal influence"))
    if proxy and mechanistic:
        reasons.append(_reason("PROXY_NOT_MECHANISTIC", "error", "proxy metrics cannot be labeled mechanistic"))
    if proxy and (formal_language or claim_class == "formal_statistical_evidence" or evidence_class == "formal_statistical_evidence"):
        reasons.append(_reason("PROXY_NOT_FORMAL_BAYESIAN", "error", "proxy or information-criterion metrics are not formal Bayesian evidence"))
    if claim_class == "formal_statistical_evidence" and (record.evidence_method or "").lower() not in _FORMAL_METHODS:
        reasons.append(_reason("FORMAL_METHOD_NOT_VALIDATED", "error", "formal statistical evidence requires a declared validated likelihood or marginal likelihood"))

    if claim_class in _REVIEW_CLASSES or evidence_class in _REVIEW_CLASSES:
        if record.n_tests is None:
            reasons.append(_reason("UNKNOWN_N_TESTS", "warning", "number of tests is unknown and was not treated as one test"))
        if record.n_tests is not None and record.n_tests > 1 and not record.multiplicity_correction:
            reasons.append(_reason("MISSING_MULTIPLICITY_CORRECTION", "warning", "multiple comparisons require an explicit correction status"))
        if record.labels_verified is not True:
            reasons.append(_reason("UNVERIFIED_LABELS", "error", "condition or target labels are not explicitly verified"))
        if not record.null_controls:
            reasons.append(_reason("MISSING_NULL_CONTROLS", "warning", "declared null controls are required for evidence review"))
        if not record.uncertainty_present:
            reasons.append(_reason("MISSING_UNCERTAINTY", "warning", "uncertainty metadata is required for evidence review"))
        if not record.effect_size_present:
            reasons.append(_reason("MISSING_EFFECT_SIZE", "warning", "effect-size metadata is required for evidence review"))

    if claim_class in _EVIDENCE_REQUIRING_PROVENANCE or evidence_class in _EVIDENCE_REQUIRING_PROVENANCE:
        if provenance.status != "complete":
            reasons.append(_reason(provenance.reason_code or "MISSING_PROVENANCE", "error", "provenance is incomplete or invalid for evidence promotion"))

    if set(record.train_subjects) & set(record.test_subjects) or set(record.train_sessions) & set(record.test_sessions):
        reasons.append(_reason("SUBJECT_SESSION_OVERLAP", "critical", "train/test subject or session overlap blocks predictive evidence"))
    if record.future_to_past_leakage is True:
        reasons.append(_reason("FUTURE_PAST_LEAKAGE", "critical", "future-to-past leakage blocks forecasting evidence"))

    metric = (record.compared_metric or "").lower().replace("-", "_").replace(" ", "_")
    relation = (record.relation or "").lower()
    if ("triadic" in metric or "triadic" in record.text.lower()) and (causal or "causal" in relation):
        reasons.append(_reason("TRIADIC_NOT_CAUSAL", "error", "triadic dependence is not causal influence"))
    if metric in {"graph_beta1", "graph_beta_1"} and _text_has(record.text, ("spatial winding", "spatial charge", "topological charge")):
        reasons.append(_reason("GRAPH_BETA1_NOT_SPATIAL_CHARGE", "error", "graph beta-1 is not spatial winding or spatial charge"))
    if _text_has(record.text, ("parasympathetic activation proves equanimity", "parasympathetic activation is equanimity", "parasympathetic activation proves nonattachment")):
        reasons.append(_reason("PARASYMPATHETIC_NOT_EQUANIMITY", "error", "parasympathetic activation is not automatically equanimity or nonattachment"))
    if _text_has(record.text, ("clean audit confirms", "clean audit proves", "audit is scientific confirmation", "audit confirms biology")):
        reasons.append(_reason("CLEAN_AUDIT_NOT_CONFIRMATION", "error", "a clean audit is not scientific confirmation"))

    codes = tuple(reason.code for reason in reasons)
    hard_reject = {
        "UNKNOWN_CLAIM_CLASS", "UNKNOWN_EVIDENCE_CLASS", "UNSUPPORTED_CLAIM_CLASS",
        "NETWORK_ACCESS_NOT_APPROVED", "UNVERIFIED_LABELS", "SUBJECT_SESSION_OVERLAP",
        "FUTURE_PAST_LEAKAGE", "SYNTHETIC_NOT_BIOLOGICAL", "TRIADIC_NOT_CAUSAL",
        "GRAPH_BETA1_NOT_SPATIAL_CHARGE", "PARASYMPATHETIC_NOT_EQUANIMITY", "CLEAN_AUDIT_NOT_CONFIRMATION",
    }
    if any(code in hard_reject for code in codes):
        decision, severity, recommended = "CLAIM_REJECTED", "critical", None
    elif "SYNTHETIC_NOT_EMPIRICAL" in codes:
        decision, severity, recommended = "CLAIM_SYNTHETIC_ONLY", "error", "synthetic_demonstration"
    elif any(code in {"MISSING_PROVENANCE", "INCOMPLETE_PROVENANCE", "INVALID_PROVENANCE"} for code in codes):
        decision, severity, recommended = "CLAIM_PROVENANCE_INVALID", "error", "proxy_inference" if proxy else "hypothesis"
    elif any(code in {"PROXY_NOT_CAUSAL", "PROXY_NOT_MECHANISTIC", "PROXY_NOT_FORMAL_BAYESIAN", "FORMAL_METHOD_NOT_VALIDATED"} for code in codes):
        decision, severity, recommended = "CLAIM_DOWNGRADED", "warning", "proxy_inference"
    elif "COMPARISON_NOT_COMPARABLE" in codes:
        decision, severity, recommended = "CLAIM_NOT_COMPARABLE", "error", None
    elif any(reason.severity == "warning" for reason in reasons):
        decision, severity, recommended = "CLAIM_REQUIRES_REVIEW", "warning", None
    elif claim_class == "speculation" or claim_class == "hypothesis" or claim_class == "synthetic_demonstration":
        decision, severity, recommended = "CLAIM_ADMISSIBLE", "info", None
    else:
        decision, severity, recommended = "CLAIM_ADMISSIBLE", "info", None

    # Eligibility is a reporting-contract property, never a scientific PASS.
    eligible = decision == "CLAIM_ADMISSIBLE" and not synthetic and claim_class in {"engineering_fact", "benchmark_result", "descriptive_empirical", "formal_statistical_evidence", "proxy_inference"}
    if decision == "CLAIM_SYNTHETIC_ONLY":
        eligible = False
    return ClaimGateResult(
        schema_version=SCHEMA_VERSION,
        claim_id=record.claim_id,
        decision=decision,
        severity=severity,
        claim_class=claim_class,
        evidence_class=evidence_class,
        data_mode=record.data_mode,
        provenance_status=provenance.status,
        recommended_downgrade_class=recommended,
        scientific_eligibility=eligible,
        scientific_pass=False,
        reason_codes=codes,
        reasons=tuple(reasons),
    )


def _incomplete_result(code: str, message: str, claim_id: str | None = None) -> ClaimGateResult:
    reason = _reason(code, "critical" if code in {"MALFORMED_INPUT", "INPUT_NOT_OBJECT"} else "error", message)
    return ClaimGateResult(
        schema_version=SCHEMA_VERSION,
        claim_id=claim_id,
        decision="CLAIM_INCOMPLETE",
        severity=reason.severity,
        claim_class=None,
        evidence_class=None,
        data_mode=None,
        provenance_status="unknown",
        recommended_downgrade_class=None,
        scientific_eligibility=False,
        scientific_pass=False,
        reason_codes=(code,),
        reasons=(reason,),
    )


def evaluate_claim(raw: ClaimRecord | Mapping[str, Any] | Any) -> ClaimGateResult:
    """Evaluate one claim without I/O or network access."""
    if isinstance(raw, ClaimRecord):
        record = raw
    else:
        try:
            record = ClaimRecord.from_mapping(raw)
        except ClaimInputError as exc:
            return _incomplete_result(exc.code, str(exc), raw.get("claim_id") if isinstance(raw, Mapping) else None)
        except Exception as exc:  # defensive contract boundary: fail closed
            return _incomplete_result("MALFORMED_INPUT", f"malformed claim input: {exc}")
    return _evaluate_valid(record)


def evaluate_claim_batch(records: Iterable[Mapping[str, Any]]) -> list[ClaimGateResult]:
    """Evaluate records in input order; no sorting or external state is used."""
    return [evaluate_claim(record) for record in records]


def _json_safe(value: Any, path: str = "$") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite output at {path}")
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item, f"{path}.{key}") for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, f"{path}[{index}]") for index, item in enumerate(value)]
    raise ValueError(f"unsupported output type at {path}: {type(value).__name__}")


def serialize_json(value: ClaimGateResult | Mapping[str, Any] | Sequence[ClaimGateResult], *, indent: int | None = 2) -> str:
    """Serialize gate output with strict finite-number handling."""
    if isinstance(value, ClaimGateResult):
        payload: Any = value.to_dict()
    elif isinstance(value, Mapping):
        payload = value
    else:
        payload = [item.to_dict() if isinstance(item, ClaimGateResult) else item for item in value]
    return json.dumps(_json_safe(payload), allow_nan=False, sort_keys=True, indent=indent) + "\n"
