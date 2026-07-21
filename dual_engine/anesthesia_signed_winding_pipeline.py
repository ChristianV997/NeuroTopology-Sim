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

# Datalad-based access to OpenNeuro (replaces broken S3 endpoint)
try:
    import datalad.api
    DATALAD_AVAILABLE = True
    DATALAD_REPO = "https://github.com/OpenNeuroDatasets/ds005620.git"
except ImportError:
    DATALAD_AVAILABLE = False

# Fallback HTTP download from public endpoints
HTTPS_ENDPOINTS = [
    "https://github.com/OpenNeuroDatasets/ds005620/raw/master",  # GitHub raw content
]

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


# ── Direct HTTP fallback (when datalad/S3 fail) ──────────────────────────────

def download_via_https(sub: str, task: str, acq: str, run: int | None, ext: str,
                       dest_path: Path) -> bool:
    """Fallback: download BIDS file via public HTTPS endpoint."""
    run_str = f"_run-{run}" if run else ""
    bids_subject = f"sub-{sub}"
    filename = f"{bids_subject}_task-{task}_acq-{acq}{run_str}_eeg.{ext}"

    for base_url in HTTPS_ENDPOINTS:
        url = f"{base_url}/{bids_subject}/eeg/{filename}"
        try:
            r = subprocess.run(["curl", "-sfL", "--max-time", "60", "-o", str(dest_path), url])
            if r.returncode == 0 and dest_path.exists() and dest_path.stat().st_size > 64:
                return True
        except Exception:
            pass

    return False


# ── Datalad-based fetching (replaces broken S3) ────────────────────────────

def ensure_datalad_clone(cache_dir: Path = None) -> Path:
    """Clone ds005620 via datalad if not already present."""
    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "openneuro" / "ds005620"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if not (cache_dir / ".git").exists():
        try:
            import datalad.api as dl
            dl.clone(DATALAD_REPO, str(cache_dir), on_failure="ignore")
        except Exception as e:
            print(f"Datalad clone failed: {e}", file=sys.stderr)
            return None
    return cache_dir


def fetch_bids_file_via_datalad(repo_path: Path, subject: str, bids_path: str) -> Path | None:
    """Fetch a BIDS file via datalad get (called from within dataset), return path if successful."""
    full_path = repo_path / subject / bids_path
    if not full_path.exists():
        return None

    # If already resolved (not a symlink), return it
    if not full_path.is_symlink():
        return full_path

    # Use datalad get from within the repo to fetch the data
    try:
        import datalad.api as dl
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(repo_path)
            # Call get with relative path
            rel_path = full_path.relative_to(repo_path)
            dl.get(str(rel_path), on_failure="ignore")
            os.chdir(original_cwd)

            # Check if resolved
            if full_path.exists() and not full_path.is_symlink():
                return full_path
        finally:
            os.chdir(original_cwd)
    except Exception as e:
        pass

    return None


def download_triplet_via_datalad(repo_path: Path, sub: str, bids_subject: str,
                                 task: str, acq: str, run: int | None,
                                 dest_dir: Path) -> Path | None:
    """Download a BIDS EEG triplet: try datalad first, fallback to HTTPS."""
    run_str = f"_run-{run}" if run else ""
    base_bids = f"{bids_subject}_task-{task}_acq-{acq}{run_str}_eeg"

    success_count = 0
    for ext in ("vhdr", "vmrk", "eeg"):
        base = f"{sub}_{task}_{acq}{run_str}_eeg"
        dst = dest_dir / f"{base}.{ext}"
        dst.unlink(missing_ok=True)

        # Try 1: datalad get from repo
        if repo_path:
            bids_path = f"eeg/{base_bids}.{ext}"
            full_path = repo_path / bids_subject / bids_path

            if full_path.exists():
                try:
                    result = subprocess.run(
                        ["datalad", "get", str(full_path)],
                        cwd=str(repo_path),
                        capture_output=True,
                        timeout=60
                    )
                except Exception:
                    pass

                # Check if resolved
                try:
                    if full_path.exists() and full_path.stat().st_size > 0:
                        import shutil
                        shutil.copy2(full_path, dst)
                        success_count += 1
                        continue
                except Exception:
                    pass

        # Try 2: Direct HTTPS fallback (GitHub raw content)
        if download_via_https(sub, task, acq, run, ext, dst):
            success_count += 1

    # Fix vhdr file references if copied with different naming
    if success_count == 3:
        base = f"{sub}_{task}_{acq}{run_str}_eeg"
        vhdr_path = dest_dir / f"{base}.vhdr"

        # Update file references in vhdr to match new filenames
        if vhdr_path.exists():
            vhdr_text = vhdr_path.read_text()
            old_base = f"{bids_subject}_task-{task}_acq-{acq}{run_str}_eeg"
            new_base = base

            # Replace references to old filenames with new ones
            vhdr_text = vhdr_text.replace(f"DataFile={old_base}.eeg", f"DataFile={new_base}.eeg")
            vhdr_text = vhdr_text.replace(f"MarkerFile={old_base}.vmrk", f"MarkerFile={new_base}.vmrk")
            vhdr_text = vhdr_text.replace(f"; Data file: {old_base}.eeg", f"; Data file: {new_base}.eeg")
            vhdr_text = vhdr_text.replace(f"; Marker file: {old_base}.vmrk", f"; Marker file: {new_base}.vmrk")

            vhdr_path.write_text(vhdr_text)

        return vhdr_path
    return None


