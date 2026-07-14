#!/usr/bin/env python3
"""Signed/localized phase-defect metrics on real propofol-sedation EEG (ds005620).

Purpose
-------
The signed-winding metrics added to validation/montage_topology.py
(signed_defect_map / net_charge_by_region / defect_spatial_clustering /
signed_defect_topology_from_band) were validated on synthetic fixtures only.
This pipeline is their first real-EEG test, on the axis ITCT's phase-winding
approach was originally built against: propofol-induced loss of consciousness,
where whole-brain topology is known from the literature to move hard (Betti-1
cycle collapse Awake~124 -> Propofol~14.6; Chennu/Sanders connectivity dampening).
It runs, per recording and per band, BOTH the existing unsigned scalars and the
new signed/localized family, so their effect sizes can be compared head-to-head
at the awake->sedation transition.

Dataset: OpenNeuro ds005620 (Bajwa, Nilsen, ..., Storm, Juel), 64-ch BrainVision
EEG, 5000 Hz. Conditions per subject: `awake` (eyes-closed baseline), `sed`
(resting propofol sedation, runs = awakenings), `sed2` (1-min resting just before
an awakening). Behavioural ground truth = the repeated-awakening paradigm. This is
a within-subject awake-vs-sedation transition, NOT a dose-graded 4-level titration
and with no recovery arm (reported as a limitation, not smoothed over).

Method (matches the rigor that just did its job on ds003969)
------------------------------------------------------------
HP 1 Hz -> bad-channel interpolation -> average reference -> picard ICA with
REAL VEOG/HEOG channels for ocular-component detection (better than ds003969's
Fp-proxy) -> CSD surface Laplacian (validated volume-conduction removal; both CSD
and eLORETA converged on ds003969) -> per band (delta..gamma) analytic phase.
eLORETA is deliberately NOT used: its fsaverage BEM host is egress-blocked and it
added nothing over CSD on ds003969.

Region labels for the signed metric are a documented 10-20 naming-convention zone
map (frontal/central/parietal/occipital/temporal-L/temporal-R) -- a coarse but
real scalp parcellation, explicitly not an anatomical atlas.

Reuse note: dual_engine/fmri_tda_pipeline.py (source of connectivity/homology/
graph helpers on `main`) is not present on this branch, so equivalents are
implemented here (PLV connectivity + ripser H1 + graph metrics), matching the
conventions of dual_engine/source_space_tda_pipeline.py.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import warnings
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
from scipy.signal import hilbert
from scipy.spatial import Delaunay

REPO = Path(__file__).resolve().parents[1]
if not (REPO / "validation").exists():
    REPO = Path("/home/user/ScienceR-Dsim")
sys.path.insert(0, str(REPO))

import mne  # noqa: E402
import networkx as nx  # noqa: E402
from ripser import ripser  # noqa: E402

from validation.montage_topology import (  # noqa: E402
    phase_grid_topology_from_band,
    signed_defect_topology_from_band,
)

mne.set_log_level("ERROR")
warnings.filterwarnings("ignore")

BANDS = {"delta": (1., 4.), "theta": (4., 8.), "alpha": (8., 13.),
         "beta": (13., 30.), "gamma": (30., 45.)}
TARGET_SFREQ = 256.
ICA_FIT_SFREQ = 128.
N_ICA = 20
EDGE_FRAC = 0.1          # edge crop = min(10 s, EDGE_FRAC * duration)
MAX_EDGE_S = 10.
MAX_DUR_S = 240.
MIN_DUR_S = 20.          # skip recordings shorter than this after cropping
N_TOPO_SAMPLES = 200     # subsampled time points for topology (unsigned + signed)
DENSITY = 0.15
AMP_QUANTILE = 0.10
EOG_CHS = ["VEOG", "HEOG"]
DROP_CHS = ["EMG"]
S3 = "https://s3.amazonaws.com/openneuro.org/ds005620"

_MONTAGE = mne.channels.make_standard_montage("standard_1020")
_MONT_POS = _MONTAGE.get_positions()["ch_pos"]


# ── 10-20 naming-convention zone map (documented coarse parcellation) ─────────

def zone_of(ch: str) -> str | None:
    """Map a 10-20 channel name to a coarse scalp zone.

    frontal / central / parietal / occipital / temporal_L / temporal_R, by the
    standard 10-20 naming convention (prefix -> lobe, trailing-digit parity ->
    hemisphere for temporal sites). This is a naming-based zone map, NOT an
    anatomical atlas -- it is only as good as the convention it reads.
    """
    c = ch.upper()
    if c.startswith(("T", "FT", "TP")):
        digits = "".join(d for d in c if d.isdigit())
        if digits:
            return "temporal_L" if int(digits[-1]) % 2 == 1 else "temporal_R"
        return "temporal_M"
    if c.startswith(("O", "I")):        # O1/O2/Oz/Iz
        return "occipital"
    if c.startswith("P"):               # P*, PO*, POz, Pz
        return "parietal"
    if c.startswith(("C", "FC")):       # C*, CP*, FC*, Cz
        return "central"
    if c.startswith(("F", "AF")):       # F*, AF*, Fp*
        return "frontal"
    return None


def build_region_labels(channel_names: list[str]) -> dict[str, str]:
    labels = {}
    for ch in channel_names:
        z = zone_of(ch)
        if z is not None:
            labels[ch] = z
    return labels


# ── montage geometry ─────────────────────────────────────────────────────────

def montage_xy_tri(ch_names):
    xy, keep = [], []
    for i, ch in enumerate(ch_names):
        if ch in _MONT_POS:
            p = _MONT_POS[ch]
            xy.append([p[0], p[1]]); keep.append(i)
    xy = np.asarray(xy, float)
    tri = Delaunay(xy).simplices
    return np.asarray(keep, int), xy, tri


# ── connectivity (PLV) -> TDA + graph (equivalents of the fMRI helpers) ───────

def plv_matrix(phase):
    z = np.exp(1j * phase)
    P = np.abs(z @ z.conj().T / z.shape[1])
    np.fill_diagonal(P, 1.0)
    return np.real(P)


def connectivity_metrics(P):
    n = P.shape[0]
    D = 1.0 - P
    np.fill_diagonal(D, 0.0)
    D = 0.5 * (D + D.T); D[D < 0] = 0.0
    h1 = ripser(D, distance_matrix=True, maxdim=1)["dgms"][1]
    if h1.size:
        life = h1[:, 1] - h1[:, 0]; life = life[np.isfinite(life)]
        b1_count = int(len(life)); persistence_sum = float(np.sum(life))
    else:
        b1_count, persistence_sum = 0, 0.0
    A = P.copy(); np.fill_diagonal(A, 0.0)
    iu = np.triu_indices(n, 1); w = A[iu]
    k = max(1, int(round(DENSITY * len(w))))
    thr = np.partition(w, -k)[-k] if k < len(w) else w.min()
    M = (A >= thr).astype(float); np.fill_diagonal(M, 0.0)
    G = nx.from_numpy_array(M)
    global_eff = float(nx.global_efficiency(G))
    mean_degree = float(np.mean([d for _, d in G.degree()]))
    try:
        modularity = float(nx.community.modularity(G, nx.community.greedy_modularity_communities(G)))
    except Exception:
        modularity = float("nan")
    return {"b1_count": b1_count, "persistence_sum": persistence_sum,
            "global_eff": global_eff, "modularity": modularity, "mean_degree": mean_degree}


# ── preprocessing ────────────────────────────────────────────────────────────

def preprocess(vhdr: Path, log):
    raw = mne.io.read_raw_brainvision(str(vhdr), preload=True, verbose="ERROR")
    present_eog = [c for c in EOG_CHS if c in raw.ch_names]
    if present_eog:
        raw.set_channel_types({c: "eog" for c in present_eog})
    drop = [c for c in DROP_CHS if c in raw.ch_names]
    if drop:
        raw.drop_channels(drop)
    scalp = [c for c in raw.ch_names if c in _MONT_POS]
    raw.pick(scalp + present_eog)
    raw.set_montage(_MONTAGE, on_missing="ignore")
    # Resample FIRST (5000 -> 256 Hz): a 1 Hz high-pass at 5000 Hz needs a
    # ~16k-tap FIR over 1.5M samples/channel and never finishes. MNE's resample
    # anti-aliases before decimation, and the analysis band is only 1-45 Hz, so
    # nothing of interest is lost by downsampling before filtering.
    if raw.info["sfreq"] > TARGET_SFREQ:
        raw.resample(TARGET_SFREQ, verbose="ERROR")
    raw.filter(1., 45., picks="all", verbose="ERROR")

    st = raw.copy().pick(scalp).get_data().std(axis=1)
    med = float(np.median(st))
    bads = [scalp[i] for i in range(len(st)) if st[i] < 1e-8 or st[i] > 5 * med]
    raw.info["bads"] = bads
    n_bad = len(bads)
    if bads:
        raw.interpolate_bads(reset_bads=True, verbose="ERROR")
    raw.set_eeg_reference("average", ch_type="eeg", verbose="ERROR")

    n_ica = 0
    if present_eog:
        ica = mne.preprocessing.ICA(n_components=N_ICA, method="picard",
                                    random_state=97, max_iter=200)
        fit_raw = raw.copy().resample(ICA_FIT_SFREQ, verbose="ERROR").filter(1., None, verbose="ERROR")
        ica.fit(fit_raw)
        excl = set()
        try:
            idx, _ = ica.find_bads_eog(raw, threshold=2.5, verbose="ERROR")
            excl.update(idx)
        except Exception as e:
            log(f"    EOG detect warn: {repr(e)[:70]}")
        ica.exclude = sorted(excl)
        n_ica = len(ica.exclude)
        raw = ica.apply(raw, verbose="ERROR")

    raw.pick(scalp)  # drop EOG channels; CSD/topology on scalp only

    dur = float(raw.times[-1])
    edge = min(MAX_EDGE_S, EDGE_FRAC * dur)
    tmax = min(dur - edge, edge + MAX_DUR_S)
    if tmax - edge < MIN_DUR_S:
        raise ValueError(f"usable segment too short ({tmax - edge:.1f}s < {MIN_DUR_S}s)")
    raw.crop(tmin=edge, tmax=tmax)

    raw_csd = mne.preprocessing.compute_current_source_density(raw, verbose="ERROR")
    return raw_csd, n_bad, n_ica, float(raw_csd.times[-1])


# ── metric computation ───────────────────────────────────────────────────────

def compute_metrics(raw_csd, log):
    keep, xy, tri = montage_xy_tri(raw_csd.ch_names)
    ch_names = [raw_csd.ch_names[i] for i in keep]
    region_labels = build_region_labels(ch_names)
    out = {}
    for band, (lo, hi) in BANDS.items():
        x = raw_csd.copy().filter(lo, hi, verbose="ERROR").get_data()[keep]
        an = hilbert(x, axis=1)
        phase, amp = np.angle(an), np.abs(an)
        idx = np.linspace(0, phase.shape[1] - 1, min(N_TOPO_SAMPLES, phase.shape[1])).astype(int)
        ph_s, amp_s = phase[:, idx], amp[:, idx]
        # (a) existing unsigned scalars
        uns = phase_grid_topology_from_band(ph_s, xy, tri, amplitude=amp_s, amp_quantile=AMP_QUANTILE)
        conn = connectivity_metrics(plv_matrix(phase))
        # (b) new signed / localized family
        sig = signed_defect_topology_from_band(
            ph_s, xy, tri, ch_names, region_labels=region_labels,
            amplitude=amp_s, amp_quantile=AMP_QUANTILE)
        out[band] = {
            "unsigned": {"Qabs": uns["Qabs"], "defect_density": uns["defect_density"],
                         "phase_grad": uns["phase_grad"], **conn},
            "signed": {"mean_net_charge_by_region": sig["mean_net_charge_by_region"],
                       "mean_abs_charge_by_region": sig["mean_abs_charge_by_region"],
                       "mean_region_chirality": sig["mean_region_chirality"],
                       "mean_n_clusters": sig["mean_n_clusters"],
                       "mean_cluster_persistence_proxy": sig["mean_cluster_persistence_proxy"]},
        }
    return out, len(keep)


@dataclass
class RecordingResult:
    subject: str
    condition: str          # awake | sed | sed2
    run: str
    status: str
    provenance: str = "real_eeg"
    n_channels: int = 0
    n_bad_interpolated: int = 0
    n_ica_excluded: int = 0
    duration_used_s: float = 0.0
    bands: dict = field(default_factory=dict)
    error: str = ""


# ── download (BrainVision triplet, preserving basenames) ─────────────────────

def download_triplet(sub: str, stem: str, dest_dir: Path) -> Path | None:
    base = f"{sub}_{stem}_eeg"
    for ext in ("vhdr", "vmrk", "eeg"):
        url = f"{S3}/{sub}/eeg/{base}.{ext}"
        dst = dest_dir / f"{base}.{ext}"
        dst.unlink(missing_ok=True)  # clear any orphan/partial from a prior aborted run
        ok = False
        for a in range(3):
            # --remove-on-error: a truncated large file must not survive and later
            # masquerade as complete; --max-time caps a stalled transfer.
            r = subprocess.run(["curl", "-sfL", "--remove-on-error", "--max-time", "300",
                                "-o", str(dst), url])
            # >64 bytes only guards against truly empty writes; curl -f already
            # fails on HTTP errors. (The .vmrk marker file is ~0.5 KB -- a larger
            # threshold here silently rejects every valid triplet.)
            if r.returncode == 0 and dst.exists() and dst.stat().st_size > 64:
                ok = True; break
            time.sleep(2 * (a + 1))
        if not ok:
            return None
    return dest_dir / f"{base}.vhdr"


def conditions_for(sub: str):
    """(condition, run_label, file_stem) list. Missing files are skipped at download."""
    items = [("awake", "EC", "task-awake_acq-EC")]
    for r in (1, 2, 3, 4):
        items.append(("sed", f"run-{r}", f"task-sed_acq-rest_run-{r}"))
        items.append(("sed2", f"run-{r}", f"task-sed2_acq-rest_run-{r}"))
    return items


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--subjects", nargs="+", required=True)
    ap.add_argument("--out", default="/home/user/ds005620/out/results.jsonl")
    ap.add_argument("--raw", default="/home/user/ds005620/raw")
    args = ap.parse_args()

    raw_dir = Path(args.raw); raw_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out); out_path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            try:
                r = json.loads(line); done.add((r["subject"], r["condition"], r["run"]))
            except Exception:
                pass

    def log(m): print(m, flush=True)

    with out_path.open("a") as fh:
        for sub in args.subjects:
            for cond, run, stem in conditions_for(sub):
                if (sub, cond, run) in done:
                    continue
                t0 = time.time()
                vhdr = download_triplet(sub, stem, raw_dir)
                if vhdr is None:
                    continue  # file absent (fewer awakenings) -- not an error
                try:
                    raw_csd, n_bad, n_ica, dur = preprocess(vhdr, log)
                    bands, nch = compute_metrics(raw_csd, log)
                    rec = RecordingResult(sub, cond, run, "ok", n_channels=nch,
                                          n_bad_interpolated=n_bad, n_ica_excluded=n_ica,
                                          duration_used_s=dur, bands=bands)
                except Exception as e:
                    rec = RecordingResult(sub, cond, run, "error", error=repr(e)[:300])
                finally:
                    for ext in ("vhdr", "vmrk", "eeg"):
                        (raw_dir / f"{sub}_{stem}_eeg.{ext}").unlink(missing_ok=True)
                fh.write(json.dumps(asdict(rec)) + "\n"); fh.flush()
                log(f"{rec.status.upper()} {sub} {cond} {run} ({time.time()-t0:.1f}s)")


if __name__ == "__main__":
    main()
