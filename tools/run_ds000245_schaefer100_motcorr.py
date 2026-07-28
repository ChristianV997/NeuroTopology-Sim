#!/usr/bin/env python3
"""Re-run the ds000245 fMRI-TDA cohort with a real anatomical parcellation and real
motion regression, replacing the caveats flagged in REPORT_ds000245_global_efficiency_gate.md:

  - Parcellation: Schaefer-100 (7-network, MNI152 2mm), warped into each subject's
    native functional grid via `tools/spatial_normalization.py` (T1->MNI affine +
    func->T1 rigid registration), instead of the prior K=100 non-anatomical KMeans
    coordinate clustering.
  - Motion: real per-volume 6-DOF rigid realignment via `tools/motion_correction.py`
    (dipy), used both as nuisance regressors (NiftiLabelsMasker `confounds`) and as
    a framewise-displacement scrubbing criterion (FD > 0.5mm frames dropped;
    subjects with > `FD_EXCLUDE_FRACTION` of frames scrubbed are excluded outright).

ds000245 ships as raw BIDS (verified against the S3 listing: no `derivatives/`,
no fMRIPrep confounds) so both of these had to be computed for real rather than
read from the dataset -- see the module docstrings in motion_correction.py and
spatial_normalization.py for exactly what "real" means here and its limits
(affine-only spatial normalization, not full nonlinear warping).

Reuses `dual_engine.fmri_tda_pipeline`'s `SubjectResult` / `connectivity_matrix` /
`persistent_homology` / `graph_metrics` / `build_cohort_payload` / `render_markdown_summary`
unchanged -- only parcellation + confound handling differ from the original pipeline.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dual_engine.fmri_tda_pipeline import (  # noqa: E402
    SubjectResult,
    build_cohort_payload,
    connectivity_matrix,
    graph_metrics,
    persistent_homology,
    render_markdown_summary,
    save_roi_timeseries,
)
from tools.motion_correction import FD_THRESHOLD_MM, get_or_compute_motion, scrub_mask  # noqa: E402
from tools.spatial_normalization import get_or_compute_func_space_atlas  # noqa: E402

FD_EXCLUDE_FRACTION = 0.25  # exclude a subject if more than this fraction of frames are scrubbed


def _infer_group(subject_name: str) -> str:
    name = subject_name.replace("sub-", "")
    return "CTL" if "CTL" in name else "ODN" if "ODN" in name else "ODP" if "ODP" in name else "UNK"


def _fetch_t1_if_missing(subject_id: str, bids_root: Path) -> Optional[Path]:
    anat_dir = bids_root / subject_id / "anat"
    existing = list(anat_dir.glob("*_T1w.nii.gz"))
    if existing:
        return existing[0]
    from tools.fetch_ds000245 import fetch

    fetch(bids_root, subjects=[subject_id], include_anat=True)
    existing = list(anat_dir.glob("*_T1w.nii.gz"))
    return existing[0] if existing else None


def run_subject(
    subject_id: str,
    group: str,
    func_path: str,
    t1_path: str,
    atlas_path: str,
    t_r: float,
    motion_cache_dir: Path,
    atlas_cache_dir: Path,
    save_timeseries_dir: Optional[str],
    downsample: int,
) -> tuple[dict[str, Any], Optional[SubjectResult]]:
    import nibabel as nib
    from nilearn.maskers import NiftiLabelsMasker

    func_img = nib.load(func_path)
    func_data = np.asanyarray(func_img.dataobj)
    n_t = func_data.shape[-1]
    ref_vol = func_data[..., n_t // 2].astype(np.float32)

    motion = get_or_compute_motion(func_path, motion_cache_dir, downsample=downsample)
    fd = motion["framewise_displacement"]
    keep = scrub_mask(fd, threshold=FD_THRESHOLD_MM)
    scrub_fraction = float(1.0 - keep.mean())
    excluded = scrub_fraction > FD_EXCLUDE_FRACTION

    qc = {
        "subject_id": subject_id,
        "group": group,
        "n_timepoints_total": int(n_t),
        "n_timepoints_kept": int(keep.sum()),
        "scrub_fraction": scrub_fraction,
        "fd_mean": float(fd.mean()),
        "fd_max": float(fd.max()),
        "excluded_motion": bool(excluded),
    }
    if excluded:
        return qc, None

    labels = get_or_compute_func_space_atlas(
        subject_id, t1_path, atlas_path, ref_vol, func_img.affine, func_data.shape[:3],
        atlas_cache_dir, downsample=downsample,
    )
    labels_img = nib.Nifti1Image(labels, func_img.affine)

    masker = NiftiLabelsMasker(
        labels_img=labels_img, standardize="zscore_sample",
        low_pass=0.1, high_pass=0.01, t_r=t_r, verbose=0,
    )
    ts = masker.fit_transform(func_path, confounds=motion["motion_params"])  # (T, R)
    ts_kept = ts[keep]

    if save_timeseries_dir is not None:
        save_roi_timeseries(ts_kept, subject_id, group, t_r, Path(save_timeseries_dir))

    conn = connectivity_matrix(ts_kept, kind="correlation")
    ph = persistent_homology(conn)
    gm = graph_metrics(conn)
    subj_result = SubjectResult(
        subject_id=subject_id, group=group,
        n_regions=conn.shape[0], n_timepoints=ts_kept.shape[0],
        betti0=ph["betti0"], betti1=ph["betti1"], total_persistence_h1=ph["total_persistence_h1"],
        modularity=gm["modularity"], global_efficiency=gm["global_efficiency"],
        mean_degree=gm["mean_degree"], small_worldness=gm["small_worldness"],
        provenance="real_fmri",
    )
    return qc, subj_result


def run(
    bids_root: Path, atlas_path: str, t_r: float, out_dir: Path,
    downsample: int, limit: Optional[int], subjects_filter: Optional[list[str]],
) -> dict[str, Any]:
    motion_cache_dir = out_dir / "motion_cache"
    atlas_cache_dir = out_dir / "atlas_cache"
    ts_dir = out_dir / "roi_timeseries"

    subs = sorted(p for p in bids_root.glob("sub-*") if p.is_dir())
    if subjects_filter is not None:
        wanted = {s if s.startswith("sub-") else f"sub-{s}" for s in subjects_filter}
        subs = [p for p in subs if p.name in wanted]
    if limit is not None:
        subs = subs[:limit]

    motion_qc = []
    subject_results = []
    for sub in subs:
        func_files = list((sub / "func").glob("*_bold.nii.gz"))
        if not func_files:
            continue
        t1_path = _fetch_t1_if_missing(sub.name, bids_root)
        if t1_path is None:
            motion_qc.append({"subject_id": sub.name, "error": "no_t1w_available"})
            continue
        group = _infer_group(sub.name)
        t0 = time.time()
        qc, subj_res = run_subject(
            sub.name, group, str(func_files[0]), str(t1_path), atlas_path, t_r,
            motion_cache_dir, atlas_cache_dir, str(ts_dir), downsample,
        )
        qc["runtime_sec"] = round(time.time() - t0, 1)
        motion_qc.append(qc)
        if subj_res is not None:
            subject_results.append(subj_res)
        print(
            f"  {sub.name} ({group}): scrub_frac={qc['scrub_fraction']:.2f} "
            f"excluded={qc['excluded_motion']} ({qc['runtime_sec']}s)"
        )

    payload = build_cohort_payload(subject_results, provenance="real_fmri")
    payload["atlas"] = "Schaefer2018_100Parcels_7Networks_FSLMNI152_2mm"
    payload["fd_threshold_mm"] = FD_THRESHOLD_MM
    payload["fd_exclude_fraction"] = FD_EXCLUDE_FRACTION
    payload["n_subjects_attempted"] = len(subs)
    payload["n_subjects_excluded_motion"] = sum(1 for q in motion_qc if q.get("excluded_motion"))
    payload["motion_qc"] = motion_qc
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bids-root", type=Path, default=_REPO_ROOT / "data" / "ds000245")
    parser.add_argument(
        "--atlas", type=Path,
        default=_REPO_ROOT / "data" / "atlases" / "schaefer_2018"
        / "Schaefer2018_100Parcels_7Networks_order_FSLMNI152_2mm.nii.gz",
    )
    parser.add_argument("--t-r", type=float, default=2.5)
    parser.add_argument(
        "--out", type=Path, default=_REPO_ROOT / "outputs" / "ds000245_fmri_tda_schaefer100_motcorr",
    )
    parser.add_argument("--downsample", type=int, default=3, help="registration downsampling stride")
    parser.add_argument("--limit", type=int, default=None, help="process only the first N subjects")
    parser.add_argument("--subjects", default=None, help="comma-separated subject ids (pilot runs)")
    args = parser.parse_args()

    subjects_filter = [s.strip() for s in args.subjects.split(",")] if args.subjects else None
    payload = run(args.bids_root, str(args.atlas), args.t_r, args.out, args.downsample, args.limit, subjects_filter)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "cohort_result.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    (args.out / "summary.md").write_text(render_markdown_summary(payload), encoding="utf-8")
    print(
        f"-> {args.out / 'cohort_result.json'} "
        f"({payload['n_ok']} ok / {payload['n_subjects_attempted']} attempted, "
        f"{payload['n_subjects_excluded_motion']} excluded for motion)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
