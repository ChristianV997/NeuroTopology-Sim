from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List

@dataclass
class ToLSource:
    source_id: str
    path: str
    title: str
    extension: str
    parse_status: str
    size_bytes: int
    sha256: str
    detected_keywords: List[str]
    source_role: str

@dataclass
class ToLClaim:
    claim_id: str
    source_id: str
    text: str
    normalized_text: str
    tier: str
    category: str
    confidence: float
    evidence_status: str
    allowed_use: str
    rewrite_required: bool
    unsafe_terms: List[str] = field(default_factory=list)
    mapped_doctrine: List[str] = field(default_factory=list)
    mapped_construct: List[str] = field(default_factory=list)
    mapped_observables: List[str] = field(default_factory=list)

@dataclass
class ToLClaimTier:
    name: str
    description: str

@dataclass
class DoctrineConstructMap:
    mapping: dict

@dataclass
class ObservableMap:
    mapping: dict

@dataclass
class ToLDigestResult:
    sources: List[ToLSource]
    claims: List[ToLClaim]

@dataclass
class ToLValidationResult:
    ok: bool
    errors: List[str]
    warnings: List[str]

def to_dict(obj):
    return asdict(obj)
