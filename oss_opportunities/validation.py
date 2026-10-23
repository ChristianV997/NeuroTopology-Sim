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
import re
from typing import Any

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


def validate_repository_candidate(record: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

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

    license_review_id = getattr(record, "license_review_id", None)
    if not isinstance(license_review_id, str) or not license_review_id.strip():
        errors.append("license_review_id is required")
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

    metadata = getattr(record, "metadata", None)
    if not isinstance(metadata, dict):
        errors.append("metadata must be a mapping")
        metadata = {}

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

    if not getattr(record, "opportunity_id", None):
        errors.append("opportunity_id is required")
    if not getattr(record, "repo_full_name", None):
        errors.append("repo_full_name is required")
    if not getattr(record, "candidate_id", None):
        errors.append("candidate_id is required -- opportunity source must be explicit (rule 3)")
    if not getattr(record, "license_review_id", None):
        errors.append("license_review_id is required -- opportunity source must be explicit (rule 3)")

    if not getattr(record, "limitations", None):
        errors.append("limitations must be a non-empty list (rule 1)")
    if not getattr(record, "provenance", None):
        errors.append("provenance is required (rule 2)")

    leverage_category = getattr(record, "leverage_category", None)
    if leverage_category not in ALLOWED_LEVERAGE_CATEGORY:
        errors.append(f"leverage_category '{leverage_category}' must be one of {sorted(ALLOWED_LEVERAGE_CATEGORY)}")

    recommended_action = getattr(record, "recommended_action", None)
    if recommended_action not in ALLOWED_RECOMMENDED_ACTION:
        errors.append(f"recommended_action '{recommended_action}' must be one of {sorted(ALLOWED_RECOMMENDED_ACTION)}")

    # Rule 4 (score aggregation must be documented/consistent).
    score_components = getattr(record, "score_components", None) or {}
    total_score = getattr(record, "total_score", None)
    if score_components and total_score is not None:
        computed = round(sum(float(v) for v in score_components.values()), 2)
        if abs(computed - round(float(total_score), 2)) > 1e-6:
            errors.append(
                f"total_score ({total_score}) must equal sum of score_components ({computed}) (rule 5)"
            )

    # Rule 6: blocked_actions must be a superset of the required floor.
    blocked_actions = set(getattr(record, "blocked_actions", None) or [])
    missing_blocked = REQUIRED_BLOCKED_ACTIONS - blocked_actions
    if missing_blocked:
        errors.append(f"blocked_actions is missing required entries: {sorted(missing_blocked)} (rule 6)")

    # Rule 7 (cross-object form) lives in
    # `validate_opportunity_against_license_review` below -- it needs the
    # paired license review object, which this single-object validator does
    # not have.

    if hasattr(record, "claim_scope") or hasattr(record, "evidence_level") or hasattr(record, "evidence_ready"):
        errors.append("OpenSourceIntegrationOpportunityV1 must not carry its own claim_scope/evidence_level/evidence_ready field")

    for field_name in ("repo_full_name", "provenance"):
        _scan_banned_phrases(getattr(record, field_name, None) or "", field_name, errors)
    for field_name in ("limitations", "integration_surface", "emulation_surface"):
        _scan_banned_phrases(getattr(record, field_name, None) or [], field_name, errors)
    _scan_banned_phrases(getattr(record, "metadata", None) or {}, "metadata", errors)

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


def validate_leverage_batch(batch: Any) -> list[str]:
    errors: list[str] = []

    if not getattr(batch, "batch_id", None):
        errors.append("batch_id is required")

    if not getattr(batch, "limitations", None):
        errors.append("limitations must be a non-empty list (rule 1)")
    if not getattr(batch, "provenance", None):
        errors.append("provenance is required (rule 2)")

    sources_scanned = getattr(batch, "sources_scanned", None) or []
    if not sources_scanned:
        errors.append("sources_scanned must be a non-empty list (rule 3)")
    for source in sources_scanned:
        if source not in ALLOWED_SOURCE:
            errors.append(f"sources_scanned contains unknown source '{source}' (must be one of {sorted(ALLOWED_SOURCE)})")

    candidates_seen = getattr(batch, "candidates_seen", None)
    opportunities_ranked = getattr(batch, "opportunities_ranked", None) or []
    opportunities_rejected = getattr(batch, "opportunities_rejected", None) or []
    if candidates_seen is not None and candidates_seen < len(opportunities_ranked) + len(opportunities_rejected):
        errors.append("candidates_seen must be >= len(opportunities_ranked) + len(opportunities_rejected)")

    if hasattr(batch, "claim_scope") or hasattr(batch, "evidence_level"):
        errors.append("OpenSourceLeverageBatchV1 must not carry its own claim_scope/evidence_level field")

    _scan_banned_phrases(getattr(batch, "provenance", None) or "", "provenance", errors)
    _scan_banned_phrases(getattr(batch, "limitations", None) or [], "limitations", errors)
    _scan_banned_phrases(getattr(batch, "metadata", None) or {}, "metadata", errors)

    return errors


# ── OpenSourceIntegrationPlanV1 ────────────────────────────────────────────


def validate_integration_plan(plan: Any) -> list[str]:
    errors: list[str] = []

    if not getattr(plan, "plan_id", None):
        errors.append("plan_id is required")
    if not getattr(plan, "batch_id", None):
        errors.append("batch_id is required")

    if not getattr(plan, "limitations", None):
        errors.append("limitations must be a non-empty list (rule 1)")
    if not getattr(plan, "provenance", None):
        errors.append("provenance is required (rule 2)")

    if hasattr(plan, "claim_scope") or hasattr(plan, "evidence_level"):
        errors.append("OpenSourceIntegrationPlanV1 must not carry its own claim_scope/evidence_level field")

    _scan_banned_phrases(getattr(plan, "provenance", None) or "", "provenance", errors)
    _scan_banned_phrases(getattr(plan, "limitations", None) or [], "limitations", errors)
    _scan_banned_phrases(getattr(plan, "metadata", None) or {}, "metadata", errors)

    return errors
