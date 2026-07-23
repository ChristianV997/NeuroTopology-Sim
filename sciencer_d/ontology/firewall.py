"""Language firewall preventing Level O proof and identity overclaims."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml


@dataclass(frozen=True)
class FirewallResult:
    allowed: bool
    violations: list[str]


def normalize_claim_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    ascii_like = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_like).strip()


def load_forbidden_claims(path: str | Path | None = None) -> list[str]:
    source = Path(path) if path else Path(__file__).with_name("claims") / "forbidden_claims.yaml"
    payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    phrases = payload.get("forbidden_claims", [])
    if not isinstance(phrases, list) or not all(isinstance(item, str) for item in phrases):
        raise ValueError("forbidden_claims.yaml must contain a string list")
    return phrases


def scan_text(text: str, forbidden_claims: Iterable[str] | None = None) -> FirewallResult:
    normalized = normalize_claim_text(text)
    phrases = list(forbidden_claims) if forbidden_claims is not None else load_forbidden_claims()
    padded_text = f" {normalized} "
    violations = [
        phrase
        for phrase in phrases
        if f" {normalize_claim_text(phrase)} " in padded_text
    ]
    return FirewallResult(allowed=not violations, violations=violations)


def assert_allowed(text: str, forbidden_claims: Iterable[str] | None = None) -> None:
    result = scan_text(text, forbidden_claims)
    if not result.allowed:
        raise ValueError(f"Forbidden ontology claim language: {result.violations}")
