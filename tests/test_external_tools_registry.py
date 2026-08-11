"""ExternalToolRegistry: load/save/query over the real committed seed
registry (external_tools/registry_seed.json) plus a synthetic registry for
isolated query/ranking behavior. No network access, no package installs --
this only reads the already-committed JSON file.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from external_tools.registry import ExternalToolRegistry, RegistryError
from external_tools.tool_record import ExternalToolRecordV1

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_PATH = _REPO_ROOT / "external_tools" / "registry_seed.json"


# ── seed registry ────────────────────────────────────────────────────────


def test_seed_registry_file_exists():
    assert _SEED_PATH.exists()


def test_seed_registry_loads():
    registry = ExternalToolRegistry.load(_SEED_PATH)
    assert len(registry.tools) >= 30


def test_seed_registry_validates_cleanly():
    registry = ExternalToolRegistry.load(_SEED_PATH)
    errors = registry.validate()
    assert errors == {}, errors


def test_seed_registry_contains_required_p0_free_open_tools():
    registry = ExternalToolRegistry.load(_SEED_PATH)
    required = {"mne-python", "mne-bids", "gudhi", "networkx", "nilearn"}
    missing = required - set(registry.tools)
    assert not missing, f"missing required tool_ids: {missing}"


def test_seed_registry_contains_all_mission_required_tools_by_name():
    registry = ExternalToolRegistry.load(_SEED_PATH)
    names = {t.name for t in registry.tools.values()}
    required_names = {
        "MNE-Python", "MNE-BIDS", "PyBIDS", "BIDS Validator", "fMRIPrep",
        "Nilearn", "MOABB", "EEGDash", "GUDHI", "Ripser.py", "NetworkX",
        "KeplerMapper", "BrainFlow", "MNE-LSL", "Autoreject", "PyPREP",
        "pyRiemann", "Braindecode", "YASA", "NeuroKit2", "EEGLAB",
        "FieldTrip", "Brainstorm", "giotto-tda",
    }
    missing = required_names - names
    assert not missing, f"missing required tool names: {missing}"


def test_seed_registry_p0_tools_are_free_or_adapter_safe():
    registry = ExternalToolRegistry.load(_SEED_PATH)
    for t in registry.list_tools(priority="P0"):
        assert t.license_risk == "permissive_low" or t.integration_mode in (
            "adapter_only", "metadata_import",
        ), f"{t.tool_id}: {t.license_risk} / {t.integration_mode}"


def test_seed_registry_commercial_competitors_are_never_dependencies():
    registry = ExternalToolRegistry.load(_SEED_PATH)
    for t in registry.tools.values():
        if t.category in ("clinical_qeeg", "commercial_neurofeedback"):
            assert t.integration_mode not in ("dependency", "optional_backend"), t.tool_id


def test_seed_registry_giotto_tda_is_avoid_core():
    registry = ExternalToolRegistry.load(_SEED_PATH)
    giotto = registry.get("giotto-tda")
    assert giotto.integration_mode == "avoid_core"
    assert giotto.license_risk == "agpl_high"
    assert giotto.priority == "avoid"


def test_seed_registry_reference_competitors_are_reference_only():
    registry = ExternalToolRegistry.load(_SEED_PATH)
    for tool_id in ("eeglab", "fieldtrip", "brainstorm"):
        t = registry.get(tool_id)
        assert t.integration_mode == "reference_only", tool_id
        assert t.priority == "reference", tool_id


def test_seed_registry_hardware_sdks_are_paid_not_dependency():
    registry = ExternalToolRegistry.load(_SEED_PATH)
    for t in registry.list_tools(category="hardware_sdk"):
        assert t.integration_mode in ("paid_api", "paid_hardware"), t.tool_id


def test_seed_registry_no_forbidden_overclaim_language():
    result = subprocess.run(
        [sys.executable, "tools/check_claim_guardrails.py", str(_SEED_PATH)],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_seed_registry_every_record_has_risks_limitations_provenance():
    registry = ExternalToolRegistry.load(_SEED_PATH)
    for t in registry.tools.values():
        assert t.risks, t.tool_id
        assert t.limitations, t.tool_id
        assert t.provenance, t.tool_id


# ── synthetic registry: query / ranking behavior ────────────────────────


def _synthetic_registry() -> ExternalToolRegistry:
    def make(name, **overrides):
        kwargs = dict(
            category="topology_tda",
            license="MIT",
            license_risk="permissive_low",
            commercial_use_status="allowed_with_notice",
            integration_mode="dependency",
            priority="P1",
            current_status="planned",
            risks=["r"],
            limitations=["l"],
            provenance="p",
        )
        kwargs.update(overrides)
        return ExternalToolRecordV1.make(name=name, **kwargs)

    tools = {
        "p0-tool": make("P0 Tool", priority="P0", integration_mode="metadata_import", artifact_outputs=["x"]),
        "p1-tool": make("P1 Tool", priority="P1"),
        "ref-tool": make(
            "Ref Tool", priority="reference", integration_mode="reference_only",
            commercial_use_status="reference_only",
        ),
        "avoid-tool": make(
            "Avoid Tool", priority="avoid", integration_mode="avoid_core",
            license_risk="agpl_high", commercial_use_status="avoid_core",
        ),
        "unknown-tool": make(
            "Unknown Tool", priority="P3", license="unknown", license_risk="unknown_high",
            integration_mode="reference_only", commercial_use_status="reference_only",
            metadata={"review_needed": True},
        ),
    }
    tools = {k: v for k, v in tools.items()}
    reg = ExternalToolRegistry({t.tool_id: t for t in tools.values()})
    return reg


def test_registry_get_and_list_tools():
    registry = _synthetic_registry()
    assert registry.get("p0-tool").name == "P0 Tool"
    try:
        registry.get("does-not-exist")
        assert False
    except RegistryError:
        pass
    assert {t.tool_id for t in registry.list_tools(priority="P0")} == {"p0-tool"}


def test_registry_save_and_reload_round_trips(tmp_path):
    registry = _synthetic_registry()
    out_path = registry.save(tmp_path / "registry.json")
    reloaded = ExternalToolRegistry.load(out_path)
    assert set(reloaded.tools) == set(registry.tools)


def test_recommended_next_excludes_reference_avoid_and_unknown():
    registry = _synthetic_registry()
    ranked_ids = {t.tool_id for t in registry.recommended_next()}
    assert "ref-tool" not in ranked_ids
    assert "avoid-tool" not in ranked_ids
    assert "unknown-tool" not in ranked_ids
    assert "p0-tool" in ranked_ids
    assert "p1-tool" in ranked_ids


def test_recommended_next_ranks_p0_before_p1():
    registry = _synthetic_registry()
    ranked = registry.recommended_next()
    ranked_ids = [t.tool_id for t in ranked]
    assert ranked_ids.index("p0-tool") < ranked_ids.index("p1-tool")


def test_recommended_next_respects_limit():
    registry = _synthetic_registry()
    ranked = registry.recommended_next(limit=1)
    assert len(ranked) == 1
    assert ranked[0].tool_id == "p0-tool"
