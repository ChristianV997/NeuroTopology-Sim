"""Deterministic finite JSON reports and scientific-integrity disclaimers."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from ops.research_cycle.catalog import load_catalog
from ops.research_cycle.json_util import dumps, json_safe, load_finite_json, text_has_nonfinite_tokens
from ops.research_cycle.runner import RunConfig, run_audit
from ops.research_cycle.safety import require_output_dir

from tests.ops.research_cycle.conftest import CATALOG, REPO_ROOT


def test_json_safe_replaces_nonfinite_with_null():
    payload = json_safe({"ok": 1.0, "bad": math.nan, "inf": math.inf, "missing": None})
    assert payload["ok"] == 1.0
    assert payload["bad"] is None
    assert payload["inf"] is None
    assert payload["missing"] is None
    text = dumps(payload)
    assert "NaN" not in text
    assert "Infinity" not in text
    load_finite_json(text)


def test_text_has_nonfinite_tokens():
    assert text_has_nonfinite_tokens('{"x": NaN}')
    assert text_has_nonfinite_tokens('{"x": Infinity}')
    assert not text_has_nonfinite_tokens('{"x": null, "note": "finite"}')


def test_deterministic_report_repeat(tmp_path: Path):
    catalog = load_catalog(CATALOG)

    def _once(dest: Path) -> dict:
        config = RunConfig(
            repo_root=REPO_ROOT,
            output_dir=require_output_dir(dest),
            catalog=catalog,
            python=sys.executable,
            emit_surfaces_enabled=False,
            generated_at="2026-09-10T00:00:00+00:00",
            step_ids=("repository_state", "finite_json_no_network"),
        )
        report, _code = run_audit(config)
        return json.loads((config.output_dir / "research_cycle_audit.json").read_text(encoding="utf-8"))

    first = _once(tmp_path / "a")
    second = _once(tmp_path / "b")
    assert first["generated_at"] == second["generated_at"] == "2026-09-10T00:00:00+00:00"
    assert [step["id"] for step in first["steps"]] == [step["id"] for step in second["steps"]]
    assert first["disclaimers"] == second["disclaimers"]
    assert first["scientific_pass"] is False
    assert first["empirical_pass"] is False
    assert "Infrastructure PASS is not a scientific PASS." in first["disclaimers"]
    assert "Synthetic fixtures are not an empirical PASS." in first["disclaimers"]
    md = (tmp_path / "a" / "research_cycle_audit.md").read_text(encoding="utf-8")
    assert "Infrastructure PASS is not a scientific PASS." in md
    load_finite_json((tmp_path / "a" / "research_cycle_audit.json").read_text(encoding="utf-8"))
