from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

ALLOWED_SOURCE_DOMAINS = [
    "rag", "graph_rag", "literature_review", "scientific_scraper", "citation_graph",
    "workflow_orchestration", "agent_runtime", "dashboard_frontend", "command_center",
    "observability", "local_ops", "data_validation", "notebook_pipeline", "knowledge_graph",
    "publication_pipeline", "scientific_ml", "toe_research",
]
ALLOWED_LICENSE_STATUS = ["compatible", "pattern_only", "incompatible", "unknown", "needs_manual_review"]
ALLOWED_COMPATIBILITY_STATUS = [
    "safe_to_adapt", "pattern_only_reimplementation_required", "blocked_license",
    "blocked_dependency_surface", "blocked_security_risk", "manual_review_required",
]
ALLOWED_CLAIM_SCOPE = ["engineering_runtime", "artifact_pattern", "implementation_blueprint", "license_review_required", "blocked"]


@dataclass
class HarvestBase:
    id: str
    repo_full_name: str = ""
    repo_url: str = ""
    source_domain: str = ""
    license_name: str = "unknown"
    license_spdx: str = "UNKNOWN"
    license_status: str = "unknown"
    compatibility_status: str = "manual_review_required"
    useful_for_subsystems: List[str] = field(default_factory=list)
    reusable_patterns: List[str] = field(default_factory=list)
    copied_artifacts: List[str] = field(default_factory=list)
    pattern_only_artifacts: List[str] = field(default_factory=list)
    risk_notes: List[str] = field(default_factory=list)
    attribution_required: bool = True
    integration_priority: str = "P2"
    claim_scope: str = "artifact_pattern"
    evidence_state: str = "fixture"
    guardrails: List[str] = field(default_factory=list)
    next_actions: List[str] = field(default_factory=list)


@dataclass
class SourceRepo(HarvestBase):
    category: str = ""
    reason_to_inspect: str = ""
    expected_artifact_types: List[str] = field(default_factory=list)
    action: str = "inspect_or_pattern_only"


@dataclass
class RepoSearchQueryPack:
    query_id: str
    search_terms: List[str]
    target_subsystems: List[str]
    desired_patterns: List[str]
    blocked_license_types: List[str]
    minimum_license_requirements: List[str]
    security_risks: List[str]
    expected_outputs: List[str]
    priority: int


@dataclass
class CandidateRepo(HarvestBase):
    domain: str = ""
    likely_license: str = "unknown"
    usefulness_score: int = 0
    maturity_score: int = 0
    maintenance_signal: int = 0
    subsystem_fit_score: int = 0
    integration_complexity: int = 0
    dependency_risk: int = 0
    license_risk: int = 0
    security_risk: int = 0
    total_priority_score: int = 0


@dataclass
class LicenseCompatibilityRecord(HarvestBase):
    detected_license: str = "unknown"
    can_copy_code: bool = False
    can_copy_docs: bool = False
    can_adapt_patterns: bool = True
    notice_required: bool = True
    manual_review_required: bool = True
    decision_rationale: str = ""


@dataclass
class ReusablePattern:
    pattern_id: str
    source_repos: List[str]
    description: str
    target_subsystems: List[str]
    copy_mode: str
    required_attribution: bool
    implementation_notes: List[str]
    compatibility_notes: List[str]
    priority: int


@dataclass
class SubsystemIntegrationBlueprint:
    target_subsystem: str
    source_pattern: str
    implementation_mode: str
    files_to_add_or_update: List[str]
    expected_outputs: List[str]
    tests_required: List[str]
    guardrails_required: List[str]
    risk_level: str
    priority: int


@dataclass
class AdapterGapRecord:
    gap_id: str
    current_state: str
    desired_state: str
    source_repo_pattern: str
    implementation_priority: str
    blocked_by: List[str]
    safe_fixture_first: bool
    expected_tests: List[str]


@dataclass
class CopiedArtifactAttribution:
    direct_code_copies: List[Dict[str, Any]]
    status: str
    policy: str


@dataclass
class PatternOnlyRecord(HarvestBase):
    pattern_summary: str = ""


@dataclass
class CompatibilityPatch:
    patch_id: str
    target_subsystem: str
    patch_goal: str
    constraints: List[str]
    patch_steps: List[str]
    priority: int


@dataclass
class ExternalSystemScore(HarvestBase):
    system_capability: str = ""
    score: int = 0


@dataclass
class IntegrationPriorityItem:
    item_id: str
    subsystem: str
    reason: str
    score: int
    next_steps: List[str]


@dataclass
class HarvestValidationResult:
    status: str
    checks: List[Dict[str, Any]]
    errors: List[str]


@dataclass
class CommandCenterHarvestPayload:
    payload_id: str
    generated_at: str
    status: str
    metrics: Dict[str, Any]


@dataclass
class RAGHarvestEntry:
    doc_id: str
    title: str
    source: str
    summary: str
    guardrails: List[str]


def to_dict(obj: Any) -> Dict[str, Any]:
    return asdict(obj)
