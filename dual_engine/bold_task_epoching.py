"""Event-related trial-locking helpers for BOLD task fMRI (ds005237 Stroop).

The signed/localized phase-topology metric (bold_phase_topology) was built for
whole-run resting-state data. For an event-related task it must be windowed to the
condition of interest, or the signal is smeared across a mostly-congruent 6.8-min
run. This module provides:

- condition_tr_masks: assign each TR to a condition's hemodynamic-response window
  (onset+hrf_lo .. onset+hrf_hi), excluding TRs claimed by both conditions
  (jittered-ISI overlap). The signed topology is then computed on the whole-run
  Hilbert phase RESTRICTED to each condition's TRs (filtering/Hilbert is done on
  the full run to avoid short-epoch filter artifacts; only the SELECTION is
  trial-locked -- the methodologically sound way to trial-lock a phase metric).
- glm_activation_contrast: the STANDARD comparator -- a canonical-HRF first-level
  GLM incongruent>congruent activation beta per parcel (the same modeling logic
  the dataset's technical-validation paper used to confirm cingulate/lateral-PFC
  responsiveness).

New, additive; the tested functions in bold_phase_topology / montage_topology /
surrogate_testing are unchanged.
"""
from __future__ import annotations

import numpy as np


def condition_tr_masks(onsets, conds, n_tr: int, tr: float,
                       hrf_lo: float = 3.0, hrf_hi: float = 9.0
                       ) -> dict[str, np.ndarray]:
    """Boolean TR masks per condition over the HRF window [onset+hrf_lo, onset+hrf_hi].

    onsets: array of trial onset times (s). conds: array of condition labels
    (e.g. 'con'/'inc'), same length. A TR claimed by more than one condition
    (overlapping jittered windows) is excluded from all condition masks and
    reported in the 'overlap' entry. The BOLD HRF to a brief stimulus peaks
    ~4-6 s post-onset and decays over several more; [3, 9] s captures the peak
    and immediate tail. Returns {label: mask, ..., 'overlap': mask}.
    """
    onsets = np.asarray(onsets, dtype=float)
    conds = np.asarray(conds)
    if onsets.shape != conds.shape:
        raise ValueError("onsets and conds must have the same shape")
    if n_tr < 1 or tr <= 0:
        raise ValueError(f"bad n_tr/tr: {n_tr}, {tr}")
    labels = [str(c) for c in np.unique(conds)]
    raw = {lab: np.zeros(n_tr, dtype=int) for lab in labels}
    for o, c in zip(onsets, conds):
        lo = int(np.ceil((o + hrf_lo) / tr))
        hi = int(np.floor((o + hrf_hi) / tr))
        lo = max(0, lo); hi = min(n_tr - 1, hi)
        if hi >= lo:
            raw[str(c)][lo:hi + 1] = 1
    stacked = np.sum([m > 0 for m in raw.values()], axis=0)
    overlap = stacked > 1
    out = {lab: (raw[lab] > 0) & ~overlap for lab in labels}
    out["overlap"] = overlap
    return out


def glm_activation_contrast(ts, onsets, conds, durations, tr,
                            contrast=("inc", "con"), hrf_model: str = "glover"
                            ) -> np.ndarray:
    """Standard comparator: per-parcel (contrast[0] - contrast[1]) activation beta
    from a canonical-HRF first-level GLM. ts: (n_parcels, n_tr). Returns
    (n_parcels,) contrast betas. Uses nilearn's design-matrix construction."""
    import pandas as pd
    from nilearn.glm.first_level import make_first_level_design_matrix

    ts = np.asarray(ts, dtype=float)
    n_parcels, n_tr = ts.shape
    frame_times = np.arange(n_tr) * tr
    ev = pd.DataFrame({"onset": np.asarray(onsets, float),
                       "duration": np.asarray(durations, float),
                       "trial_type": [str(c) for c in conds]})
    dm = make_first_level_design_matrix(frame_times, ev, hrf_model=hrf_model,
                                        drift_model="cosine", high_pass=0.01)
    cols = list(dm.columns)
    if contrast[0] not in cols or contrast[1] not in cols:
        raise ValueError(f"contrast conditions {contrast} not in design {cols}")
    X = dm.values
    # OLS betas for all parcels at once: beta = (X'X)^-1 X' Y'
    XtX_inv = np.linalg.pinv(X.T @ X)
    betas = (XtX_inv @ X.T @ ts.T).T          # (n_parcels, n_regressors)
    ci = cols.index(contrast[0]); cj = cols.index(contrast[1])
    con = betas[:, ci] - betas[:, cj]
    if not np.all(np.isfinite(con)):
        raise ValueError("non-finite GLM contrast")
    return con
