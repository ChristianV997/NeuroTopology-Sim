from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.stats import pearsonr


def pcist_proxy(epoch_2d):
    """Compute lightweight temporal complexity surrogate, not canonical PCIst.

    Sums sign-transition count and mean active fraction of the channel-mean
    z-scored signal. This is a cheap proxy used for dataset-level scaffolding;
    it is not the canonical PCIst measure and must not be reported as one.
    """
    x = np.mean(epoch_2d, axis=0)
    z = (x - np.mean(x)) / (np.std(x) + 1e-12)
    b = (z > 0).astype(np.int8)
    transitions = np.sum(np.abs(np.diff(b)))
    active = np.mean(b)
    return float(transitions + active)


def pcist_surrogate(epoch_2d):
    """Deprecated alias for :func:`pcist_proxy`. Kept for backward compatibility."""
    return pcist_proxy(epoch_2d)


def q_pcist_correlation(df: pd.DataFrame):
    """Pearson r between Qabs and a PCI-like complexity column.

    Prefers ``pcist_proxy`` and falls back to legacy ``PCIst`` when present.
    Returns NaNs when neither column is present.
    """
    if "Qabs" not in df.columns:
        return {"r": np.nan, "p": np.nan}
    if "pcist_proxy" in df.columns:
        col = "pcist_proxy"
    elif "PCIst" in df.columns:
        col = "PCIst"
    else:
        return {"r": np.nan, "p": np.nan}
    sub = df[["Qabs", col]].dropna()
    if len(sub) < 3:
        return {"r": np.nan, "p": np.nan, "n": int(len(sub))}
    r, p = pearsonr(sub["Qabs"], sub[col])
    return {"r": float(r), "p": float(p), "n": int(len(sub))}
