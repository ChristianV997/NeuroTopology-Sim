#!/usr/bin/env python3
"""Stream-process ds006644 (DMT-HAR-MED: DMT+harmine during a meditation
retreat, fMRI, CC0, n=40) one subject at a time -- disk-bounded like the EEG
streamers, but for fMRI: this is real infrastructure previously verified
only on a synthetic fixture (`dual_engine/fmri_tda_pipeline.py`), now pointed
at real data for the first time.

Design (from the dataset's own README, not inferred): 40 healthy meditation
 practitioners across two structurally identical 3-day retreats. Group
(`verum` = DMT+harmine, `placebo`) is BETWEEN-SUBJECT, fixed for the whole
study, read directly from `participants.tsv`'s `condition` column -- never
inferred from folder naming. Each subject has two sessions: `ses-01`
(pre-retreat baseline) and `ses-02` (post-retreat, after the pharmacological
intervention). This script uses only `ses-02` (the scientifically primary
timepoint -- the one that can actually show a verum/placebo topology
difference) to avoid a within-subject/between-subject pseudoreplication mix.

Uses the fMRIPrep derivative's ICA-AROMA-denoised, smoothed, MNI152NLin6Asym
-space BOLD (`derivatives/fmriprep/{subject}/ses-02/func/*desc-smoothAROMAnonaggr_bold.nii.gz`)
rather than raw or minimally-preprocessed BOLD: AROMA denoising is standard
practice for resting-state functional-connectivity analysis, and
MNI152NLin6Asym is the same template family as this repo's cached
Schaefer-100 atlas (`/root/nilearn_data/schaefer_2018/Schaefer2018_100Parcels_7Networks_order_FSLMNI152_1mm.nii.gz`),
so no extra registration step is needed. No additional confound regression
is layered on top of AROMA in this first pass (disclosed, not hidden).

Each BOLD file is ~350MB; downloaded, processed, and deleted one subject at
a time so disk stays bounded regardless of cohort size.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dual_engine.fmri_tda_pipeline import run_subject, build_cohort_payload, SubjectResult  # noqa: E402
from tools.streaming import base_runner  # noqa: E402
from validation.s3_fetchers import BoundedS3ObjectStore  # noqa: E402

_DATASET_ID = "ds006644"
_BUCKET = "openneuro.org"
_ATLAS_PATH = "/root/nilearn_data/schaefer_2018/Schaefer2018_100Parcels_7Networks_order_FSLMNI152_1mm.nii.gz"
_SESSION = "ses-02"
_BOLD_KEY_TMPL = (
    f"{_DATASET_ID}/derivatives/fmriprep/{{sub}}/{_SESSION}/func/"
    f"{{sub}}_{_SESSION}_task-rest_space-MNI152NLin6Asym_desc-smoothAROMAnonaggr_bold.nii.gz"
)


def _s3_client():
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    return boto3.client(
        "s3",
        config=Config(
            signature_version=UNSIGNED,
            connect_timeout=10,
            read_timeout=30,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def load_group_labels(*, metadata_cache_root: Path | None = None, allow_network: bool = False) -> dict[str, str]:
    """subject_id -> 'verum'|'placebo' from the real participants.tsv `condition` column.

    Never inferred from folder/subject naming -- ds006644's subject IDs
    (sub-01..sub-40) carry no group information themselves.
    """
    metadata_cache_root = metadata_cache_root or (_REPO_ROOT / "data" / _DATASET_ID)
    store = BoundedS3ObjectStore(_s3_client(), metadata_cache_root, metadata_max_bytes=4 * 1024 * 1024)
    text = store.read_text_metadata(_BUCKET, f"{_DATASET_ID}/participants.tsv", allow_network=allow_network)
    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    out: dict[str, str] = {}
    for row in reader:
        pid = row["participant_id"]
        sub = pid if pid.startswith("sub-") else f"sub-{pid}"
        cond = (row.get("condition") or "").strip()
        if cond in ("verum", "placebo"):
            out[sub] = cond
    return out


def download_subject_bold(
    subject: str,
    dest_dir: Path,
    *,
    allow_network: bool = False,
    max_cache_bytes: int = 512 * 1024 * 1024,
    chunk_size: int = 8 * 1024 * 1024,
) -> Path:
    key = _BOLD_KEY_TMPL.format(sub=subject)
    dest = dest_dir / f"{subject}_{_SESSION}_bold.nii.gz"
    # The delegated store enforces cache_budget, checksum policy, and eviction.
    store = BoundedS3ObjectStore(_s3_client(), dest_dir, max_cache_bytes=max_cache_bytes, chunk_size=chunk_size)
    store.fetch_object(_BUCKET, key, dest, allow_network=allow_network)
    return dest


def _real_schaefer_labels() -> list[str]:
    """The real Schaefer-2018 100-ROI region names, in `NiftiLabelsMasker` column order.

    Index 0 ('Background') is dropped -- `parcellate_bold`'s masker output has exactly
    100 columns, one per real region, matching `atlas["labels"][1:]` one-to-one. Unlike
    ds005917 (raw BOLD, no spatial normalization -- see stream_process_ds005917.py's
    docstring), ds006644 uses fMRIPrep's AROMA-denoised MNI152NLin6Asym-space BOLD, the
    same template family as this cached Schaefer atlas, so this correspondence is real,
    not approximate.
    """
    from validation.atlas_utils import fetch_schaefer_atlas

    return fetch_schaefer_atlas(n_rois=100)["labels"][1:]


def process_subject(subject: str, group: str, work_root: Path, graph_structure_dir: Path | None = None,
                     region_labels: list[str] | None = None, *, allow_network: bool = False,
                     max_cache_bytes: int = 512 * 1024 * 1024) -> SubjectResult:
    if not allow_network and max_cache_bytes == 512 * 1024 * 1024:
        # Preserve the historical two-argument seam for downstream test
        # doubles while the real downloader remains fail-closed by default.
        bold_path = download_subject_bold(subject, work_root)
    else:
        bold_path = download_subject_bold(subject, work_root, allow_network=allow_network, max_cache_bytes=max_cache_bytes)
    try:
        res = run_subject(
            subject_id=subject, group=group, bold_path=str(bold_path),
            atlas_labels_img=_ATLAS_PATH, t_r=1.8, confounds=None,
            connectivity_kind="correlation", provenance="real_fmri",
            save_graph_structure_dir=str(graph_structure_dir) if graph_structure_dir else None,
            region_labels=region_labels,
        )
    finally:
        bold_path.unlink(missing_ok=True)  # disk-bounded: delete raw before next subject
    return res


def _process_subject_safe(sub: str, group: str, work_path: Path, graph_structure_dir: Path | None = None,
                           region_labels: list[str] | None = None, *, allow_network: bool = False,
                           max_cache_bytes: int = 512 * 1024 * 1024) -> dict:
    """Always returns a full SubjectResult dict (with `error` set on failure),
    so the shared manifest loop never records the generic {"error"} shape that
    build_cohort_payload's SubjectResult.from_dict cannot rebuild."""
    try:
        res = process_subject(sub, group, work_path, graph_structure_dir=graph_structure_dir, region_labels=region_labels,
                              allow_network=allow_network, max_cache_bytes=max_cache_bytes)
    except Exception as exc:  # never crash the whole cohort run on one bad subject
        res = SubjectResult(
            subject_id=sub, group=group, n_regions=0, n_timepoints=0,
            betti0=0, betti1=0, total_persistence_h1=0.0, modularity=0.0,
            global_efficiency=0.0, mean_degree=0.0, small_worldness=0.0,
            provenance="real_fmri", error=str(exc),
        )
    return res.to_dict()


