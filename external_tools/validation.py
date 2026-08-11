"""Structural validation and shared vocabulary for the external tool
integration registry and adapter contracts.

This module defines "is this record well-formed and does it stay inside
this repository's license/commercial-use/claim-scope policy" -- not
"should this tool actually be integrated next" (that ranking lives in
`external_tools.registry`'s `recommended_next`) and not "does an adapter
for this tool exist" (none do; see docs/external_tool_integration_strategy.md).

Reuses this repository's existing claim/evidence vocabulary and
banned-phrase scanner rather than declaring new copies, mirroring how
`benchmarks.validation` and `reports.validation` reuse
`sciencer_d.btc_icft.report_guardrails` / `transitions.governance` /
`phase_space.coordinate.scan_banned_phrases` instead of a new phrase list
each time. This module adds one small, additive phrase list of its own
(`EXTERNAL_TOOL_EXTRA_BANNED_PHRASES`), the same pattern
`transitions.governance.TRANSITION_EXTRA_BANNED_PHRASES` established --
scraping/reverse-engineering language is specific to this layer and not
covered by the shared base list.
"""
from __future__ import annotations

import re
from typing import Any

from phase_space.coordinate import scan_banned_phrases
from transitions.governance import ALLOWED_CLAIM_SCOPES, ALLOWED_EVIDENCE_LEVELS

# ── shared vocabulary ────────────────────────────────────────────────────

ALLOWED_CATEGORIES: frozenset[str] = frozenset(
    {
        "neurophysiology_core",
        "bids_neuroinformatics",
        "fmri_neuroimaging",
        "dataset_benchmark",
        "topology_tda",
        "graph_network",
        "eeg_preprocessing_qc",
        "bci_ml_baseline",
        "live_acquisition",
        "physiology_sleep",
        "commercial_neurofeedback",
        "clinical_qeeg",
        "hardware_sdk",
        "reference_competitor",
    }
)

ALLOWED_LICENSE_RISK: frozenset[str] = frozenset(
    {"permissive_low", "copyleft_medium", "agpl_high", "proprietary_high", "unknown_high"}
)

# License risk tiers that must never be used as a live code dependency of
# the commercial core path. Deliberately includes copyleft_medium (not just
# agpl_high): a GPL-family dependency imposes the same "cannot ship as a
# closed/commercial dependency" constraint as AGPL for this repository's
# purposes, even though AGPL carries the additional network-use clause.
_NON_DEPENDENCY_LICENSE_RISK: frozenset[str] = frozenset(
    {"copyleft_medium", "agpl_high", "proprietary_high", "unknown_high"}
)

ALLOWED_COMMERCIAL_USE_STATUS: frozenset[str] = frozenset(
    {
        "allowed_with_notice",
        "allowed_optional_dependency",
        "adapter_only_recommended",
        "external_cli_only",
        "reference_only",
        "paid_contract_required",
        "avoid_core",
    }
)

ALLOWED_INTEGRATION_MODES: frozenset[str] = frozenset(
    {
        "dependency",
        "optional_backend",
        "adapter_only",
        "metadata_import",
        "external_cli",
        "paid_api",
        "paid_hardware",
        "reference_only",
        "avoid_core",
    }
)

ALLOWED_PRIORITIES: frozenset[str] = frozenset({"P0", "P1", "P2", "P3", "reference", "avoid"})

ALLOWED_CURRENT_STATUS: frozenset[str] = frozenset(
    {
        "planned",
        "ready_for_adapter",
        "optional_future",
        "reference_only",
        "blocked_pending_license_review",
        "blocked_proprietary",
        "avoid_core",
    }
)

# Priority values a tool is allowed to carry when its integration_mode is
# reference_only or avoid_core (rules 6/7): these modes must never be
# picked up by automatic "what should we build next" ranking.
_REFERENCE_ONLY_ALLOWED_PRIORITIES: frozenset[str] = frozenset({"reference"})
_AVOID_CORE_ALLOWED_PRIORITIES: frozenset[str] = frozenset({"avoid"})

