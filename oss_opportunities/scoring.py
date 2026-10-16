"""OSS leverage scoring -- a simple, documented, additive heuristic, not
ML and not a scientific/quality judgment. Mirrors
`dataset_importers.scoring.score_candidate`'s stance: transparent
components, each traceable to an observed candidate/license-review field.

Trending/stars are a *discovery priority* signal only -- they widen
`maintenance_signal`/`documentation_quality_signal` slightly but never
raise `license_safety` or unlock a commercial-core action on their own
(mission rule: "High stars/trending improves discovery priority, not
correctness or quality").
"""
from __future__ import annotations

from typing import Any

from oss_opportunities.license_review import RepositoryLicenseReviewV1
from oss_opportunities.repository_candidate import OpenSourceRepositoryCandidateV1
from oss_opportunities.validation import REQUIRED_BLOCKED_ACTIONS

# ── keyword -> leverage_category hints (topics/description substring
# match only, never a claim about what the repository actually does) ────
_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "document_ingestion": ("markdown", "pdf", "document", "ocr", "convert", "parser", "ingest"),
    "web_literature_acquisition": ("crawl", "scrape", "scraping", "web-extraction", "firecrawl"),
    "workflow_orchestration": ("workflow", "orchestrat", "dag", "pipeline-scheduler", "airflow", "temporal", "n8n"),
    "agent_harness": ("agent", "llm-agent", "autonomous-agent", "dify"),
    "code_graph_memory": ("code-graph", "graph-rag", "codebase-graph", "code-search", "memory"),
    "research_memory": ("research", "memory", "knowledge-graph", "note-taking"),
    "report_visualization": ("diagram", "visualization", "animation", "manim", "chart"),
    "frontend_stack": ("frontend", "react", "router", "ui-library", "component-library", "css"),
    "backend_api_stack": ("api-framework", "web-framework", "backend", "rest-api", "validation-library"),
    "database_data_stack": ("database", "orm", "sql", "postgres", "data-store"),
    "infra_observability_stack": ("observability", "monitoring", "metrics", "infrastructure", "container", "deployment"),
    "dataset_discovery": ("dataset", "data-catalog", "data-discovery"),
    "scientific_computing": ("scientific-computing", "numerical", "simulation"),
    "security_compliance": ("security", "compliance", "audit", "pentest", "vulnerability"),
}

# Repositories this repo already has a comparable built-in path for --
# reduces direct-integration score (mission: "existing built equivalents
# should reduce direct integration score"), never blocks emulation/reference.
_HAS_EXISTING_EQUIVALENT: frozenset[str] = frozenset(
    {
        "job_runner",  # workflow_orchestration: this repo already has job_runner.worker
        "benchmark_packs",  # report_visualization/renderer: already has benchmark_packs.renderer
    }
)

# Language/ecosystem families this repository's Python core does not
# consume directly -- large TypeScript/infra stacks default to
# emulation/reference rather than integration (mission rule).
_NON_PYTHON_CORE_LANGUAGES: frozenset[str] = frozenset(
    {"typescript", "javascript", "go", "rust", "java", "kotlin", "ruby", "php"}
)

_LICENSE_SAFETY_SCORE: dict[str, float] = {
    "permissive_low": 3.0,
    "weak_copyleft_medium": 1.0,
    "strong_copyleft_high": 0.0,
    "source_available_or_fair_code_high": 0.0,
    "proprietary_or_unknown_high": -1.0,
    "missing_high": -1.0,
}


def _keyword_hits(candidate: OpenSourceRepositoryCandidateV1, category: str) -> int:
    haystack = " ".join([candidate.description or "", " ".join(candidate.topics or []), candidate.name or ""]).lower()
    return sum(1 for kw in _CATEGORY_KEYWORDS.get(category, ()) if kw in haystack)


def infer_leverage_category(candidate: OpenSourceRepositoryCandidateV1) -> str:
    """Deterministic keyword-overlap classification -- ties broken by the
    fixed iteration order of `_CATEGORY_KEYWORDS` (declared, not sorted, so
    document_ingestion/web_literature_acquisition are preferred over
    generic infra categories on an exact tie, matching this milestone's
    stated highest-value categories). Falls back to `reject_or_defer` if
    nothing matches -- a candidate is never force-fit into a category."""
    best_category = "reject_or_defer"
    best_hits = 0
    for category in _CATEGORY_KEYWORDS:
        hits = _keyword_hits(candidate, category)
        if hits > best_hits:
            best_hits = hits
            best_category = category
    return best_category


