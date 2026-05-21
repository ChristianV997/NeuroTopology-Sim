from __future__ import annotations

def build_reviewed_contract_audit(data_audit: dict) -> dict:
    has_contract = any(c.get("category") == "reviewed_contract" and c.get("found") for c in data_audit.get("checks", []))
    return {
        "dataset_id": "DS005620",
        "contract_found": has_contract,
        "requires_human_peer_review": True,
        "peer_review_confirmed_by_human": False,
        "missing_contract_items": [] if has_contract else ["reviewed_contract_materialized", "peer_review_signoff"],
    }