_CLINICAL_COMPETITOR_CATEGORIES: frozenset[str] = frozenset(
    {"clinical_qeeg", "commercial_neurofeedback"}
)
_CLINICAL_COMPETITOR_ALLOWED_MODES: frozenset[str] = frozenset(
    {"reference_only", "paid_api", "paid_hardware", "avoid_core"}
)

ALLOWED_OUTPUT_TARGETS: frozenset[str] = frozenset(
    {
        "DatasetRecordV1",
        "ArtifactRecordV1",
        "TransitionRecordV1",
        "PhaseSpaceCoordinateV1",
        "EvidenceBundleV1",
        "EvidenceReportV1",
        "external_metadata_only",
    }
)

ALLOWED_IMPLEMENTATION_STATUSES: frozenset[str] = frozenset(
    {"planned", "not_implemented", "in_development", "implemented"}
)

# Fixed forbidden-output categories every adapter contract must declare (a
# contract may list more, never fewer) -- mirrors
# `reports.evidence_report._blocked_claims_template`'s fixed-template
# approach: the set is not derived from tool-specific content, it is the
# same non-negotiable floor for every adapter this registry could ever
# describe.
REQUIRED_FORBIDDEN_OUTPUTS: frozenset[str] = frozenset(
    {
        "clinical_claim",
        "diagnostic_claim",
        "treatment_claim",
        "consciousness_biomarker_claim",
        "spiritual_attainment_claim",
        "mechanistic_causal_claim",
    }
)

# A contract's provenance_requirements must include at least this, so an
# adapter cannot silently drop which version of the external tool (and
# which of its parameters) produced a given artifact.
REQUIRED_PROVENANCE_REQUIREMENTS: frozenset[str] = frozenset({"source_tool_version"})

# Encodes "adapter must fail closed if required metadata is absent" (mission
# Phase C) as a required, checkable member of validation_requirements rather
# than an unenforceable prose promise.
REQUIRED_VALIDATION_REQUIREMENTS: frozenset[str] = frozenset(
    {"fail_closed_if_required_metadata_missing"}
)

# Additive to sciencer_d.btc_icft.report_guardrails.BANNED_REPORT_PHRASES +
# transitions.governance.TRANSITION_EXTRA_BANNED_PHRASES (both already
# folded into phase_space.coordinate.scan_banned_phrases's internal list) --
# phrases specific to unsafe *tool-integration* language: recommending
# scraping proprietary dashboards/reports, copying paid software, or
# extracting closed SDK internals (rule 11).
EXTERNAL_TOOL_EXTRA_BANNED_PHRASES: tuple[str, ...] = (
    "scrape proprietary",
    "scrape the dashboard",
    "scrape their dashboard",
    "scrape paid",
    "copy proprietary code",
    "copy the proprietary",
    "clone paid software",
    "clone their paid",
    "extract private sdk",
    "extract the private sdk",
    "reverse engineer proprietary",
    "reverse-engineer proprietary",
    "bypass their license",
    "bypass license restrictions",
    "circumvent license",
)


class ExternalToolValidationError(ValueError):
    """Raised when a tool record or adapter contract fails structural validation."""


def _scan_extra_phrases(value: Any, path: str, errors: list[str]) -> None:
    """Recursively flag this layer's addendum phrases only (see
    EXTERNAL_TOOL_EXTRA_BANNED_PHRASES). Kept separate from the shared-list
    scan below so the shared scanner's own recursion runs exactly once per
    top-level field instead of once per nesting level."""
    if isinstance(value, str):
        low = value.lower()
        for phrase in EXTERNAL_TOOL_EXTRA_BANNED_PHRASES:
            if phrase in low:
                errors.append(f"{path}: banned phrase detected: '{phrase}'")
    elif isinstance(value, dict):
        for key, sub in value.items():
            _scan_extra_phrases(sub, f"{path}.{key}", errors)
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _scan_extra_phrases(item, f"{path}[{idx}]", errors)


