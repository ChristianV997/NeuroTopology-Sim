"""Contract adapters between the real upstream registries and the
Awareness Studio research-cycle orchestrator's input contract.

This module is deliberately self-contained (stdlib only): it does not
import ``tools.awareness_studio_research`` (Claude A's literature
registry, PR #276), any hypothesis-registry implementation (owned by
Antigravity C), or ``tools.awareness_studio_research_loop.compiler`` /
``state_machine`` (PR #283, read-only). All three are consumed only as
data -- raw dicts shaped like their real record types -- never as code.
Validating a producer's *output* against a documented contract should
not require importing the consumer's implementation; that is the whole
point of an adapter/contract test.

Every adapter is a pure function: ``adapt_*(raw: dict) -> AdaptedRecord``.
It never raises on malformed input -- it returns ``ok=False`` plus a list
of ``Diagnostic``s explaining exactly what does not fit, and it never
silently strengthens a weak claim (see ``NEVER_COERCE`` below and the
module-level guard functions).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# --- Real upstream vocabularies -------------------------------------------
# Mirrors tools/awareness_studio_research/models.py (Claude A, PR #276,
# read-only -- these are copied as data, not imported as code) and the
# orchestrator's own contract (docs/awareness_studio/research_cycle_orchestration.md,
# PR #283, read-only).

EVIDENCE_TIERS = {"T1_verified_primary", "T2_verified_secondary", "T3_unverified_claimed", "T4_disputed"}
VERIFICATION_STATUSES = {"verified", "unverified", "disputed"}
SOURCE_STATUSES = {"active", "superseded", "disputed", "retracted"}
CLAIM_STATUSES = {"empirical", "theoretical", "proxy", "speculative", "unsupported"}
CLAIM_CLASSES = {"correlational", "causal", "theoretical", "methodological", "descriptive"}
LINK_RELATIONSHIPS = {"supports", "contradicts", "refines", "extends", "unrelated"}

#: The real registry's event-sourced store (tools/awareness_studio_research/store.py)
#: only ever appends events with these ``entity_type`` values. It never
#: emits "hypothesis" -- hypotheses are owned by a different registry
#: entirely (Antigravity C's). See DIAGNOSTIC_HYPOTHESIS_EVIDENCE_UPDATE_GAP.
REGISTRY_EVIDENCE_UPDATE_ENTITY_TYPES = {"source", "claim", "correlate", "hypothesis_link", "dataset_link", "experiment_link"}

#: The orchestrator's own evidence_updates gate (PR #283,
#: state_machine.py) only ever advances a hypothesis past
#: EVIDENCE_UPDATE_READY when it finds entity_type=="hypothesis". That
#: literal is never produced by the real registry above -- a confirmed,
#: structural contract gap between the two systems.
ORCHESTRATOR_EXPECTED_EVIDENCE_UPDATE_ENTITY_TYPE = "hypothesis"

EVIDENCE_CLASS = {"synthetic", "proxy", "empirical", "formal", "unknown"}

# --- Real Antigravity C hypothesis-registry vocabularies -------------------
# Mirrors tools/research_cycle/schema.py (already merged to main -- read
# only via git show / static text, never imported). This is a
# *substantially* different shape from what the orchestrator's own
# hypothesis_registry/experiment_plans contracts assume; see the
# migration diagnostics this module produces for the specifics.

HYPOTHESIS_STATUSES = {
    "proposed", "preregistered", "ready_for_execution", "executed", "supported_as_specified",
    "weakened", "falsified", "inconclusive", "blocked_by_data", "blocked_by_method", "retired",
}
EPISTEMIC_LABELS = {"speculative_hypothesis", "exploratory", "preregistered_empirical", "computational_model", "surrogate_baseline", "empirically_constrained"}
EVIDENCE_DATA_TYPES = {"empirical_dataset", "synthetic_simulation", "literature_claim", "proxy_bayes_factor"}

#: Best-effort, non-authoritative hint from the real registry's
#: epistemic_label vocabulary to the orchestrator's evidence_class
#: vocabulary. Every value produced through this table still carries an
#: AMBIGUOUS_MAPPING diagnostic (see map_epistemic_label_to_evidence_class)
#: -- the table exists to make the mapping visible and reviewable, not to
#: license silently trusting it as equivalent.
_EPISTEMIC_LABEL_TO_EVIDENCE_CLASS_HINT = {
    "speculative_hypothesis": "unknown",
    "exploratory": "unknown",
    "preregistered_empirical": "empirical",
    "computational_model": "synthetic",
    "surrogate_baseline": "proxy",
    "empirically_constrained": "empirical",
}

#: The exact five coercions this module must never perform, regardless of
#: how permissively an upstream record is written (requirement 4).
NEVER_COERCE = (
    "formal_to_proxy",
    "empirical_to_synthetic",
    "theory_to_observation",
    "disputed_source_to_confirmed_source",
    "prediction_to_causal_effect",
)

# --- Diagnostics ------------------------------------------------------------

MISSING_FIELD = "missing_field"
INCOMPATIBLE_TYPE = "incompatible_type"
UNSUPPORTED_VERSION = "unsupported_version"
AMBIGUOUS_MAPPING = "ambiguous_mapping"
UNVERIFIED_PROVENANCE = "unverified_provenance"
SYNTHETIC_ONLY_INPUT = "synthetic_only_input"

DIAGNOSTIC_KINDS = {MISSING_FIELD, INCOMPATIBLE_TYPE, UNSUPPORTED_VERSION, AMBIGUOUS_MAPPING, UNVERIFIED_PROVENANCE, SYNTHETIC_ONLY_INPUT}


@dataclass(frozen=True)
class Diagnostic:
    kind: str
    field: str
    detail: str
    record_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "field": self.field, "detail": self.detail, "record_id": self.record_id}


@dataclass(frozen=True)
class AdaptedRecord:
    ok: bool
    record: dict[str, Any] | None
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "record": self.record, "diagnostics": [d.to_dict() for d in self.diagnostics]}


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _looks_like_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


# --- 1. Literature source records -------------------------------------------


def adapt_literature_source(raw: dict[str, Any]) -> AdaptedRecord:
    diagnostics: list[Diagnostic] = []
    record_id = raw.get("source_id") if isinstance(raw.get("source_id"), str) else None

    if not _is_nonempty_str(raw.get("source_id")):
        diagnostics.append(Diagnostic(MISSING_FIELD, "source_id", "source_id is required and must be a non-empty string", record_id))
    if not _is_nonempty_str(raw.get("source_checksum")):
        diagnostics.append(Diagnostic(MISSING_FIELD, "source_checksum", "source_checksum is required and must be a non-empty string", record_id))
    elif not _looks_like_sha256_hex(raw["source_checksum"]):
        diagnostics.append(
            Diagnostic(UNVERIFIED_PROVENANCE, "source_checksum", f"source_checksum {raw['source_checksum']!r} is not a 64-character sha256 hex digest; treated as an unverifiable local value, not rejected", record_id)
        )

    evidence_tier = raw.get("evidence_tier")
    if evidence_tier is not None and evidence_tier not in EVIDENCE_TIERS:
        diagnostics.append(Diagnostic(UNSUPPORTED_VERSION, "evidence_tier", f"evidence_tier {evidence_tier!r} is not one of {sorted(EVIDENCE_TIERS)} -- registry may be on a newer/older tier vocabulary", record_id))

    verification_status = raw.get("verification_status")
    if verification_status is not None and verification_status not in VERIFICATION_STATUSES:
        diagnostics.append(Diagnostic(INCOMPATIBLE_TYPE, "verification_status", f"verification_status {verification_status!r} is not one of {sorted(VERIFICATION_STATUSES)}", record_id))

    status = raw.get("status")
    if status is not None and status not in SOURCE_STATUSES:
        diagnostics.append(Diagnostic(INCOMPATIBLE_TYPE, "status", f"status {status!r} is not one of {sorted(SOURCE_STATUSES)}", record_id))

    if any(d.kind == MISSING_FIELD for d in diagnostics):
        return AdaptedRecord(ok=False, record=None, diagnostics=diagnostics)

    # NEVER_COERCE: disputed_source_to_confirmed_source -- passthrough
    # verbatim, never upgraded, regardless of any other field.
    adapted = {
        "source_id": raw["source_id"],
        "title": raw.get("title") if isinstance(raw.get("title"), str) else None,
        "doi": raw.get("doi") if isinstance(raw.get("doi"), str) else None,
        "source_checksum": raw["source_checksum"],
        "evidence_tier": evidence_tier if evidence_tier in EVIDENCE_TIERS else "T3_unverified_claimed",
        "verification_status": verification_status if verification_status in VERIFICATION_STATUSES else "unverified",
        "status": status if status in SOURCE_STATUSES else "active",
        "limitations": [v for v in raw.get("limitations", []) if isinstance(v, str)] if isinstance(raw.get("limitations"), list) else [],
    }
    return AdaptedRecord(ok=True, record=adapted, diagnostics=diagnostics)


# --- 2. Extracted claim records ----------------------------------------------


def adapt_extracted_claim(raw: dict[str, Any]) -> AdaptedRecord:
    diagnostics: list[Diagnostic] = []
    record_id = raw.get("claim_id") if isinstance(raw.get("claim_id"), str) else None

    if not _is_nonempty_str(raw.get("claim_id")):
        diagnostics.append(Diagnostic(MISSING_FIELD, "claim_id", "claim_id is required and must be a non-empty string", record_id))
    if not _is_nonempty_str(raw.get("source_id")):
        diagnostics.append(Diagnostic(MISSING_FIELD, "source_id", "source_id is required and must be a non-empty string", record_id))
    if not isinstance(raw.get("claim_text"), str):
        diagnostics.append(Diagnostic(MISSING_FIELD, "claim_text", "claim_text is required and must be a string", record_id))

    claim_status = raw.get("claim_status")
    if claim_status is not None and claim_status not in CLAIM_STATUSES:
        diagnostics.append(Diagnostic(INCOMPATIBLE_TYPE, "claim_status", f"claim_status {claim_status!r} is not one of {sorted(CLAIM_STATUSES)}", record_id))

    claim_class = raw.get("claim_class")
    if claim_class is not None and claim_class not in CLAIM_CLASSES:
        diagnostics.append(Diagnostic(INCOMPATIBLE_TYPE, "claim_class", f"claim_class {claim_class!r} is not one of {sorted(CLAIM_CLASSES)}", record_id))

    if any(d.kind == MISSING_FIELD for d in diagnostics):
        return AdaptedRecord(ok=False, record=None, diagnostics=diagnostics)

    # NEVER_COERCE: theory_to_observation -- a "theoretical" claim_status
    # is passed through unchanged, never reported as "empirical". An
    # unrecognized claim_status degrades to "unsupported" (the weakest
    # bucket), never upward to "empirical".
    adapted = {
        "claim_id": raw["claim_id"],
        "source_id": raw["source_id"],
        "claim_text": raw["claim_text"],
        "claim_class": claim_class if claim_class in CLAIM_CLASSES else "descriptive",
        "claim_status": claim_status if claim_status in CLAIM_STATUSES else "unsupported",
        "linked_hypothesis": raw.get("linked_hypothesis") if isinstance(raw.get("linked_hypothesis"), str) else None,
    }
    return AdaptedRecord(ok=True, record=adapted, diagnostics=diagnostics)


# --- 3. Hypothesis records ----------------------------------------------------
#
# Grounded against the REAL, already-merged tools/research_cycle/schema.py
# HypothesisRecord.v1 -- which turns out to differ from the orchestrator's
# assumed hypothesis_registry shape in several confirmed ways:
#   - no ``claim_ids`` field at all (has ``evidence_links`` /
#     ``contradictory_evidence_links`` instead, which are NOT literature-
#     claim ids specifically -- they may reference experiment evidence too).
#   - ``statement`` doesn't exist; the closest field is ``precise_claim``.
#   - ``null_prediction`` and ``falsification_criterion`` DO exist under
#     the same names -- a genuine compatible match.
#   - review state lives in a nested ``human_review_gate`` object, not a
#     separate reviewer_decisions record (see adapt_human_review_gate).
#   - ``epistemic_label`` uses a completely different vocabulary than the
#     orchestrator's evidence_class (see map_epistemic_label_to_evidence_class).


def map_epistemic_label_to_evidence_class(epistemic_label: Any) -> tuple[str, Diagnostic | None]:
    """Non-authoritative hint mapping -- always paired with a diagnostic
    so the mapping is visible for human review, never silently trusted."""
    if epistemic_label not in EPISTEMIC_LABELS:
        return "unknown", Diagnostic(INCOMPATIBLE_TYPE, "epistemic_label", f"epistemic_label {epistemic_label!r} is not one of {sorted(EPISTEMIC_LABELS)}", None)
    hint = _EPISTEMIC_LABEL_TO_EVIDENCE_CLASS_HINT[epistemic_label]
    return hint, Diagnostic(
        AMBIGUOUS_MAPPING,
        "epistemic_label",
        f"epistemic_label={epistemic_label!r} has no exact orchestrator evidence_class equivalent; hinted as {hint!r} (see _EPISTEMIC_LABEL_TO_EVIDENCE_CLASS_HINT) but this is a best-effort suggestion, not an authoritative mapping -- a human should confirm before this value is used to satisfy any gate",
        None,
    )


def adapt_hypothesis_record(raw: dict[str, Any]) -> AdaptedRecord:
    """``raw`` is shaped like the real ``HypothesisRecord.v1``
    (tools/research_cycle/schema.py), not the orchestrator's own contract
    -- this adapter performs the actual cross-system translation."""
    diagnostics: list[Diagnostic] = []
    record_id = raw.get("hypothesis_id") if isinstance(raw.get("hypothesis_id"), str) else None

    if not _is_nonempty_str(raw.get("hypothesis_id")):
        diagnostics.append(Diagnostic(MISSING_FIELD, "hypothesis_id", "hypothesis_id is required and must be a non-empty string", record_id))
    if not _is_nonempty_str(raw.get("null_prediction")):
        diagnostics.append(Diagnostic(MISSING_FIELD, "null_prediction", "null_prediction is required by the orchestrator's null_prediction gate", record_id))

    schema_version = raw.get("schema_version")
    if schema_version is not None and schema_version != "HypothesisRecord.v1":
        diagnostics.append(Diagnostic(UNSUPPORTED_VERSION, "schema_version", f"schema_version {schema_version!r} is not the HypothesisRecord.v1 this adapter targets", record_id))

    status = raw.get("status")
    if status is not None and status not in HYPOTHESIS_STATUSES:
        diagnostics.append(Diagnostic(INCOMPATIBLE_TYPE, "status", f"status {status!r} is not one of {sorted(HYPOTHESIS_STATUSES)}", record_id))

    # claim_ids: the real registry has no equivalent field. evidence_links
    # is NOT substituted -- it may reference non-claim evidence, and
    # substituting it would be an unwarranted assumption about semantics
    # this adapter cannot verify.
    if raw.get("evidence_links"):
        diagnostics.append(
            Diagnostic(
                AMBIGUOUS_MAPPING,
                "claim_ids",
                "HypothesisRecord.v1 has no claim_ids field; its evidence_links are NOT assumed to be literature claim ids (they may reference experiment/other evidence) and are left unmapped -- claim_ids is emitted empty",
                record_id,
            )
        )
    else:
        diagnostics.append(Diagnostic(MISSING_FIELD, "claim_ids", "HypothesisRecord.v1 has no claim_ids or equivalent field; claim_ids is emitted empty", record_id))

    epistemic_label = raw.get("epistemic_label")
    evidence_class_hint, label_diag = (None, None)
    if epistemic_label is not None:
        evidence_class_hint, label_diag = map_epistemic_label_to_evidence_class(epistemic_label)
        if label_diag is not None:
            diagnostics.append(label_diag)

    if not _is_nonempty_str(raw.get("hypothesis_id")) or not _is_nonempty_str(raw.get("null_prediction")):
        return AdaptedRecord(ok=False, record=None, diagnostics=diagnostics)

    # NEVER_COERCE: prediction_to_causal_effect -- predicted_direction /
    # precise_claim are carried through as descriptive text; this adapter
    # never adds or implies a causal claim_class on their behalf.
    adapted = {
        "hypothesis_id": raw["hypothesis_id"],
        "statement": raw.get("precise_claim") if isinstance(raw.get("precise_claim"), str) else "",
        "claim_ids": [],
        "null_prediction": raw["null_prediction"],
        "falsification_criterion": raw.get("falsification_criterion") if isinstance(raw.get("falsification_criterion"), str) else None,
        "source_status": status if status in HYPOTHESIS_STATUSES else None,
        "source_epistemic_label": epistemic_label if epistemic_label in EPISTEMIC_LABELS else None,
        "evidence_class_hint": evidence_class_hint,
        "source_contradictory_evidence_links": [v for v in raw.get("contradictory_evidence_links", []) if isinstance(v, str)] if isinstance(raw.get("contradictory_evidence_links"), list) else [],
    }
    return AdaptedRecord(ok=True, record=adapted, diagnostics=diagnostics)


def adapt_human_review_gate(raw_human_review_gate: dict[str, Any], *, subject_id: str) -> AdaptedRecord:
    """Maps the real registry's nested ``HumanReviewGate`` (``{passed,
    reviewer, timestamp, review_notes}``, embedded on the hypothesis
    record) to the orchestrator's separate ``reviewer_decisions`` entry
    shape (``{subject_type, subject_id, decision, reviewer, notes}``).

    ``passed=True`` unambiguously maps to ``"approved"``. ``passed=False``
    is genuinely ambiguous -- the real schema does not distinguish "not
    yet reviewed" from "reviewed and rejected" -- so it maps to the more
    neutral ``"pending"`` (both ``"pending"`` and ``"rejected"`` block
    orchestrator progression identically, so this ambiguity is harmless
    for cycle-state purposes, but is still flagged rather than silently
    resolved).
    """
    diagnostics: list[Diagnostic] = []
    passed = raw_human_review_gate.get("passed")
    if not isinstance(passed, bool):
        diagnostics.append(Diagnostic(MISSING_FIELD, "passed", "human_review_gate.passed is required and must be a bool", subject_id))
        return AdaptedRecord(ok=False, record=None, diagnostics=diagnostics)

    if passed is False:
        diagnostics.append(
            Diagnostic(
                AMBIGUOUS_MAPPING,
                "passed",
                "human_review_gate.passed=false does not distinguish 'not yet reviewed' from 'reviewed and rejected'; mapped to decision='pending' (both 'pending' and 'rejected' block orchestrator progression identically, so this does not change downstream behavior, but the ambiguity itself is not resolved)",
                subject_id,
            )
        )

    adapted = {
        "subject_type": "hypothesis",
        "subject_id": subject_id,
        "decision": "approved" if passed else "pending",
        "reviewer": raw_human_review_gate.get("reviewer") if isinstance(raw_human_review_gate.get("reviewer"), str) else None,
        "notes": raw_human_review_gate.get("review_notes") if isinstance(raw_human_review_gate.get("review_notes"), str) else None,
    }
    return AdaptedRecord(ok=True, record=adapted, diagnostics=diagnostics)


# --- 4. Experiment plans -------------------------------------------------------
#
# Grounded against the REAL, already-merged tools/research_cycle/schema.py
# ExperimentPlan.v1 -- also substantially different from the orchestrator's
# assumed shape:
#   - id field is ``plan_id``, not ``experiment_id`` (renamed, not lost).
#   - ``is_synthetic`` (not ``synthetic``) DOES exist -- a compatible
#     rename.
#   - ``falsification_criterion`` does NOT exist on the plan (it lives on
#     the hypothesis record instead in this schema, but under the *same*
#     field name -- see adapt_hypothesis_record). Left null here with a
#     diagnostic; a caller should fall back to the hypothesis's copy.
#   - no ``metrics``/unit/feature_family concept at all (has ``variables``
#     + free-text ``analysis_protocol`` instead) -- cannot be
#     reconstructed without inventing units this adapter was never told.
#   - no ``held_out_split_locked``/``is_predictive``/``preregistered``
#     fields at all -- the locked_holdout gate is structurally
#     unsatisfiable from this registry's export as it stands today.
#   - ``checksum`` is the *record's own* content-integrity checksum, not a
#     dataset checksum -- NEVER substituted for dataset_checksum (that
#     would silently claim data provenance the checksum does not carry).
#     ``provenance`` is inspected for an explicit ``dataset_checksum`` key
#     only; if absent, dataset_checksum is null + a diagnostic.


def adapt_experiment_plan(raw: dict[str, Any]) -> AdaptedRecord:
    """``raw`` is shaped like the real ``ExperimentPlan.v1``
    (tools/research_cycle/schema.py)."""
    diagnostics: list[Diagnostic] = []
    plan_id = raw.get("plan_id") if isinstance(raw.get("plan_id"), str) else None
    record_id = plan_id

    if not _is_nonempty_str(raw.get("plan_id")):
        diagnostics.append(Diagnostic(MISSING_FIELD, "plan_id", "plan_id is required and must be a non-empty string (maps to the orchestrator's experiment_id)", record_id))

    schema_version = raw.get("schema_version")
    if schema_version is not None and schema_version != "ExperimentPlan.v1":
        diagnostics.append(Diagnostic(UNSUPPORTED_VERSION, "schema_version", f"schema_version {schema_version!r} is not the ExperimentPlan.v1 this adapter targets", record_id))

    is_synthetic = raw.get("is_synthetic")
    if is_synthetic is True:
        diagnostics.append(Diagnostic(SYNTHETIC_ONLY_INPUT, "is_synthetic", f"experiment {record_id!r} is declared is_synthetic=true; it can never satisfy the empirical/formal-evidence gates", record_id))

    provenance = raw.get("provenance") if isinstance(raw.get("provenance"), dict) else {}
    dataset_checksum = provenance.get("dataset_checksum") if isinstance(provenance.get("dataset_checksum"), str) else None
    if dataset_checksum is None:
        diagnostics.append(
            Diagnostic(
                MISSING_FIELD,
                "dataset_checksum",
                "ExperimentPlan.v1 has no direct dataset_checksum field; its own 'checksum' is the record's content-integrity hash, not a dataset checksum, and is never substituted -- checked provenance for an explicit dataset_checksum key and found none",
                record_id,
            )
        )

    diagnostics.append(
        Diagnostic(
            MISSING_FIELD,
            "metrics",
            "ExperimentPlan.v1 has no metrics[]/unit/feature_family concept (has 'variables' + free-text 'analysis_protocol' instead); metrics is emitted empty rather than guessing units",
            record_id,
        )
    )
    diagnostics.append(
        Diagnostic(
            MISSING_FIELD,
            "held_out_split_locked",
            "ExperimentPlan.v1 has no held_out_split_locked/is_predictive/preregistered fields; the orchestrator's locked_holdout gate cannot be satisfied from this registry's export as it stands",
            record_id,
        )
    )
    diagnostics.append(
        Diagnostic(
            MISSING_FIELD,
            "falsification_criterion",
            "ExperimentPlan.v1 has no falsification_criterion of its own -- it lives on the linked HypothesisRecord.v1 under the same field name; callers should carry it over from adapt_hypothesis_record's output for the same hypothesis_id rather than expect it here",
            record_id,
        )
    )

    if not _is_nonempty_str(raw.get("plan_id")):
        return AdaptedRecord(ok=False, record=None, diagnostics=diagnostics)

    # NEVER_COERCE: empirical_to_synthetic (and the reverse) -- is_synthetic
    # is carried through exactly as declared, never inferred from anything
    # else (e.g. a missing dataset_source is NOT treated as evidence of
    # syntheticity).
    adapted = {
        "experiment_id": raw["plan_id"],
        "hypothesis_id": raw.get("hypothesis_id") if isinstance(raw.get("hypothesis_id"), str) else None,
        "falsification_criterion": None,
        "metrics": [],
        "dataset_id": raw.get("data_source") if isinstance(raw.get("data_source"), str) else None,
        "dataset_checksum": dataset_checksum,
        "held_out_split_locked": None,
        "is_predictive": False,
        "preregistered": False,
        "synthetic": bool(is_synthetic) if isinstance(is_synthetic, bool) else False,
        "source_record_checksum": raw.get("checksum") if isinstance(raw.get("checksum"), str) else None,
    }
    return AdaptedRecord(ok=True, record=adapted, diagnostics=diagnostics)


# --- 5. Evidence updates --------------------------------------------------------


def adapt_evidence_update(raw: dict[str, Any]) -> AdaptedRecord:
    diagnostics: list[Diagnostic] = []
    record_id = raw.get("update_id") if isinstance(raw.get("update_id"), str) else None

    if not _is_nonempty_str(raw.get("update_id")):
        diagnostics.append(Diagnostic(MISSING_FIELD, "update_id", "update_id is required and must be a non-empty string", record_id))
    if not _is_nonempty_str(raw.get("entity_type")):
        diagnostics.append(Diagnostic(MISSING_FIELD, "entity_type", "entity_type is required and must be a non-empty string", record_id))
    if not _is_nonempty_str(raw.get("entity_id")):
        diagnostics.append(Diagnostic(MISSING_FIELD, "entity_id", "entity_id is required and must be a non-empty string", record_id))

    if any(d.kind == MISSING_FIELD for d in diagnostics):
        return AdaptedRecord(ok=False, record=None, diagnostics=diagnostics)

    entity_type = raw["entity_type"]
    if entity_type not in REGISTRY_EVIDENCE_UPDATE_ENTITY_TYPES:
        diagnostics.append(
            Diagnostic(INCOMPATIBLE_TYPE, "entity_type", f"entity_type {entity_type!r} is not one of the real registry's own vocabulary {sorted(REGISTRY_EVIDENCE_UPDATE_ENTITY_TYPES)}", record_id)
        )
    elif entity_type != ORCHESTRATOR_EXPECTED_EVIDENCE_UPDATE_ENTITY_TYPE:
        # This is the confirmed, structural gap: the real registry never
        # emits entity_type="hypothesis" (see the module docstring), but
        # the orchestrator's EVIDENCE_UPDATE_READY gate only recognizes
        # exactly that literal. Never silently remapped -- surfaced.
        diagnostics.append(
            Diagnostic(
                AMBIGUOUS_MAPPING,
                "entity_type",
                f"evidence_update entity_type={entity_type!r} is valid in the registry's own vocabulary, but the orchestrator's evidence-update-readiness gate only advances a hypothesis on entity_type={ORCHESTRATOR_EXPECTED_EVIDENCE_UPDATE_ENTITY_TYPE!r}; "
                "no automatic mapping is applied -- a human must decide whether a hypothesis_link update for this hypothesis should count as its evidence update, since the two registries do not share an entity_type vocabulary for hypothesis-level events",
                record_id,
            )
        )

    adapted = {
        "update_id": raw["update_id"],
        "entity_type": entity_type,
        "entity_id": raw["entity_id"],
        "update_type": raw.get("update_type") if isinstance(raw.get("update_type"), str) else "created",
        "reason": raw.get("reason") if isinstance(raw.get("reason"), str) else "",
    }
    return AdaptedRecord(ok=True, record=adapted, diagnostics=diagnostics)


# --- 5b. Experiment evidence updates (Antigravity C's EvidenceUpdate.v1) ----
#
# "Evidence update" is an overloaded term across the two upstream
# registries: Claude A's literature registry uses it for a versioning
# event on a source/claim/link record (handled by adapt_evidence_update
# above); Antigravity C's research_cycle registry uses the *same* term
# for a rich experimental-result record combining what the orchestrator
# splits across execution_results + null_surrogate_results +
# validation_reports + a contradiction flag. This adapter targets the
# latter and fans it out into the three orchestrator shapes it actually
# corresponds to.


def adapt_experiment_evidence_update(raw: dict[str, Any]) -> tuple[AdaptedRecord, dict[str, Any] | None, dict[str, Any] | None]:
    """Returns (ledger-ish execution AdaptedRecord, null_test dict or
    None, contradiction info dict or None). ``raw`` is shaped like the
    real ``EvidenceUpdate.v1``."""
    diagnostics: list[Diagnostic] = []
    experiment_id = raw.get("experiment_id") if isinstance(raw.get("experiment_id"), str) else None

    if not _is_nonempty_str(raw.get("evidence_id")):
        diagnostics.append(Diagnostic(MISSING_FIELD, "evidence_id", "evidence_id is required and must be a non-empty string", experiment_id))
    if not _is_nonempty_str(raw.get("experiment_id")):
        diagnostics.append(Diagnostic(MISSING_FIELD, "experiment_id", "experiment_id is required and must be a non-empty string", experiment_id))

    data_type = raw.get("data_type")
    if data_type is not None and data_type not in EVIDENCE_DATA_TYPES:
        diagnostics.append(Diagnostic(INCOMPATIBLE_TYPE, "data_type", f"data_type {data_type!r} is not one of {sorted(EVIDENCE_DATA_TYPES)}", experiment_id))

    is_synthetic = raw.get("is_synthetic")
    if is_synthetic is True or data_type == "synthetic_simulation":
        diagnostics.append(Diagnostic(SYNTHETIC_ONLY_INPUT, "is_synthetic", f"evidence update for experiment {experiment_id!r} is synthetic; it can never satisfy the empirical/formal-evidence gates", experiment_id))

    if any(d.kind == MISSING_FIELD for d in diagnostics):
        return AdaptedRecord(ok=False, record=None, diagnostics=diagnostics), None, None

    # data_mode: is_synthetic (explicit bool) always wins over data_type
    # -- NEVER_COERCE: empirical_to_synthetic and its reverse both forbid
    # inferring one from the other when they'd disagree; is_synthetic is
    # the more explicit, narrower-scoped field, so it is authoritative,
    # and a disagreement is flagged rather than silently resolved.
    if isinstance(is_synthetic, bool) and data_type is not None and data_type in EVIDENCE_DATA_TYPES:
        data_type_says_synthetic = data_type == "synthetic_simulation"
        if is_synthetic != data_type_says_synthetic:
            diagnostics.append(
                Diagnostic(
                    AMBIGUOUS_MAPPING, "is_synthetic",
                    f"is_synthetic={is_synthetic} disagrees with data_type={data_type!r}; is_synthetic is treated as authoritative but this disagreement is not resolved automatically",
                    experiment_id,
                )
            )
    data_mode = "synthetic" if is_synthetic is True else ("empirical" if data_type == "empirical_dataset" else "unknown")

    execution_record = {
        "experiment_id": raw["experiment_id"],
        "status": "completed",
        "data_mode": data_mode,
        "input_checksums": [c for c in (raw.get("source_checksum"),) if isinstance(c, str)],
        "output_checksums": [c for c in (raw.get("experiment_checksum"),) if isinstance(c, str)],
        "software_commit": None,
        "runtime_seconds": None,
        "dependency_state": "satisfied",
        "metric_values": [],
        "source_record_checksum": raw.get("checksum") if isinstance(raw.get("checksum"), str) else None,
    }

    null_test = None
    p_value = raw.get("observed_p_value")
    if isinstance(p_value, (int, float)):
        # NEVER_COERCE: this adapter does not itself decide PASS/FAIL from
        # a p-value threshold (that would be performing statistics, not
        # adapting a contract) -- it only carries the observed value
        # through, unlabeled, for a human/downstream system to interpret.
        null_test = {
            "experiment_id": raw["experiment_id"],
            "method": "reported_p_value",
            "verdict": "unknown",
            "statistic": float(p_value) if math.isfinite(p_value) else None,
            "notes": "verdict intentionally left unclassified -- this adapter does not perform statistical inference",
        }

    contradiction = None
    if raw.get("is_contradictory") is True:
        contradiction = {
            "hypothesis_id": raw.get("hypothesis_id") if isinstance(raw.get("hypothesis_id"), str) else None,
            "evidence_id": raw.get("evidence_id"),
            "detail": raw.get("contradiction_details") if isinstance(raw.get("contradiction_details"), str) else "(no contradiction_details provided)",
        }

    return AdaptedRecord(ok=True, record=execution_record, diagnostics=diagnostics), null_test, contradiction


# --- 6. Artifact ledger rows ------------------------------------------------------


def adapt_ledger_row(raw: dict[str, Any]) -> AdaptedRecord:
    diagnostics: list[Diagnostic] = []
    record_id = raw.get("experiment_id") if isinstance(raw.get("experiment_id"), str) else None

    if not _is_nonempty_str(raw.get("experiment_id")):
        diagnostics.append(Diagnostic(MISSING_FIELD, "experiment_id", "experiment_id is required and must be a non-empty string", record_id))

    scientific_status = raw.get("scientific_status")
    if scientific_status is not None and scientific_status not in EVIDENCE_CLASS:
        diagnostics.append(Diagnostic(INCOMPATIBLE_TYPE, "scientific_status", f"scientific_status {scientific_status!r} is not one of {sorted(EVIDENCE_CLASS)}", record_id))

    if any(d.kind == MISSING_FIELD for d in diagnostics):
        return AdaptedRecord(ok=False, record=None, diagnostics=diagnostics)

    # NEVER_COERCE: formal_to_proxy / empirical_to_synthetic -- an
    # unrecognized or absent scientific_status becomes "unknown", never
    # silently promoted OR demoted to a specific stronger/weaker label.
    adapted = {
        "experiment_id": raw["experiment_id"],
        "hypothesis_id": raw.get("hypothesis_id") if isinstance(raw.get("hypothesis_id"), str) else None,
        "source_checksum": raw.get("source_checksum") if isinstance(raw.get("source_checksum"), str) else None,
        "input_checksums": [v for v in raw.get("input_checksums", []) if isinstance(v, str)] if isinstance(raw.get("input_checksums"), list) else [],
        "output_checksums": [v for v in raw.get("output_checksums", []) if isinstance(v, str)] if isinstance(raw.get("output_checksums"), list) else [],
        "scientific_status": scientific_status if scientific_status in EVIDENCE_CLASS else "unknown",
        "reviewer_status": raw.get("reviewer_status") if isinstance(raw.get("reviewer_status"), str) else "pending",
    }
    return AdaptedRecord(ok=True, record=adapted, diagnostics=diagnostics)


# --- Cross-registry validation (claim graph coordination) -------------------


def validate_cross_registry_hypothesis_links(*, claims: list[dict[str, Any]], hypothesis_links: list[dict[str, Any]], known_hypothesis_ids: set[str]) -> list[Diagnostic]:
    """The literature registry (Claude A) and the hypothesis registry
    (Antigravity C) are two independent systems with no shared id-issuing
    authority -- nothing guarantees a ``linked_hypothesis``/
    ``hypothesis_links[].hypothesis_id`` value coined on one side
    actually exists on the other. This is checked explicitly rather than
    assumed."""
    diagnostics: list[Diagnostic] = []
    for claim in claims:
        linked = claim.get("linked_hypothesis")
        if linked and linked not in known_hypothesis_ids:
            diagnostics.append(
                Diagnostic(AMBIGUOUS_MAPPING, "linked_hypothesis", f"claim {claim.get('claim_id')!r} names linked_hypothesis={linked!r}, which is not a known hypothesis_id in the supplied hypothesis registry", claim.get("claim_id"))
            )
    for link in hypothesis_links:
        hyp_id = link.get("hypothesis_id")
        if hyp_id and hyp_id not in known_hypothesis_ids:
            diagnostics.append(
                Diagnostic(AMBIGUOUS_MAPPING, "hypothesis_id", f"hypothesis_link references hypothesis_id={hyp_id!r}, which is not a known hypothesis_id in the supplied hypothesis registry", hyp_id)
            )
    return diagnostics


# --- Bundle-level adapters ----------------------------------------------------


def adapt_literature_evidence_bundle(raw: dict[str, Any]) -> tuple[dict[str, Any], list[Diagnostic]]:
    """Adapts a full literature-registry export into the orchestrator's
    ``literature_evidence`` input-contract shape. Records that fail
    adaptation are dropped from the output (never fabricated), but every
    diagnostic that led to a drop is preserved."""
    diagnostics: list[Diagnostic] = []
    sources, claims, hlinks, elinks, updates = [], [], [], [], []

    for raw_source in raw.get("sources", []) if isinstance(raw.get("sources"), list) else []:
        result = adapt_literature_source(raw_source)
        diagnostics.extend(result.diagnostics)
        if result.ok:
            sources.append(result.record)

    for raw_claim in raw.get("claims", []) if isinstance(raw.get("claims"), list) else []:
        result = adapt_extracted_claim(raw_claim)
        diagnostics.extend(result.diagnostics)
        if result.ok:
            claims.append(result.record)

    for raw_link in raw.get("hypothesis_links", []) if isinstance(raw.get("hypothesis_links"), list) else []:
        hyp_id = raw_link.get("hypothesis_id")
        claim_ids = raw_link.get("claim_ids")
        if not _is_nonempty_str(hyp_id):
            diagnostics.append(Diagnostic(MISSING_FIELD, "hypothesis_id", "hypothesis_links entry missing hypothesis_id", None))
            continue
        relationship = raw_link.get("relationship")
        if relationship is not None and relationship not in LINK_RELATIONSHIPS:
            diagnostics.append(Diagnostic(INCOMPATIBLE_TYPE, "relationship", f"relationship {relationship!r} is not one of {sorted(LINK_RELATIONSHIPS)}", hyp_id))
        hlinks.append({"hypothesis_id": hyp_id, "claim_ids": [c for c in claim_ids if isinstance(c, str)] if isinstance(claim_ids, list) else [], "relationship": relationship if relationship in LINK_RELATIONSHIPS else "supports"})

    for raw_link in raw.get("experiment_links", []) if isinstance(raw.get("experiment_links"), list) else []:
        ref = raw_link.get("experiment_ref")
        if not _is_nonempty_str(ref):
            diagnostics.append(Diagnostic(MISSING_FIELD, "experiment_ref", "experiment_links entry missing experiment_ref", None))
            continue
        claim_ids = raw_link.get("claim_ids")
        elinks.append({"experiment_ref": ref, "claim_ids": [c for c in claim_ids if isinstance(c, str)] if isinstance(claim_ids, list) else [], "relationship": raw_link.get("relationship", "supports")})

    for raw_update in raw.get("evidence_updates", []) if isinstance(raw.get("evidence_updates"), list) else []:
        result = adapt_evidence_update(raw_update)
        diagnostics.extend(result.diagnostics)
        if result.ok:
            updates.append(result.record)

    bundle = {"sources": sources, "claims": claims, "hypothesis_links": hlinks, "experiment_links": elinks, "evidence_updates": updates}
    return bundle, diagnostics


def adapt_hypothesis_registry_bundle(raw: dict[str, Any]) -> tuple[dict[str, Any], list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    hypotheses = []
    for raw_hyp in raw.get("hypotheses", []) if isinstance(raw.get("hypotheses"), list) else []:
        result = adapt_hypothesis_record(raw_hyp)
        diagnostics.extend(result.diagnostics)
        if result.ok:
            hypotheses.append(result.record)
    return {"hypotheses": hypotheses}, diagnostics
