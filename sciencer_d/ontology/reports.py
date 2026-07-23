"""Deterministic Level O report and machine-readable artifact generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .registry import OntologyRegistry
from .schemas import OntologyEvidenceEvent
from .scoring import score_claim


REPORT_TITLE = (
    "What Can We Say About Consciousness, Awareness, Self, Soul, and Ontology?"
)


def _write_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _render_report(registry: OntologyRegistry, scores: list[dict[str, Any]]) -> str:
    scores_by_id = {row["claim_id"]: row for row in scores}
    claim_rows = "\n".join(
        f"| {claim.claim_id} | {claim.title} | {scores_by_id[claim.claim_id]['status']} | "
        f"{claim.ladder_level} |"
        for claim in registry.claims
    )
    score_rows = "\n".join(
        f"| {row['claim_id']} | {row['composite']:.4f} | {row['status']} |"
        for row in scores
    )
    current = [
        claim.title
        for claim in registry.claims
        if scores_by_id[claim.claim_id]["status"] in {"O-A", "O-B"}
    ]
    speculative = [
        claim.title
        for claim in registry.claims
        if scores_by_id[claim.claim_id]["status"] == "O-C"
    ]
    current_lines = "\n".join(f"- {title}" for title in current) or "- None"
    speculative_lines = "\n".join(f"- {title}" for title in speculative) or "- None"
    next_experiments = "\n".join(
        f"- **{claim.claim_id}:** {requirement}"
        for claim in registry.claims
        for requirement in claim.required_evidence[:1]
    )

    return f"""# {REPORT_TITLE}

## 1. Executive thesis
Level O is a claim-governed evidence ledger downstream of empirical BTC/ICFT work. Its classifications describe evidence posture and never establish an ontology by themselves.

This report indexes {len(registry.papers)} curated records, {len(registry.claim_links)} bounded claim links, and {len(registry.falsifiers)} explicit falsifiers. Registry content never changes a claim status automatically.

## 2. Ontology ladder H0-H4
- **H0:** engineering and fixture behavior
- **H1:** empirical state-marker associations
- **H2:** falsifiable mechanism bridges
- **H3:** phenomenological and comparative-ontology bridges
- **H4:** speculative ontology candidates under explicit quarantine

## 3. Claim table
| Claim ID | Title | Evaluated status | Ladder |
| --- | --- | --- | --- |
{claim_rows}

## 4. Score table
| Claim ID | Composite | Status |
| --- | ---: | --- |
{score_rows}

## 5. What can be stated now
These entries are bounded empirical or bridge hypotheses, subject to their listed evidence requirements:
{current_lines}

## 6. What remains speculative
These entries remain quarantined ontology candidates:
{speculative_lines}

## 7. Forbidden claims
Identity equations, metaphysical proof language, automatic spiritual attainment inference, and fixture-to-empirical promotion are rejected by policy.

## 8. Required evidence for promotion
Promotion requires independent empirical evidence, explicit falsifiers, matched controls, preregistered analyses where applicable, and human review. Philosophical coherence alone is insufficient.

## 9. BTC/ICFT mapping
BTC/ICFT outputs may constrain or motivate bridge hypotheses. They cannot automatically promote a Level O claim or establish person-level identity, postmortem persistence, or metaphysical finality.

## 10. Next experiments
{next_experiments}
"""


def build_ontology_report(
    out_dir: str | Path,
    registry: OntologyRegistry | None = None,
) -> dict[str, Path]:
    ledger = registry or OntologyRegistry.load()
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)

    scores = [score_claim(claim).to_dict() for claim in ledger.claims]
    status_by_id = {row["claim_id"]: row["status"] for row in scores}
    links_by_claim = {
        claim.claim_id: [
            link.paper_id
            for link in ledger.claim_links
            if link.claim_id == claim.claim_id
        ]
        for claim in ledger.claims
    }
    events = [
        OntologyEvidenceEvent(
            event_id=f"SEED-{index:03d}",
            claim_id=claim.claim_id,
            event_type="curated_seed_review",
            description="Curated references registered without automatic promotion",
            source_ids=links_by_claim[claim.claim_id],
            resulting_status=status_by_id[claim.claim_id],
        ).to_dict()
        for index, claim in enumerate(ledger.claims, start=1)
    ]

    paths = {
        "report": output / "level_o_ontology_report.md",
        "claims": output / "ontology_claims.json",
        "scores": output / "ontology_scores.json",
        "events": output / "ontology_evidence_events.json",
    }
    paths["report"].write_text(_render_report(ledger, scores), encoding="utf-8")
    _write_json(paths["claims"], [claim.to_dict() for claim in ledger.claims])
    _write_json(paths["scores"], scores)
    _write_json(paths["events"], events)
    return paths
