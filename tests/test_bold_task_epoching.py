from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_MOD = Path(__file__).resolve().parents[1] / "dual_engine" / "bold_task_epoching.py"
_spec = importlib.util.spec_from_file_location("bold_task_epoching", _MOD)
bte = importlib.util.module_from_spec(_spec)
import sys as _sys
_sys.modules["bold_task_epoching"] = bte
_spec.loader.exec_module(bte)


def test_condition_tr_masks_basic_and_overlap_excluded():
    # con at t=0 (window 3-9s), inc at t=10 (window 13-19s) -> disjoint at tr=1
    onsets = np.array([0.0, 10.0])
    conds = np.array(["con", "inc"])
    m = bte.condition_tr_masks(onsets, conds, n_tr=30, tr=1.0, hrf_lo=3.0, hrf_hi=9.0)
    assert m["con"].sum() > 0 and m["inc"].sum() > 0
    # no TR is in both condition masks
    assert not np.any(m["con"] & m["inc"])
    # con window ~ tr 3..9, inc window ~ tr 13..19
    assert m["con"][3] and m["con"][9] and not m["con"][13]
    assert m["inc"][13] and m["inc"][19] and not m["inc"][3]


def test_condition_tr_masks_overlap_reported_and_excluded():
    # two conditions whose HRF windows overlap -> overlap TRs excluded from both
    onsets = np.array([0.0, 1.0])
    conds = np.array(["con", "inc"])
    m = bte.condition_tr_masks(onsets, conds, n_tr=20, tr=1.0, hrf_lo=3.0, hrf_hi=9.0)
    assert m["overlap"].sum() > 0
    assert not np.any(m["con"] & m["overlap"])
    assert not np.any(m["inc"] & m["overlap"])


def test_condition_tr_masks_validation():
    with pytest.raises(ValueError):
        bte.condition_tr_masks(np.array([0.0, 1.0]), np.array(["con"]), 10, 1.0)


def test_glm_activation_contrast_recovers_injected_response():
    rng = np.random.default_rng(0)
    tr, n_tr, n_parcels = 1.0, 200, 8
    # incongruent onsets every ~20s, congruent offset
    inc_on = np.arange(5, 190, 20.0)
    con_on = np.arange(12, 190, 20.0)
    onsets = np.concatenate([inc_on, con_on])
    conds = np.array(["inc"] * len(inc_on) + ["con"] * len(con_on))
    durations = np.full(len(onsets), 2.0)
    # build an inc HRF regressor and inject it strongly into parcel 0 only
    import pandas as pd
    from nilearn.glm.first_level import make_first_level_design_matrix
    ft = np.arange(n_tr) * tr
    dm = make_first_level_design_matrix(
        ft, pd.DataFrame({"onset": onsets, "duration": durations,
                          "trial_type": list(conds)}), hrf_model="glover")
    inc_reg = dm["inc"].values
    ts = 0.2 * rng.standard_normal((n_parcels, n_tr))
    ts[0] += 5.0 * inc_reg          # parcel 0 responds to incongruent trials
    con = bte.glm_activation_contrast(ts, onsets, conds, durations, tr)
    assert con.shape == (n_parcels,)
    # parcel 0 has by far the largest inc>con contrast
    assert con[0] == pytest.approx(np.max(con)) and con[0] > 1.0