# ── Legacy S3 download (fallback, likely broken) ────────────────────────────

def download_triplet(sub: str, stem: str, dest_dir: Path) -> Path | None:
    """Legacy S3 download. Use datalad instead."""
    base = f"{sub}_{stem}_eeg"
    for ext in ("vhdr", "vmrk", "eeg"):
        url = f"https://s3.amazonaws.com/openneuro.org/ds005620/{sub}/eeg/{base}.{ext}"
        dst = dest_dir / f"{base}.{ext}"
        dst.unlink(missing_ok=True)
        ok = False
        for a in range(3):
            r = subprocess.run(["curl", "-sfL", "--remove-on-error", "--max-time", "300",
                                "-o", str(dst), url])
            if r.returncode == 0 and dst.exists() and dst.stat().st_size > 64:
                ok = True; break
            time.sleep(2 * (a + 1))
        if not ok:
            return None
    return dest_dir / f"{base}.vhdr"


def bids_conditions_for(bids_subject: str):
    """(condition, task, acq, run) tuples for a BIDS subject. Missing are skipped at download."""
    items = [
        ("awake", "awake", "EC", None),   # sub-XXXX_task-awake_acq-EC_eeg
        ("awake", "awake", "EO", None),   # sub-XXXX_task-awake_acq-EO_eeg (if available)
    ]
    for r in (1, 2, 3, 4):
        items.append(("sed", "sed", "rest", r))      # sub-XXXX_task-sed_acq-rest_run-{r}_eeg
        items.append(("sed2", "sed2", "rest", r))    # sub-XXXX_task-sed2_acq-rest_run-{r}_eeg
    return items


def conditions_for(sub: str):
    """(condition, run_label, file_stem) list. Missing files are skipped at download."""
    items = [("awake", "EC", "task-awake_acq-EC")]
    for r in (1, 2, 3, 4):
        items.append(("sed", f"run-{r}", f"task-sed_acq-rest_run-{r}"))
        items.append(("sed2", f"run-{r}", f"task-sed2_acq-rest_run-{r}"))
    return items


