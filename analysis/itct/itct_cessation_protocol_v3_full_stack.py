"""ITCT cessation protocol v3 — real, runnable full-stack pipeline.

Replaces the prior 64-byte placeholder. Computes real quantities from a phase-locking-value
(PLV) series that is EITHER derived from real BIDS EEG windows (provenance="real_bids") OR
generated synthetically (provenance="synthetic_proxy"). Provenance is recorded in every output
record — synthetic results never masquerade as real EEG.

Metrics (real numerics; persistent homology via the maintained `ripser` library, not a
custom reimplementation):
  beta1              — count of persistent H1 (loop) features from `ripser` alive at the given
                       PLV similarity threshold. Real persistent homology, not a graph-theory
                       proxy.
  spectral_dimension — from the PLV-graph Laplacian eigenvalue staircase (networkx).
  loschmidt_echo     — |<psi0|e^{-iHt}|psi0>|^2 for an effective Hamiltonian from the PLV matrix
                       (scipy.linalg.expm).
  ep_discriminant    — discriminant of a 2x2 non-Hermitian Hamiltonian; ~0 => exceptional point.
  tus_engaged        — threshold control flag (a biometric control policy; NOT a clinical or
                       spiritual efficacy claim).

NOT validated here (labelled in output.not_validated_here): hyperscanning collective resilience
(needs simultaneous multi-subject recordings), SYK scrambling, quantum extremal surfaces.

`_plv_from_windows`, `compute_beta1`, `compute_persistence_diagram`, and
`compute_spectral_dimension` are thin wrappers over `analysis/connectivity_topology.py`,
which is the real, independently-tested, reusable home for this module's real PLV +
persistent-homology core (factored out so other pipelines -- e.g. the BTC/ICFT dataset
reports, which never used this real connectivity/TDA machinery -- can reuse it without
depending on this file's more speculative extras below, which stay here unpromoted).

Usage:
  python -m analysis.itct.itct_cessation_protocol_v3_full_stack --bids-root <ds005620> \
      --subject 01 --task sedated --out outputs/itct
  python -m analysis.itct.itct_cessation_protocol_v3_full_stack --synthetic --out outputs/itct
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from analysis.connectivity_topology import compute_plv as _plv_from_windows  # noqa: E402
from analysis.connectivity_topology import (  # noqa: E402
    compute_beta1 as _shared_compute_beta1,
)
from analysis.connectivity_topology import (  # noqa: E402
    compute_persistence_diagram as _shared_compute_persistence_diagram,
)
from analysis.connectivity_topology import (  # noqa: E402
    compute_spectral_dimension as _shared_compute_spectral_dimension,
)


def load_plv_from_bids(bids_root, subject, task, n_windows=20, window_seconds=4.0, max_channels=16):
    from data.bids_ingest import discover_bids_eeg, _read_raw
    import mne

    records = [
        r for r in discover_bids_eeg(bids_root)
        if (r.subject_id or "").endswith(subject) and (r.task_label or "") == task
    ]
    if not records:
        raise FileNotFoundError(f"no EEG for sub-{subject} task-{task} under {bids_root}")
    raw = _read_raw(records[0].path)
    raw.load_data(verbose="ERROR")
    picks = mne.pick_types(raw.info, eeg=True)[:max_channels]
    sfreq = float(raw.info["sfreq"])
    win = int(window_seconds * sfreq)
    data = raw.get_data(picks=picks)
    series = []
    for w in range(n_windows):
        s, e = w * win, (w + 1) * win
        if e > data.shape[1]:
            break
        series.append(_plv_from_windows(data[:, s:e]))
    if not series:
        raise ValueError("recording too short for requested windows")
    return np.stack(series), "real_bids"


def synthetic_plv_series(n_windows=20, n_channels=16, seed=42):
    rng = np.random.default_rng(seed)
    series = []
    for w in range(n_windows):
        base = 0.3 + 0.5 * np.exp(-((w - n_windows / 2) ** 2) / (2 * (n_windows / 6) ** 2))
        M = np.full((n_channels, n_channels), base) + 0.1 * rng.standard_normal((n_channels, n_channels))
        M = np.clip((M + M.T) / 2, 0, 1)
        np.fill_diagonal(M, 1.0)
        series.append(M)
    return np.stack(series), "synthetic_proxy"


def compute_beta1(plv, threshold=0.5):
    """First Betti number via REAL persistent homology (ripser), not a cyclomatic-number proxy.

    Thin wrapper over `analysis.connectivity_topology.compute_beta1` (see that
    module's docstring for the full explanation) -- kept as a same-named,
    same-signature function here so existing callers/tests of this file don't
    need to change.
    """
    return _shared_compute_beta1(plv, threshold=threshold)


def compute_persistence_diagram(plv):
    """Full H0/H1 persistence diagrams (ripser), for manuscript-grade figures via persim.

    Thin wrapper over `analysis.connectivity_topology.compute_persistence_diagram`.
    """
    return _shared_compute_persistence_diagram(plv)


def compute_spectral_dimension(plv, threshold=0.5):
    """Spectral dimension from the PLV-graph Laplacian eigenvalue staircase.

    Thin wrapper over `analysis.connectivity_topology.compute_spectral_dimension`.
    """
    return _shared_compute_spectral_dimension(plv, threshold=threshold)


def build_effective_hamiltonian(plv, nonherm=0.1):
    H = plv.astype(complex)
    H += 1j * nonherm * np.diag(np.linspace(-1, 1, plv.shape[0]))
    return H


def loschmidt_echo(plv, t=1.0):
    from scipy.linalg import expm

    H = build_effective_hamiltonian(plv)
    C = H.shape[0]
    psi0 = np.ones(C, dtype=complex) / np.sqrt(C)
    amp = psi0.conj() @ (expm(-1j * H * t) @ psi0)
    return float(np.abs(amp) ** 2)


def exceptional_point_discriminant(kappa, g1, g2, w0=1.0):
    a, d, b, c = w0 - 1j * g1, w0 - 1j * g2, kappa, kappa
    return float(np.abs((a - d) ** 2 + 4 * b * c))


@dataclass
class ITCTWindowRecord:
    window: int
    beta1: int
    spectral_dimension: float
    loschmidt_echo: float
    ep_discriminant: float
    tus_engaged: bool
    provenance: str


def run(plv_series, provenance, tus_beta1_threshold=2):
    records = []
    for w, plv in enumerate(plv_series):
        b1 = compute_beta1(plv)
        records.append(asdict(ITCTWindowRecord(
            window=w, beta1=b1,
            spectral_dimension=compute_spectral_dimension(plv),
            loschmidt_echo=loschmidt_echo(plv),
            ep_discriminant=exceptional_point_discriminant(0.5, 0.2, 0.2),
            tus_engaged=b1 <= tus_beta1_threshold,
            provenance=provenance,
        )))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description="ITCT cessation protocol v3 (real full stack)")
    ap.add_argument("--bids-root", default=None)
    ap.add_argument("--subject", default="01")
    ap.add_argument("--task", default="sedated")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--n-windows", type=int, default=20)
    ap.add_argument("--out", default="outputs/itct")
    args = ap.parse_args()

    if args.bids_root and not args.synthetic:
        plv_series, provenance = load_plv_from_bids(args.bids_root, args.subject, args.task, n_windows=args.n_windows)
    else:
        plv_series, provenance = synthetic_plv_series(n_windows=args.n_windows)

    records = run(plv_series, provenance)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "protocol": "itct_cessation_v3",
        "provenance": provenance,
        "n_windows": len(records),
        "not_validated_here": ["hyperscanning_collective_resilience", "syk_scrambling", "quantum_extremal_surfaces"],
        "records": records,
    }
    (out / "itct_cessation_result.json").write_text(json.dumps(payload, indent=2))
    b1s = [r["beta1"] for r in records]
    print(f"provenance={provenance} n_windows={len(records)} beta1[min={min(b1s)},max={max(b1s)}] "
          f"le0={records[0]['loschmidt_echo']:.4f} -> {out/'itct_cessation_result.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
