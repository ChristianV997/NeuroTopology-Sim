"""Local, deterministic research-claim audit layer.

This package classifies and audits scientific-language claims. It never
rewrites claim text or scientific results. Audit findings live only in
the validator output.
"""

from .audit import audit_claims, audit_claims_payload
from .schema import (
    CLAIM_CATEGORIES,
    CLAIM_RECORD_FIELDS,
    EMPIRICAL_SYNTHETIC_STATUSES,
    PROXY_FORMAL_STATUSES,
    REVIEWER_STATES,
)

__all__ = [
    "CLAIM_CATEGORIES",
    "CLAIM_RECORD_FIELDS",
    "EMPIRICAL_SYNTHETIC_STATUSES",
    "PROXY_FORMAL_STATUSES",
    "REVIEWER_STATES",
    "audit_claims",
    "audit_claims_payload",
]
