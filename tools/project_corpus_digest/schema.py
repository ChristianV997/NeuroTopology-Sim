from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class _Row:
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LocalSourceRegistryItem(_Row):
    id: str; name: str; path: str; artifact_type: str; category: str; claim_scope: str; evidence_state: str
    allowed_use: str; prohibited_claims: List[str]; safety_notes: List[str]
    publication_lane: Optional[str] = None; reusable_asset_candidates: List[str] = field(default_factory=list)


@dataclass
class LocalFileInventoryRow(LocalSourceRegistryItem):
    size_bytes: int = 0


@dataclass
class ArchiveInventoryRow(LocalSourceRegistryItem):
    file_count: int = 0; top_level_folders: List[str] = field(default_factory=list); filetype_histogram: Dict[str, int] = field(default_factory=dict)


@dataclass
class DigestMatrixRow(LocalSourceRegistryItem):
    summary: str = ""


@dataclass
class ClaimRiskRow(_Row):
    id: str; name: str; path: str; artifact_type: str; category: str; claim_scope: str; evidence_state: str
    allowed_use: str; prohibited_claims: List[str]; safety_notes: List[str]
    risky_phrase: str = ""; safe_rewrite: str = ""; publication_lane: Optional[str] = None; reusable_asset_candidates: List[str] = field(default_factory=list)


@dataclass
class PublicationLane(_Row):
    id: str; name: str; path: str; artifact_type: str; category: str; claim_scope: str; evidence_state: str
    allowed_use: str; prohibited_claims: List[str]; safety_notes: List[str]
    publication_lane: Optional[str] = None; reusable_asset_candidates: List[str] = field(default_factory=list)


@dataclass
class ReusableAssetRow(_Row):
    id: str; name: str; path: str; artifact_type: str; category: str; claim_scope: str; evidence_state: str
    allowed_use: str; prohibited_claims: List[str]; safety_notes: List[str]
    publication_lane: Optional[str] = None; reusable_asset_candidates: List[str] = field(default_factory=list)


@dataclass
class ValidationResult(_Row):
    id: str; name: str; path: str; artifact_type: str; category: str; claim_scope: str; evidence_state: str
    allowed_use: str; prohibited_claims: List[str]; safety_notes: List[str]
    valid: bool = False; errors: List[str] = field(default_factory=list)
    publication_lane: Optional[str] = None; reusable_asset_candidates: List[str] = field(default_factory=list)


@dataclass
class RagPackItem(_Row):
    id: str; name: str; path: str; artifact_type: str; category: str; claim_scope: str; evidence_state: str
    allowed_use: str; prohibited_claims: List[str]; safety_notes: List[str]
    redaction_rules: List[str] = field(default_factory=list)
    publication_lane: Optional[str] = None; reusable_asset_candidates: List[str] = field(default_factory=list)
