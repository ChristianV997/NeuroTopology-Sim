"""Closed vocabularies and identifier rules for the measurement/hypothesis mapping contract.

A mapping has two namespaces. The operational side names code that exists and derives
its identifier from that code. The interpretation side names a hypothesis, cites its
sources, and lists what would count against it. Nothing here computes a feature, assigns
an evidence state, or alters a gate decision. Vocabularies are reused from the existing
feature-contract and claim-gate modules rather than redefined.
"""
from __future__ import annotations

import re

from shared.feature_contracts.models import FeatureFamily
from shared.feature_contracts.validators import VALID_UNITS

SCHEMA = "NeuroTopologySim.MeasurementHypothesisMapping.v1"
REPORT_SCHEMA = "NeuroTopologySim.MeasurementHypothesisReport.v1"

REGISTERED_FAMILIES: frozenset[str] = frozenset(family.value for family in FeatureFamily)
REGISTERED_UNITS: frozenset[str] = VALID_UNITS
DATA_TYPES: frozenset[str] = frozenset({"float64", "int64", "bool", "str"})

# A mathematical operator may only be imported as a signal-processing generator. A
# mapping that treats an operator as a physical object is rejected.
OPERATOR_ROLES: frozenset[str] = frozenset({"signal_processing_generator"})

# Interpretations enter as proposals. Empirical, formal, benchmark, and engineering
# classes are decided by the claim gate, never declared by a mapping.
INTERPRETATION_CLAIM_CLASSES: frozenset[str] = frozenset({"hypothesis", "speculation"})

SOURCE_VERIFICATIONS: frozenset[str] = frozenset({"publisher_page", "repository_page", "search_index_metadata"})

# Gate decisions that leave a proposal admissible as a proposal. Any other decision blocks it.
NON_BLOCKING_GATE_DECISIONS: frozenset[str] = frozenset({"CLAIM_ADMISSIBLE", "CLAIM_REQUIRES_REVIEW"})

# Interpretation-namespace terms. These may appear only in interpretation fields, never
# in an operational identifier. Matching ignores case, underscores, and punctuation.
THEORY_NAMESPACE_TERMS: tuple[str, ...] = (
    "ttfcd", "uttl", "consciousness", "awareness", "soul", "nibbana", "samsara", "vedana",
    "tanha", "upadana", "karma", "liberation", "afterlife", "equanimity", "nonattachment",
    "discernment", "gauge", "quantum",
)

TOP_LEVEL_FIELDS = frozenset({
    "schema", "mapping_id", "operational", "measurement", "operator", "interpretation",
    "sources", "not_established",
})
OPERATIONAL_FIELDS = frozenset({"feature_id", "feature_family", "family_note", "implementation"})
IMPLEMENTATION_FIELDS = frozenset({"module", "symbol", "output_key", "metric_kind_literal", "sha256"})
MEASUREMENT_FIELDS = frozenset({"definition", "units", "data_type", "preprocessing"})
OPERATOR_FIELDS = frozenset({"name", "role", "literal_physical_identity", "source_ids"})
INTERPRETATION_FIELDS = frozenset({
    "hypothesis_id", "claim_class", "proposed_interpretation", "assumptions",
    "alternative_explanations", "confounds", "falsifiers", "source_ids", "theory_term",
})
FALSIFIER_FIELDS = frozenset({"id", "test", "discriminates"})
SOURCE_FIELDS = frozenset({"source_id", "title", "uri", "version", "published", "accessed", "verification"})

# Renaming an operational feature is never allowed; the identifier is derived from code.
RENAME_KEYS: frozenset[str] = frozenset({"feature_name", "display_name", "alias", "renamed_as", "label"})

# Evidence and promotion fields belong to the gate. A mapping that carries any of them is rejected.
EVIDENCE_KEYS: frozenset[str] = frozenset({
    "evidence_state", "evidence_class", "evidence_ready", "scientific_pass", "formal_bayes_factor",
    "gate", "gate_decision", "scientific_eligibility", "promotion", "evidence_promotion",
})

MAPPING_ID_RE = re.compile(r"MHM-[0-9]{4}")
SOURCE_ID_RE = re.compile(r"[a-z][a-z0-9_]{2,63}")
HYPOTHESIS_ID_RE = re.compile(r"H-[A-Z0-9][A-Z0-9-]{2,39}")
IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
HEX64_RE = re.compile(r"[0-9a-f]{64}")
PUBLISHED_RE = re.compile(r"[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?")
THEORY_TERM_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*\.[a-z][a-z0-9_]*")
FALSIFIER_ID_RE = re.compile(r"F[0-9]+")
