"""Validate a measurement/hypothesis mapping against the repository's existing contracts.

A result of VALID_HYPOTHESIS_MAPPING means three things. The mapping is well formed. Its
operational side resolves to code whose checksum matches. Its interpretation names sources,
alternatives, confounds, and falsifiers. It does not mean the interpretation is supported.
The report always carries ``evidence_ready: false``. The gate decision is the one the
existing claim gate returns for the proposal, never one the mapping declares.

Command line: ``python -m shared.measurement_hypothesis MAPPING.json [--repo-root .] [--as-of YYYY-MM-DD]``
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlsplit

from tools.research_claim_gate.gate import evaluate_claim, serialize_json

from .language import scan_interpretation, target_construct_hits, theory_terms_in
from .resolve import parse, repo_file, returned_literals, sha256_of, top_level_function
from .schema import (
    CONSTRUCT_VALIDITY_FIELDS,
    CONSTRUCT_VALIDITY_STATUS,
    DATA_ACCESS_STATUS,
    DATA_TYPES,
    EMPIRICAL_CLAIM_FIELDS,
    EMPIRICAL_CLAIM_STATUS,
    EVIDENCE_KEYS,
    IDENTITY_STATUSES,
    OPERATIONAL_CATEGORIES,
    FALSIFIER_FIELDS,
    FALSIFIER_ID_RE,
    HEX64_RE,
    HYPOTHESIS_ID_RE,
    IDENTIFIER_RE,
    IMPLEMENTATION_FIELDS,
    INTERPRETATION_CLAIM_CLASSES,
    INTERPRETATION_FIELDS,
    MAPPING_ID_RE,
    MEASUREMENT_FIELDS,
    NON_BLOCKING_GATE_DECISIONS,
    OPERATIONAL_FIELDS,
    OPERATOR_FIELDS,
    OPERATOR_ROLES,
    PUBLISHED_RE,
    REGISTERED_FAMILIES,
    REGISTERED_UNITS,
    RENAME_KEYS,
    REPORT_SCHEMA,
    SCHEMA,
    SOURCE_FIELDS,
    SOURCE_ID_RE,
    SOURCE_VERIFICATIONS,
    THEORY_TERM_RE,
    TOP_LEVEL_FIELDS,
)

Fail = Callable[[str, str, str], None]

_LANGUAGE_CODES: dict[str, str] = {
    "equivalence": "EQUIVALENCE_LANGUAGE",
    "causal_or_mechanism": "CAUSAL_OR_MECHANISM_LANGUAGE",
    "empirical_support": "EMPIRICAL_SUPPORT_IMPLIED",
    "shared_claim_rules": "SHARED_CLAIM_RULE",
    "ontology_firewall": "ONTOLOGY_FIREWALL_VIOLATION",
}


def validate_mapping(mapping: Any, *, repo_root: Path, as_of: date) -> dict[str, Any]:
    """Validate one mapping. Returns a report; never raises on malformed input."""
    errors: list[dict[str, str]] = []

    def fail(code: str, path: str, message: str) -> None:
        errors.append({"code": code, "path": path, "message": message})

    if not isinstance(mapping, Mapping):
        fail("MALFORMED_MAPPING", "$", "a mapping must be a JSON object")
        return _report(None, errors, {}, None)
    try:
        json.dumps(mapping, allow_nan=False)
    except (TypeError, ValueError):
        fail("NON_FINITE_OR_NON_JSON", "$", "a mapping must be finite JSON")
        return _report(None, errors, {}, None)

    _forbid_evidence_keys(mapping, "$", fail)
    _check_unknown(mapping, TOP_LEVEL_FIELDS, "$", fail)
    if mapping.get("schema") != SCHEMA:
        fail("SCHEMA_MISMATCH", "$.schema", f"expected {SCHEMA}")
    mapping_id = mapping.get("mapping_id")
    if not (isinstance(mapping_id, str) and MAPPING_ID_RE.fullmatch(mapping_id)):
        fail("MAPPING_ID_INVALID", "$.mapping_id", "expected MHM-NNNN")

    sources = _check_sources(mapping.get("sources"), as_of, fail)
    operational = _check_operational(mapping.get("operational"), repo_root, fail)
    _check_measurement(mapping.get("measurement"), operational, fail)
    _check_operator(mapping.get("operator"), sources, fail)
    category = operational.get("category")
    interpretation = _check_interpretation(mapping.get("interpretation"), sources, fail)
    _check_empirical_claim(mapping.get("empirical_claim"), fail)
    _check_construct_validity(mapping.get("construct_validity"), fail)
    _check_not_established(mapping.get("not_established"), fail)

    gate = None
    if interpretation is not None:
        gate = _gate_reference(mapping_id, interpretation, sources, operational, fail)
    return _report(mapping_id, errors, _public_implementation(operational), gate, category=category)


# ── shared structural checks ─────────────────────────────────────────────────

def _forbid_evidence_keys(node: Any, path: str, fail: Fail) -> None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            child = f"{path}.{key}"
            if key in EVIDENCE_KEYS:
                fail("EVIDENCE_FIELD_NOT_PERMITTED", child,
                     "evidence and promotion fields are assigned by the claim gate, not declared by a mapping")
            _forbid_evidence_keys(value, child, fail)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _forbid_evidence_keys(item, f"{path}[{index}]", fail)


def _check_unknown(block: Mapping[str, Any], allowed: frozenset, path: str, fail: Fail) -> None:
    for key in block:
        if key in allowed or key in EVIDENCE_KEYS:
            continue  # evidence keys are reported once, by _forbid_evidence_keys
        if key in RENAME_KEYS:
            fail("OPERATIONAL_RENAME_NOT_PERMITTED", f"{path}.{key}",
                 "a feature keeps the identifier derived from its code; a mapping cannot rename it")
        else:
            fail("UNKNOWN_FIELD", f"{path}.{key}", "field is not part of the contract")


def _scan_operational_text(value: Any, path: str, fail: Fail) -> None:
    if isinstance(value, str):
        hits = theory_terms_in(value)
        if hits:
            fail("THEORY_TERM_IN_OPERATIONAL_IDENTIFIER", path,
                 f"{hits} belong to the interpretation namespace and may not appear in an operational identifier")


def _scan_target(value: Any, path: str, fail: Fail) -> None:
    if isinstance(value, str):
        hits = target_construct_hits(value)
        if hits:
            fail("EQUIVALENCE_TO_TARGET_CONSTRUCT", path,
                 f"a descriptor is equated with {hits}; state the target only as an empirical question in empirical_claim")


def _text_list(raw: Any, path: str, code: str, fail: Fail) -> list[str]:
    if not (isinstance(raw, list) and raw and all(isinstance(item, str) and item.strip() for item in raw)):
        fail(code, path, "at least one non-empty statement is required")
        return []
    return list(raw)


# ── sources ──────────────────────────────────────────────────────────────────

def _check_sources(raw: Any, as_of: date, fail: Fail) -> dict[str, Mapping[str, Any]]:
    if not (isinstance(raw, list) and raw):
        fail("SOURCE_REFERENCES_MISSING", "$.sources", "at least one source reference with exact version and access date is required")
        return {}
    registry: dict[str, Mapping[str, Any]] = {}
    for index, source in enumerate(raw):
        path = f"$.sources[{index}]"
        if not isinstance(source, Mapping):
            fail("SOURCE_MALFORMED", path, "a source reference must be an object")
            continue
        _check_unknown(source, SOURCE_FIELDS, path, fail)
        for field in sorted(SOURCE_FIELDS):
            value = source.get(field)
            if not (isinstance(value, str) and value.strip()):
                fail("SOURCE_FIELD_MISSING", f"{path}.{field}", f"source reference lacks {field}")
        source_id = source.get("source_id")
        if isinstance(source_id, str) and SOURCE_ID_RE.fullmatch(source_id):
            if source_id in registry:
                fail("SOURCE_ID_DUPLICATE", f"{path}.source_id", f"{source_id!r} is declared more than once")
            else:
                registry[source_id] = source
        elif source_id is not None:
            fail("SOURCE_ID_INVALID", f"{path}.source_id", "expected a lowercase identifier")
        uri = source.get("uri")
        if isinstance(uri, str) and uri:
            try:
                parts = urlsplit(uri)
                hostname = parts.hostname
                # Accessing .port performs urllib's deferred port validation.
                _ = parts.port
            except ValueError:
                fail("SOURCE_URI_INVALID", f"{path}.uri", "source uri is malformed")
            else:
                if parts.scheme != "https" or not hostname:
                    code = "SOURCE_URI_NOT_HTTPS" if parts.scheme != "https" else "SOURCE_URI_INVALID"
                    message = "source uri must be an https URL" if code == "SOURCE_URI_NOT_HTTPS" else "source uri is malformed"
                    fail(code, f"{path}.uri", message)
        published = source.get("published")
        if isinstance(published, str) and published and not PUBLISHED_RE.fullmatch(published):
            fail("SOURCE_DATE_INVALID", f"{path}.published", "expected YYYY, YYYY-MM, or YYYY-MM-DD")
        accessed = source.get("accessed")
        if isinstance(accessed, str) and accessed:
            try:
                day: Optional[date] = date.fromisoformat(accessed)
            except ValueError:
                day = None
                fail("SOURCE_DATE_INVALID", f"{path}.accessed", "expected an ISO date")
            if day is not None and day > as_of:
                fail("SOURCE_ACCESS_IN_FUTURE", f"{path}.accessed", "access date is after the validation date")
        verification = source.get("verification")
        if isinstance(verification, str) and verification and verification not in SOURCE_VERIFICATIONS:
            fail("SOURCE_VERIFICATION_UNKNOWN", f"{path}.verification",
                 f"expected one of {sorted(SOURCE_VERIFICATIONS)}")
    return registry


def _check_source_ids(raw: Any, sources: Mapping[str, Any], path: str, fail: Fail) -> None:
    if not (isinstance(raw, list) and raw):
        fail("SOURCE_REFERENCES_MISSING", path, "at least one source id is required")
        return
    for index, source_id in enumerate(raw):
        if not (isinstance(source_id, str) and source_id in sources):
            fail("SOURCE_UNRESOLVED", f"{path}[{index}]", "id does not match a declared source reference")


# ── operational side ─────────────────────────────────────────────────────────

def _check_operational(raw: Any, repo_root: Path, fail: Fail) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "category": None, "module": None, "symbol": None, "output_key": None, "metric_kind": None,
        "resolved": False, "sha256_matches": False, "symbol_found": False,
        "output_key_found": False, "metric_kind_found": False, "tree": None,
    }
    if not isinstance(raw, Mapping):
        fail("OPERATIONAL_BLOCK_MISSING", "$.operational", "the operational block is required")
        return facts
    _check_unknown(raw, OPERATIONAL_FIELDS, "$.operational", fail)

    family = raw.get("feature_family")
    if family is not None and not (isinstance(family, str) and family in REGISTERED_FAMILIES):
        fail("FEATURE_FAMILY_UNREGISTERED", "$.operational.feature_family", "not a registered FeatureFamily value")
    note = raw.get("family_note")
    if family is None and not (isinstance(note, str) and note.strip()):
        fail("FAMILY_NOTE_MISSING", "$.operational.family_note",
             "a mapping with no registered family must say why none applies")
    if isinstance(note, str):
        _scan_operational_text(note, "$.operational.family_note", fail)

    category = raw.get("category")
    if category is None:
        fail("CATEGORY_MISSING", "$.operational.category", "every descriptor declares a category")
    elif not (isinstance(category, str) and category in OPERATIONAL_CATEGORIES):
        fail("CATEGORY_UNKNOWN", "$.operational.category", "category is not in the closed vocabulary")
    else:
        facts["category"] = category

    impl = raw.get("implementation")
    base = "$.operational.implementation"
    if not isinstance(impl, Mapping):
        fail("IMPLEMENTATION_MISSING", base, "an implementation reference is required")
        return facts
    _check_unknown(impl, IMPLEMENTATION_FIELDS, base, fail)

    module = impl.get("module")
    symbol = impl.get("symbol")
    output_key = impl.get("output_key")
    metric_kind = impl.get("metric_kind_literal")
    digest = impl.get("sha256")
    facts.update(module=module, symbol=symbol, output_key=output_key, metric_kind=metric_kind)

    for name, value in (("symbol", symbol), ("output_key", output_key), ("metric_kind_literal", metric_kind)):
        if not (isinstance(value, str) and IDENTIFIER_RE.fullmatch(value)):
            fail("IMPLEMENTATION_FIELD_INVALID", f"{base}.{name}", "expected a Python identifier")
    if not (isinstance(digest, str) and HEX64_RE.fullmatch(digest)):
        fail("SHA256_INVALID", f"{base}.sha256", "expected 64 lowercase hex characters")

    # Operational identifiers come from code, so none may carry interpretation terms.
    for name, value in (("module", module), ("symbol", symbol), ("output_key", output_key),
                        ("metric_kind_literal", metric_kind)):
        _scan_operational_text(value, f"{base}.{name}", fail)
    feature_id = raw.get("feature_id")
    _scan_operational_text(feature_id, "$.operational.feature_id", fail)
    if not (isinstance(symbol, str) and isinstance(output_key, str) and feature_id == f"{symbol}.{output_key}"):
        fail("FEATURE_ID_NOT_DERIVED", "$.operational.feature_id",
             "feature_id must equal <symbol>.<output_key>; a mapping cannot name an existing feature")

    path = repo_file(repo_root, module)
    if path is None:
        fail("IMPLEMENTATION_UNRESOLVED", f"{base}.module", "module must be a file inside the repository")
        return facts
    facts["resolved"] = True
    if sha256_of(path) != digest:
        fail("IMPLEMENTATION_DRIFT", f"{base}.sha256",
             "declared checksum does not match the current file; re-review the mapping against the code")
    else:
        facts["sha256_matches"] = True
    try:
        tree = parse(path)
    except SyntaxError:
        fail("IMPLEMENTATION_UNPARSEABLE", f"{base}.module", "module does not parse")
        return facts
    facts["tree"] = tree

    function = top_level_function(tree, symbol)
    if function is None:
        fail("SYMBOL_UNRESOLVED", f"{base}.symbol",
             f"no module-level function {symbol!r} exists in {module}")
        return facts
    facts["symbol_found"] = True
    literals = returned_literals(function)
    facts["output_key_found"] = isinstance(output_key, str) and output_key in literals
    if not facts["output_key_found"]:
        fail("OUTPUT_KEY_UNRESOLVED", f"{base}.output_key", f"{output_key!r} is not returned by {symbol}")
    facts["metric_kind_found"] = isinstance(metric_kind, str) and metric_kind in literals
    if not facts["metric_kind_found"]:
        fail("METRIC_KIND_UNRESOLVED", f"{base}.metric_kind_literal", f"{metric_kind!r} is not produced by {symbol}")
    return facts


def _public_implementation(facts: Mapping[str, Any]) -> dict[str, Any]:
    """Resolution facts only. The category is reported at the top level, not as a resolution fact."""
    return {key: value for key, value in facts.items() if key not in ("tree", "category")}


def _check_measurement(raw: Any, operational: Mapping[str, Any], fail: Fail) -> None:
    base = "$.measurement"
    if not isinstance(raw, Mapping):
        fail("MEASUREMENT_BLOCK_MISSING", base, "a measurement definition is required")
        return
    _check_unknown(raw, MEASUREMENT_FIELDS, base, fail)

    definition = raw.get("definition")
    if isinstance(definition, str) and definition.strip():
        _scan_operational_text(definition, f"{base}.definition", fail)
        _scan_target(definition, f"{base}.definition", fail)
    else:
        fail("DEFINITION_MISSING", f"{base}.definition", "a measurement needs a definition")

    units = raw.get("units")
    if units is None or units == "":
        fail("UNITS_MISSING", f"{base}.units", "every measurement must declare units")
    elif not (isinstance(units, str) and units in REGISTERED_UNITS):
        fail("UNITS_UNREGISTERED", f"{base}.units", "units are not in the registered feature-contract set")

    data_type = raw.get("data_type")
    if not (isinstance(data_type, str) and data_type in DATA_TYPES):
        fail("DATA_TYPE_INVALID", f"{base}.data_type", f"expected one of {sorted(DATA_TYPES)}")

    steps = raw.get("preprocessing")
    if not (isinstance(steps, list) and steps):
        fail("PREPROCESSING_MISSING", f"{base}.preprocessing", "declare the preprocessing steps applied before the feature")
        return
    observables = raw.get("observables")
    if not (isinstance(observables, list) and observables
            and all(isinstance(item, str) and item.strip() for item in observables)):
        fail("OBSERVABLES_MISSING", f"{base}.observables",
             "name the sensor-space observables the descriptor is computed from")
    else:
        for index, item in enumerate(observables):
            _scan_operational_text(item, f"{base}.observables[{index}]", fail)
            hits = target_construct_hits(item)
            if hits:
                fail("EQUIVALENCE_TO_TARGET_CONSTRUCT", f"{base}.observables[{index}]",
                     f"an observable is named as {hits}; a sensor measure is never equated with a target construct")
    tree = operational.get("tree")
    for index, step in enumerate(steps):
        path = f"{base}.preprocessing[{index}]"
        if not (isinstance(step, str) and IDENTIFIER_RE.fullmatch(step)):
            fail("PREPROCESSING_INVALID", path, "a preprocessing step must name a function in the same module")
            continue
        _scan_operational_text(step, path, fail)
        if tree is None or top_level_function(tree, step) is None:
            fail("PREPROCESSING_UNRESOLVED", path, f"{step!r} is not a module-level function in {operational.get('module')}")


# ── operator and interpretation ──────────────────────────────────────────────

def _check_operator(raw: Any, sources: Mapping[str, Any], fail: Fail) -> None:
    base = "$.operator"
    if not isinstance(raw, Mapping):
        fail("OPERATOR_BLOCK_MISSING", base, "an operator block is required")
        return
    _check_unknown(raw, OPERATOR_FIELDS, base, fail)
    name = raw.get("name")
    if not (isinstance(name, str) and name.strip()):
        fail("OPERATOR_NAME_MISSING", f"{base}.name", "name the mathematical operator")
    _scan_target(name, f"{base}.name", fail)
    role = raw.get("role")
    if not (isinstance(role, str) and role in OPERATOR_ROLES):
        fail("OPERATOR_ROLE_NOT_PERMITTED", f"{base}.role",
             "an operator is only a signal-processing generator; it is never a physical object")
    status = raw.get("identity_status")
    if status is None:
        fail("IDENTITY_STATUS_MISSING", f"{base}.identity_status",
             "state whether the operator carries a borrowed formal identity")
    elif not (isinstance(status, str) and status in IDENTITY_STATUSES):
        fail("IDENTITY_STATUS_UNKNOWN", f"{base}.identity_status", "identity_status is not in the closed vocabulary")
    elif status == "borrowed_formal_identity":
        conditions = raw.get("identity_conditions")
        if not (isinstance(conditions, str) and conditions.strip()):
            fail("IDENTITY_CONDITIONS_MISSING", f"{base}.identity_conditions",
                 "a borrowed identity must state its conditions and normalization")
    if raw.get("literal_physical_identity") is not False:
        fail("LITERAL_PHYSICAL_IDENTITY_NOT_PERMITTED", f"{base}.literal_physical_identity",
             "must be false: a mathematical operator is not claimed to be a physical object")
    _check_source_ids(raw.get("source_ids"), sources, f"{base}.source_ids", fail)


def _check_interpretation(raw: Any, sources: Mapping[str, Any], fail: Fail) -> Optional[dict[str, Any]]:
    base = "$.interpretation"
    if not isinstance(raw, Mapping):
        fail("INTERPRETATION_BLOCK_MISSING", base, "an interpretation block is required")
        return None
    _check_unknown(raw, INTERPRETATION_FIELDS, base, fail)

    hypothesis_id = raw.get("hypothesis_id")
    if not (isinstance(hypothesis_id, str) and HYPOTHESIS_ID_RE.fullmatch(hypothesis_id)):
        fail("HYPOTHESIS_ID_INVALID", f"{base}.hypothesis_id", "expected H-<ID>")
    claim_class = raw.get("claim_class")
    if not (isinstance(claim_class, str) and claim_class in INTERPRETATION_CLAIM_CLASSES):
        fail("CLAIM_CLASS_NOT_PERMITTED", f"{base}.claim_class",
             "a mapping may propose only hypothesis or speculation; empirical, formal, benchmark, and "
             "engineering classes are decided by the claim gate, not declared by a mapping")

    text = raw.get("proposed_interpretation")
    has_text = isinstance(text, str) and bool(text.strip())
    if not has_text:
        fail("INTERPRETATION_MISSING", f"{base}.proposed_interpretation", "state the proposed interpretation")
    assumptions = _text_list(raw.get("assumptions"), f"{base}.assumptions", "ASSUMPTIONS_MISSING", fail)
    alternatives = _text_list(raw.get("alternative_explanations"), f"{base}.alternative_explanations",
                              "ALTERNATIVES_MISSING", fail)
    confounds = _text_list(raw.get("confounds"), f"{base}.confounds", "CONFOUNDS_MISSING", fail)
    _check_falsifiers(raw.get("falsifiers"), base, fail)
    _check_source_ids(raw.get("source_ids"), sources, f"{base}.source_ids", fail)

    term = raw.get("theory_term")
    if term is not None:
        if not (isinstance(term, str) and THEORY_TERM_RE.fullmatch(term)):
            fail("THEORY_TERM_INVALID", f"{base}.theory_term", "expected Namespace.term")
        elif not raw.get("source_ids"):
            fail("THEORY_TERM_WITHOUT_SOURCE", f"{base}.theory_term",
                 "an interpretation term needs a source reference")

    if has_text:
        _scan_language(text, f"{base}.proposed_interpretation", fail)
    for index, statement in enumerate(assumptions):
        _scan_language(statement, f"{base}.assumptions[{index}]", fail)
    candidates = ([(text, f"{base}.proposed_interpretation")] if has_text else []) + [
        (statement, f"{base}.assumptions[{index}]") for index, statement in enumerate(assumptions)] + [
        (item, f"{base}.alternative_explanations[{index}]") for index, item in enumerate(alternatives)] + [
        (item, f"{base}.confounds[{index}]") for index, item in enumerate(confounds)]
    for piece, piece_path in candidates:
        hits = target_construct_hits(piece)
        if hits:
            fail("EQUIVALENCE_TO_TARGET_CONSTRUCT", piece_path,
                 f"a descriptor is equated with {hits}; state the target only as an empirical question in empirical_claim")

    if not has_text:
        return None
    return {
        "hypothesis_id": hypothesis_id,
        "claim_class": claim_class,
        "text": text,
        "source_ids": [item for item in raw.get("source_ids") or [] if isinstance(item, str) and item in sources],
    }


def _check_falsifiers(raw: Any, base: str, fail: Fail) -> None:
    path = f"{base}.falsifiers"
    if not (isinstance(raw, list) and raw):
        fail("FALSIFIERS_MISSING", path, "at least one test that could count against the interpretation is required")
        return
    for index, item in enumerate(raw):
        item_path = f"{path}[{index}]"
        if not isinstance(item, Mapping):
            fail("FALSIFIER_INCOMPLETE", item_path, "a falsifier must be an object")
            continue
        _check_unknown(item, FALSIFIER_FIELDS, item_path, fail)
        falsifier_id = item.get("id")
        if not (isinstance(falsifier_id, str) and FALSIFIER_ID_RE.fullmatch(falsifier_id)):
            fail("FALSIFIER_INCOMPLETE", f"{item_path}.id", "expected F<number>")
        for field in ("test", "discriminates"):
            value = item.get(field)
            if not (isinstance(value, str) and value.strip()):
                fail("FALSIFIER_INCOMPLETE", f"{item_path}.{field}", f"a falsifier needs {field}")
            _scan_target(value, f"{item_path}.{field}", fail)


def _scan_language(text: str, path: str, fail: Fail) -> None:
    hits = scan_interpretation(text)
    for category, code in _LANGUAGE_CODES.items():
        if hits[category]:
            fail(code, path, f"{category.replace('_', ' ')} wording: {hits[category]}")


def _check_empirical_claim(raw: Any, fail: Fail) -> None:
    """Level 4: the empirical claim is stated and designed, but this contract never runs it."""
    base = "$.empirical_claim"
    if not isinstance(raw, Mapping):
        fail("EMPIRICAL_CLAIM_MISSING", base, "state the empirical claim and its analysis design, even though it is not run")
        return
    _check_unknown(raw, EMPIRICAL_CLAIM_FIELDS, base, fail)
    for field in ("statement", "required_data", "analysis_design"):
        value = raw.get(field)
        if not (isinstance(value, str) and value.strip()):
            fail("EMPIRICAL_CLAIM_FIELD_MISSING", f"{base}.{field}", f"{field} is required")
    _scan_target(raw.get("required_data"), f"{base}.required_data", fail)
    controls = raw.get("controls")
    if not (isinstance(controls, list) and controls and all(isinstance(c, str) and c.strip() for c in controls)):
        fail("EMPIRICAL_CONTROLS_MISSING", f"{base}.controls",
             "name the null and control conditions the claim would require")
    status = raw.get("status")
    if status != EMPIRICAL_CLAIM_STATUS:
        code = "EMPIRICAL_STATUS_OVERSTATED" if isinstance(status, str) and status.upper() in {
            "PASS", "VALIDATED", "CONFIRMED", "SUPPORTED", "ESTABLISHED", "VALID"} else "EMPIRICAL_STATUS_NOT_PERMITTED"
        fail(code, f"{base}.status", f"must be {EMPIRICAL_CLAIM_STATUS}: this contract runs no empirical analysis")
    if raw.get("data_access") != DATA_ACCESS_STATUS:
        fail("DATA_ACCESS_NOT_PERMITTED", f"{base}.data_access",
             f"must be {DATA_ACCESS_STATUS}: no participant recordings are accessed")
    statement = raw.get("statement")
    if isinstance(statement, str) and statement.strip():
        question = statement.strip().endswith("?")
        hits = scan_interpretation(statement)
        checks = [("equivalence", "EQUIVALENCE_LANGUAGE"), ("shared_claim_rules", "SHARED_CLAIM_RULE"),
                  ("ontology_firewall", "ONTOLOGY_FIREWALL_VIOLATION")]
        if not question:
            # A statement that asserts a result is an overstated claim while the analysis is NOT_RUN.
            checks += [("causal_or_mechanism", "CAUSAL_OR_MECHANISM_LANGUAGE"),
                       ("empirical_support", "EMPIRICAL_SUPPORT_IMPLIED")]
            _scan_target(statement, f"{base}.statement", fail)
        for category, code in checks:
            if hits[category]:
                fail(code, f"{base}.statement", f"{category.replace('_', ' ')} wording: {hits[category]}")


def _check_construct_validity(raw: Any, fail: Fail) -> None:
    """Whether the descriptor measures the intended construct. This contract never establishes it."""
    base = "$.construct_validity"
    if not isinstance(raw, Mapping):
        fail("CONSTRUCT_VALIDITY_MISSING", base,
             "state construct validity explicitly; a computable descriptor is not yet a measurement of the construct")
        return
    _check_unknown(raw, CONSTRUCT_VALIDITY_FIELDS, base, fail)
    status = raw.get("status")
    if status != CONSTRUCT_VALIDITY_STATUS:
        code = "CONSTRUCT_VALIDITY_OVERSTATED" if isinstance(status, str) and status.upper() in {
            "VALIDATED", "ESTABLISHED", "CONFIRMED", "SUPPORTED", "PASS", "VALID"} else "CONSTRUCT_VALIDITY_STATUS_NOT_PERMITTED"
        fail(code, f"{base}.status",
             f"must be {CONSTRUCT_VALIDITY_STATUS}: computability does not establish that the descriptor measures the construct")
    for field in ("intended_construct", "basis"):
        value = raw.get(field)
        if not (isinstance(value, str) and value.strip()):
            fail("CONSTRUCT_VALIDITY_FIELD_MISSING", f"{base}.{field}", f"{field} is required")
    basis = raw.get("basis")
    if isinstance(basis, str) and basis.strip():
        _scan_language(basis, f"{base}.basis", fail)
        _scan_target(basis, f"{base}.basis", fail)


def _check_not_established(raw: Any, fail: Fail) -> None:
    if not (isinstance(raw, list) and raw and all(isinstance(item, str) and item.strip() for item in raw)):
        fail("NOT_ESTABLISHED_MISSING", "$.not_established",
             "state what the mapping does not establish; at least one statement is required")


# ── gate reference ───────────────────────────────────────────────────────────

def _gate_reference(mapping_id: Any, interpretation: Mapping[str, Any], sources: Mapping[str, Any],
                    operational: Mapping[str, Any], fail: Fail) -> dict[str, Any]:
    """Ask the existing claim gate about the proposal. The result is recorded, never stored as a state."""
    first = sources.get(interpretation["source_ids"][0]) if interpretation["source_ids"] else {}
    metric_kind = operational.get("metric_kind")
    claim_id = f"{mapping_id if isinstance(mapping_id, str) else 'unidentified'}:{interpretation['hypothesis_id']}"
    gate_input = {
        "claim_id": claim_id,
        "text": interpretation["text"],
        "claim_class": interpretation["claim_class"],
        "evidence_class": interpretation["claim_class"],
        "data_mode": "none_declared",
        "proxy_status": "proxy" if isinstance(metric_kind, str) and "proxy" in metric_kind else None,
        "provenance": {
            "source_id": first.get("source_id"),
            "source_uri": first.get("uri"),
            "dataset_version": first.get("version"),
        },
    }
    result = json.loads(serialize_json(evaluate_claim(gate_input)))
    decision = result.get("decision")
    if decision not in NON_BLOCKING_GATE_DECISIONS:
        fail("GATE_DECISION_BLOCKS_MAPPING", "$.interpretation",
             f"the claim gate returned {decision}; the proposal cannot be admitted as a hypothesis")
    if result.get("scientific_eligibility") is not False or result.get("scientific_pass") is not False:
        fail("GATE_ELIGIBILITY_UNEXPECTED", "$.interpretation",
             "a hypothesis mapping must remain ineligible for scientific evidence")
    return {
        "claim_id": claim_id,
        "decision": decision,
        "claim_class": result.get("claim_class"),
        "reason_codes": result.get("reason_codes", []),
        "scientific_eligibility": result.get("scientific_eligibility"),
        "scientific_pass": result.get("scientific_pass"),
        "formal_bayes_factor": None,
    }


# Codes that mean the descriptor cannot be run as declared. They never mean the construct is measured.
_COMPUTABILITY_CODES = frozenset({
    "IMPLEMENTATION_UNRESOLVED", "IMPLEMENTATION_DRIFT", "IMPLEMENTATION_UNPARSEABLE",
    "IMPLEMENTATION_FIELD_INVALID", "IMPLEMENTATION_MISSING", "SHA256_INVALID", "SYMBOL_UNRESOLVED",
    "OUTPUT_KEY_UNRESOLVED", "METRIC_KIND_UNRESOLVED", "PREPROCESSING_UNRESOLVED",
    "PREPROCESSING_INVALID", "PREPROCESSING_MISSING", "FEATURE_ID_NOT_DERIVED", "CATEGORY_MISSING",
    "CATEGORY_UNKNOWN", "OPERATIONAL_BLOCK_MISSING",
})


def _report(mapping_id: Any, errors: list[dict[str, str]], implementation: Mapping[str, Any],
            gate: Optional[Mapping[str, Any]], category: Any = None) -> dict[str, Any]:
    computable = (
        bool(implementation.get("resolved") and implementation.get("symbol_found")
             and implementation.get("sha256_matches") and implementation.get("output_key_found")
             and implementation.get("metric_kind_found"))
        and not any(error["code"] in _COMPUTABILITY_CODES for error in errors)
    )
    return {
        "schema": REPORT_SCHEMA,
        "mapping_id": mapping_id,
        "contract_status": "REJECTED" if errors else "VALID_HYPOTHESIS_MAPPING",
        "evidence_ready": False,
        "category": category,
        "computable": computable,
        "construct_validity_status": CONSTRUCT_VALIDITY_STATUS,
        "empirical_claim_status": EMPIRICAL_CLAIM_STATUS,
        "data_access_status": DATA_ACCESS_STATUS,
        "measures_intended_construct": False,
        "errors": errors,
        "implementation": dict(implementation),
        "gate": dict(gate) if gate is not None else None,
    }


# ── command line ─────────────────────────────────────────────────────────────

def load_mapping(path: Path) -> Any:
    def _reject(name: str) -> None:
        raise ValueError(f"non-finite JSON constant: {name}")

    def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in pairs]
        repeated = sorted({key for key in keys if keys.count(key) > 1})
        if repeated:
            # Do not echo caller-controlled field names into CLI diagnostics.
            raise ValueError("duplicate JSON keys are not allowed")
        return dict(pairs)

    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=_reject,
                      object_pairs_hook=_no_duplicates)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a measurement/hypothesis mapping. Never assigns evidence.")
    parser.add_argument("mapping", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)
    try:
        mapping: Any = load_mapping(args.mapping)
    except (OSError, ValueError):
        # Parser and filesystem exceptions may contain caller-controlled paths or
        # input fragments. Keep the machine-readable failure stable and sanitized.
        report = _report(None, [{"code": "MAPPING_UNREADABLE", "path": "$",
                                "message": "mapping could not be read or parsed"}], {}, None)
    else:
        report = validate_mapping(mapping, repo_root=args.repo_root, as_of=args.as_of)
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return 0 if report["contract_status"] == "VALID_HYPOTHESIS_MAPPING" else 1
