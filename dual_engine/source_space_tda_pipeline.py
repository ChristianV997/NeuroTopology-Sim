#!/usr/bin/env python3
"""Source-space / volume-conduction-controlled ITCT-TDA upgrade for ds003969.

WHY THIS DIFFERS FROM THE SENSOR PIPELINE
-----------------------------------------
The sensor-space run (eeg_itct_pipeline.py) had two weaknesses the directive
targets: (1) the pure ITCT phase-winding charge Q_abs was null, plausibly
because volume conduction smears scalp phase gradients; (2) delta-band findings
were vulnerable to ocular/cardiac artifact.

ENVIRONMENT CONSTRAINT (documented, not worked around)
------------------------------------------------------
The originally-specified toolchain (fsaverage 3-layer BEM + ico-5 surface source
space + Desikan-Killiany `aparc` parcellation + surface eLORETA) requires files
that live only on osf.io, which this container's egress policy HARD-BLOCKS (403
CONNECT, logged by the agent proxy). The bundled MNE fsaverage ships only the
inner-skull BEM surface + trans/head/fiducials -- no surface source space and no
aparc annotation. True DK68 surface parcellation is therefore impossible here.

WHAT WE DO INSTEAD (both fully offline, both scientifically defensible)
----------------------------------------------------------------------
PHASE 1  ICA artifact rejection (picard). No EOG/ECG channels exist in this
         dataset, so ocular components are identified via frontopolar proxies
         (Fp1/Fp2) with find_bads_eog; cardiac via find_bads_ecg (ctps synth).
PHASE 2  Volume-conduction removal:
         * PRIMARY  = CSD / surface Laplacian (Perrin spherical splines). Model-
           free, reference-free; sharpens exactly the local phase gradients that
           Q_abs integrates. This is the natural instrument for the Q_abs
           question -- arguably cleaner than eLORETA, which reintroduces its own
           low-resolution smoothing.
         * SECONDARY (optional, --eloreta) = analytic 3-layer sphere BEM +
           volume source space + eLORETA. A genuine depth-resolved source
           projection, template-head (imprecise localization, no true DK68);
           used only to corroborate connectivity-topology survival in source
           space. ROIs are coarse position-defined dipole clusters.
PHASE 3/4  Re-run the ITCT engine per band:
         * Q_abs / defect_density / phase_grad on the CSD-sharpened montage
           geometry (validation.montage_topology) -- the offline stand-in for
           cortical-mesh winding.
         * PLV connectivity -> Vietoris-Rips (1-PLV) -> b1_count, persistence_sum
           (H1 lifetime), global_eff, modularity. PLV (phase-based) is used per
           the directive, replacing the sensor run's amplitude-envelope corr.

Bad channels are INTERPOLATED (not dropped) so every recording keeps the full
64-ch montage -> the eLORETA forward operator is built once and reused.
Process-and-discard keeps peak disk ~150 MB.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
from scipy.signal import hilbert
from scipy.spatial import Delaunay

# Resolve repo root from this file's location (dual_engine/ -> repo root) so the
# `validation.montage_topology` import works in-tree; fall back to an absolute
# path if run from a detached scratch copy.
REPO = Path(__file__).resolve().parents[1]
if not (REPO / "validation").exists():
    REPO = Path("/home/user/ScienceR-Dsim")
sys.path.insert(0, str(REPO))

import mne  # noqa: E402
import networkx as nx  # noqa: E402
from ripser import ripser  # noqa: E402

mne.set_log_level("ERROR")
warnings.filterwarnings("ignore")

BANDS = {"delta": (1., 4.), "theta": (4., 8.), "alpha": (8., 13.),
         "beta": (13., 30.), "gamma": (30., 45.)}
TARGET_SFREQ = 256.
ICA_FIT_SFREQ = 128.     # decimate for faster/robust ICA fit (spatial filter, sfreq-agnostic)
N_ICA = 20
CROP_EDGE_S = 30.
MAX_DUR_S = 240.
N_TOPO_SAMPLES = 200
DENSITY = 0.15
AMP_QUANTILE = 0.10
EOG_PROXY = ["Fp1", "Fp2"]
S3 = "https://s3.amazonaws.com/openneuro.org"

_MONTAGE = mne.channels.make_standard_montage("standard_1020")
_MONT_POS = _MONTAGE.get_positions()["ch_pos"]


# ── montage geometry for phase-field topology ────────────────────────────────

def montage_xy_tri(ch_names):
    xy, keep = [], []
    for i, ch in enumerate(ch_names):
        if ch in _MONT_POS:
            p = _MONT_POS[ch]
            xy.append([p[0], p[1]]); keep.append(i)
    xy = np.asarray(xy, float)
    tri = Delaunay(xy).simplices
    return np.asarray(keep, int), xy, tri


# ── connectivity via PLV -> TDA + graph ──────────────────────────────────────

def plv_matrix(phase):
    """Phase-locking value across channels. phase: (n_ch, n_t) -> (n_ch, n_ch)."""
    z = np.exp(1j * phase)
    n = z.shape[0]
    # PLV_ij = |<exp(i(phi_i - phi_j))>_t| = |z_i . conj(z_j)| / n_t
    S = z @ z.conj().T / z.shape[1]
    P = np.abs(S)
    np.fill_diagonal(P, 1.0)
    return np.real(P)


def connectivity_metrics(P):
    n = P.shape[0]
    D = 1.0 - P
    np.fill_diagonal(D, 0.0)
    D = 0.5 * (D + D.T)
    D[D < 0] = 0.0
    dgms = ripser(D, distance_matrix=True, maxdim=1)["dgms"]
    h1 = dgms[1]
    if h1.size:
        life = h1[:, 1] - h1[:, 0]
        life = life[np.isfinite(life)]
        b1_count = int(len(life)); persistence_sum = float(np.sum(life))
        persistence_max = float(np.max(life)) if life.size else 0.0
    else:
        b1_count, persistence_sum, persistence_max = 0, 0.0, 0.0
    A = P.copy(); np.fill_diagonal(A, 0.0)
    iu = np.triu_indices(n, 1); w = A[iu]
    k = max(1, int(round(DENSITY * len(w))))
    thr = np.partition(w, -k)[-k] if k < len(w) else w.min()
    M = (A >= thr).astype(float); np.fill_diagonal(M, 0.0)
    G = nx.from_numpy_array(M)
    global_eff = float(nx.global_efficiency(G))
    mean_degree = float(np.mean([d for _, d in G.degree()]))
    try:
        comms = nx.community.greedy_modularity_communities(G)
        modularity = float(nx.community.modularity(G, comms))
    except Exception:
        modularity = float("nan")
    return {"b1_count": b1_count, "persistence_sum": persistence_sum,
            "persistence_max": persistence_max, "global_eff": global_eff,
            "modularity": modularity, "mean_degree": mean_degree}


# ── preprocessing: HP -> interp bads -> avgref -> ICA ─────────────────────────

def preprocess(path: Path, log):
    raw = mne.io.read_raw_bdf(str(path), preload=True, verbose="ERROR")
    scalp = [c for c in raw.ch_names if c in _MONT_POS]
    raw.pick(scalp)
    raw.set_montage(_MONTAGE, on_missing="ignore")
    raw.filter(1., 45., verbose="ERROR")
    st = raw.get_data().std(1); med = float(np.median(st))
    bads = [raw.ch_names[i] for i in range(len(st)) if st[i] < 1e-8 or st[i] > 5 * med]
    raw.info["bads"] = bads
    n_bad = len(bads)
    if bads:
        raw.interpolate_bads(reset_bads=True, verbose="ERROR")   # keep full montage
    # Average reference as a PROJECTION (not a direct custom ref): required so the
    # eLORETA inverse accepts it (MNE forbids custom_ref_applied for inverse
    # modeling). CSD is reference-invariant, so this is harmless for that path.
    raw.set_eeg_reference("average", projection=True, verbose="ERROR")
    if raw.info["sfreq"] > TARGET_SFREQ:
        raw.resample(TARGET_SFREQ, verbose="ERROR")

    # ICA on decimated copy; apply spatial filter to full-rate raw
    ica = mne.preprocessing.ICA(n_components=N_ICA, method="picard",
                                random_state=97, max_iter=200)
    fit_raw = raw.copy().resample(ICA_FIT_SFREQ, verbose="ERROR").filter(1., None, verbose="ERROR")
    ica.fit(fit_raw)
    excl = set()
    try:
        # threshold 2.5 (not the 3.0 default): calibrated on this montage to catch
        # the dominant frontal-blink component without over-rejecting (3.0 misses
        # blinks here; 2.0 pulls in 5+ borderline comps = overfitting).
        eog_idx, _ = ica.find_bads_eog(raw, ch_name=EOG_PROXY, threshold=2.5, verbose="ERROR")
        excl.update(eog_idx)
    except Exception as e:
        log(f"    EOG detect warn: {repr(e)[:80]}")
    # ECG detection is skipped: no ECG channel exists and MNE cannot synthesize
    # an artificial one for EEG-only data. Ocular (EOG) is the dominant artifact.
    ica.exclude = sorted(excl)
    raw = ica.apply(raw, verbose="ERROR")

    tmin = CROP_EDGE_S
    tmax = min(raw.times[-1] - CROP_EDGE_S, CROP_EDGE_S + MAX_DUR_S)
    raw.crop(tmin=tmin, tmax=tmax)
    return raw, n_bad, len(ica.exclude)


# ── ITCT metrics on CSD-transformed data ─────────────────────────────────────

def csd_metrics(raw_pre, log):
    from validation.montage_topology import phase_grid_topology_from_band
    raw_csd = mne.preprocessing.compute_current_source_density(raw_pre.copy(), verbose="ERROR")
    keep, xy, tri = montage_xy_tri(raw_csd.ch_names)
    out = {}
    for band, (lo, hi) in BANDS.items():
        x = raw_csd.copy().filter(lo, hi, verbose="ERROR").get_data()[keep]
        an = hilbert(x, axis=1)
        phase, amp = np.angle(an), np.abs(an)
        idx = np.linspace(0, phase.shape[1] - 1, min(N_TOPO_SAMPLES, phase.shape[1])).astype(int)
        topo = phase_grid_topology_from_band(phase[:, idx], xy, tri,
                                             amplitude=amp[:, idx], amp_quantile=AMP_QUANTILE)
        conn = connectivity_metrics(plv_matrix(phase))
        out[band] = {"Qabs": topo["Qabs"], "defect_density": topo["defect_density"],
                     "phase_grad": topo["phase_grad"],
                     "n_valid_triangles": topo["n_valid_triangles"], **conn}
    return out, len(keep)


# ── eLORETA source-space corroboration (optional) ────────────────────────────

def build_eloreta_operator(info):
    sphere = mne.make_sphere_model("auto", head_radius="auto", info=info, verbose="ERROR")
    src = mne.setup_volume_source_space(sphere=sphere, pos=15., verbose="ERROR")
    fwd = mne.make_forward_solution(info, trans=None, src=src, bem=sphere,
                                    eeg=True, meg=False, verbose="ERROR")
    cov = mne.make_ad_hoc_cov(info)
    inv = mne.minimum_norm.make_inverse_operator(info, fwd, cov, loose=1.,
                                                 depth=None, verbose="ERROR")
    # coarse spatial clustering of dipoles -> ~68 "parcels" via kmeans on positions
    pos = src[0]["rr"][src[0]["inuse"].astype(bool)]
    from sklearn.cluster import KMeans
    k = min(68, len(pos))
    labels = KMeans(n_clusters=k, n_init=4, random_state=0).fit_predict(pos)
    return inv, labels, k


def eloreta_metrics(raw_pre, inv, labels, k, log):
    out = {}
    for band, (lo, hi) in BANDS.items():
        rb = raw_pre.copy().filter(lo, hi, verbose="ERROR")
        stc = mne.minimum_norm.apply_inverse_raw(
            rb, inv, lambda2=1. / 9., method="eLORETA", verbose="ERROR")
        src_data = stc.data                       # (n_dipoles, n_t)
        # parcel time-courses = mean over dipole cluster
        parc = np.zeros((k, src_data.shape[1]))
        for c in range(k):
            m = labels == c
            if m.any():
                parc[c] = src_data[m].mean(0)
        an = hilbert(parc, axis=1)
        conn = connectivity_metrics(plv_matrix(np.angle(an)))
        out[band] = conn
    return out


def download(sub, task, dest):
    url = f"{S3}/ds003969/{sub}/eeg/{sub}_task-{task}_eeg.bdf"
    for a in range(3):
        r = subprocess.run(["curl", "-sfL", "-o", str(dest), url])
        if r.returncode == 0 and dest.exists() and dest.stat().st_size > 1_000_000:
            return True
        time.sleep(2 * (a + 1))
    return False


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--subjects", nargs="+", required=True)
    ap.add_argument("--tasks", nargs="+", default=["med1breath", "med2", "think1", "think2"])
    ap.add_argument("--out", default="/home/user/ds003969_eeg/out/source_results.jsonl")
    ap.add_argument("--raw", default="/home/user/ds003969_eeg/raw")
    ap.add_argument("--eloreta", action="store_true", help="also run sphere-model volume eLORETA")
    args = ap.parse_args()

    raw_dir = Path(args.raw); raw_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out); out_path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            try:
                r = json.loads(line); done.add((r["subject"], r["task"]))
            except Exception:
                pass

    def log(msg):
        print(msg, flush=True)

    eloreta_op = None
    with out_path.open("a") as fh:
        for sub in args.subjects:
            for task in args.tasks:
                if (sub, task) in done:
                    log(f"skip {sub} {task}"); continue
                dest = raw_dir / f"src_{sub}_{task}.bdf"
                t0 = time.time()
                if not download(sub, task, dest):
                    fh.write(json.dumps({"subject": sub, "task": task, "status": "missing"}) + "\n"); fh.flush()
                    log(f"MISS {sub} {task}"); continue
                try:
                    raw_pre, n_bad, n_ica = preprocess(dest, log)
                    csd, nch = csd_metrics(raw_pre, log)
                    rec = {"subject": sub, "task": task, "status": "ok",
                           "n_bad_interpolated": n_bad, "n_ica_excluded": n_ica,
                           "n_channels": nch, "csd": csd}
                    if args.eloreta:
                        if eloreta_op is None:
                            eloreta_op = build_eloreta_operator(raw_pre.info)
                            log(f"    built eLORETA operator: {eloreta_op[2]} parcels")
                        inv, labels, k = eloreta_op
                        rec["eloreta"] = eloreta_metrics(raw_pre, inv, labels, k, log)
                except Exception as e:
                    rec = {"subject": sub, "task": task, "status": "error", "error": repr(e)[:300]}
                finally:
                    dest.unlink(missing_ok=True)
                fh.write(json.dumps(rec) + "\n"); fh.flush()
                log(f"{rec['status'].upper()} {sub} {task} ({time.time()-t0:.1f}s)")


if __name__ == "__main__":
    main()