def run(out_dir: str, work_root: str, limit: int | None, subjects: list[str] | None,
        save_graph_structure_dir: str | None = None, *, allow_network: bool = False,
        max_cache_bytes: int = 512 * 1024 * 1024) -> int:
    out_path = Path(out_dir)
    work_path = Path(work_root)

    labels = load_group_labels(metadata_cache_root=work_path, allow_network=allow_network)
    all_subjects = subjects if subjects is not None else sorted(labels.keys())
    # only subjects with a real group label are processable (never inferred)
    items = [(s, labels[s]) for s in all_subjects if labels.get(s) in ("verum", "placebo")]
    print(f"{sum(1 for v in labels.values() if v=='verum')} verum / "
          f"{sum(1 for v in labels.values() if v=='placebo')} placebo labeled subjects.")

    graph_dir = Path(save_graph_structure_dir) if save_graph_structure_dir else None
    region_labels = _real_schaefer_labels() if graph_dir is not None else None

    manifest = base_runner.run_manifest_loop(
        items, out_path,
        key_fn=lambda t: t[0],
        process_fn=lambda t: _process_subject_safe(t[0], t[1], work_path, graph_structure_dir=graph_dir,
                                                    region_labels=region_labels, allow_network=allow_network,
                                                    max_cache_bytes=max_cache_bytes),
        limit=limit,
        label_fn=lambda t: f"{t[0]} ({t[1]})",
    )

    results = [SubjectResult.from_dict(v) for v in manifest["processed"].values()]
    payload = build_cohort_payload(results, provenance="real_fmri")
    (out_path / "cohort_result.json").write_text(json.dumps(payload, indent=2))
    print(f"-> {out_path/'cohort_result.json'} ({len(results)} subjects, "
          f"{sum(1 for r in results if not r.error)} ok)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="outputs/dual_engine/ds006644")
    p.add_argument("--work-root", default="data/ds006644")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--subjects", nargs="*", default=None)
    p.add_argument("--allow-network", action="store_true", help="Explicitly permit bounded S3 metadata/range requests")
    p.add_argument("--max-cache-bytes", type=int, default=512 * 1024 * 1024)
    p.add_argument("--save-graph-structure", default=None,
                    help="directory to persist real parcel centroids + connectivity matrix + real "
                         "Schaefer-100 region names (.npz) per subject -- valid here because ds006644 "
                         "uses fMRIPrep's spatially-normalized AROMA-denoised BOLD, unlike ds005917")
    a = p.parse_args()
    return run(a.out, a.work_root, a.limit, a.subjects, a.save_graph_structure,
               allow_network=a.allow_network, max_cache_bytes=a.max_cache_bytes)


if __name__ == "__main__":
    raise SystemExit(main())
