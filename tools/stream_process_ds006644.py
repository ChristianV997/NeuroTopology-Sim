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
-space BOLD (`derivatives/fmriprep/.../desc-smoothAROMAnonaggr_bold.nii.gz`)
rather than raw or minimally-preprocessed BOLD: AROMA denoising is standard
practice for resting-state functional-connectivity analysis, and
MNI152NLin6Asym is the same template family as this repo's cached
Schaefer-100 atlas (`/root/nilearn_data/schaefer_2018/...FSLMNI152_1mm...`),
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

_DATASET_ID = "ds006644"
_BUCKET = "openneuro.org"
_ATLAS_PATH = "/root/nilearn_data/schaefer_2018/Schaefer2018_100Parcels_7Networks_order_FSLMNI152_1mm.nii.gz"
_SESSION = "ses-02"
_BOLD_KEY_TMPL = (
    f"{_DATASET_ID}/derivatives/fmriprep/{{sub}}/{_SESSION}/func/"
    f"{{sub}}_{_SESSION}_task-rest_space-MNI152NLin6Asym_desc-smoothAROMAnonaggr_bold.nii.gz"
)


def load_group_labels() -> dict[str, str]:
    """subject_id -> 'verum'|'placebo' from the real participants.tsv `condition` column.

    Never inferred from folder/subject naming -- ds006644's subject IDs
    (sub-01..sub-40) carry no group information themselves.
    """
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    obj = s3.get_object(Bucket=_BUCKET, Key=f"{_DATASET_ID}/participants.tsv")
    text = obj["Body"].read().decode("utf-8")
    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    out: dict[str, str] = {}
    for row in reader:
        pid = row["participant_id"]
        sub = pid if pid.startswith("sub-") else f"sub-{pid}"
        cond = (row.get("condition") or "").strip()
        if cond in ("verum", "placebo"):
            out[sub] = cond
    return out


def download_subject_bold(subject: str, dest_dir: Path) -> Path:
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    key = _BOLD_KEY_TMPL.format(sub=subject)
    dest = dest_dir / f"{subject}_{_SESSION}_bold.nii.gz"
    dest_dir.mkdir(parents=True, exist_ok=True)
    s3.download_file(_BUCKET, key, str(dest))
    return dest


def process_subject(subject: str, group: str, work_root: Path) -> SubjectResult:
    bold_path = download_subject_bold(subject, work_root)
    try:
        res = run_subject(
            subject_id=subject, group=group, bold_path=str(bold_path),
            atlas_labels_img=_ATLAS_PATH, t_r=1.8, confounds=None,
            connectivity_kind="correlation", provenance="real_fmri",
        )
    finally:
        bold_path.unlink(missing_ok=True)  # disk-bounded: delete raw before next subject
    return res


def run(out_dir: str, work_root: str, limit: int | None, subjects: list[str] | None) -> int:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    work_path = Path(work_root)

    manifest_path = out_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"processed": {}}

    labels = load_group_labels()
    all_subjects = subjects if subjects is not None else sorted(labels.keys())
    if limit is not None:
        remaining = [s for s in all_subjects if s not in manifest["processed"]][:limit]
    else:
        remaining = [s for s in all_subjects if s not in manifest["processed"]]

    print(f"{len(all_subjects)} subjects total ({sum(1 for v in labels.values() if v=='verum')} verum / "
          f"{sum(1 for v in labels.values() if v=='placebo')} placebo), "
          f"{len(manifest['processed'])} already done, {len(remaining)} to process this run.")

    for sub in remaining:
        group = labels.get(sub)
        if group is None:
            print(f"--- {sub}: SKIP (no group label in participants.tsv) ---")
            continue
        print(f"--- {sub} ({group}) ---")
        try:
            res = process_subject(sub, group, work_path)
        except Exception as exc:  # never crash the whole cohort run on one bad subject
            res = SubjectResult(
                subject_id=sub, group=group, n_regions=0, n_timepoints=0,
                betti0=0, betti1=0, total_persistence_h1=0.0, modularity=0.0,
                global_efficiency=0.0, mean_degree=0.0, small_worldness=0.0,
                provenance="real_fmri", error=str(exc),
            )
        manifest["processed"][sub] = res.to_dict()
        manifest_path.write_text(json.dumps(manifest, indent=2))
        status = "OK" if not res.error else f"ERROR: {res.error[:100]}"
        print(f"  {status}  betti1={res.betti1} total_pers_h1={res.total_persistence_h1:.3f}")

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
    a = p.parse_args()
    return run(a.out, a.work_root, a.limit, a.subjects)


if __name__ == "__main__":
    raise SystemExit(main())
