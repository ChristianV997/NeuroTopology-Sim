"""Determinism, no-network, and fingerprint contracts."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from tools.evidence_promotion_gate.adapters import load_case_dir
from tools.evidence_promotion_gate.evaluator import evaluate_case
from tools.evidence_promotion_gate.reporting import serialize_json

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PACKAGE = Path(__file__).resolve().parents[2] / "tools" / "evidence_promotion_gate"


def test_repeat_evaluation_is_deterministic():
    case = load_case_dir(FIXTURES / "proxy_k")
    first = evaluate_case(case)
    second = evaluate_case(load_case_dir(FIXTURES / "proxy_k"))
    left = first.to_dict()
    right = second.to_dict()
    left.pop("claim_gate", None)
    right.pop("claim_gate", None)
    if isinstance(left.get("claim_gate"), dict):
        pass
    assert serialize_json(first.to_dict()) == serialize_json(second.to_dict())
    assert first.input_fingerprints == second.input_fingerprints
    assert first.input_fingerprints["files"]
    assert first.input_fingerprints["combined"]


def test_package_does_not_import_network_clients():
    forbidden = {"requests", "httpx", "aiohttp", "urllib.request", "socket"}
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
                imported.add(node.module)
        assert forbidden.isdisjoint(imported), f"{path.name} imported {imported & forbidden}"


def test_scientific_pass_never_true_in_serialized_output():
    for name in ("engineering_ok", "descriptive_review_ok", "proxy_k", "synthetic_run"):
        payload = evaluate_case(load_case_dir(FIXTURES / name)).to_dict()
        text = serialize_json(payload)
        parsed = json.loads(text)
        assert parsed["scientific_pass"] is False
        assert parsed["formal_bayes_factor"] is None or name != "proxy_k"
