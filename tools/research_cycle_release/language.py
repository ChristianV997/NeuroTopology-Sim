"""Unsupported-language scans for report metadata."""
from __future__ import annotations

import re
from typing import List, Tuple

FORBIDDEN_STRONG_PHRASES = (
    "proved consciousness",
    "proves consciousness",
    "confirmed liberation",
    "confirms liberation",
    "demonstrated quantum coherence",
    "demonstrates quantum coherence",
    "scientific pass",
    "bayes factor proves",
    "causal evidence confirmed",
)
_CAUSAL = re.compile(r"\bcaus(?:e|ed|es|ing|ation|al)\b", re.IGNORECASE)
_PROXY_CAUSAL = re.compile(
    r"\bproxy\b.{0,40}\b(?:causal|causation|causes)\b|\bcausal\b.{0,40}\bproxy\b",
    re.IGNORECASE | re.DOTALL,
)


def find_forbidden_phrases(text: str) -> List[str]:
    if not text:
        return []
    lowered = text.lower()
    return sorted({p for p in FORBIDDEN_STRONG_PHRASES if p in lowered})


def scan_report_metadata(text: str) -> Tuple[List[str], bool, bool]:
    return (
        find_forbidden_phrases(text),
        bool(text) and bool(_CAUSAL.search(text)),
        bool(text) and bool(_PROXY_CAUSAL.search(text)),
    )
