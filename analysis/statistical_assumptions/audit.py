"""Read-only statistical-assumption auditor.

Never repairs inputs, never computes a Bayes factor, never emits scientific_pass=true.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .json_util import NonFiniteJsonError, assert_finite_or_null, dumps_strict, finite_or_none, sha256_text
from .schema import (
    AUDITOR_ID, AUDITOR_VERSION, AUDIT_STATES, EVIDENCE_CLASS,
    KNOWN_CORRECTIONS, KNOWN_NULL_MODELS, MIN_NULL_REPLICATES, MIN_PAIRS_WARN,
    SCHEMA_ID, SEVERITY_ORDER,
)


def _finding(code: str, *, severity: str, detail: str, evidence_path: str, state_hint: str) -> dict[str, Any]:
    return {"code": code, "severity": severity, "detail": detail, "evidence_path": evidence_path, "state_hint": state_hint}


def _load_json_source(path: Path | None, inline: Any, label: str) -> tuple[Any, dict[str, Any]]:
    meta = {"label": label, "path": str(path) if path is not None else None, "checksum_sha256": None, "present": False}
    if path is not None:
        if not path.is_file():
            return None, {**meta, "error": "file_not_found"}
        raw = path.read_text(encoding="utf-8")
        meta["checksum_sha256"] = sha256_text(raw)
        meta["present"] = True
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            return None, {**meta, "error": f"invalid_json:{exc}"}
        try:
            assert_finite_or_null(payload, path=f"$.{label}")
        except NonFiniteJsonError as exc:
            return None, {**meta, "error": str(exc)}
        return payload, meta
    if inline is not None:
        meta["checksum_sha256"] = sha256_text(dumps_strict(inline))
        meta["present"] = True
        return inline, meta
    return None, meta


def _pairs_from_cohort(cohort: Mapping[str, Any]) -> tuple[list[str], list[float | None]]:
    raw_pairs = cohort.get("pairs")
    if isinstance(raw_pairs, list) and raw_pairs:
        ids: list[str] = []
        diffs: list[float | None] = []
        for item in raw_pairs:
            if not isinstance(item, Mapping):
                ids.append("")
                diffs.append(None)
                continue
            sid = item.get("pair_id") or item.get("subject_id") or item.get("id")
            ids.append("" if sid is None else str(sid))
            if "difference" in item:
                diffs.append(finite_or_none(item.get("difference")))
            elif "condition_a" in item and "condition_b" in item:
                a = finite_or_none(item.get("condition_a"))
                b = finite_or_none(item.get("condition_b"))
                diffs.append(None if a is None or b is None else a - b)
            else:
                diffs.append(finite_or_none(item.get("value")))
        return ids, diffs
    ids = [str(x) for x in (cohort.get("pair_ids") or [])]
    raw_d = cohort.get("differences") or cohort.get("paired_differences") or []
    diffs = [finite_or_none(x) for x in raw_d] if isinstance(raw_d, list) else []
    return ids, diffs


def _families(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _audit_cohort(cohort: Mapping[str, Any] | None, path_label: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if cohort is None:
        return [_finding("COHORT_MISSING", severity="error", detail="cohort-statistics report was not supplied", evidence_path=path_label, state_hint="AUDIT_INCOMPLETE")]
    ids, diffs = _pairs_from_cohort(cohort)
    declared_n = cohort.get("n_pairs_declared") or cohort.get("n_pairs")
    try:
        declared_n_int = int(declared_n) if declared_n is not None else None
    except (TypeError, ValueError):
        declared_n_int = None
        findings.append(_finding("DECLARED_N_UNPARSEABLE", severity="error", detail="n_pairs_declared is not an integer", evidence_path=f"{path_label}.n_pairs_declared", state_hint="AUDIT_INVALID_INPUT"))
    nonempty_ids = [i for i in ids if i]
    if nonempty_ids:
        seen: set[str] = set()
        dupes: list[str] = []
        for item in nonempty_ids:
            if item in seen and item not in dupes:
                dupes.append(item)
            seen.add(item)
        if dupes:
            findings.append(_finding("DUPLICATE_PAIRS", severity="error", detail=f"duplicate pair identifiers: {dupes}", evidence_path=f"{path_label}.pairs", state_hint="AUDIT_INVALID_INPUT"))
    missing_diff = sum(1 for d in diffs if d is None)
    if missing_diff:
        findings.append(_finding("MISSING_SUBJECT_PAIRS", severity="error", detail=f"{missing_diff} pair difference(s) missing or non-finite", evidence_path=f"{path_label}.differences", state_hint="AUDIT_INCOMPLETE"))
    finite_diffs = [d for d in diffs if d is not None]
    n_obs = len(finite_diffs)
    if declared_n_int is not None and n_obs < declared_n_int:
        findings.append(_finding("MISSING_SUBJECT_PAIRS", severity="warning", detail=f"observed finite pairs {n_obs} < declared {declared_n_int}", evidence_path=f"{path_label}.n_pairs_declared", state_hint="AUDIT_INCOMPLETE"))
    ess = finite_or_none(cohort.get("effective_sample_size") or cohort.get("n_effective"))
    if ess is None:
        findings.append(_finding("ESS_MISSING", severity="warning", detail="effective paired sample size metadata is missing", evidence_path=f"{path_label}.effective_sample_size", state_hint="AUDIT_INCOMPLETE"))
    elif n_obs and ess > n_obs + 1e-9:
        findings.append(_finding("ESS_EXCEEDS_N", severity="error", detail=f"effective_sample_size {ess} exceeds observed pairs {n_obs}", evidence_path=f"{path_label}.effective_sample_size", state_hint="AUDIT_INVALID_INPUT"))
    power_n = ess if ess is not None else float(n_obs)
    if power_n < MIN_PAIRS_WARN:
        findings.append(_finding("INSUFFICIENT_PAIRS", severity="error", detail=f"effective paired n={power_n} is below the audit floor {MIN_PAIRS_WARN}", evidence_path=f"{path_label}.effective_sample_size", state_hint="AUDIT_INSUFFICIENT_POWER"))
    if finite_diffs:
        if all(d == 0.0 for d in finite_diffs):
            findings.append(_finding("ALL_ZERO_DIFFERENCES", severity="error", detail="all finite paired differences are zero", evidence_path=f"{path_label}.differences", state_hint="AUDIT_SCIENTIFIC_REVIEW_REQUIRED"))
        mean = sum(finite_diffs) / len(finite_diffs)
        var = sum((d - mean) ** 2 for d in finite_diffs) / max(len(finite_diffs) - 1, 1)
        if var == 0.0:
            findings.append(_finding("ZERO_VARIANCE", severity="error", detail="paired differences have zero variance", evidence_path=f"{path_label}.differences", state_hint="AUDIT_SCIENTIFIC_REVIEW_REQUIRED"))
        n_zero = sum(1 for d in finite_diffs if d == 0.0)
        if n_zero and n_zero < len(finite_diffs):
            findings.append(_finding("TIES_OR_ZERO_DIFFS", severity="warning", detail=f"{n_zero} zero differences / ties among {len(finite_diffs)} finite pairs", evidence_path=f"{path_label}.differences", state_hint="AUDIT_SCIENTIFIC_REVIEW_REQUIRED"))
    declared_tests = cohort.get("n_tests_declared") or cohort.get("n_tests")
    observed_tests = cohort.get("n_tests_observed")
    correction = str(cohort.get("correction_method") or cohort.get("correction") or "").lower()
    if declared_tests is None and observed_tests is None:
        findings.append(_finding("TEST_COUNT_UNKNOWN", severity="error", detail="declared and observed test counts are both missing", evidence_path=f"{path_label}.n_tests", state_hint="AUDIT_MULTIPLICITY_UNRESOLVED"))
    else:
        try:
            d_int = int(declared_tests) if declared_tests is not None else None
        except (TypeError, ValueError):
            d_int = None
        try:
            o_int = int(observed_tests) if observed_tests is not None else None
        except (TypeError, ValueError):
            o_int = None
        if d_int is not None and o_int is not None and d_int != o_int:
            findings.append(_finding("TEST_COUNT_MISMATCH", severity="error", detail=f"declared n_tests={d_int} != observed n_tests={o_int}", evidence_path=f"{path_label}.n_tests", state_hint="AUDIT_MULTIPLICITY_UNRESOLVED"))
        n_compare = o_int if o_int is not None else d_int
        if n_compare is not None and n_compare > 1 and (correction not in KNOWN_CORRECTIONS or correction == "none"):
            findings.append(_finding("MULTIPLICITY_UNRESOLVED", severity="error", detail="more than one test without Bonferroni or Holm correction", evidence_path=f"{path_label}.correction_method", state_hint="AUDIT_MULTIPLICITY_UNRESOLVED"))
    families = _families(cohort.get("metric_family") or cohort.get("metric_families"))
    if len(families) > 1:
        findings.append(_finding("METRIC_FAMILIES_POOLED", severity="error", detail=f"metric families pooled in one report: {families}", evidence_path=f"{path_label}.metric_family", state_hint="AUDIT_SCIENTIFIC_REVIEW_REQUIRED"))
    if cohort.get("conflates_graph_and_spatial") is True:
        findings.append(_finding("GRAPH_SPATIAL_CONFLATION", severity="error", detail="report declares graph/spatial metric conflation", evidence_path=f"{path_label}.conflates_graph_and_spatial", state_hint="AUDIT_SCIENTIFIC_REVIEW_REQUIRED"))
    return findings


def _audit_null(null: Mapping[str, Any] | None, path_label: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if null is None:
        return [_finding("NULL_REPORT_MISSING", severity="warning", detail="null-calibration report was not supplied", evidence_path=path_label, state_hint="AUDIT_INCOMPLETE")]
    model = null.get("null_model") or null.get("model")
    if not model:
        findings.append(_finding("NULL_MODEL_MISSING", severity="error", detail="null-model identity is missing", evidence_path=f"{path_label}.null_model", state_hint="AUDIT_NULL_MODEL_UNRESOLVED"))
    elif str(model) not in KNOWN_NULL_MODELS:
        findings.append(_finding("NULL_MODEL_UNKNOWN", severity="error", detail=f"unrecognized null model {model!r}", evidence_path=f"{path_label}.null_model", state_hint="AUDIT_NULL_MODEL_UNRESOLVED"))
    n_rep = null.get("n_replicates")
    try:
        n_rep_int = int(n_rep) if n_rep is not None else None
    except (TypeError, ValueError):
        n_rep_int = None
    if n_rep_int is None:
        findings.append(_finding("NULL_REPLICATES_MISSING", severity="error", detail="null replicate count is missing", evidence_path=f"{path_label}.n_replicates", state_hint="AUDIT_NULL_MODEL_UNRESOLVED"))
    elif n_rep_int < MIN_NULL_REPLICATES:
        findings.append(_finding("NULL_REPLICATES_LOW", severity="warning", detail=f"n_replicates={n_rep_int} is below the recommended floor {MIN_NULL_REPLICATES}", evidence_path=f"{path_label}.n_replicates", state_hint="AUDIT_INSUFFICIENT_POWER"))
    if finite_or_none(null.get("effective_sample_size")) is None and null.get("n_effective") is None:
        findings.append(_finding("NULL_ESS_MISSING", severity="warning", detail="null-calibration effective sample-size metadata is missing", evidence_path=f"{path_label}.effective_sample_size", state_hint="AUDIT_INCOMPLETE"))
    return findings


def _audit_prereg(prereg: Mapping[str, Any] | None, path_label: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if prereg is None:
        return [_finding("PREREG_MISSING", severity="warning", detail="preregistration report was not supplied", evidence_path=path_label, state_hint="AUDIT_INCOMPLETE")]
    missing = []
    if not prereg.get("estimand"):
        missing.append("estimand")
    if prereg.get("n_tests") is None:
        missing.append("n_tests")
    if not prereg.get("correction_method") and not prereg.get("correction"):
        missing.append("correction_method")
    if not prereg.get("metric_family") and not prereg.get("metric_families"):
        missing.append("metric_family")
    if missing:
        findings.append(_finding("PREREG_INCOMPLETE", severity="warning", detail=f"preregistration missing fields: {missing}", evidence_path=path_label, state_hint="AUDIT_INCOMPLETE"))
    if not prereg.get("stopping_rule"):
        findings.append(_finding("STOPPING_RULE_MISSING", severity="warning", detail="no stopping rule declared", evidence_path=f"{path_label}.stopping_rule", state_hint="AUDIT_INCOMPLETE"))
    return findings


def _is_synth(blob: Any) -> bool:
    if not isinstance(blob, Mapping):
        return False
    return blob.get("synthetic") is True or blob.get("synthetic_demo") is True or blob.get("empirical_synthetic_status") == "synthetic" or blob.get("data_origin") in {"synthetic_fixture", "synthetic"}


def _synthetic_status(cohort: Any, null: Any, prereg: Any) -> tuple[bool, str]:
    present = [b for b in (cohort, null) if b is not None]
    flags = [_is_synth(b) for b in present]
    if flags and all(flags):
        return True, "synthetic"
    if any(_is_synth(b) for b in (cohort, null, prereg)):
        return True, "mixed"
    return False, "empirical_or_unspecified"


def _choose_state(findings: list[dict[str, Any]], synthetic_only: bool) -> str:
    hints = [item["state_hint"] for item in findings]
    for key in ("AUDIT_INVALID_INPUT", "AUDIT_MULTIPLICITY_UNRESOLVED", "AUDIT_NULL_MODEL_UNRESOLVED", "AUDIT_INSUFFICIENT_POWER", "AUDIT_SCIENTIFIC_REVIEW_REQUIRED"):
        if key in hints:
            return key
    if synthetic_only:
        return "AUDIT_SYNTHETIC_ONLY"
    if "AUDIT_INCOMPLETE" in hints:
        return "AUDIT_INCOMPLETE"
    return "AUDIT_CLEAN"


def _formal_k(supplied: Any) -> float | None:
    if isinstance(supplied, Mapping) and supplied.get("formally_valid") is True:
        return finite_or_none(supplied.get("k_value") or supplied.get("formal_bayes_factor"))
    return None


def audit_sources(*, cohort, null, prereg, source_meta, supplied_k=None) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for meta in source_meta:
        if meta.get("error"):
            findings.append(_finding("SOURCE_UNREADABLE", severity="error", detail=str(meta["error"]), evidence_path=meta.get("path") or meta.get("label") or "source", state_hint="AUDIT_INVALID_INPUT"))
    findings.extend(_audit_cohort(cohort if isinstance(cohort, Mapping) else None, "cohort_statistics"))
    findings.extend(_audit_null(null if isinstance(null, Mapping) else None, "null_calibration"))
    findings.extend(_audit_prereg(prereg if isinstance(prereg, Mapping) else None, "preregistration"))
    synthetic_only, synthetic_status = _synthetic_status(cohort, null, prereg)
    if synthetic_only:
        findings.append(_finding("SYNTHETIC_INPUT", severity="warning", detail="one or more source reports are synthetic demonstrations", evidence_path="synthetic_status", state_hint="AUDIT_SYNTHETIC_ONLY"))
    state = _choose_state(findings, synthetic_only)
    if state not in AUDIT_STATES:
        state = "AUDIT_SCIENTIFIC_REVIEW_REQUIRED"
    codes = {item["code"] for item in findings}
    recommendations = []
    if "INSUFFICIENT_PAIRS" in codes:
        recommendations.append("Increase paired sample size or keep the claim at speculation.")
    if "MULTIPLICITY_UNRESOLVED" in codes or "TEST_COUNT_UNKNOWN" in codes:
        recommendations.append("Declare n_tests and apply Bonferroni or Holm; do not treat unknown n_tests as 1.")
    if "NULL_MODEL_MISSING" in codes or "NULL_MODEL_UNKNOWN" in codes:
        recommendations.append("Attach a recognized seeded null-calibration report.")
    if "GRAPH_SPATIAL_CONFLATION" in codes or "METRIC_FAMILIES_POOLED" in codes:
        recommendations.append("Keep graph_beta1 and spatial_winding_q in separate families.")
    if "SYNTHETIC_INPUT" in codes:
        recommendations.append("Do not promote synthetic calibration to empirical evidence.")
    recommendations.append("Do not treat AUDIT_CLEAN as biological confirmation or a scientific PASS.")
    report = {
        "schema": SCHEMA_ID,
        "auditor": AUDITOR_ID,
        "version": AUDITOR_VERSION,
        "evidence_class": EVIDENCE_CLASS,
        "status": state,
        "scientific_pass": False,
        "formal_bayes_factor": _formal_k(supplied_k),
        "k_value": _formal_k(supplied_k),
        "falsification_verdict": None,
        "findings": findings,
        "severity": max((SEVERITY_ORDER.get(item["severity"], 0) for item in findings), default=0),
        "source_checksums": source_meta,
        "unresolved_questions": sorted({item["detail"] for item in findings if item["severity"] != "info"}),
        "recommendations": recommendations,
        "provenance": {
            "cohort_statistics": next((m.get("path") for m in source_meta if m.get("label") == "cohort_statistics"), None),
            "null_calibration": next((m.get("path") for m in source_meta if m.get("label") == "null_calibration"), None),
            "preregistration": next((m.get("path") for m in source_meta if m.get("label") == "preregistration"), None),
        },
        "synthetic_status": synthetic_status,
        "synthetic_demo": synthetic_only,
        "limitations": [
            "AUDIT_CLEAN is internal consistency only.",
            "This auditor does not compute or alter a formal Bayes factor.",
            "Statistical cleanliness is not evidence of consciousness, meditation, propofol mechanism, quantum coherence, exceptional points, or biological topological phases.",
            "Synthetic nulls and fixtures cannot create a scientific PASS.",
        ],
    }
    assert_finite_or_null(report)
    return report


def audit_payload(payload: Mapping[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    assert_finite_or_null(payload, path="$.input")
    base = root or Path.cwd()

    def _resolve(key: str):
        block = payload.get(key)
        path = None
        inline = None
        if isinstance(block, str):
            path = Path(block)
            if not path.is_absolute():
                path = base / path
        elif isinstance(block, Mapping) and "path" in block:
            path = Path(str(block["path"]))
            if not path.is_absolute():
                path = base / path
            inline = block.get("inline")
        elif isinstance(block, Mapping):
            inline = block
        return _load_json_source(path, inline, key)

    cohort, cmeta = _resolve("cohort_statistics")
    null, nmeta = _resolve("null_calibration")
    prereg, pmeta = _resolve("preregistration")
    supplied = payload.get("formal_bayes_factor_supply")
    return audit_sources(
        cohort=cohort if isinstance(cohort, Mapping) else None,
        null=null if isinstance(null, Mapping) else None,
        prereg=prereg if isinstance(prereg, Mapping) else None,
        source_meta=[cmeta, nmeta, pmeta],
        supplied_k=supplied if isinstance(supplied, Mapping) else None,
    )


def load_and_audit(text: str, *, root: Path | None = None) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"input is not valid JSON: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("input must be a JSON object")
    try:
        return audit_payload(payload, root=root)
    except NonFiniteJsonError as exc:
        raise ValueError(str(exc)) from exc
