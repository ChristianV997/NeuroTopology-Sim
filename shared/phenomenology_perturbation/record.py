"""PhenomenologyPerturbationRecord — additive domain record (not RunRecord).

Optional ``parent_run_id`` may reference ``RunRecordV1.run_id`` without mutating
generic run provenance. C5 sidecar contracts are out of scope here.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional

from shared.research_claims.json_util import (
    NonFiniteJsonError,
    assert_finite_or_null,
    dumps_strict,
    loads_strict,
)

from .paths import safe_relative_path
from .schema import (
    ACCESS_STATUSES,
    ARTIFACT_PATH_KEYS,
    CAUSAL_CLAIM_TYPES,
    CONSENT_STATUSES,
    DATA_STATUSES,
    EVIDENCE_STATUSES,
    INTEGRITY_MODES,
    LATENT_PROFILE_LABEL,
    MAX_REPORT_TEXT_CHARS,
    OBSERVATION_ORIGINS,
    PERTURBATION_MODALITIES,
    PROHIBITED_CLASSIFIER_PHRASES,
    PROHIBITED_IDENTIFIER_KEYS,
    PROHIBITED_KEYS,
    SCHEMA,
    TIME_REFERENCES,
    TOP_LEVEL_REQUIRED,
)

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_EMAIL_RE = re.compile(r"\b\S+@\S+\.\S+\b")


SCHEMA  # re-export convenience


class PhenomenologyValidationError(ValueError):
    """Malformed phenomenology / perturbation record."""


def _norm_text(value: str) -> str:
    return re.sub(r"[\s_\-]+", " ", value.casefold())


def _reject_prohibited_text(value: str, path: str) -> None:
    lowered = _norm_text(value)
    for phrase in PROHIBITED_CLASSIFIER_PHRASES:
        if _norm_text(phrase) in lowered:
            raise PhenomenologyValidationError(
                f"{path}: prohibited classifier/attainment language ({phrase!r})"
            )


def _reject_prohibited_keys(obj: Mapping[str, Any], path: str) -> None:
    for key in obj:
        if key in PROHIBITED_KEYS:
            raise PhenomenologyValidationError(f"{path}: prohibited key {key!r}")
        if key in PROHIBITED_IDENTIFIER_KEYS:
            raise PhenomenologyValidationError(
                f"{path}: prohibited direct-identifier key {key!r} (privacy)"
            )
        if isinstance(key, str):
            _reject_prohibited_text(key, f"{path}.<key>")


def _reject_identifier_leak(value: str, path: str) -> None:
    if _EMAIL_RE.search(value):
        raise PhenomenologyValidationError(f"{path}: email-like text rejected (privacy)")


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or isinstance(value, (str, list)):
        raise PhenomenologyValidationError(f"{path}: expected object")
    return value


def _require_str(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise PhenomenologyValidationError(f"{path}: expected string")
    if not allow_empty and value.strip() == "":
        raise PhenomenologyValidationError(f"{path}: empty string")
    _reject_prohibited_text(value, path)
    _reject_identifier_leak(value, path)
    return value


def _require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise PhenomenologyValidationError(f"{path}: expected boolean (not int)")
    return value


def _require_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhenomenologyValidationError(f"{path}: expected finite number")
    number = float(value)
    try:
        assert_finite_or_null(number, path)
    except NonFiniteJsonError as exc:
        raise PhenomenologyValidationError(str(exc)) from exc
    return number


def _validate_practice(practice: Mapping[str, Any]) -> Dict[str, Any]:
    _reject_prohibited_keys(practice, "$.practice")
    out: Dict[str, Any] = {
        "instruction_id": _require_str(practice.get("instruction_id"), "$.practice.instruction_id"),
        "instruction_text": _require_str(
            practice.get("instruction_text"), "$.practice.instruction_text", allow_empty=True
        ),
    }
    # Practice dose (not skill)
    if "practice_dose" not in practice:
        raise PhenomenologyValidationError("$.practice.practice_dose: required")
    dose = _require_mapping(practice.get("practice_dose"), "$.practice.practice_dose")
    _reject_prohibited_keys(dose, "$.practice.practice_dose")
    dose_out: Dict[str, Any] = {}
    if "duration_s" in dose:
        dose_out["duration_s"] = _require_number(dose["duration_s"], "$.practice.practice_dose.duration_s")
        if dose_out["duration_s"] < 0:
            raise PhenomenologyValidationError("$.practice.practice_dose.duration_s: must be >= 0")
    if "session_count" in dose:
        sc = dose["session_count"]
        if isinstance(sc, bool) or not isinstance(sc, int) or sc < 0:
            raise PhenomenologyValidationError("$.practice.practice_dose.session_count: expected non-negative int")
        dose_out["session_count"] = sc
    if not dose_out:
        raise PhenomenologyValidationError(
            "$.practice.practice_dose: require duration_s and/or session_count"
        )
    out["practice_dose"] = dose_out

    # Optional skill label — must not be confused with dose or attainment
    if "practice_control_skill" in practice and practice["practice_control_skill"] is not None:
        skill = _require_mapping(practice["practice_control_skill"], "$.practice.practice_control_skill")
        _reject_prohibited_keys(skill, "$.practice.practice_control_skill")
        skill_out: Dict[str, Any] = {
            "label": _require_str(skill.get("label"), "$.practice.practice_control_skill.label"),
            "not_practice_dose": True,
            "is_attainment_claim": False,
        }
        if "self_report_level" in skill and skill["self_report_level"] is not None:
            skill_out["self_report_level"] = _require_number(
                skill["self_report_level"], "$.practice.practice_control_skill.self_report_level"
            )
        if "notes" in skill and skill["notes"] is not None:
            skill_out["notes"] = _require_str(skill["notes"], "$.practice.practice_control_skill.notes", allow_empty=True)
        out["practice_control_skill"] = skill_out

    # Optional slow transition params — explicitly not attainment
    if "slow_transition_params" in practice and practice["slow_transition_params"] is not None:
        th = _require_mapping(practice["slow_transition_params"], "$.practice.slow_transition_params")
        _reject_prohibited_keys(th, "$.practice.slow_transition_params")
        th_out: Dict[str, Any] = {
            "is_attainment_claim": False,
            "parameters": {},
        }
        params = th.get("parameters", {})
        params = _require_mapping(params, "$.practice.slow_transition_params.parameters")
        for key, val in params.items():
            if not isinstance(key, str):
                raise PhenomenologyValidationError("$.practice.slow_transition_params.parameters: keys must be str")
            th_out["parameters"][key] = _require_number(
                val, f"$.practice.slow_transition_params.parameters.{key}"
            )
        out["slow_transition_params"] = th_out
    return out


def _validate_perturbation(pert: Mapping[str, Any]) -> Dict[str, Any]:
    _reject_prohibited_keys(pert, "$.perturbation")
    modality = pert.get("modality")
    if modality not in PERTURBATION_MODALITIES:
        raise PhenomenologyValidationError(f"$.perturbation.modality: invalid {modality!r}")
    onset = _require_number(pert.get("onset_s"), "$.perturbation.onset_s")
    offset = pert.get("offset_s")
    out: Dict[str, Any] = {
        "event_id": _require_str(pert.get("event_id"), "$.perturbation.event_id"),
        "randomized": _require_bool(pert.get("randomized"), "$.perturbation.randomized"),
        "onset_s": onset,
        "modality": modality,
        "observation_origin": pert.get("observation_origin"),
        # Typed release fields (separate from free-form parameters).
        "target": _require_str(pert.get("target"), "$.perturbation.target"),
        "amplitude": _require_number(pert.get("amplitude"), "$.perturbation.amplitude"),
        "units": _require_str(pert.get("units"), "$.perturbation.units"),
    }
    if out["observation_origin"] not in OBSERVATION_ORIGINS:
        raise PhenomenologyValidationError(
            f"$.perturbation.observation_origin: invalid {out['observation_origin']!r}"
        )
    if offset is not None:
        offset_f = _require_number(offset, "$.perturbation.offset_s")
        if offset_f < onset:
            raise PhenomenologyValidationError(
                "$.perturbation: offset_s must be >= onset_s"
            )
        out["offset_s"] = offset_f
    else:
        out["offset_s"] = None
    params = pert.get("parameters", {})
    params = _require_mapping(params, "$.perturbation.parameters")
    _reject_prohibited_keys(params, "$.perturbation.parameters")
    clean_params: Dict[str, Any] = {}
    for key, val in params.items():
        if not isinstance(key, str):
            raise PhenomenologyValidationError("$.perturbation.parameters: keys must be str")
        if isinstance(val, str):
            clean_params[key] = _require_str(val, f"$.perturbation.parameters.{key}", allow_empty=True)
        elif isinstance(val, bool):
            clean_params[key] = val
        else:
            clean_params[key] = _require_number(val, f"$.perturbation.parameters.{key}")
    out["parameters"] = clean_params
    if "onset_sample" in pert and pert["onset_sample"] is not None:
        sample = pert["onset_sample"]
        if isinstance(sample, bool) or not isinstance(sample, int) or sample < 0:
            raise PhenomenologyValidationError(
                "$.perturbation.onset_sample: expected non-negative int"
            )
        out["onset_sample"] = sample
    if "clock_alignment" in pert and pert["clock_alignment"] is not None:
        align = _require_mapping(pert["clock_alignment"], "$.perturbation.clock_alignment")
        _reject_prohibited_keys(align, "$.perturbation.clock_alignment")
        ref = align.get("time_reference")
        if ref not in TIME_REFERENCES:
            raise PhenomenologyValidationError(
                f"$.perturbation.clock_alignment.time_reference: invalid {ref!r}"
            )
        out["clock_alignment"] = {
            "time_reference": ref,
            "sync_uncertainty_ms": _require_number(
                align.get("sync_uncertainty_ms", 0.0),
                "$.perturbation.clock_alignment.sync_uncertainty_ms",
            ),
        }
        if out["clock_alignment"]["sync_uncertainty_ms"] < 0:
            raise PhenomenologyValidationError(
                "$.perturbation.clock_alignment.sync_uncertainty_ms: must be >= 0"
            )
    return out


def _validate_behavior(behavior: Mapping[str, Any]) -> Dict[str, Any]:
    _reject_prohibited_keys(behavior, "$.behavior")
    missing = _require_bool(behavior.get("missing"), "$.behavior.missing")
    origin = behavior.get("observation_origin")
    if origin not in OBSERVATION_ORIGINS:
        raise PhenomenologyValidationError(f"$.behavior.observation_origin: invalid {origin!r}")
    response = behavior.get("response", None)
    reason = behavior.get("missingness_reason")
    if missing:
        if response is not None:
            raise PhenomenologyValidationError(
                "$.behavior: missing=true but response is present (inconsistent missingness)"
            )
        if reason is None or (isinstance(reason, str) and reason.strip() == ""):
            raise PhenomenologyValidationError(
                "$.behavior.missingness_reason: required when missing=true"
            )
        _require_str(reason, "$.behavior.missingness_reason")
    else:
        if response is None:
            raise PhenomenologyValidationError(
                "$.behavior: missing=false but response is null (inconsistent missingness)"
            )
        if reason is not None:
            raise PhenomenologyValidationError(
                "$.behavior.missingness_reason: must be null when missing=false"
            )
    out: Dict[str, Any] = {
        "missing": missing,
        "response": response,
        "missingness_reason": reason if missing else None,
        "observation_origin": origin,
    }
    if "rt_s" in behavior and behavior["rt_s"] is not None:
        rt = _require_number(behavior["rt_s"], "$.behavior.rt_s")
        if rt < 0:
            raise PhenomenologyValidationError("$.behavior.rt_s: must be >= 0")
        out["rt_s"] = rt
    return out


def _validate_delayed_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    _reject_prohibited_keys(report, "$.delayed_report")
    origin = report.get("observation_origin")
    if origin not in OBSERVATION_ORIGINS:
        raise PhenomenologyValidationError(
            f"$.delayed_report.observation_origin: invalid {origin!r}"
        )
    t0 = _require_number(report.get("target_interval_start_s"), "$.delayed_report.target_interval_start_s")
    t1 = _require_number(report.get("target_interval_end_s"), "$.delayed_report.target_interval_end_s")
    if t1 < t0:
        raise PhenomenologyValidationError(
            "$.delayed_report: target_interval_end_s must be >= target_interval_start_s"
        )
    response_time = _require_number(report.get("response_time_s"), "$.delayed_report.response_time_s")
    delay = _require_number(report.get("report_delay_s"), "$.delayed_report.report_delay_s")
    if delay < 0:
        raise PhenomenologyValidationError("$.delayed_report.report_delay_s: must be >= 0")
    # Timing consistency: delay should match response_time - target_interval_end
    expected = response_time - t1
    if abs(expected - delay) > 1e-9:
        raise PhenomenologyValidationError(
            "$.delayed_report: report_delay_s must equal response_time_s - target_interval_end_s "
            f"(got delay={delay}, expected={expected})"
        )
    if response_time < t1:
        raise PhenomenologyValidationError(
            "$.delayed_report: response_time_s must be >= target_interval_end_s for a delayed report"
        )
    report_text = _require_str(
        report.get("report_text"), "$.delayed_report.report_text", allow_empty=True
    )
    if len(report_text) > MAX_REPORT_TEXT_CHARS:
        raise PhenomenologyValidationError(
            f"$.delayed_report.report_text: exceeds portable max "
            f"{MAX_REPORT_TEXT_CHARS} chars (privacy); store full narrative off-artifact"
        )
    language = report.get("language", "und")
    language = _require_str(language, "$.delayed_report.language")
    out: Dict[str, Any] = {
        "prompt_exact": _require_str(report.get("prompt_exact"), "$.delayed_report.prompt_exact"),
        "target_interval_start_s": t0,
        "target_interval_end_s": t1,
        "response_time_s": response_time,
        "report_delay_s": delay,
        "report_text": report_text,
        "language": language,
        "observation_origin": origin,
        "not_latent_state": True,
    }
    if "confidence" in report and report["confidence"] is not None:
        conf = _require_number(report["confidence"], "$.delayed_report.confidence")
        if conf < 0 or conf > 1:
            raise PhenomenologyValidationError("$.delayed_report.confidence: expected in [0, 1]")
        out["confidence"] = conf
    else:
        out["confidence"] = None
    return out


def _validate_physiology_neural(phys: Mapping[str, Any]) -> Dict[str, Any]:
    """Optional physiology/neural *features* — never consciousness/attainment labels."""
    _reject_prohibited_keys(phys, "$.physiology_neural")
    origin = phys.get("observation_origin")
    if origin not in OBSERVATION_ORIGINS:
        raise PhenomenologyValidationError(
            f"$.physiology_neural.observation_origin: invalid {origin!r}"
        )
    if phys.get("is_consciousness_or_attainment_label") is True:
        raise PhenomenologyValidationError(
            "$.physiology_neural: is_consciousness_or_attainment_label must not be true "
            "(EEG/physiology features are not attainment or consciousness labels)"
        )
    features = _require_mapping(phys.get("features"), "$.physiology_neural.features")
    clean_feats: Dict[str, Any] = {}
    for name, spec in features.items():
        if not isinstance(name, str) or not name:
            raise PhenomenologyValidationError(
                "$.physiology_neural.features: names must be non-empty str"
            )
        spec_m = _require_mapping(spec, f"$.physiology_neural.features.{name}")
        _reject_prohibited_keys(spec_m, f"$.physiology_neural.features.{name}")
        clean_feats[name] = {
            "value": _require_number(
                spec_m.get("value"), f"$.physiology_neural.features.{name}.value"
            ),
            "units": _require_str(
                spec_m.get("units"), f"$.physiology_neural.features.{name}.units"
            ),
        }
    out: Dict[str, Any] = {
        "observation_origin": origin,
        "features": clean_feats,
        "is_consciousness_or_attainment_label": False,
        "not_participant_report": True,
        "not_latent_state": True,
    }
    if "reference" in phys and phys["reference"] is not None:
        out["reference"] = _require_str(
            phys["reference"], "$.physiology_neural.reference", allow_empty=True
        )
    else:
        out["reference"] = ""
    return out


def _validate_signal_quality(sq: Mapping[str, Any]) -> Dict[str, Any]:
    _reject_prohibited_keys(sq, "$.signal_quality")
    out: Dict[str, Any] = {
        "eeg_ok": _require_bool(sq.get("eeg_ok"), "$.signal_quality.eeg_ok"),
        "sync_ok": _require_bool(sq.get("sync_ok"), "$.signal_quality.sync_ok"),
    }
    ref = sq.get("time_reference", "session_t0")
    if ref not in TIME_REFERENCES:
        raise PhenomenologyValidationError(f"$.signal_quality.time_reference: invalid {ref!r}")
    out["time_reference"] = ref
    if "sync_offset_ms" in sq and sq["sync_offset_ms"] is not None:
        out["sync_offset_ms"] = _require_number(sq["sync_offset_ms"], "$.signal_quality.sync_offset_ms")
    else:
        out["sync_offset_ms"] = None
    if "sync_uncertainty_ms" in sq and sq["sync_uncertainty_ms"] is not None:
        unc = _require_number(sq["sync_uncertainty_ms"], "$.signal_quality.sync_uncertainty_ms")
        if unc < 0:
            raise PhenomenologyValidationError("$.signal_quality.sync_uncertainty_ms: must be >= 0")
        out["sync_uncertainty_ms"] = unc
    else:
        out["sync_uncertainty_ms"] = None
    if "sample_rate_hz" in sq and sq["sample_rate_hz"] is not None:
        rate = _require_number(sq["sample_rate_hz"], "$.signal_quality.sample_rate_hz")
        if rate <= 0:
            raise PhenomenologyValidationError("$.signal_quality.sample_rate_hz: must be > 0")
        out["sample_rate_hz"] = rate
    else:
        out["sample_rate_hz"] = None
    units = sq.get("units", {})
    units = _require_mapping(units, "$.signal_quality.units")
    _reject_prohibited_keys(units, "$.signal_quality.units")
    clean_units: Dict[str, str] = {}
    for key, val in units.items():
        if not isinstance(key, str):
            raise PhenomenologyValidationError("$.signal_quality.units: keys must be str")
        clean_units[key] = _require_str(val, f"$.signal_quality.units.{key}")
    out["units"] = clean_units
    if "notes" in sq and sq["notes"] is not None:
        out["notes"] = _require_str(sq["notes"], "$.signal_quality.notes", allow_empty=True)
    else:
        out["notes"] = ""
    return out


def _validate_latent_profile(latent: Mapping[str, Any]) -> Dict[str, Any]:
    _reject_prohibited_keys(latent, "$.latent_profile")
    label = latent.get("label")
    if label != LATENT_PROFILE_LABEL:
        raise PhenomenologyValidationError(
            f"$.latent_profile.label: must be {LATENT_PROFILE_LABEL!r} (got {label!r})"
        )
    if latent.get("directly_observed") is True:
        raise PhenomenologyValidationError(
            "$.latent_profile: directly_observed must not be true (x_t is not observed)"
        )
    variables = _require_mapping(latent.get("variables"), "$.latent_profile.variables")
    clean: Dict[str, Any] = {}
    for name, spec in variables.items():
        if not isinstance(name, str) or not name:
            raise PhenomenologyValidationError("$.latent_profile.variables: names must be non-empty str")
        # x_t naming is allowed as inferred variable name with uncertainty only
        spec_m = _require_mapping(spec, f"$.latent_profile.variables.{name}")
        point = _require_number(spec_m.get("point"), f"$.latent_profile.variables.{name}.point")
        unc = _require_number(
            spec_m.get("uncertainty"), f"$.latent_profile.variables.{name}.uncertainty"
        )
        if unc < 0:
            raise PhenomenologyValidationError(
                f"$.latent_profile.variables.{name}.uncertainty: must be >= 0"
            )
        clean[name] = {"point": point, "uncertainty": unc}
    provenance = latent.get("model_provenance")
    if provenance is None:
        raise PhenomenologyValidationError(
            "$.latent_profile.model_provenance: required when latent_profile is present"
        )
    prov = _require_mapping(provenance, "$.latent_profile.model_provenance")
    _reject_prohibited_keys(prov, "$.latent_profile.model_provenance")
    prov_out: Dict[str, Any] = {
        "model_id": _require_str(prov.get("model_id"), "$.latent_profile.model_provenance.model_id"),
    }
    if "code_path" in prov and prov["code_path"] is not None:
        try:
            prov_out["code_path"] = safe_relative_path(prov["code_path"])
        except ValueError as exc:
            raise PhenomenologyValidationError(
                f"$.latent_profile.model_provenance.code_path: {exc}"
            ) from exc
    if "recorded_code_sha256" in prov and prov["recorded_code_sha256"] is not None:
        digest = prov["recorded_code_sha256"]
        if not isinstance(digest, str) or not _SHA256_RE.match(digest):
            raise PhenomenologyValidationError(
                "$.latent_profile.model_provenance.recorded_code_sha256: expected 64 hex chars"
            )
        prov_out["recorded_code_sha256"] = digest.lower()
        prov_out["integrity_disclaimer"] = (
            "recorded digests support integrity checks only; not authenticity or run authorship"
        )
    return {
        "label": LATENT_PROFILE_LABEL,
        "directly_observed": False,
        "variables": clean,
        "model_provenance": prov_out,
        "notes": _require_str(latent.get("notes", ""), "$.latent_profile.notes", allow_empty=True)
        if "notes" in latent
        else "",
    }


def _validate_integrity(
    integrity: Mapping[str, Any],
    *,
    artifact_paths: Mapping[str, str],
    verify_root: Optional[Path],
) -> Dict[str, Any]:
    _reject_prohibited_keys(integrity, "$.integrity")
    mode = integrity.get("mode", "record_only")
    if mode not in INTEGRITY_MODES:
        raise PhenomenologyValidationError(f"$.integrity.mode: invalid {mode!r}")
    digests = integrity.get("path_sha256", {})
    digests = _require_mapping(digests, "$.integrity.path_sha256")
    clean: Dict[str, str] = {}
    for key, digest in digests.items():
        if key not in ARTIFACT_PATH_KEYS:
            raise PhenomenologyValidationError(f"$.integrity.path_sha256: unknown path role {key!r}")
        if not isinstance(digest, str) or not _SHA256_RE.match(digest):
            raise PhenomenologyValidationError(
                f"$.integrity.path_sha256.{key}: expected 64 hex chars"
            )
        clean[key] = digest.lower()
    out: Dict[str, Any] = {
        "mode": mode,
        "path_sha256": clean,
        "disclaimer": (
            "Hashes support integrity checks only; they do not prove authenticity "
            "or that a particular run authored the bytes."
        ),
    }
    if mode == "verify_paths":
        if verify_root is None:
            raise PhenomenologyValidationError(
                "$.integrity.mode=verify_paths requires verify_root argument"
            )
        root = Path(verify_root).resolve()
        for key, expected in clean.items():
            if key not in artifact_paths:
                raise PhenomenologyValidationError(
                    f"$.integrity: digest for {key!r} but artifact_paths lacks that role"
                )
            rel = artifact_paths[key]
            candidate = (root / rel).resolve()
            try:
                candidate.relative_to(root)
            except ValueError as exc:
                raise PhenomenologyValidationError(
                    f"$.integrity: path escapes verify_root for {key!r}"
                ) from exc
            if not candidate.is_file():
                raise PhenomenologyValidationError(
                    f"$.integrity: missing file for {key!r}: {rel}"
                )
            actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if actual != expected:
                raise PhenomenologyValidationError(
                    f"$.integrity: sha256 mismatch for {key!r}"
                )
        out["verified"] = True
    else:
        out["verified"] = False
    return out


def _validate_artifact_paths(paths: Mapping[str, Any]) -> Dict[str, str]:
    _reject_prohibited_keys(paths, "$.artifact_paths")
    out: Dict[str, str] = {}
    for key, val in paths.items():
        if key not in ARTIFACT_PATH_KEYS:
            raise PhenomenologyValidationError(f"$.artifact_paths: unknown key {key!r}")
        if val is None:
            continue
        try:
            out[key] = safe_relative_path(val)
        except ValueError as exc:
            raise PhenomenologyValidationError(f"$.artifact_paths.{key}: {exc}") from exc
    return out


def _validate_privacy(privacy: Mapping[str, Any]) -> Dict[str, Any]:
    """Consent/access status distinct from optional opaque pseudonym tokens.

    Schema validation is **not** a complete privacy or redaction pipeline.
    """
    _reject_prohibited_keys(privacy, "$.privacy")
    consent = privacy.get("consent_status")
    if consent not in CONSENT_STATUSES:
        raise PhenomenologyValidationError(f"$.privacy.consent_status: invalid {consent!r}")
    access = privacy.get("access_status")
    if access not in ACCESS_STATUSES:
        raise PhenomenologyValidationError(f"$.privacy.access_status: invalid {access!r}")
    out: Dict[str, Any] = {
        "consent_status": consent,
        "access_status": access,
        # Hard-coded: validating this block does not complete privacy/redaction work.
        "schema_is_complete_privacy_pipeline": False,
    }
    if "pseudonym_token" in privacy and privacy["pseudonym_token"] is not None:
        token = _require_str(privacy["pseudonym_token"], "$.privacy.pseudonym_token")
        # Opaque token only — reject tokens that look like contact identifiers.
        out["pseudonym_token"] = token
    else:
        out["pseudonym_token"] = None
    # Keep nulls distinct: unavailable flags must not coerce to false/zero elsewhere.
    if "redaction_complete" in privacy and privacy["redaction_complete"] is not None:
        out["redaction_complete"] = _require_bool(
            privacy["redaction_complete"], "$.privacy.redaction_complete"
        )
    else:
        out["redaction_complete"] = None
    return out


def _check_origin_vs_data_status(data_status: str, origins: List[str]) -> None:
    """Reject synthetic observations labeled as exclusively measured, and vice versa mismatches."""
    if data_status == "empirical_measured":
        for origin in origins:
            if origin == "synthetic":
                raise PhenomenologyValidationError(
                    "data_status=empirical_measured but a section has observation_origin=synthetic "
                    "(synthetic data mislabeled as measured)"
                )
    if data_status == "synthetic":
        for origin in origins:
            if origin == "measured":
                raise PhenomenologyValidationError(
                    "data_status=synthetic but a section has observation_origin=measured "
                    "(invalid source status mix without mixed_declared)"
                )


def validate_record_dict(
    d: Mapping[str, Any],
    *,
    verify_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Validate and return a normalized record dict. Raises PhenomenologyValidationError.

    ``verify_root`` is required only when ``integrity.mode == "verify_paths"``.
    """
    if not isinstance(d, Mapping):
        raise PhenomenologyValidationError("$: expected object")
    _reject_prohibited_keys(d, "$")
    missing = TOP_LEVEL_REQUIRED - set(d)
    if missing:
        raise PhenomenologyValidationError(f"$: missing required fields {sorted(missing)}")

    if d.get("schema") != SCHEMA:
        raise PhenomenologyValidationError(f"$.schema: expected {SCHEMA!r}")

    data_status = d.get("data_status")
    if data_status not in DATA_STATUSES:
        raise PhenomenologyValidationError(f"$.data_status: invalid {data_status!r}")
    claim = d.get("causal_claim_type")
    if claim not in CAUSAL_CLAIM_TYPES:
        raise PhenomenologyValidationError(f"$.causal_claim_type: invalid {claim!r}")
    evidence_status = d.get("evidence_status")
    if evidence_status not in EVIDENCE_STATUSES:
        raise PhenomenologyValidationError(f"$.evidence_status: invalid {evidence_status!r}")

    record_id = _require_str(d.get("record_id"), "$.record_id")
    parent_run_id = d.get("parent_run_id")
    if parent_run_id is not None:
        parent_run_id = _require_str(parent_run_id, "$.parent_run_id")

    practice = _validate_practice(_require_mapping(d.get("practice"), "$.practice"))
    perturbation = _validate_perturbation(_require_mapping(d.get("perturbation"), "$.perturbation"))
    behavior = _validate_behavior(_require_mapping(d.get("behavior"), "$.behavior"))
    delayed = _validate_delayed_report(_require_mapping(d.get("delayed_report"), "$.delayed_report"))
    signal_quality = _validate_signal_quality(_require_mapping(d.get("signal_quality"), "$.signal_quality"))

    origins = [
        perturbation["observation_origin"],
        behavior["observation_origin"],
        delayed["observation_origin"],
    ]

    physiology_neural = None
    if "physiology_neural" in d and d["physiology_neural"] is not None:
        physiology_neural = _validate_physiology_neural(
            _require_mapping(d["physiology_neural"], "$.physiology_neural")
        )
        origins.append(physiology_neural["observation_origin"])

    _check_origin_vs_data_status(data_status, origins)

    artifact_paths: Dict[str, str] = {}
    if "artifact_paths" in d and d["artifact_paths"] is not None:
        artifact_paths = _validate_artifact_paths(
            _require_mapping(d["artifact_paths"], "$.artifact_paths")
        )

    out: Dict[str, Any] = {
        "schema": SCHEMA,
        "record_id": record_id,
        "parent_run_id": parent_run_id,
        "data_status": data_status,
        "causal_claim_type": claim,
        "evidence_status": evidence_status,
        "practice": practice,
        "perturbation": perturbation,
        "behavior": behavior,
        "delayed_report": delayed,
        "signal_quality": signal_quality,
        "physiology_neural": physiology_neural,
        "latent_profile": None,
        "artifact_paths": artifact_paths,
        "privacy": {
            "consent_status": "not_recorded",
            "access_status": "unavailable",
            "pseudonym_token": None,
            "redaction_complete": None,
            "schema_is_complete_privacy_pipeline": False,
        },
        "integrity": {
            "mode": "record_only",
            "path_sha256": {},
            "verified": False,
            "disclaimer": (
                "Hashes support integrity checks only; they do not prove authenticity "
                "or that a particular run authored the bytes."
            ),
        },
        "claim_limits": {
            "dose_equals_skill": False,
            "report_equals_latent": False,
            "model_estimate_equals_participant_report": False,
            "eeg_feature_equals_consciousness_or_attainment": False,
            "slow_parameter_equals_liberation": False,
            "digest_equals_authenticity_or_scientific_validity": False,
        },
    }

    if "privacy" in d and d["privacy"] is not None:
        out["privacy"] = _validate_privacy(_require_mapping(d["privacy"], "$.privacy"))
    if "latent_profile" in d and d["latent_profile"] is not None:
        out["latent_profile"] = _validate_latent_profile(
            _require_mapping(d["latent_profile"], "$.latent_profile")
        )
    if "integrity" in d and d["integrity"] is not None:
        out["integrity"] = _validate_integrity(
            _require_mapping(d["integrity"], "$.integrity"),
            artifact_paths=artifact_paths,
            verify_root=verify_root,
        )

    # Finite sweep on full normalized payload
    try:
        assert_finite_or_null(out)
    except NonFiniteJsonError as exc:
        raise PhenomenologyValidationError(str(exc)) from exc
    return out


