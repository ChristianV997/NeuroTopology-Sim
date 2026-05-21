from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List

@dataclass
class BaseRecord:
    id: str
    source: str = "local_fixture"
    title: str = ""
    authors: List[str] = field(default_factory=list)
    year: int = 0
    venue: str = ""
    url: str = ""
    doi: str = ""
    pmid: str = ""
    arxiv_id: str = ""
    semantic_scholar_id: str = ""
    openalex_id: str = ""
    abstract: str = ""
    source_metadata: Dict[str, Any] = field(default_factory=dict)
    query_pack: str = ""
    retrieval_mode: str = "fixture"
    evidence_tier: str = "T0_speculative_conceptual"
    relevance_score: float = 0.0
    novelty_score: float = 0.0
    method_quality_score: float = 0.0
    falsifier_value: float = 0.0
    integration_value: float = 0.0
    safety_value: float = 0.0
    maps_to_constructs: List[str] = field(default_factory=list)
    extracted_claims: List[Dict[str, Any]] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    falsifiers: List[str] = field(default_factory=list)
    recommended_action: str = "watch"
    claim_scope: str = "literature_summary"
    evidence_state: str = "metadata_only"
    source_artifacts: List[str] = field(default_factory=list)


def to_dict(obj):
    return asdict(obj)