def save_timeseries(raw_csd, sub: str, cond: str, run: str, ts_dir: Path) -> str:
    """Durable capability: persist the CSD-transformed, ICA-cleaned per-recording
    scalp time series (montage-kept channels only, the exact array the metrics and
    the surrogate gate operate on) + channel names to a .npz. This is the raw
    material the surrogate gate needs and which prior runs discarded. Reusable for
    any future run via --save-timeseries; independent of metric computation.
    """
    keep, _xy, _tri = montage_xy_tri(raw_csd.ch_names)
    ch_names = [raw_csd.ch_names[i] for i in keep]
    data = raw_csd.get_data()[keep].astype(np.float32)
    ts_dir.mkdir(parents=True, exist_ok=True)
    path = ts_dir / f"{sub}_{cond}_{run}.npz"
    np.savez_compressed(path, data=data, ch_names=np.array(ch_names, dtype=object),
                        sfreq=float(raw_csd.info["sfreq"]), subject=sub,
                        condition=cond, run=run, provenance="real_eeg")
    return str(path)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--subjects", nargs="+", default=None,
                    help="BIDS subject IDs (e.g., 1010 1016 1017). If omitted, all available subjects")
    ap.add_argument("--out", default="/home/user/ds005620/out/results.jsonl")
    ap.add_argument("--raw", default="/home/user/ds005620/raw")
    ap.add_argument("--save-timeseries", default=None,
                    help="directory to persist CSD post-ICA per-recording timeseries (.npz)")
    ap.add_argument("--conditions", nargs="+", default=None,
                    help="restrict to these conditions (e.g. awake sed); default all")
    ap.add_argument("--data-dir", default=None,
                    help="local BIDS-format data directory (overrides datalad, for testing/offline)")
    ap.add_argument("--use-datalad", action="store_true", default=False,
                    help="use datalad for OpenNeuro access (default false, set to true for real data)")
    args = ap.parse_args()

    ts_dir = Path(args.save_timeseries) if args.save_timeseries else None
    cond_filter = set(args.conditions) if args.conditions else None
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

    # Determine data source: local dir or datalad
    repo_path = None
    if args.data_dir:
        repo_path = Path(args.data_dir)
        if not repo_path.exists():
            log(f"Error: data directory not found: {repo_path}")
            sys.exit(1)
        log(f"Using local data directory: {repo_path}")
    elif args.use_datalad:
        if not DATALAD_AVAILABLE:
            print("Error: datalad not installed. Install with: pip install datalad datalad-osf", file=sys.stderr)
            sys.exit(1)
        repo_path = ensure_datalad_clone()
        if repo_path is None:
            log("Failed to clone ds005620 via datalad")
            sys.exit(1)
        log(f"Using datalad repo: {repo_path}")

    # Determine which subjects to process
    if args.subjects:
        subjects = [f"sub-{s}" if not s.startswith("sub-") else s for s in args.subjects]
    elif repo_path:
        # Discover all subjects in the repo
        subjects = sorted([d.name for d in repo_path.iterdir() if d.is_dir() and d.name.startswith("sub-")])
        log(f"Discovered {len(subjects)} subjects")
    else:
        print("Error: must provide --subjects or --data-dir or --use-datalad", file=sys.stderr)
        sys.exit(1)

    with out_path.open("a") as fh:
        for bids_subject in subjects:
            sub_short = bids_subject.replace("sub-", "")
            for cond, task, acq, run in bids_conditions_for(bids_subject):
                if cond_filter is not None and cond not in cond_filter:
                    continue
                if (sub_short, cond, str(run or "")) in done:
                    continue
                t0 = time.time()

                # Fetch via datalad
                vhdr = download_triplet_via_datalad(repo_path, sub_short, bids_subject,
                                                     task, acq, run, raw_dir)
                if vhdr is None:
                    continue  # file absent (fewer awakenings) -- not an error

                try:
                    raw_csd, n_bad, n_ica, dur = preprocess(vhdr, log)
                    bands, nch = compute_metrics(raw_csd, log)
                    if ts_dir is not None:
                        run_label = run if run else ""
                        save_timeseries(raw_csd, sub_short, cond, str(run_label), ts_dir)
                    rec = RecordingResult(sub_short, cond, str(run or ""), "ok", n_channels=nch,
                                          n_bad_interpolated=n_bad, n_ica_excluded=n_ica,
                                          duration_used_s=dur, bands=bands)
                except Exception as e:
                    rec = RecordingResult(sub_short, cond, str(run or ""), "error", error=repr(e)[:300])
                finally:
                    # Clean up temp files
                    for ext in ("vhdr", "vmrk", "eeg"):
                        base = f"{sub_short}_{task}_{acq}"
                        if run:
                            base += f"_run-{run}"
                        base += "_eeg"
                        (raw_dir / f"{base}.{ext}").unlink(missing_ok=True)

                fh.write(json.dumps(asdict(rec)) + "\n"); fh.flush()
                log(f"{rec.status.upper()} {sub_short} {cond} {run or ''} ({time.time()-t0:.1f}s)")


if __name__ == "__main__":
    main()
