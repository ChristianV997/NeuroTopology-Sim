"""Loader and referential-integrity checks for Level O ledger data."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, TypeVar

import yaml

from .firewall import scan_text
from .schemas import (
    OntologyClaim,
    OntologyClaimLink,
    OntologyFalsifier,
    OntologyPaper,
    Record,
)


R = TypeVar("R", bound=Record)

REQUIRED_EVIDENCE_CATEGORIES = {
    "mainstream_consciousness_theories",
    "covert_consciousness",
    "minimal_nondual_awareness",
    "meditation_cessation_phenomenology",
    "nde_lucidity",
    "philosophy_of_mind",
    "bioelectric_basal_cognition",
    "em_field_bioelectromagnetism",
    "quantum_biophysical_candidates",
    "holography_qec",
    "cosmological_natural_selection",
    "theravada_state_space",
}


def _read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a mapping in {path}")
    return payload


def _records(path: Path, key: str, record_type: type[R]) -> list[R]:
    rows = _read_yaml(path).get(key, [])
    if not isinstance(rows, list):
        raise ValueError(f"{path} field {key!r} must be a list")
    return [record_type.from_dict(row) for row in rows]


def _assert_unique(values: list[str], label: str) -> None:
    duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
    if duplicates:
        raise ValueError(f"Duplicate {label}: {duplicates}")


@dataclass
class OntologyRegistry:
    claims: list[OntologyClaim]
    papers: list[OntologyPaper]
    claim_links: list[OntologyClaimLink]
    falsifiers: list[OntologyFalsifier]
    mappings: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @classmethod
    def load(cls, root: str | Path | None = None) -> "OntologyRegistry":
        base = Path(root) if root else Path(__file__).parent
        mappings = {
            name: _read_yaml(base / "mappings" / f"{name}_map.yaml").get("mappings", [])
            for name in ("btc_icft", "theravada", "cosmology", "philosophy")
        }
        registry = cls(
            claims=_records(
                base / "claims" / "ontology_claims.yaml",
                "claims",
                OntologyClaim,
            ),
            papers=_records(
                base / "evidence" / "papers.yaml",
                "papers",
                OntologyPaper,
            ),
            claim_links=_records(
                base / "evidence" / "claim_links.yaml",
                "claim_links",
                OntologyClaimLink,
            ),
            falsifiers=_records(
                base / "evidence" / "falsifiers.yaml",
                "falsifiers",
                OntologyFalsifier,
            ),
            mappings=mappings,
        )
        registry.validate()
        return registry

    def validate(self) -> None:
        claim_ids = [claim.claim_id for claim in self.claims]
        paper_ids = [paper.paper_id for paper in self.papers]
        falsifier_ids = [item.falsifier_id for item in self.falsifiers]
        _assert_unique(claim_ids, "claim IDs")
        _assert_unique(paper_ids, "paper IDs")
        _assert_unique(falsifier_ids, "falsifier IDs")
        _assert_unique(
            [f"{link.claim_id}:{link.paper_id}" for link in self.claim_links],
            "claim-paper links",
        )

        known_claims = set(claim_ids)
        known_papers = set(paper_ids)
        for link in self.claim_links:
            if link.claim_id not in known_claims:
                raise ValueError(f"Unknown claim link claim_id: {link.claim_id}")
            if link.paper_id not in known_papers:
                raise ValueError(f"Unknown claim link paper_id: {link.paper_id}")
        for falsifier in self.falsifiers:
            if falsifier.claim_id not in known_claims:
                raise ValueError(f"Unknown falsifier claim_id: {falsifier.claim_id}")
        claims_with_falsifiers = {item.claim_id for item in self.falsifiers}
        missing_falsifiers = sorted(known_claims - claims_with_falsifiers)
        if missing_falsifiers:
            raise ValueError(f"Claims missing falsifiers: {missing_falsifiers}")

        linked_papers = {link.paper_id for link in self.claim_links}
        unlinked_papers = sorted(known_papers - linked_papers)
        if unlinked_papers:
            raise ValueError(f"Papers without claim links: {unlinked_papers}")
        claims_with_links = {link.claim_id for link in self.claim_links}
        unlinked_claims = sorted(known_claims - claims_with_links)
        if unlinked_claims:
            raise ValueError(f"Claims without paper links: {unlinked_claims}")

        categories = {paper.category for paper in self.papers}
        missing_categories = sorted(REQUIRED_EVIDENCE_CATEGORIES - categories)
        if missing_categories:
            raise ValueError(f"Missing evidence categories: {missing_categories}")
        for mapping_name, rows in self.mappings.items():
            if not isinstance(rows, list):
                raise ValueError(f"Mapping {mapping_name} must be a list")
            for row in rows:
                claim_id = row.get("claim_id") if isinstance(row, dict) else None
                if claim_id not in known_claims:
                    raise ValueError(
                        f"Mapping {mapping_name} references unknown claim_id: {claim_id}"
                    )

        rejected = {}
        for claim in self.claims:
            result = scan_text(claim.statement)
            if not result.allowed:
                rejected[claim.claim_id] = result.violations
        if rejected:
            raise ValueError(f"Seed claim statements violate the firewall: {rejected}")

        evidence_text = json.dumps(
            {
                "papers": [paper.to_dict() for paper in self.papers],
                "claim_links": [link.to_dict() for link in self.claim_links],
                "falsifiers": [item.to_dict() for item in self.falsifiers],
                "mappings": self.mappings,
            },
            ensure_ascii=False,
        )
        evidence_scan = scan_text(evidence_text)
        if not evidence_scan.allowed:
            raise ValueError(
                f"Seed evidence violates the firewall: {evidence_scan.violations}"
            )

    def claim_by_id(self, claim_id: str) -> OntologyClaim:
        for claim in self.claims:
            if claim.claim_id == claim_id:
                return claim
        raise KeyError(claim_id)