def _scan_banned_phrases(value: Any, path: str, errors: list[str]) -> None:
    """One full recursive pass combining the shared base list with this
    layer's addendum -- each list called exactly once per top-level field."""
    scan_banned_phrases(value, path, errors)
    _scan_extra_phrases(value, path, errors)


def slugify_tool_id(name: str) -> str:
    """Deterministic slug used as `tool_id` -- lowercase, hyphen-separated."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug


# ── ExternalToolRecordV1 validation ─────────────────────────────────────


def validate_tool_record(record: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    name = getattr(record, "name", None)
    if not name:
        errors.append("name is required")

    tool_id = getattr(record, "tool_id", None)
    if not tool_id:
        errors.append("tool_id is required")
    elif name and tool_id != slugify_tool_id(name):
        # Rule 3: tool_id must be deterministic / validated stable.
        errors.append(
            f"tool_id '{tool_id}' is not the deterministic slug of name '{name}' "
            f"(expected '{slugify_tool_id(name)}') (rule 3)"
        )

    category = getattr(record, "category", None)
    if category not in ALLOWED_CATEGORIES:
        errors.append(f"category '{category}' must be one of {sorted(ALLOWED_CATEGORIES)}")

    license_risk = getattr(record, "license_risk", None)
    if license_risk not in ALLOWED_LICENSE_RISK:
        errors.append(f"license_risk '{license_risk}' must be one of {sorted(ALLOWED_LICENSE_RISK)}")

    commercial_use_status = getattr(record, "commercial_use_status", None)
    if commercial_use_status not in ALLOWED_COMMERCIAL_USE_STATUS:
        errors.append(
            f"commercial_use_status '{commercial_use_status}' must be one of "
            f"{sorted(ALLOWED_COMMERCIAL_USE_STATUS)}"
        )

    integration_mode = getattr(record, "integration_mode", None)
    if integration_mode not in ALLOWED_INTEGRATION_MODES:
        errors.append(
            f"integration_mode '{integration_mode}' must be one of {sorted(ALLOWED_INTEGRATION_MODES)}"
        )

    priority = getattr(record, "priority", None)
    if priority not in ALLOWED_PRIORITIES:
        errors.append(f"priority '{priority}' must be one of {sorted(ALLOWED_PRIORITIES)}")

    current_status = getattr(record, "current_status", None)
    if current_status not in ALLOWED_CURRENT_STATUS:
        errors.append(f"current_status '{current_status}' must be one of {sorted(ALLOWED_CURRENT_STATUS)}")

    # Rule 1: non-empty risks and limitations.
    risks = getattr(record, "risks", None) or []
    if not risks:
        errors.append("risks must be a non-empty list (rule 1)")
    limitations = getattr(record, "limitations", None) or []
    if not limitations:
        errors.append("limitations must be a non-empty list (rule 1)")

    # Rule 2: non-empty provenance.
    if not getattr(record, "provenance", None):
        errors.append("provenance is required (rule 2)")

    license_value = getattr(record, "license", None)
    metadata = getattr(record, "metadata", None) or {}

    # Rule 12: unknown license must be high risk and not dependency.
    if not license_value or str(license_value).strip().lower() == "unknown":
        if license_risk != "unknown_high":
            errors.append("license 'unknown' requires license_risk='unknown_high' (rule 12)")
        if integration_mode == "dependency":
            errors.append("license 'unknown' cannot use integration_mode='dependency' (rule 12)")
        if not metadata.get("review_needed"):
            errors.append(
                "license 'unknown' requires metadata.review_needed=true (rule 12)"
            )

    # Rule 4: GPL/AGPL/proprietary/unknown license risk cannot be a live
    # dependency of the commercial core. Fail closed -- no per-record
    # override is honored by this validator (see module docstring / repo
    # docs for the rationale).
    if license_risk in _NON_DEPENDENCY_LICENSE_RISK and integration_mode == "dependency":
        errors.append(
            f"license_risk '{license_risk}' cannot use integration_mode='dependency' "
            "for the commercial core (rule 4, fail closed)"
        )

    # Rule 5: paid/proprietary tools cannot be dependency or optional_backend.
    if (
        commercial_use_status == "paid_contract_required" or license_risk == "proprietary_high"
    ) and integration_mode in {"dependency", "optional_backend"}:
        errors.append(
            "paid/proprietary tools cannot use integration_mode "
            "'dependency' or 'optional_backend' (rule 5)"
        )

    # Rule 6: reference_only tools cannot be auto-selected for implementation.
    if integration_mode == "reference_only" and priority not in _REFERENCE_ONLY_ALLOWED_PRIORITIES:
        errors.append(
            f"integration_mode='reference_only' requires priority in "
            f"{sorted(_REFERENCE_ONLY_ALLOWED_PRIORITIES)} (rule 6)"
        )

    # Rule 7: avoid_core tools cannot be selected for implementation.
    if integration_mode == "avoid_core" and priority not in _AVOID_CORE_ALLOWED_PRIORITIES:
        errors.append(
            f"integration_mode='avoid_core' requires priority in "
            f"{sorted(_AVOID_CORE_ALLOWED_PRIORITIES)} (rule 7)"
        )

    # Rule 8: P0 tools must be free/permissive or adapter-only/reference-safe.
    if priority == "P0" and not (
        license_risk == "permissive_low" or integration_mode in {"adapter_only", "metadata_import"}
    ):
        errors.append(
            "priority='P0' requires license_risk='permissive_low' or "
            "integration_mode in ('adapter_only', 'metadata_import') (rule 8)"
        )

    # Rule 9: clinical_qeeg / commercial_neurofeedback competitors default
    # to reference_only unless a legitimate public API/hardware SDK path
    # is used instead.
    if category in _CLINICAL_COMPETITOR_CATEGORIES and integration_mode not in _CLINICAL_COMPETITOR_ALLOWED_MODES:
        errors.append(
            f"category '{category}' requires integration_mode in "
            f"{sorted(_CLINICAL_COMPETITOR_ALLOWED_MODES)} (rule 9)"
        )

    # Rules 10/11: banned overclaim + scraping/reverse-engineering language.
    for field_name in ("name", "planned_adapter", "provenance"):
        _scan_banned_phrases(getattr(record, field_name, None) or "", field_name, errors)
    for field_name in ("risks", "limitations", "allowed_uses", "forbidden_uses"):
        _scan_banned_phrases(getattr(record, field_name, None) or [], field_name, errors)
    _scan_banned_phrases(metadata, "metadata", errors)

    return errors


# ── AdapterContractV1 validation ────────────────────────────────────────


def validate_adapter_contract(contract: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    if not getattr(contract, "adapter_id", None):
        errors.append("adapter_id is required")
    if not getattr(contract, "tool_id", None):
        errors.append("tool_id is required")
    if not getattr(contract, "adapter_name", None):
        errors.append("adapter_name is required")

    integration_mode = getattr(contract, "integration_mode", None)
    if integration_mode not in ALLOWED_INTEGRATION_MODES:
        errors.append(
            f"integration_mode '{integration_mode}' must be one of {sorted(ALLOWED_INTEGRATION_MODES)}"
        )

    output_targets = getattr(contract, "output_targets", None) or []
    if not output_targets:
        errors.append("output_targets must be a non-empty list")
    for target in output_targets:
        if target not in ALLOWED_OUTPUT_TARGETS:
            errors.append(f"output_targets contains unknown target '{target}' (must be one of {sorted(ALLOWED_OUTPUT_TARGETS)})")

    # "Adapter must declare feature namespaces."
    feature_namespaces = getattr(contract, "feature_namespaces", None) or []
    if not feature_namespaces:
        errors.append("feature_namespaces must be a non-empty list")

    # "Adapter must declare provenance requirements" + must preserve
    # source-tool version provenance when applicable.
    provenance_requirements = getattr(contract, "provenance_requirements", None) or []
    if not provenance_requirements:
        errors.append("provenance_requirements must be a non-empty list")
    missing_provenance = REQUIRED_PROVENANCE_REQUIREMENTS - set(provenance_requirements)
    if missing_provenance:
        errors.append(f"provenance_requirements is missing required entries: {sorted(missing_provenance)}")

    validation_requirements = getattr(contract, "validation_requirements", None) or []
    if not validation_requirements:
        errors.append("validation_requirements must be a non-empty list")
    missing_validation = REQUIRED_VALIDATION_REQUIREMENTS - set(validation_requirements)
    if missing_validation:
        errors.append(f"validation_requirements is missing required entries: {sorted(missing_validation)}")

    # Adapter must not output clinical/diagnostic/treatment/biomarker/
    # consciousness-detection/spiritual-attainment/mechanistic-proof claims.
    forbidden_outputs = getattr(contract, "forbidden_outputs", None) or []
    if not forbidden_outputs:
        errors.append("forbidden_outputs must be a non-empty list")
    missing_forbidden = REQUIRED_FORBIDDEN_OUTPUTS - set(forbidden_outputs)
    if missing_forbidden:
        errors.append(f"forbidden_outputs is missing required entries: {sorted(missing_forbidden)}")

    # Claim/evidence ceilings reuse the shared, already-safe vocabulary --
    # BLOCKED_CLAIM_SCOPES (clinical, diagnostic, ...) is a disjoint set and
    # can never appear in ALLOWED_CLAIM_SCOPES, so this check alone already
    # enforces "adapter cannot exceed exploratory_metric claim scope by
    # default" together with the dataclass's own exploratory_metric default.
    claim_scope_ceiling = getattr(contract, "allowed_claim_scope_ceiling", None)
    if claim_scope_ceiling not in ALLOWED_CLAIM_SCOPES:
        errors.append(
            f"allowed_claim_scope_ceiling '{claim_scope_ceiling}' must be one of {sorted(ALLOWED_CLAIM_SCOPES)}"
        )
    evidence_level_ceiling = getattr(contract, "evidence_level_ceiling", None)
    if evidence_level_ceiling not in ALLOWED_EVIDENCE_LEVELS:
        errors.append(
            f"evidence_level_ceiling '{evidence_level_ceiling}' must be one of {sorted(ALLOWED_EVIDENCE_LEVELS)}"
        )

    implementation_status = getattr(contract, "implementation_status", None)
    if implementation_status not in ALLOWED_IMPLEMENTATION_STATUSES:
        errors.append(
            f"implementation_status '{implementation_status}' must be one of "
            f"{sorted(ALLOWED_IMPLEMENTATION_STATUSES)}"
        )
    # This milestone implements no adapters -- "adapter cannot claim
    # validation readiness by default" and no contract seeded here may
    # imply a working adapter exists.
    if implementation_status == "implemented" and not (getattr(contract, "metadata", None) or {}).get(
        "implementation_verified"
    ):
        errors.append(
            "implementation_status='implemented' requires metadata.implementation_verified=true"
        )

    limitations = getattr(contract, "limitations", None) or []
    if not limitations:
        errors.append("limitations must be a non-empty list")

    metadata = getattr(contract, "metadata", None) or {}
    for field_name in ("adapter_name",):
        _scan_banned_phrases(getattr(contract, field_name, None) or "", field_name, errors)
    for field_name in ("limitations", "forbidden_outputs", "provenance_requirements", "validation_requirements"):
        _scan_banned_phrases(getattr(contract, field_name, None) or [], field_name, errors)
    _scan_banned_phrases(metadata, "metadata", errors)

    return errors
