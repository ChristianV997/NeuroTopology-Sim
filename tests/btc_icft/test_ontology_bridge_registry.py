"""Tests for ontology bridge registry (O2)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sciencer_d.btc_icft.ontology.bridges import (
    load_bridge_registry,
    parse_bridges,
    summarize_bridge_status,
    validate_bridge_registry,
)


_REGISTRY_PATH = Path(__file__).parent.parent.parent / "configs" / "btc_icft" / "ontology_bridge_registry.json"


def _load() -> dict:
    return load_bridge_registry(str(_REGISTRY_PATH))


def test_registry_loads_and_has_bridges():
    reg = _load()
    assert reg["bridges"]
    assert len(reg["bridges"]) >= 6


def test_registry_validates_clean():
    reg = _load()
    errors = validate_bridge_registry(reg)
    assert errors == [], f"unexpected validation errors: {errors}"


def test_bridge_ids_unique():
    reg = _load()
    ids = [b["bridge_id"] for b in reg["bridges"]]
    assert len(ids) == len(set(ids))


def test_invalid_layer_rejected():
    reg = _load()
    bad = copy.deepcopy(reg)
    bad["bridges"][0]["source_layer"] = "NOT_A_LAYER"
    errors = validate_bridge_registry(bad)
    assert any("invalid source_layer" in e for e in errors)


def test_o_target_bridge_defaults_to_quarantine():
    reg = _load()
    for b in reg["bridges"]:
        if b["target_layer"] == "O_ONTOLOGY_CANDIDATE":
            assert b.get("always_quarantined") or (
                b.get("promotion_thresholds", {}).get("requires_independent_dataset")
                and b.get("promotion_thresholds", {}).get("requires_mechanism_evidence")
            ), f"{b['bridge_id']}: ontology-target must be quarantined or require independent evidence"


def test_forbidden_phrases_rejected_in_allowed_claim():
    reg = _load()
    bad = copy.deepcopy(reg)
    bad["bridges"][0]["allowed_claim"] = "This proves consciousness clearly."
    errors = validate_bridge_registry(bad)
    assert any("forbidden phrase" in e for e in errors)


def test_summarize_bridge_status_mock_blocks_real_execution():
    reg = _load()
    bridges = parse_bridges(reg)
    # B1 requires real execution
    b1 = next(b for b in bridges if b.bridge_id == "B1_M_MARKERS_TO_REVIEWED_LABELS")
    status = summarize_bridge_status(b1, set(), set(), "mock_e2e")
    assert status["status"] == "blocked_pending_real_execution"


def test_summarize_bridge_status_quarantined_bridge():
    reg = _load()
    bridges = parse_bridges(reg)
    b4 = next(b for b in bridges if b.bridge_id == "B4_NO_DIRECT_CONSCIOUSNESS_EQUIVALENCE")
    status = summarize_bridge_status(b4, set(), set(), "real_local")
    assert status["status"] == "quarantined"