@dataclass
class PhenomenologyPerturbationRecord:
    """Thin wrapper around a validated dict."""

    data: Dict[str, Any] = field(repr=False)

    @classmethod
    def from_dict(
        cls,
        d: Mapping[str, Any],
        *,
        verify_root: Optional[Path] = None,
    ) -> "PhenomenologyPerturbationRecord":
        return cls(data=validate_record_dict(d, verify_root=verify_root))

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.data)

    @property
    def record_id(self) -> str:
        return str(self.data["record_id"])

    @property
    def parent_run_id(self) -> Optional[str]:
        return self.data.get("parent_run_id")


def dumps_record(
    record: PhenomenologyPerturbationRecord | Mapping[str, Any],
    *,
    verify_root: Optional[Path] = None,
) -> str:
    if isinstance(record, PhenomenologyPerturbationRecord):
        payload = record.to_dict()
    else:
        payload = validate_record_dict(record, verify_root=verify_root)
    try:
        return dumps_strict(payload)
    except NonFiniteJsonError as exc:
        raise PhenomenologyValidationError(str(exc)) from exc


def loads_record(
    text: str,
    *,
    verify_root: Optional[Path] = None,
) -> PhenomenologyPerturbationRecord:
    try:
        payload = loads_strict(text)
    except NonFiniteJsonError as exc:
        raise PhenomenologyValidationError(str(exc)) from exc
    if not isinstance(payload, MutableMapping):
        raise PhenomenologyValidationError("$: expected object after JSON load")
    return PhenomenologyPerturbationRecord.from_dict(payload, verify_root=verify_root)
