"""Tests for the code-executed dataset onboarding registry and the generic,
registry-driven Level-M modules that replaced the per-dataset duplication.

The decisive guarantee under test: the generic evaluate/write produce
BYTE-IDENTICAL output to each existing per-dataset `{ds}_windows.py`, so
migrating the 3 eligible datasets onto the generic path is a refactor, not a
behavior change.
"""
from __future__ import annotations

import importlib
import tempfile
from dataclasses import asdict
from pathlib import Path

import pytest

from sciencer_d.btc_icft.datasets.onboarding_registry import (
    DatasetConfig,
    get_dataset_config,
    load_registry,
    registered_dataset_ids,
)
import sciencer_d.btc_icft.level_m.generic_windows as G

_ELIGIBLE = ["ds005620", "ds003969", "ds003816"]


# ── registry loading ─────────────────────────────────────────────────────────

def test_registry_loads_eligible_datasets():
    ids = registered_dataset_ids()
    for ds in _ELIGIBLE:
        assert ds in ids
    # ds001787 is deliberately NOT registered (dual-mode shape stays separate)
    assert "ds001787" not in ids


def test_registry_task_to_state_matches_existing_shims():
    """The registry must reproduce each shipped shim's `_TASK_TO_STATE` exactly --
    a drift here would silently mislabel real windows."""
    for ds in _ELIGIBLE:
        cfg = get_dataset_config(ds)
        shim = importlib.import_module(f"sciencer_d.btc_icft.level_m.{ds}_windows_real")
        assert cfg.task_to_state == shim._TASK_TO_STATE


def test_unknown_dataset_raises_keyerror_listing_registered():
    with pytest.raises(KeyError, match="not in onboarding registry"):
        get_dataset_config("ds_does_not_exist")


def test_contrast_lookup_and_unknown_task():
    cfg = get_dataset_config("ds005620")
    assert cfg.contrast("awake_vs_sedated").label_field == "state_label"
    with pytest.raises(ValueError, match="Unknown task"):
        cfg.contrast("nope")


def test_invalid_label_field_rejected(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"datasets": {"dsX": {"dataset_id": "dsX", "task_to_state": {"a": "a"},'
        ' "contrasts": [{"name": "c", "label_field": "not_a_field", "class0": "a", "class1": "b"}],'
        ' "default_task": "c"}}}'
    )
    with pytest.raises(ValueError, match="invalid label_field"):
        load_registry(str(bad))


# ── byte-identical consolidation guarantee ───────────────────────────────────

def _synthetic_rows(RowClass, triples):
    rows = []
    for i, (st, beh, rep) in enumerate(triples):
        rows.append(RowClass(
            row_id=f"sub-0{i}_win-0", subject_id=f"sub-0{i % 2}", session_id="ses-01", run_id="01",
            window_id="win-0", task_label=st, state_label=st, behavior_label=beh, report_label=rep,
            y=None, spectral_power_proxy=0.1 + i * 0.05, entropy_proxy=0.3, lzc_proxy=0.2, artifact_score=0.1 * i,
            source_file=f"mock/{st}.edf", window_start_s=0.0, window_end_s=10.0, warnings=[]))
    return rows


_SAMPLES = {
    "ds005620": [("awake", "responsive", "experience"), ("sedated", "unresponsive", "no_experience"), ("other", "x", "y")],
    "ds003969": [("meditation", None, None), ("thinking", None, None), ("other", None, None)],
    "ds003816": [("meditation", None, None), ("resting", None, None), ("other", None, None)],
}


@pytest.mark.parametrize("ds", _ELIGIBLE)
def test_generic_evaluate_byte_identical_to_per_dataset(ds):
    old = importlib.import_module(f"sciencer_d.btc_icft.level_m.{ds}_windows")
    cfg = get_dataset_config(ds)
    triples = _SAMPLES[ds]
    r_old = old.evaluate_level_m_windows(_synthetic_rows(old.LevelMWindowRow, triples), task=cfg.default_task)
    r_gen = G.evaluate_level_m_windows(_synthetic_rows(G.LevelMWindowRow, triples), cfg, task=cfg.default_task)
    assert asdict(r_old) == asdict(r_gen)


@pytest.mark.parametrize("ds", _ELIGIBLE)
def test_generic_write_outputs_byte_identical_to_per_dataset(ds):
    old = importlib.import_module(f"sciencer_d.btc_icft.level_m.{ds}_windows")
    cfg = get_dataset_config(ds)
    triples = _SAMPLES[ds]
    r_old = old.evaluate_level_m_windows(_synthetic_rows(old.LevelMWindowRow, triples), task=cfg.default_task)
    r_gen = G.evaluate_level_m_windows(_synthetic_rows(G.LevelMWindowRow, triples), cfg, task=cfg.default_task)
    to = Path(tempfile.mkdtemp()); tg = Path(tempfile.mkdtemp())
    old.write_level_m_window_outputs(r_old, str(to))
    G.write_level_m_window_outputs(r_gen, str(tg), cfg)
    for name in ("features_m.csv", "metrics_m.json", "artifact_report.json",
                 "leakage_report.json", "omega_event.json", "report.md"):
        assert (to / name).read_text() == (tg / name).read_text(), f"{ds}/{name} differs"


def test_all_ds005620_contrasts_byte_identical():
    old = importlib.import_module("sciencer_d.btc_icft.level_m.ds005620_windows")
    cfg = get_dataset_config("ds005620")
    triples = _SAMPLES["ds005620"]
    for task in ("awake_vs_sedated", "responsive_vs_unresponsive", "experience_vs_no_experience"):
        r_old = old.evaluate_level_m_windows(_synthetic_rows(old.LevelMWindowRow, triples), task=task)
        r_gen = G.evaluate_level_m_windows(_synthetic_rows(G.LevelMWindowRow, triples), cfg, task=task)
        assert asdict(r_old) == asdict(r_gen), f"contrast {task} differs"
