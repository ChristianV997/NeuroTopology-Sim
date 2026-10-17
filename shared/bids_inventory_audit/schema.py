"""Constants for the synthetic-only BIDS inventory and checksum boundary.

Nothing in this module identifies a dataset, a cohort, a license, or a registration.
The status values describe what the helper can and cannot establish. The scope string
mirrors the vocabulary of the Round 6 statement. This package is an independent
reimplementation and does not import or reuse any Round 6 code.
"""
from __future__ import annotations

import hashlib
import re

SCHEMA = "NeuroTopologySim.BidsInventoryAudit.v1"
SCOPE = "INVENTORY_LEVEL_ONLY_PENDING_AUTHORITATIVE_MANIFEST"
STATUS = "HOLD"
EVIDENCE_CLASS = "SYNTHETIC_ONLY"
COHORT_IDENTITY = "NOT_ESTABLISHED"

# UNREGISTERED_DRAFT means no external timestamp or registration exists. Every result
# in this package carries it, whether or not a payload digest verified.
REGISTRATION_STATUS = "UNREGISTERED_DRAFT"

SUBJECT_RE = re.compile(r"sub-[A-Za-z0-9]+")
ENTITY_RE = re.compile(r"([A-Za-z]+)-([A-Za-z0-9]+)")
SUFFIX_RE = re.compile(r"[A-Za-z0-9]+")
TASK_LABEL_RE = re.compile(r"[A-Za-z0-9]+")
HEX64_RE = re.compile(r"[0-9a-f]{64}")

EMPTY_BYTES_SHA256 = hashlib.sha256(b"").hexdigest()

# Digests written as words, or as a repeated character, are never valid registrations.
PLACEHOLDER_TOKENS = frozenset({
    "tbd", "todo", "placeholder", "xxx", "none", "null", "changeme", "<sha256>", "<digest>",
})

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

# A backup or temporary copy is not a data file. Counting it would manufacture coverage.
BACKUP_SUFFIXES = frozenset({"bak", "tmp", "old", "orig", "swp", "part", "partial"})
