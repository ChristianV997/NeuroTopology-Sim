#!/usr/bin/env python3
"""Stream-process ds005917 (NIMH Ketamine Mechanism of Action Study) one
subject at a time -- disk-bounded, real BOLD, WITHIN-SUBJECT drug-vs-placebo
crossover contrast on the MDD group.

**Honest scope/quality note (why this dataset differs from ds006644):**
ds005917 ships raw BOLD only -- no fMRIPrep or other spatial-normalization
derivatives (confirmed via S3 listing), and this sandbox has no FSL/ANTs to
normalize it to a shared anatomical atlas. Rather than fabricate a weak
custom registration, this module uses `dual_engine.fmri_tda_pipeline
.parcellate_bold`'s EXISTING, already-tested fallback path
(`atlas_labels_img=None` -> per-subject KMeans coordinate parcellation in
each subject's own native space, explicitly documented there as "labelled
synthetic, never presented as an anatomical atlas"). This is methodologically
sound for what this pipeline actually computes: Betti numbers, modularity,
global efficiency, and total persistence are graph-topology summary
statistics, invariant to node (region) labeling/correspondence -- they do
NOT require region N in one subject to anatomically match region N in
another. What would be invalid without a shared atlas is a per-region
statistic (e.g. "connectivity between region 12 and region 47"); this
pipeline never computes one. The BOLD SIGNAL itself is 100% real
(`provenance="real_fmri"`); only the parcel boundaries are per-subject
data-driven rather than anatomically registered.

**Design** (from the dataset's own `participants.tsv`, not inferred):
Real BIDS session labels directly encode condition: `ses-d2`/`ses-d10` =
drug (ketamine) sessions, `ses-p2`/`ses-p10` = placebo sessions (2 or 10
days post-infusion). This is a WITHIN-SUBJECT crossover -- every complete
subject has both arms. This script uses `ses-d2` vs `ses-p2` (the earlier,
closer-to-infusion timepoint for each arm) on `task-rest_run-01`, restricted
to the MDD group (n=25 with complete d/p session data -- the largest,
best-powered subgroup; `HC` n=18 and `BP` n=2 are available for a future
pass but not run here).

Each rest-run BOLD is ~50MB; downloaded, processed, and deleted one
session at a time so disk stays bounded regardless of cohort size.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dual_engine.fmri_tda_pipeline import parcellate_bold, connectivity_matrix, persistent_homology, graph_metrics  # noqa: E402

_DATASET_ID = "ds005917"
_BUCKET = "openneuro.org"
_TR = 2.5
_CONDITIONS = {"drug": "ses-d2", "placebo": "ses-p2"}
_BOLD_KEY_TMPL = f"{_DATASET_ID}/{{sub}}/{{ses}}/func/{{sub}}_{{ses}}_task-rest_run-01_bold.nii.gz"
_METRICS = ("betti1", "total_persistence_h1", "modularity", "global_efficiency", "mean_degree", "small_worldness")


def load_mdd_complete_subjects() -> list[str]:
    """MDD subjects with both infusion arms present -- real, not inferred."""
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    obj = s3.get_object(Bucket=_BUCKET, Key=f"{_DATASET_ID}/participants.tsv")
    text = obj["Body"].read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    out = []
    for row in reader:
        if row.get("group") == "MDD" and row.get("infusion_1") in ("d", "p") and row.get("infusion_2") in ("d", "p"):
            out.append(row["participant_id"])
    return out


def download_bold(subject: str, session: str, dest_dir: Path) -> Path:
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    key = _BOLD_KEY_TMPL.format(sub=subject, ses=session)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{subject}_{session}_bold.nii.gz"
    s3.download_file(_BUCKET, key, str(dest))
    return dest


def process_session(subject: str, session: str, work_root: Path) -> dict:
    try:
        bold_path = download_bold(subject, session, work_root)
    except Exception as exc:
        # Real, observed case: not every subject with complete infusion_1/2
        # crossover metadata actually has a ses-d2/ses-p2 rest-run file on S3
        # (e.g. sub-MOA113's ses-d2 is 404). Record and skip, don't crash the run.
        return {"n_regions": 0, "n_timepoints": 0, "betti0": 0, "betti1": 0,
                "total_persistence_h1": 0.0, "modularity": 0.0, "global_efficiency": 0.0,
                "mean_degree": 0.0, "small_worldness": 0.0, "error": f"download failed: {exc}"}
    try:
        ts = parcellate_bold(str(bold_path), atlas_labels_img=None, t_r=_TR, n_synthetic_parcels=100)
        conn = connectivity_matrix(ts, kind="correlation")
        ph = persistent_homology(conn)
        gm = graph_metrics(conn)
        return {
            "n_regions": int(conn.shape[0]), "n_timepoints": int(ts.shape[0]),
            "betti0": ph["betti0"], "betti1": ph["betti1"],
            "total_persistence_h1": ph["total_persistence_h1"],
            "modularity": gm["modularity"], "global_efficiency": gm["global_efficiency"],
            "mean_degree": gm["mean_degree"], "small_worldness": gm["small_worldness"],
            "error": "",
        }
    except Exception as exc:
        return {"n_regions": 0, "n_timepoints": 0, "betti0": 0, "betti1": 0,
                "total_persistence_h1": 0.0, "modularity": 0.0, "global_efficiency": 0.0,
                "mean_degree": 0.0, "small_worldness": 0.0, "error": str(exc)}
    finally:
        bold_path.unlink(missing_ok=True)  # disk-bounded


def run(out_dir: str, work_root: str, limit: int | None, subjects: list[str] | None) -> int:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    work_path = Path(work_root)

    manifest_path = out_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"processed": {}}

    all_subjects = subjects if subjects is not None else load_mdd_complete_subjects()
    remaining = [s for s in all_subjects if s not in manifest["processed"]]
    if limit is not None:
        remaining = remaining[:limit]

    print(f"{len(all_subjects)} MDD subjects with complete drug/placebo crossover, "
          f"{len(manifest['processed'])} already done, {len(remaining)} to process this run.")

    for sub in remaining:
        print(f"--- {sub} ---")
        result = {}
        for cond, ses in _CONDITIONS.items():
            r = process_session(sub, ses, work_path)
            result[cond] = r
            status = "OK" if not r["error"] else f"ERROR: {r['error'][:80]}"
            print(f"  {cond} ({ses}): {status}  betti1={r['betti1']} total_pers_h1={r['total_persistence_h1']:.3f}")
        manifest["processed"][sub] = result
        manifest_path.write_text(json.dumps(manifest, indent=2))

    (out_path / "cohort_result.json").write_text(json.dumps(manifest["processed"], indent=2))
    n_complete = sum(1 for v in manifest["processed"].values()
                      if not v["drug"]["error"] and not v["placebo"]["error"])
    print(f"-> {out_path/'cohort_result.json'} "
          f"({len(manifest['processed'])} subjects, {n_complete} with both arms clean)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="outputs/dual_engine/ds005917")
    p.add_argument("--work-root", default="data/ds005917")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--subjects", nargs="*", default=None)
    a = p.parse_args()
    return run(a.out, a.work_root, a.limit, a.subjects)


if __name__ == "__main__":
    raise SystemExit(main())