def score_opportunity(
    candidate: OpenSourceRepositoryCandidateV1, license_review: RepositoryLicenseReviewV1
) -> dict[str, Any]:
    """Return a plain dict with every field
    `oss_opportunities.opportunity_batch.build_opportunities_from_candidates`
    needs to construct an `OpenSourceIntegrationOpportunityV1`."""
    leverage_category = infer_leverage_category(candidate)
    language = (candidate.primary_language or "").strip().lower()
    is_non_python_core = language in _NON_PYTHON_CORE_LANGUAGES
    has_existing_equivalent = any(token in (candidate.repo_full_name or "").lower() for token in _HAS_EXISTING_EQUIVALENT)

    direct_product_leverage = 2.0 if leverage_category in ("document_ingestion", "web_literature_acquisition", "dataset_discovery") else 0.0
    awareness_studio_leverage = 2.0 if leverage_category in ("code_graph_memory", "research_memory", "agent_harness") else 0.0
    report_pipeline_leverage = 1.5 if leverage_category == "report_visualization" else 0.0
    document_ingestion_leverage = 2.0 if leverage_category == "document_ingestion" else 0.0
    literature_acquisition_leverage = 2.0 if leverage_category == "web_literature_acquisition" else 0.0
    code_graph_memory_leverage = 2.0 if leverage_category == "code_graph_memory" else 0.0
    workflow_orchestration_leverage = 1.0 if leverage_category == "workflow_orchestration" else 0.0
    frontend_saas_leverage = 1.5 if leverage_category in ("frontend_stack", "backend_api_stack", "database_data_stack") else 0.0
    infra_observability_leverage = 1.0 if leverage_category == "infra_observability_stack" else 0.0

    # Adapter-surface credit needs more than keyword overlap. A documented
    # surface (homepage or an explicit adapter docs URL) earns full credit; a
    # category inferred only from description/topics earns half credit.
    documented_surface = bool(candidate.homepage_url) or bool((candidate.metadata or {}).get("adapter_docs_url"))
    if leverage_category in ("reject_or_defer", "security_compliance"):
        adapter_surface_clarity = 0.0
    elif documented_surface:
        adapter_surface_clarity = 1.0
    else:
        adapter_surface_clarity = 0.5

    # Trending/stars widen maintenance/documentation signal only -- a
    # discovery-priority nudge, never a correctness/license signal.
    stars = candidate.stars or 0
    star_gain = candidate.star_gain or 0
    maintenance_signal = min(1.5, 0.5 if candidate.latest_activity_status == "active" else 0.0) + (0.5 if star_gain > 0 else 0.0)
    documentation_quality_signal = 0.5 if candidate.homepage_url or candidate.description else 0.0

    license_safety = _LICENSE_SAFETY_SCORE.get(license_review.license_risk, -1.0)

    dependency_weight_penalty = 0.0
    if is_non_python_core:
        dependency_weight_penalty += 1.0
    if leverage_category in ("frontend_stack", "infra_observability_stack", "database_data_stack"):
        dependency_weight_penalty += 0.5

    security_risk_penalty = 0.0
    if leverage_category == "security_compliance":
        security_risk_penalty += 1.0
    if candidate.metadata and candidate.metadata.get("requires_credentials"):
        security_risk_penalty += 1.0

    duplication_penalty = 1.5 if has_existing_equivalent else 0.0

    commercial_core_penalty = 0.0
    if license_review.commercial_core_policy in ("blocked_pending_review", "blocked"):
        commercial_core_penalty += 1.0

    score_components = {
        "direct_product_leverage": round(direct_product_leverage, 2),
        "awareness_studio_leverage": round(awareness_studio_leverage, 2),
        "report_pipeline_leverage": round(report_pipeline_leverage, 2),
        "document_ingestion_leverage": round(document_ingestion_leverage, 2),
        "literature_acquisition_leverage": round(literature_acquisition_leverage, 2),
        "code_graph_memory_leverage": round(code_graph_memory_leverage, 2),
        "workflow_orchestration_leverage": round(workflow_orchestration_leverage, 2),
        "frontend_saas_leverage": round(frontend_saas_leverage, 2),
        "infra_observability_leverage": round(infra_observability_leverage, 2),
        "adapter_surface_clarity": round(adapter_surface_clarity, 2),
        "maintenance_signal": round(maintenance_signal, 2),
        "documentation_quality_signal": round(documentation_quality_signal, 2),
        "license_safety": round(license_safety, 2),
        "dependency_weight_penalty": round(-dependency_weight_penalty, 2),
        "security_risk_penalty": round(-security_risk_penalty, 2),
        "duplication_penalty": round(-duplication_penalty, 2),
        "commercial_core_penalty": round(-commercial_core_penalty, 2),
    }
    total_score = round(sum(score_components.values()), 2)

    # ── recommended_action + blocked_actions ────────────────────────────
    blocked = leverage_category == "reject_or_defer"

    if blocked:
        recommended_action = "reject" if total_score < 0 else "defer"
    elif license_review.license_risk in ("missing_high", "proprietary_or_unknown_high"):
        # Unresolved license: an empty/unknown string, or an unmatched license
        # string. Adoption of any kind waits for a license review.
        recommended_action = "license_review_required"
    elif leverage_category == "security_compliance":
        recommended_action = "security_review_required"
    elif is_non_python_core or leverage_category in ("frontend_stack", "backend_api_stack", "database_data_stack", "infra_observability_stack"):
        recommended_action = "emulate_architecture_pattern"
    elif leverage_category in ("document_ingestion", "web_literature_acquisition"):
        # High-value categories always get a real integration path: only a
        # permissive_low license (the one risk tier whose default
        # commercial_core_policy is copy-permitting, see
        # oss_opportunities.license_review._DEFAULT_POLICY_BY_RISK) can be
        # an in-process optional adapter. Every other risk tier -- weak
        # copyleft, strong copyleft, source-available/fair-code,
        # proprietary/unknown (e.g. an AGPL scraping library) -- is still
        # worth using, just only as an external process/service adapter,
        # never as copied-in code (rule 8).
        if license_review.license_risk == "permissive_low":
            recommended_action = "integrate_as_optional_adapter"
        else:
            recommended_action = "integrate_as_external_tool_record"
    elif leverage_category in ("code_graph_memory", "research_memory", "agent_harness", "workflow_orchestration"):
        recommended_action = "emulate_architecture_pattern"
    elif leverage_category == "report_visualization":
        recommended_action = "create_docs_reference"
    elif leverage_category == "dataset_discovery":
        recommended_action = "integrate_as_external_tool_record"
    else:
        recommended_action = "create_future_task"

    # A recommended_action implying code-copy must never survive when the
    # license review does not permit it -- enforced here (defense in depth
    # on top of validate_opportunity_against_license_review's cross-check).
    if recommended_action == "integrate_as_optional_adapter" and license_review.license_risk not in ("permissive_low",):
        recommended_action = "integrate_as_external_tool_record"

    # Credentialed adoption is never a direct adapter or tool-record path: it
    # waits for security review first. credential_required_execution stays in
    # blocked_actions regardless.
    if (candidate.metadata or {}).get("requires_credentials") and recommended_action in (
        "integrate_as_optional_adapter",
        "integrate_as_external_tool_record",
    ):
        recommended_action = "security_review_required"

    blocked_actions = sorted(REQUIRED_BLOCKED_ACTIONS)

    integration_surface: list[str] = []
    emulation_surface: list[str] = []
    if recommended_action in ("integrate_as_optional_adapter", "integrate_as_external_tool_record"):
        integration_surface.append(f"external_tools record for {candidate.repo_full_name} ({leverage_category})")
    if recommended_action == "emulate_architecture_pattern":
        emulation_surface.append(f"architecture pattern reference for {candidate.repo_full_name} ({leverage_category})")

    def _relevance(*categories: str) -> str:
        if leverage_category not in categories:
            return "none"
        return "high" if total_score >= 3.0 else "moderate"

    relevance_to_neurotopology_sim = _relevance("document_ingestion", "dataset_discovery", "scientific_computing")
    relevance_to_awareness_studio = _relevance("code_graph_memory", "research_memory", "agent_harness", "document_ingestion")
    relevance_to_report_packs = _relevance("report_visualization")
    relevance_to_literature_pipeline = _relevance("web_literature_acquisition", "document_ingestion")
    relevance_to_saas_future = _relevance("frontend_stack", "backend_api_stack", "database_data_stack", "infra_observability_stack")

    security_risk = "elevated" if security_risk_penalty > 0 else "low"
    dependency_weight = "heavy" if dependency_weight_penalty >= 1.0 else ("light" if dependency_weight_penalty > 0 else "none")
    maintenance_signal_label = "active" if candidate.latest_activity_status == "active" else "unknown"
    implementation_complexity = "high" if leverage_category in ("workflow_orchestration", "code_graph_memory", "agent_harness") else "moderate"

    return {
        "leverage_category": leverage_category,
        "recommended_action": recommended_action,
        "blocked_actions": blocked_actions,
        "integration_surface": integration_surface,
        "emulation_surface": emulation_surface,
        "relevance_to_neurotopology_sim": relevance_to_neurotopology_sim,
        "relevance_to_awareness_studio": relevance_to_awareness_studio,
        "relevance_to_report_packs": relevance_to_report_packs,
        "relevance_to_literature_pipeline": relevance_to_literature_pipeline,
        "relevance_to_saas_future": relevance_to_saas_future,
        "security_risk": security_risk,
        "dependency_weight": dependency_weight,
        "maintenance_signal": maintenance_signal_label,
        "implementation_complexity": implementation_complexity,
        "score_components": score_components,
        "total_score": total_score,
    }
