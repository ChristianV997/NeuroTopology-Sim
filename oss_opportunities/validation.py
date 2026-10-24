"""Structural validation and shared vocabulary for
`OpenSourceRepositoryCandidateV1`/`RepositoryLicenseReviewV1`/
`OpenSourceIntegrationOpportunityV1`/`OpenSourceLeverageBatchV1`/
`OpenSourceIntegrationPlanV1`.

Reuses this repository's existing banned-phrase scanner
(`phase_space.coordinate.scan_banned_phrases`) plus
`external_tools.validation.EXTERNAL_TOOL_EXTRA_BANNED_PHRASES`
(scraping/reverse-engineering/proprietary-copy overclaim phrases already
vetted there -- this layer's own concern, code-copy-without-review
language, is additive on top) and `dataset_acquisition.store.
ALLOWED_TARGET_ROOT_PREFIXES` for output-root safety, mirroring every
other validation module in this repository family (see
`dataset_opportunities.validation` for the closest structural precedent).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date
from typing import Any
from urllib.parse import urlsplit

from dataset_acquisition.store import ALLOWED_TARGET_ROOT_PREFIXES
from external_tools.validation import EXTERNAL_TOOL_EXTRA_BANNED_PHRASES
from phase_space.coordinate import scan_banned_phrases
from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES
from transitions.governance import TRANSITION_EXTRA_BANNED_PHRASES

# ── OpenSourceRepositoryCandidateV1 vocabulary ──────────────────────────

ALLOWED_SOURCE: frozenset[str] = frozenset(
    {
        "trendshift_daily",
        "trendshift_weekly",
        "trendshift_monthly",
        "trendshift_yearly",
        "trendshift_signal",
        "star_history_starmap",
        "github_manual_seed",
        "github_metadata",
        "local_fixture",
    }
)


def candidate_observation_id(
    *, repo_full_name: str, source: str, source_timeframe: str, source_snapshot_date: str
) -> str:
    """Return the stable identifier for one source/snapshot observation."""
    basis = {
        "repo_full_name": repo_full_name,
        "source": source,
        "source_timeframe": source_timeframe,
        "source_snapshot_date": source_snapshot_date,
    }
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

# ── RepositoryLicenseReviewV1 vocabulary ────────────────────────────────

ALLOWED_LICENSE_RISK: frozenset[str] = frozenset(
    {
        "permissive_low",
        "weak_copyleft_medium",
        "strong_copyleft_high",
        "source_available_or_fair_code_high",
        "proprietary_or_unknown_high",
        "missing_high",
    }
)

ALLOWED_LICENSE_REVIEW_STATUS: frozenset[str] = frozenset(
    {"heuristic_unreviewed", "human_reviewed"}
)

ALLOWED_COMMERCIAL_CORE_POLICY: frozenset[str] = frozenset(
    {
        "allowed_with_attribution",
        "adapter_only",
        "external_process_only",
        "docs_reference_only",
        "blocked_pending_review",
        "blocked",
    }
)

# Only a permissive_low license may ever carry a code-copy-permitting
# commercial_core_policy (rule 8: GPL/AGPL/fair-code/proprietary/unknown
# licenses cannot be commercial-core copy candidates). Fail closed -- no
# per-record override, mirroring external_tools.validation's rule 4.
_COMMERCIAL_CORE_COPY_ALLOWED_LICENSE_RISK: frozenset[str] = frozenset({"permissive_low"})
_COMMERCIAL_CORE_COPY_POLICIES: frozenset[str] = frozenset({"allowed_with_attribution"})

LICENSE_POLICY_VERSION: str = "1"

# ── OpenSourceIntegrationOpportunityV1 vocabulary ───────────────────────

ALLOWED_LEVERAGE_CATEGORY: frozenset[str] = frozenset(
    {
        "document_ingestion",
        "web_literature_acquisition",
        "workflow_orchestration",
        "agent_harness",
        "code_graph_memory",
        "research_memory",
        "report_visualization",
        "frontend_stack",
        "backend_api_stack",
        "database_data_stack",
        "infra_observability_stack",
        "dataset_discovery",
        "scientific_computing",
        "security_compliance",
        "reject_or_defer",
    }
)

ALLOWED_RECOMMENDED_ACTION: frozenset[str] = frozenset(
    {
        "integrate_as_optional_adapter",
        "integrate_as_external_tool_record",
        "emulate_architecture_pattern",
        "create_docs_reference",
        "create_future_task",
        "license_review_required",
        "security_review_required",
        "defer",
        "reject",
    }
)

# Any opportunity's blocked_actions must be a superset of this floor --
# things this scout can never authorize regardless of how well-scored a
# repository is (mission's required blocked_actions list, rule 6).
REQUIRED_BLOCKED_ACTIONS: frozenset[str] = frozenset(
    {
        "copy_code_without_license_review",
        "auto_install_dependency",
        "execute_untrusted_code",
        "commercial_core_copy_without_review",
        "credential_required_execution",
        "automatic_outreach",
        "automatic_marketing_claim",
    }
)

SCORING_VERSION: str = "1"
PLANNER_VERSION: str = "1"
SCHEMA_VERSION: str = "1"

# Version 1 score rows are a closed heuristic vector. Allowing an arbitrary
# extra component, an omitted component, or a non-finite value would let a
# deserialized batch invent its own ranking while still satisfying a sum
# check.
EXPECTED_SCORE_COMPONENTS: frozenset[str] = frozenset(
    {
        "direct_product_leverage",
        "awareness_studio_leverage",
        "report_pipeline_leverage",
        "document_ingestion_leverage",
        "literature_acquisition_leverage",
        "code_graph_memory_leverage",
        "workflow_orchestration_leverage",
        "frontend_saas_leverage",
        "infra_observability_leverage",
        "adapter_surface_clarity",
        "maintenance_signal",
        "documentation_quality_signal",
        "license_safety",
        "dependency_weight_penalty",
        "security_risk_penalty",
        "duplication_penalty",
        "commercial_core_penalty",
    }
)

FORBIDDEN_CLAIM_FIELDS: frozenset[str] = frozenset(
    {"claim_scope", "evidence_level", "evidence_ready", "scientific_pass", "scientific_status"}
)

# ── shared banned-phrase chain ──────────────────────────────────────────

OSS_OPPORTUNITY_EXTRA_BANNED_PHRASES: tuple[str, ...] = EXTERNAL_TOOL_EXTRA_BANNED_PHRASES + (
    "copied their code",
    "copied the code directly",
    "reimplemented by copying",
    "integration is complete",
    "already integrated into",
    "fully integrated",
)

_ALL_OSS_OPPORTUNITY_BANNED_PHRASES: tuple[str, ...] = (
    BANNED_REPORT_PHRASES + TRANSITION_EXTRA_BANNED_PHRASES + OSS_OPPORTUNITY_EXTRA_BANNED_PHRASES
)


class OssOpportunityValidationError(ValueError):
    """Raised when an oss_opportunities object fails structural validation."""


class OssOpportunityStoreError(ValueError):
    """Raised for oss_opportunities store-level problems (unsafe output_root, missing input, ...)."""


def reject_forbidden_claim_fields(payload: Any, context: str) -> None:
    if not isinstance(payload, dict):
        return
    forbidden = sorted(
        key for key in payload
        if isinstance(key, str) and key.casefold() in FORBIDDEN_CLAIM_FIELDS
    )
    if forbidden:
        raise OssOpportunityValidationError(
            f"{context} contains unsupported field(s): {forbidden}"
        )


def strict_json_loads(text: str) -> Any:
    """Parse JSON evidence without last-key-wins or non-standard NaN values."""
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise OssOpportunityValidationError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise OssOpportunityValidationError(f"non-finite JSON constant {value!r} is invalid")

    try:
        return json.loads(text, object_pairs_hook=reject_duplicate_keys, parse_constant=reject_constant)
    except json.JSONDecodeError as exc:
        raise OssOpportunityValidationError(f"invalid JSON document: {exc.msg}") from exc


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _check_supported_version(value: Any, expected: str, field_name: str, errors: list[str]) -> None:
    if not isinstance(value, str) or value != expected:
        errors.append(f"{field_name} must be the supported version {expected!r}")


def scan_text_for_banned_phrases(text: str) -> list[str]:
    low = text.lower()
    return [phrase for phrase in _ALL_OSS_OPPORTUNITY_BANNED_PHRASES if phrase in low]


def _scan_banned_phrases(value: Any, path: str, errors: list[str]) -> None:
    scan_banned_phrases(value, path, errors)
    if isinstance(value, str):
        low = value.lower()
        for phrase in OSS_OPPORTUNITY_EXTRA_BANNED_PHRASES:
            if phrase in low:
                errors.append(f"{path}: banned phrase detected: '{phrase}'")
    elif isinstance(value, dict):
        for key, sub in value.items():
            _scan_banned_phrases(sub, f"{path}.{key}", errors)
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _scan_banned_phrases(item, f"{path}[{idx}]", errors)


def _check_string_keys(value: Any, path: str, errors: list[str]) -> None:
    """Check recursively that metadata is JSON-compatible and finite."""
    if isinstance(value, dict):
        for key, sub in value.items():
            if not isinstance(key, str):
                errors.append(f"{path}: mapping key {key!r} must be a string")
            elif key.casefold() in FORBIDDEN_CLAIM_FIELDS:
                errors.append(f"{path}.{key}: unsupported field; OSS adoption metadata cannot assert scientific/evidence status")
            _check_string_keys(sub, f"{path}.{key}", errors)
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _check_string_keys(item, f"{path}[{idx}]", errors)
    elif isinstance(value, float) and not math.isfinite(value):
        errors.append(f"{path}: non-finite numbers are not valid JSON evidence")
    elif value is not None and not isinstance(value, (str, bool, int, float)):
        errors.append(f"{path}: value of type {type(value).__name__} is not JSON-compatible")


def validate_repo_relative_root(value: Any, field_name: str) -> list[str]:
    errors: list[str] = []
    if not value or not isinstance(value, str):
        errors.append(f"{field_name} is required (non-empty string)")
        return errors
    raw = value.strip()
    if raw.startswith("/") or raw.startswith("~") or ".." in raw.split("/"):
        errors.append(f"{field_name} must be a safe relative repository path, got {value!r}")
        return errors
    if not any(raw == prefix.rstrip("/") or raw.startswith(prefix) for prefix in ALLOWED_TARGET_ROOT_PREFIXES):
        errors.append(f"{field_name} must be under one of {ALLOWED_TARGET_ROOT_PREFIXES}, got {value!r}")
    return errors


# ── OpenSourceRepositoryCandidateV1 ──────────────────────────────────────


# GitHub owner/repo form. Anything else (a bare name, extra path segments)
# cannot identify one repository unambiguously.
_REPO_FULL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _is_iso_calendar_date(value: str) -> bool:
    if _ISO_DATE.fullmatch(value) is None:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_http_url(value: str) -> bool:
    parts = urlsplit(value.strip())
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def validate_repository_candidate(record: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []
    _check_supported_version(getattr(record, "schema_version", None), SCHEMA_VERSION, "schema_version", errors)

    candidate_id = getattr(record, "candidate_id", None)
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        errors.append("candidate_id is required")

    repo_full_name = getattr(record, "repo_full_name", None)
    if not isinstance(repo_full_name, str) or not repo_full_name.strip():
        errors.append("repo_full_name is required")

    limitations = getattr(record, "limitations", None)
    if not isinstance(limitations, list) or not limitations:
        errors.append("limitations must be a non-empty list (rule 1)")
    elif any(not isinstance(item, str) or not item.strip() for item in limitations):
        errors.append("limitations must contain only non-empty strings")

    provenance = getattr(record, "provenance", None)
    if not isinstance(provenance, str) or not provenance.strip():
        errors.append("provenance is required (rule 2)")

    source = getattr(record, "source", None)
    if not isinstance(source, str):
        errors.append("source must be a string")
    elif source not in ALLOWED_SOURCE:
        errors.append(f"source must be one of {sorted(ALLOWED_SOURCE)} -- source must be explicit (rule 3)")

    metadata = getattr(record, "metadata", None)
    if not isinstance(metadata, dict):
        errors.append("metadata must be a mapping")
        metadata = {}

    for field_name in (
        "name", "description", "license_spdx", "license_name", "license_url",
        "source_timeframe", "source_snapshot_date", "primary_language",
        "latest_activity_status", "homepage_url",
    ):
        value = getattr(record, field_name, None)
        optional = field_name in ("license_url", "license_spdx", "license_name")
        if value is None and optional:
            continue
        if not isinstance(value, str):
            errors.append(f"{field_name} must be a string")

    for field_name in ("topics", "observed_categories"):
        value = getattr(record, field_name, None)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            errors.append(f"{field_name} must be a list of strings")

    for field_name in ("source_rank", "stars", "star_gain", "fork_count"):
        value = getattr(record, field_name, None)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            errors.append(f"{field_name} must be a non-negative integer or None")
        elif value is not None and value < 0:
            errors.append(f"{field_name} must be a non-negative integer or None")

    if "requires_credentials" in metadata and not isinstance(metadata["requires_credentials"], bool):
        errors.append("metadata.requires_credentials must be a boolean")
    adapter_docs_url = metadata.get("adapter_docs_url")
    if adapter_docs_url is not None and not isinstance(adapter_docs_url, str):
        errors.append("metadata.adapter_docs_url must be a string")
    elif adapter_docs_url and not _is_http_url(adapter_docs_url):
        errors.append("metadata.adapter_docs_url must be an http(s) URL when present")
    homepage_url = getattr(record, "homepage_url", None)
    if isinstance(homepage_url, str) and homepage_url.strip() and not _is_http_url(homepage_url):
        errors.append("homepage_url must be an http(s) URL when present")
    snapshot_date = getattr(record, "source_snapshot_date", None)
    if isinstance(snapshot_date, str) and not _is_iso_calendar_date(snapshot_date):
        errors.append("source_snapshot_date must be an ISO calendar date (YYYY-MM-DD)")

    # Rule 13: Trendshift Signal raw payload must never be embedded for
    # redistribution.
    if source == "trendshift_signal":
        if metadata.get("redistributes_raw_signal_data"):
            errors.append(
                "source='trendshift_signal' must not set metadata.redistributes_raw_signal_data=true "
                "-- raw Trendshift Signal API data must not be redistributed (rule 13)"
            )
        for raw_key in ("raw_response", "raw_payload", "raw_signal_api_response"):
            if raw_key in metadata:
                errors.append(
                    f"source='trendshift_signal' must not embed metadata.{raw_key} "
                    "-- raw Trendshift Signal API data must not be redistributed (rule 13)"
                )

    if hasattr(record, "claim_scope") or hasattr(record, "evidence_level") or hasattr(record, "evidence_ready"):
        errors.append("OpenSourceRepositoryCandidateV1 must not carry its own claim_scope/evidence_level/evidence_ready field")
    if any(hasattr(record, key) for key in FORBIDDEN_CLAIM_FIELDS):
        errors.append("OpenSourceRepositoryCandidateV1 must not carry scientific/evidence promotion fields")

    _check_string_keys(metadata, "metadata", errors)

    for field_name in ("name", "description", "provenance"):
        value = getattr(record, field_name, None)
        if isinstance(value, str):
            _scan_banned_phrases(value, field_name, errors)
    for field_name in ("limitations", "observed_categories", "topics"):
        value = getattr(record, field_name, None)
        if isinstance(value, list):
            _scan_banned_phrases(value, field_name, errors)
    _scan_banned_phrases(metadata, "metadata", errors)

    # Ambiguous source identity: one name must mean exactly one repository.
    # Each check runs only when the field is present; a missing
    # repo_full_name is already reported above. A non-string identity field
    # is reported as an error, never raised: this function does not raise.
    repo_full_name = getattr(record, "repo_full_name", None)
    owner = getattr(record, "owner", None)
    repo_url = getattr(record, "repo_url", None)
    owner = "" if owner is None else owner
    repo_url = "" if repo_url is None else repo_url
    identity_fields = (("repo_full_name", repo_full_name), ("owner", owner), ("repo_url", repo_url))
    non_string = [name for name, value in identity_fields if not isinstance(value, str)]
    if non_string:
        errors.extend(f"{name} must be a string" for name in non_string)
    else:
        if repo_full_name and not _REPO_FULL_NAME_RE.match(repo_full_name):
            errors.append("repo_full_name must be 'owner/name' (ambiguous source identity)")
        if owner and "/" in repo_full_name and owner.lower() != repo_full_name.split("/", 1)[0].lower():
            errors.append("owner does not match repo_full_name (ambiguous source identity)")
        repo_url = repo_url.strip().rstrip("/")
        if repo_url and repo_full_name:
            expected_url = f"https://github.com/{repo_full_name}"
            if repo_url.lower() != expected_url.lower():
                errors.append(
                    "repo_url does not point to repo_full_name (ambiguous source identity)"
                )

    source_timeframe = getattr(record, "source_timeframe", None)
    source_snapshot_date = getattr(record, "source_snapshot_date", None)
    if all(isinstance(value, str) for value in (repo_full_name, source, source_timeframe, source_snapshot_date)):
        expected_id = candidate_observation_id(
            repo_full_name=repo_full_name,
            source=source,
            source_timeframe=source_timeframe,
            source_snapshot_date=source_snapshot_date,
        )
        if isinstance(candidate_id, str) and candidate_id != expected_id:
            errors.append("candidate_id does not match observation identity")

    return errors


# ── RepositoryLicenseReviewV1 ─────────────────────────────────────────────


def validate_license_review(record: Any) -> list[str]:
    errors: list[str] = []
    _check_supported_version(getattr(record, "schema_version", None), SCHEMA_VERSION, "schema_version", errors)

    license_review_id = getattr(record, "license_review_id", None)
    if not isinstance(license_review_id, str) or not license_review_id.strip():
        errors.append("license_review_id is required")
    repo_full_name = getattr(record, "repo_full_name", None)
    if not isinstance(repo_full_name, str) or not repo_full_name.strip():
        errors.append("repo_full_name is required")
    policy_version = getattr(record, "license_policy_version", None)
    _check_supported_version(policy_version, LICENSE_POLICY_VERSION, "license_policy_version", errors)

    limitations = getattr(record, "limitations", None)
    if not isinstance(limitations, list) or not limitations:
        errors.append("limitations must be a non-empty list (rule 1)")
    elif any(not isinstance(item, str) or not item.strip() for item in limitations):
        errors.append("limitations must contain only non-empty strings")
    provenance = getattr(record, "provenance", None)
    if not isinstance(provenance, str) or not provenance.strip():
        errors.append("provenance is required (rule 2)")

    # Rule 4: license risk must be explicit; unknown/missing licenses
    # become high risk.
    license_risk = getattr(record, "license_risk", None)
    if not isinstance(license_risk, str) or license_risk not in ALLOWED_LICENSE_RISK:
        errors.append(f"license_risk must be one of {sorted(ALLOWED_LICENSE_RISK)} (rule 4)")

    license_spdx = getattr(record, "license_spdx", None)
    if license_spdx is not None and not isinstance(license_spdx, str):
        errors.append("license_spdx must be a string or None")
    license_name = getattr(record, "license_name", None)
    if license_name is not None and not isinstance(license_name, str):
        errors.append("license_name must be a string or None")
    if (not license_spdx or (isinstance(license_spdx, str) and license_spdx.strip().lower() in ("unknown", ""))) and license_risk not in (
        "missing_high",
        "proprietary_or_unknown_high",
    ):
        errors.append(
            "license_spdx is missing/unknown -- license_risk must be 'missing_high' or "
            "'proprietary_or_unknown_high' (rule 4)"
        )

    commercial_core_policy = getattr(record, "commercial_core_policy", None)
    if not isinstance(commercial_core_policy, str) or commercial_core_policy not in ALLOWED_COMMERCIAL_CORE_POLICY:
        errors.append(
            "commercial_core_policy must be one of "
            f"{sorted(ALLOWED_COMMERCIAL_CORE_POLICY)}"
        )

    # Rule 8: GPL/AGPL/fair-code/proprietary/unknown licenses cannot be
    # commercial-core copy candidates. Fail closed -- only permissive_low
    # may ever carry a copy-permitting policy.
    if (
        isinstance(commercial_core_policy, str)
        and commercial_core_policy in _COMMERCIAL_CORE_COPY_POLICIES
        and isinstance(license_risk, str)
        and license_risk not in _COMMERCIAL_CORE_COPY_ALLOWED_LICENSE_RISK
    ):
        errors.append(
            "license risk cannot use the selected copy-permitting commercial policy "
            "(rule 8, fail closed)"
        )

    allowed_use_modes = getattr(record, "allowed_use_modes", None)
    if not isinstance(allowed_use_modes, list) or not allowed_use_modes:
        errors.append("allowed_use_modes must be a non-empty list")
    elif any(not isinstance(item, str) or not item.strip() for item in allowed_use_modes):
        errors.append("allowed_use_modes must contain only non-empty strings")
    blocked_use_modes = getattr(record, "blocked_use_modes", None)
    if not isinstance(blocked_use_modes, list) or not blocked_use_modes:
        errors.append("blocked_use_modes must be a non-empty list")
    elif any(not isinstance(item, str) or not item.strip() for item in blocked_use_modes):
        errors.append("blocked_use_modes must contain only non-empty strings")

    review_status = getattr(record, "review_status", None)
    if not isinstance(review_status, str) or review_status not in ALLOWED_LICENSE_REVIEW_STATUS:
        errors.append(f"review_status must be one of {sorted(ALLOWED_LICENSE_REVIEW_STATUS)}")

    attribution_required = getattr(record, "attribution_required", None)
    if not isinstance(attribution_required, bool):
        errors.append("attribution_required must be a boolean")

    metadata = getattr(record, "metadata", None)
    if not isinstance(metadata, dict):
        errors.append("metadata must be a mapping")
        metadata = {}

    if review_status == "human_reviewed":
        reviewer = metadata.get("reviewer")
        if not isinstance(reviewer, str) or not reviewer.strip():
            errors.append("review_status='human_reviewed' requires metadata.reviewer (a named reviewer)")

    # The only observation status this pipeline emits is "conflict". Any
    # other present value (wrong case, bool, list, None, ...) is malformed
    # evidence and must not silently fall through as "no conflict".
    if "license_observation_status" in metadata and metadata["license_observation_status"] != "conflict":
        errors.append("metadata.license_observation_status, when present, must be exactly 'conflict'")
    _check_string_keys(metadata, "metadata", errors)

    if (
        isinstance(license_review_id, str)
        and license_review_id
        and isinstance(repo_full_name, str)
        and (license_spdx is None or isinstance(license_spdx, str))
    ):
        # Import lazily: license_review imports these validators, so a
        # module-level import would create a cycle.
        from oss_opportunities.license_review import compute_license_review_id

        expected_review_id = compute_license_review_id(
            repo_full_name=repo_full_name, license_spdx=license_spdx,
            license_policy_version=getattr(record, "license_policy_version", LICENSE_POLICY_VERSION),
        )
        if license_review_id != expected_review_id:
            errors.append("license_review_id does not match repository/license/policy-version evidence")

    for field_name in ("license_name", "provenance", "commercial_core_policy"):
        value = getattr(record, field_name, None)
        if isinstance(value, str):
            _scan_banned_phrases(value, field_name, errors)
    for field_name in ("limitations", "allowed_use_modes", "blocked_use_modes"):
        value = getattr(record, field_name, None)
        if isinstance(value, list):
            _scan_banned_phrases(value, field_name, errors)
    _scan_banned_phrases(metadata, "metadata", errors)

    return errors


# ── OpenSourceIntegrationOpportunityV1 ────────────────────────────────────


def validate_integration_opportunity(record: Any) -> list[str]:
    errors: list[str] = []
    _check_supported_version(getattr(record, "schema_version", None), SCHEMA_VERSION, "schema_version", errors)

    opportunity_id = getattr(record, "opportunity_id", None)
    repo_full_name = getattr(record, "repo_full_name", None)
    candidate_id = getattr(record, "candidate_id", None)
    license_review_id = getattr(record, "license_review_id", None)
    if not isinstance(opportunity_id, str) or not opportunity_id.strip():
        errors.append("opportunity_id is required")
    if not isinstance(repo_full_name, str) or not repo_full_name.strip():
        errors.append("repo_full_name is required")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        errors.append("candidate_id is required -- opportunity source must be explicit (rule 3)")
    if not isinstance(license_review_id, str) or not license_review_id.strip():
        errors.append("license_review_id is required -- opportunity source must be explicit (rule 3)")
    scoring_version = getattr(record, "scoring_version", None)
    _check_supported_version(scoring_version, SCORING_VERSION, "scoring_version", errors)
    if (
        isinstance(opportunity_id, str) and opportunity_id
        and isinstance(repo_full_name, str) and repo_full_name
        and isinstance(candidate_id, str) and candidate_id
        and isinstance(scoring_version, str)
    ):
        if opportunity_id != record.recompute_id():
            errors.append("opportunity_id does not match repository/candidate/scoring version")

    limitations = getattr(record, "limitations", None)
    if not isinstance(limitations, list) or not limitations:
        errors.append("limitations must be a non-empty list (rule 1)")
    elif any(not isinstance(item, str) or not item.strip() for item in limitations):
        errors.append("limitations must contain only non-empty strings")
    provenance = getattr(record, "provenance", None)
    if not isinstance(provenance, str) or not provenance.strip():
        errors.append("provenance is required (rule 2)")
    for field_name in ("integration_surface", "emulation_surface"):
        values = getattr(record, field_name, None)
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
            errors.append(f"{field_name} must be a list of strings")

    leverage_category = getattr(record, "leverage_category", None)
    if not isinstance(leverage_category, str) or leverage_category not in ALLOWED_LEVERAGE_CATEGORY:
        errors.append(f"leverage_category '{leverage_category}' must be one of {sorted(ALLOWED_LEVERAGE_CATEGORY)}")

    recommended_action = getattr(record, "recommended_action", None)
    if not isinstance(recommended_action, str) or recommended_action not in ALLOWED_RECOMMENDED_ACTION:
        errors.append(f"recommended_action '{recommended_action}' must be one of {sorted(ALLOWED_RECOMMENDED_ACTION)}")

    # Rule 4 (score aggregation must be documented/consistent).
    score_components = getattr(record, "score_components", None)
    total_score = getattr(record, "total_score", None)
    if not isinstance(score_components, dict) or set(score_components) != EXPECTED_SCORE_COMPONENTS:
        errors.append("score_components must contain exactly the versioned score component keys")
    elif (
        any(not isinstance(key, str) for key in score_components)
        or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in score_components.values())
        or any(not _is_finite_number(value) for value in score_components.values())
    ):
        errors.append("score_components values must be finite numeric values (not booleans)")
    elif not _is_finite_number(total_score):
        errors.append("total_score must be a finite number")
    else:
        try:
            computed_raw = math.fsum(score_components.values())
        except OverflowError:
            errors.append("score_components sum must remain finite")
        else:
            if not math.isfinite(computed_raw):
                errors.append("score_components sum must remain finite")
            else:
                computed = round(computed_raw, 2)
                if abs(computed - round(float(total_score), 2)) > 1e-6:
                    errors.append(
                        f"total_score ({total_score}) must equal sum of score_components ({computed}) (rule 5)"
                    )

    # Rule 6: blocked_actions must be a superset of the required floor.
    blocked_actions_value = getattr(record, "blocked_actions", None)
    if not isinstance(blocked_actions_value, list):
        errors.append("blocked_actions must be a list")
        blocked_actions_value = []
    if any(not isinstance(action, str) for action in blocked_actions_value):
        errors.append("blocked_actions must contain only strings")
    blocked_actions = {action for action in blocked_actions_value if isinstance(action, str)}
    missing_blocked = REQUIRED_BLOCKED_ACTIONS - blocked_actions
    if missing_blocked:
        errors.append(f"blocked_actions is missing required entries: {sorted(missing_blocked)} (rule 6)")

    # Rule 7 (cross-object form) lives in
    # `validate_opportunity_against_license_review` below -- it needs the
    # paired license review object, which this single-object validator does
    # not have.

    if hasattr(record, "claim_scope") or hasattr(record, "evidence_level") or hasattr(record, "evidence_ready"):
        errors.append("OpenSourceIntegrationOpportunityV1 must not carry its own claim_scope/evidence_level/evidence_ready field")
    if any(hasattr(record, key) for key in FORBIDDEN_CLAIM_FIELDS):
        errors.append("OpenSourceIntegrationOpportunityV1 must not carry scientific/evidence promotion fields")

    for field_name in ("repo_full_name", "provenance"):
        _scan_banned_phrases(getattr(record, field_name, None) or "", field_name, errors)
    for field_name in ("limitations", "integration_surface", "emulation_surface"):
        _scan_banned_phrases(getattr(record, field_name, None) or [], field_name, errors)
    _scan_banned_phrases(getattr(record, "metadata", None) or {}, "metadata", errors)
    metadata = getattr(record, "metadata", None)
    if not isinstance(metadata, dict):
        errors.append("metadata must be a mapping")
    _check_string_keys(getattr(record, "metadata", None) or {}, "metadata", errors)

    return errors


def validate_opportunity_against_license_review(opportunity: Any, license_review: Any) -> list[str]:
    """Cross-object check (mission rule 7): an opportunity may only
    recommend `integrate_as_optional_adapter` in a way that implies
    committing code from the repository if the paired license review's
    `commercial_core_policy` actually permits copy-in. Called by
    `opportunity_batch.build_opportunities_from_candidates` at
    construction time -- kept separate from `validate_integration_opportunity`
    because it needs both objects, not just one."""
    errors: list[str] = []
    if getattr(opportunity, "repo_full_name", None) != getattr(license_review, "repo_full_name", None):
        errors.append("opportunity and license_review repository identities do not match")
    review_id = getattr(license_review, "license_review_id", None)
    try:
        expected_review_id = license_review.recompute_id()
    except (AttributeError, TypeError, ValueError, OverflowError):
        expected_review_id = None
    if not isinstance(review_id, str) or review_id != expected_review_id:
        errors.append("license_review_id does not match its repository/license/policy version")
    if getattr(opportunity, "license_review_id", None) != review_id:
        errors.append("opportunity license_review_id does not match the paired license review")
    recommended_action = getattr(opportunity, "recommended_action", None)
    commercial_core_policy = getattr(license_review, "commercial_core_policy", None)
    license_risk = getattr(license_review, "license_risk", None)

    # `integrate_as_optional_adapter` is the one recommended_action that
    # implies copying the repository's own code in-process -- it may only
    # ever pair with the single (policy, risk) combination that actually
    # permits that (rule 7/8). This must fail closed for every other
    # combination, not only when commercial_core_policy already happens to
    # be copy-permitting -- a mismatched/tampered pair (e.g.
    # commercial_core_policy="external_process_only" or
    # "docs_reference_only" alongside this action) is exactly the case
    # this cross-object check exists to catch.
    if recommended_action == "integrate_as_optional_adapter":
        if commercial_core_policy not in _COMMERCIAL_CORE_COPY_POLICIES or license_risk not in _COMMERCIAL_CORE_COPY_ALLOWED_LICENSE_RISK:
            errors.append(
                f"opportunity recommends '{recommended_action}' but license_review has "
                f"commercial_core_policy='{commercial_core_policy}', license_risk='{license_risk}' -- "
                f"only commercial_core_policy in {sorted(_COMMERCIAL_CORE_COPY_POLICIES)} with license_risk "
                f"in {sorted(_COMMERCIAL_CORE_COPY_ALLOWED_LICENSE_RISK)} permits this action (rule 7/8)"
            )
    return errors


# ── OpenSourceLeverageBatchV1 ──────────────────────────────────────────────


_REVIEW_ACTIONS = frozenset({"license_review_required", "security_review_required"})


def _validate_ranked_entry(entry: Any, index: int, errors: list[str]) -> None:
    """Re-validate one ranked entry from first principles so a hand-edited or
    deserialised batch cannot carry a forged action, a mismatched embedded
    license review, or non-numeric scores past the planner/renderer. The
    check is structural consistency only: it does not make the entry
    verified legal, security, or scientific evidence."""
    from oss_opportunities.integration_opportunity import OpenSourceIntegrationOpportunityV1
    from oss_opportunities.license_review import RepositoryLicenseReviewV1, classify_license_risk

    prefix = f"opportunities_ranked[{index}]"
    if not isinstance(entry, dict):
        errors.append(f"{prefix} must be a mapping")
        return
    try:
        reject_forbidden_claim_fields(entry, prefix)
    except OssOpportunityValidationError as exc:
        errors.append(str(exc))
    review_dict = entry.get("license_review")
    if not isinstance(review_dict, dict):
        errors.append(f"{prefix}.license_review must be a mapping (embedded review is required)")
        return
    score = entry.get("total_score")
    if not _is_finite_number(score):
        errors.append(f"{prefix}.total_score must be a finite number")
        return
    try:
        if type(review_dict.get("attribution_required")) is not bool:
            errors.append(f"{prefix}.license_review.attribution_required must be a boolean")
        opportunity = OpenSourceIntegrationOpportunityV1.from_dict(
            {k: v for k, v in entry.items() if k != "license_review"}
        )
        review = RepositoryLicenseReviewV1.from_dict(review_dict)
        problems = [f"opportunity: {e}" for e in opportunity.validate()]
        problems += [f"license_review: {e}" for e in review.validate()]
        if not problems:
            problems += validate_opportunity_against_license_review(opportunity, review)
            if opportunity.repo_full_name.casefold() != review.repo_full_name.casefold():
                problems.append("embedded license_review repo_full_name does not match the opportunity")
            if review.license_review_id != review.recompute_id():
                problems.append("embedded license_review id does not match its repo/license (forged or edited)")
            if review.license_risk != classify_license_risk(review.license_spdx):
                problems.append("embedded license_review license_risk does not match its license_spdx")
            if opportunity.license_review_id != review.license_review_id:
                problems.append("embedded license_review id does not match license_review_id")
            unresolved = (
                (review.metadata or {}).get("license_observation_status") == "conflict"
                or review.commercial_core_policy in ("blocked_pending_review", "blocked")
                or review.license_risk in ("missing_high", "proprietary_or_unknown_high")
            )
            if unresolved and opportunity.recommended_action not in _REVIEW_ACTIONS:
                problems.append(
                    f"unresolved license evidence requires a review action, got '{opportunity.recommended_action}'"
                )
    except Exception as exc:  # validators report, never raise
        problems = [f"malformed entry ({type(exc).__name__})"]
    errors.extend(f"{prefix}: {p}" for p in problems)


def validate_leverage_batch(batch: Any) -> list[str]:
    errors: list[str] = []
    _check_supported_version(getattr(batch, "schema_version", None), SCHEMA_VERSION, "schema_version", errors)

    batch_id = getattr(batch, "batch_id", None)
    scoring_version = getattr(batch, "scoring_version", None)
    if not isinstance(batch_id, str) or not batch_id.strip():
        errors.append("batch_id is required")
    _check_supported_version(scoring_version, SCORING_VERSION, "scoring_version", errors)

    if not getattr(batch, "limitations", None):
        errors.append("limitations must be a non-empty list (rule 1)")
    if not getattr(batch, "provenance", None):
        errors.append("provenance is required (rule 2)")

    for field_name in (
        "sources_scanned", "opportunities_ranked", "opportunities_rejected", "top_immediate_adapters",
        "top_architecture_emulation", "top_docs_references", "top_rejections", "limitations",
    ):
        if not isinstance(getattr(batch, field_name, None), list):
            errors.append(f"{field_name} must be a list")
    if not isinstance(getattr(batch, "top_by_category", None), dict):
        errors.append("top_by_category must be a mapping")
    if not isinstance(getattr(batch, "metadata", None), dict):
        errors.append("metadata must be a mapping")

    sources_value = getattr(batch, "sources_scanned", None)
    sources_scanned = sources_value if isinstance(sources_value, list) else []
    if not sources_scanned:
        errors.append("sources_scanned must be a non-empty list (rule 3)")
    for source in sources_scanned:
        if not isinstance(source, str) or source not in ALLOWED_SOURCE:
            errors.append(f"sources_scanned contains unknown source '{source}' (must be one of {sorted(ALLOWED_SOURCE)})")

    candidates_seen = getattr(batch, "candidates_seen", None)
    opportunities_ranked = getattr(batch, "opportunities_ranked", None)
    opportunities_rejected = getattr(batch, "opportunities_rejected", None)
    lists_ok = True
    for label, value in (("opportunities_ranked", opportunities_ranked), ("opportunities_rejected", opportunities_rejected)):
        if not isinstance(value, list):
            errors.append(f"{label} must be a list")
            lists_ok = False
    if not isinstance(candidates_seen, int) or isinstance(candidates_seen, bool) or candidates_seen < 0:
        errors.append("candidates_seen must be a non-negative integer")
    if lists_ok:
        if isinstance(candidates_seen, int) and not isinstance(candidates_seen, bool) and candidates_seen != len(opportunities_ranked) + len(opportunities_rejected):
            errors.append("candidates_seen must equal ranked plus explicitly rejected candidate rows")
        if candidates_seen is not None and (not isinstance(candidates_seen, int) or isinstance(candidates_seen, bool)):
            errors.append("candidates_seen must be an integer")
        for index, entry in enumerate(opportunities_ranked):
            _validate_ranked_entry(entry, index, errors)
        primary_ids: set[str] = set()
        primary_repo_by_id: dict[str, str] = {}
        for index, entry in enumerate(opportunities_ranked):
            if isinstance(entry, dict) and isinstance(entry.get("opportunity_id"), str):
                if entry["opportunity_id"] in primary_ids:
                    errors.append(f"opportunities_ranked[{index}].opportunity_id is duplicated")
                primary_ids.add(entry["opportunity_id"])
                if isinstance(entry.get("repo_full_name"), str):
                    primary_repo_by_id[entry["opportunity_id"]] = entry["repo_full_name"].casefold()
        for index, entry in enumerate(opportunities_rejected):
            if not isinstance(entry, dict):
                errors.append(f"opportunities_rejected[{index}] must be a mapping")
                continue
            for key in ("repo_full_name", "reason"):
                if not isinstance(entry.get(key), str) or not entry.get(key):
                    errors.append(f"opportunities_rejected[{index}].{key} must be a non-empty string")
            duplicate_of = entry.get("duplicate_of")
            if "omitted_by_top_n" in entry and type(entry["omitted_by_top_n"]) is not bool:
                errors.append(f"opportunities_rejected[{index}].omitted_by_top_n must be a boolean")
            if entry.get("omitted_by_top_n") is True and not str(entry.get("reason", "")).startswith("top_n_limit:"):
                errors.append(f"opportunities_rejected[{index}] top_n omission requires a top_n_limit reason")
            if duplicate_of is None and isinstance(entry.get("opportunity_id"), str):
                if entry["opportunity_id"] in primary_ids:
                    errors.append(f"opportunities_rejected[{index}].opportunity_id duplicates a canonical row")
                primary_ids.add(entry["opportunity_id"])
                if isinstance(entry.get("repo_full_name"), str):
                    primary_repo_by_id[entry["opportunity_id"]] = entry["repo_full_name"].casefold()
        for index, entry in enumerate(opportunities_rejected):
            if not isinstance(entry, dict) or "duplicate_of" not in entry:
                continue
            duplicate_of = entry.get("duplicate_of")
            if not isinstance(duplicate_of, str) or duplicate_of not in primary_ids:
                errors.append(f"opportunities_rejected[{index}].duplicate_of must identify a canonical candidate row")
            elif entry.get("opportunity_id") is not None:
                errors.append(f"opportunities_rejected[{index}] duplicate diagnostics must not claim a distinct opportunity_id")
            elif isinstance(entry.get("repo_full_name"), str) and primary_repo_by_id.get(duplicate_of) != entry["repo_full_name"].casefold():
                errors.append(f"opportunities_rejected[{index}].duplicate_of repository does not match its canonical row")

        ranked_ids = [entry["opportunity_id"] for entry in opportunities_ranked if isinstance(entry, dict) and isinstance(entry.get("opportunity_id"), str)]
        if len(ranked_ids) == len(opportunities_ranked) and isinstance(scoring_version, str) and all(isinstance(source, str) for source in sources_scanned):
            from oss_opportunities.opportunity_batch import compute_batch_id
            expected_batch_id = compute_batch_id(
                opportunity_ids=ranked_ids,
                sources_scanned=sources_scanned,
                scoring_version=scoring_version,
            )
            if batch_id != expected_batch_id:
                errors.append("batch_id does not match ranked opportunity IDs, sources, and scoring version")

        expected_categories: dict[str, list[str]] = {}
        for entry in opportunities_ranked:
            if isinstance(entry, dict) and isinstance(entry.get("leverage_category"), str) and isinstance(entry.get("repo_full_name"), str):
                expected_categories.setdefault(entry["leverage_category"], []).append(entry["repo_full_name"])
        if getattr(batch, "top_by_category", None) != expected_categories:
            errors.append("top_by_category does not match ranked opportunities")
        expected_projections = {
            "top_immediate_adapters": [entry["repo_full_name"] for entry in opportunities_ranked if isinstance(entry, dict) and isinstance(entry.get("repo_full_name"), str) and entry.get("recommended_action") in ("integrate_as_optional_adapter", "integrate_as_external_tool_record")],
            "top_architecture_emulation": [entry["repo_full_name"] for entry in opportunities_ranked if isinstance(entry, dict) and isinstance(entry.get("repo_full_name"), str) and entry.get("recommended_action") == "emulate_architecture_pattern"],
            "top_docs_references": [entry["repo_full_name"] for entry in opportunities_ranked if isinstance(entry, dict) and isinstance(entry.get("repo_full_name"), str) and entry.get("recommended_action") == "create_docs_reference"],
            "top_rejections": [entry["repo_full_name"] for entry in opportunities_rejected if isinstance(entry, dict) and isinstance(entry.get("repo_full_name"), str) and "duplicate_of" not in entry and not entry.get("omitted_by_top_n")],
        }
        for field_name, expected in expected_projections.items():
            if getattr(batch, field_name, None) != expected:
                errors.append(f"{field_name} does not match ranked/rejected rows")

    if hasattr(batch, "claim_scope") or hasattr(batch, "evidence_level"):
        errors.append("OpenSourceLeverageBatchV1 must not carry its own claim_scope/evidence_level field")
    if any(hasattr(batch, key) for key in FORBIDDEN_CLAIM_FIELDS):
        errors.append("OpenSourceLeverageBatchV1 must not carry scientific/evidence promotion fields")

    _scan_banned_phrases(getattr(batch, "provenance", None) or "", "provenance", errors)
    _scan_banned_phrases(getattr(batch, "limitations", None) or [], "limitations", errors)
    _scan_banned_phrases(getattr(batch, "metadata", None) or {}, "metadata", errors)
    _check_string_keys(getattr(batch, "metadata", None) or {}, "metadata", errors)

    return errors


# ── OpenSourceIntegrationPlanV1 ────────────────────────────────────────────


def validate_integration_plan(plan: Any) -> list[str]:
    errors: list[str] = []
    _check_supported_version(getattr(plan, "schema_version", None), SCHEMA_VERSION, "schema_version", errors)

    plan_id = getattr(plan, "plan_id", None)
    batch_id = getattr(plan, "batch_id", None)
    planner_version = getattr(plan, "planner_version", None)
    if not isinstance(plan_id, str) or not plan_id.strip():
        errors.append("plan_id is required")
    if not isinstance(batch_id, str) or not batch_id.strip():
        errors.append("batch_id is required")
    _check_supported_version(planner_version, PLANNER_VERSION, "planner_version", errors)

    selected_ids = getattr(plan, "selected_opportunity_ids", None)
    action_fields = (
        "immediate_adapter_candidates", "external_tool_record_candidates", "architecture_emulation_candidates",
        "documentation_reference_candidates", "license_review_queue", "security_review_queue", "deferred_candidates",
    )
    if not isinstance(selected_ids, list) or any(not isinstance(value, str) or not value for value in selected_ids):
        errors.append("selected_opportunity_ids must be a list of non-empty strings")
        selected_ids = []
    if len(set(selected_ids)) != len(selected_ids):
        errors.append("selected_opportunity_ids must not contain duplicates")
    emitted_ids: list[str] = []
    for field_name in action_fields:
        rows = getattr(plan, field_name, None)
        if not isinstance(rows, list):
            errors.append(f"{field_name} must be a list")
            continue
        for index, row in enumerate(rows):
            prefix = f"{field_name}[{index}]"
            if not isinstance(row, dict):
                errors.append(f"{prefix} must be a mapping")
                continue
            try:
                reject_forbidden_claim_fields(row, prefix)
            except OssOpportunityValidationError as exc:
                errors.append(str(exc))
            opportunity_id = row.get("opportunity_id")
            if not isinstance(opportunity_id, str) or not opportunity_id:
                errors.append(f"{prefix}.opportunity_id must be a non-empty string")
            else:
                emitted_ids.append(opportunity_id)
            for key in ("repo_full_name", "leverage_category", "license_risk", "commercial_core_policy"):
                if not isinstance(row.get(key), str) or not row.get(key):
                    errors.append(f"{prefix}.{key} must be a non-empty string")
            if row.get("not_executed") is not True or row.get("not_installed") is not True:
                errors.append(f"{prefix} must retain not_executed=true and not_installed=true")
    if len(emitted_ids) != len(set(emitted_ids)) or set(emitted_ids) != set(selected_ids):
        errors.append("selected_opportunity_ids do not match unique action-queue rows")

    rejected_rows = getattr(plan, "rejected_candidates", None)
    if not isinstance(rejected_rows, list):
        errors.append("rejected_candidates must be a list")
    else:
        for index, row in enumerate(rejected_rows):
            if not isinstance(row, dict):
                errors.append(f"rejected_candidates[{index}] must be a mapping")
                continue
            try:
                reject_forbidden_claim_fields(row, f"rejected_candidates[{index}]")
            except OssOpportunityValidationError as exc:
                errors.append(str(exc))
            if not isinstance(row.get("repo_full_name"), str) or not row.get("repo_full_name"):
                errors.append(f"rejected_candidates[{index}].repo_full_name must be a non-empty string")
            if not isinstance(row.get("reason"), str) or not row.get("reason"):
                errors.append(f"rejected_candidates[{index}].reason must be a non-empty string")
            if row.get("not_executed") is not True:
                errors.append(f"rejected_candidates[{index}] must retain not_executed=true")
            if "omitted_by_max_selected" in row and type(row["omitted_by_max_selected"]) is not bool:
                errors.append(f"rejected_candidates[{index}].omitted_by_max_selected must be a boolean")
            if row.get("omitted_by_max_selected") is True and isinstance(row.get("reason"), str) and not row["reason"].startswith("max_selected_limit:"):
                errors.append(f"rejected_candidates[{index}] selection omission requires a max_selected_limit reason")
    proposed_next_prs = getattr(plan, "proposed_next_prs", None)
    if not isinstance(proposed_next_prs, list) or any(not isinstance(item, str) or not item.strip() for item in proposed_next_prs):
        errors.append("proposed_next_prs must be a list of non-empty strings")
    if not isinstance(getattr(plan, "metadata", None), dict):
        errors.append("metadata must be a mapping")
    else:
        _check_string_keys(plan.metadata, "metadata", errors)

    if isinstance(batch_id, str) and isinstance(plan_id, str) and isinstance(planner_version, str) and isinstance(selected_ids, list):
        from oss_opportunities.planner import compute_plan_id
        if plan_id != compute_plan_id(batch_id=batch_id, selected_opportunity_ids=selected_ids, planner_version=planner_version):
            errors.append("plan_id does not match batch, selected opportunities, and planner version")

    limitations = getattr(plan, "limitations", None)
    if not isinstance(limitations, list) or not limitations:
        errors.append("limitations must be a non-empty list (rule 1)")
    elif any(not isinstance(item, str) or not item.strip() for item in limitations):
        errors.append("limitations must contain only non-empty strings")
    provenance = getattr(plan, "provenance", None)
    if not isinstance(provenance, str) or not provenance.strip():
        errors.append("provenance is required (rule 2)")

    if hasattr(plan, "claim_scope") or hasattr(plan, "evidence_level"):
        errors.append("OpenSourceIntegrationPlanV1 must not carry its own claim_scope/evidence_level field")
    if any(hasattr(plan, key) for key in FORBIDDEN_CLAIM_FIELDS):
        errors.append("OpenSourceIntegrationPlanV1 must not carry scientific/evidence promotion fields")

    _scan_banned_phrases(getattr(plan, "provenance", None) or "", "provenance", errors)
    _scan_banned_phrases(getattr(plan, "limitations", None) or [], "limitations", errors)
    _scan_banned_phrases(getattr(plan, "metadata", None) or {}, "metadata", errors)
    _check_string_keys(getattr(plan, "metadata", None) or {}, "metadata", errors)

    return errors
