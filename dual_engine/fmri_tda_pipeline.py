"""Resting-state fMRI functional-connectivity + persistent-homology pipeline.

Correctly scoped for BOLD fMRI (e.g. OpenNeuro ds000245): this does NOT reuse the EEG
analytic-signal phase-winding pipeline (BOLD at TR~2.5s cannot carry that phase information).
Instead it computes:

  1. Parcellated region x time series (NiftiLabelsMasker: standardize, band-pass 0.01-0.1 Hz,
     confound regression if a confounds file is supplied).
  2. Functional connectivity matrix (correlation / partial correlation, nilearn).
  3. Persistent homology on the connectivity graph (ripser on the 1-|corr| distance matrix):
     Betti numbers b0/b1 and total persistence.
  4. Classical graph metrics (networkx): modularity, global efficiency, mean degree,
     small-worldness proxy.
  5. Group comparison (CTL vs ODN vs ODP) with effect sizes, not just p-values.

Provenance: every per-subject result is stamped `provenance="real_fmri"` when run on real
NIfTI, or `provenance="synthetic_proxy"` for the offline self-test fixture.

IMPORTANT (honesty): as of this commit the pipeline has been verified end-to-end ONLY on a
synthetic 4D fMRI fixture (see `synthetic_bold_fixture`). It has NOT been run on the real
ds000245 volumes, which could not be transferred into the build sandbox (the Google Drive
MCP connector returns file bytes as base64 in the tool response; a 38 MB NIfTI is far too
large for that channel). Run it on a machine with the data on local disk to obtain real
results. No real empirical result is claimed here.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
import sys
from typing import Optional

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# --------------------------------------------------------------------------- data classes


@dataclass
class SubjectResult:
    subject_id: str
    group: str
    n_regions: int
    n_timepoints: int
    betti0: int
    betti1: int
    total_persistence_h1: float
    modularity: float
    global_efficiency: float
    mean_degree: float
    small_worldness: float
    provenance: str
    error: str = ""
    covariates: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SubjectResult":
        """Rebuild a SubjectResult from a serialized dict (ignores unknown keys)."""
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


# --------------------------------------------------------------------------- participants


def load_participants(bids_root: str) -> dict:
    """Parse a BIDS `participants.tsv` into {subject_id -> {column: value}}.

    Subject ids are normalized to include the `sub-` prefix (matching folder names). Values
    are kept as strings except numeric-looking ones, which are coerced to float. Returns an
    empty dict if the file is absent -- covariates are optional and never fabricated.
    """
    path = Path(bids_root) / "participants.tsv"
    if not path.exists():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return {}
    header = lines[0].split("\t")
    id_col = 0  # BIDS mandates participant_id first
    out: dict = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = line.split("\t")
        if len(cells) != len(header):
            continue
        sid = cells[id_col]
        if not sid.startswith("sub-"):
            sid = "sub-" + sid
        row = {}
        for col, val in zip(header, cells):
            if col == "participant_id":
                continue
            try:
                row[col] = float(val)
            except (ValueError, TypeError):
                row[col] = val
        out[sid] = row
    return out


# --------------------------------------------------------------------------- parcellation


def parcellate_bold(
    bold_path: str,
    atlas_labels_img: Optional[str] = None,
    t_r: Optional[float] = None,
    confounds: Optional[str] = None,
    low_pass: float = 0.1,
    high_pass: float = 0.01,
    n_synthetic_parcels: int = 100,
) -> np.ndarray:
    """Return a (n_timepoints, n_regions) parcellated time series.

    If `atlas_labels_img` is given, use nilearn's NiftiLabelsMasker with standardization,
    band-pass filtering, and optional confound regression (the standard resting-state
    recipe). If no atlas is given (offline self-test), fall back to a deterministic
    coordinate-based parcellation via KMeans on in-brain voxel coordinates -- labelled
    synthetic, never presented as an anatomical atlas.
    """
    import nibabel as nib

    img = nib.load(bold_path)
    data = np.asanyarray(img.dataobj)  # (X, Y, Z, T)
    if data.ndim != 4:
        raise ValueError(f"expected 4D BOLD, got shape {data.shape}")

    if atlas_labels_img is not None:
        from nilearn.maskers import NiftiLabelsMasker

        masker = NiftiLabelsMasker(
            labels_img=atlas_labels_img,
            standardize="zscore_sample",
            low_pass=low_pass,
            high_pass=high_pass,
            t_r=t_r,
            verbose=0,
        )
        ts = masker.fit_transform(bold_path, confounds=confounds)
        return np.asarray(ts, dtype=float)

    # ---- offline fallback: deterministic coordinate parcellation (synthetic) ----
    from sklearn.cluster import KMeans
    from scipy.signal import butter, filtfilt

    X, Y, Z, T = data.shape
    mean_vol = data.mean(axis=3)
    thresh = np.percentile(mean_vol, 60)  # crude in-brain mask
    mask = mean_vol > thresh
    coords = np.argwhere(mask)
    if len(coords) < n_synthetic_parcels:
        n_synthetic_parcels = max(2, len(coords) // 4)
    km = KMeans(n_clusters=n_synthetic_parcels, n_init=3, random_state=0)
    labels = km.fit_predict(coords)

    series = np.zeros((T, n_synthetic_parcels), dtype=float)
    for p in range(n_synthetic_parcels):
        vox = coords[labels == p]
        if len(vox) == 0:
            continue
        vals = data[vox[:, 0], vox[:, 1], vox[:, 2], :]  # (n_vox, T)
        series[:, p] = vals.mean(axis=0)

    # standardize + band-pass (same intent as the masker path)
    series = (series - series.mean(axis=0)) / (series.std(axis=0) + 1e-9)
    if t_r:
        fs = 1.0 / t_r
        nyq = fs / 2.0
        lo, hi = high_pass / nyq, min(low_pass / nyq, 0.99)
        if 0 < lo < hi < 1:
            b, a = butter(2, [lo, hi], btype="band")
            series = filtfilt(b, a, series, axis=0)
    return series


# --------------------------------------------------------------------------- connectivity


def connectivity_matrix(timeseries: np.ndarray, kind: str = "correlation") -> np.ndarray:
    """(T, R) -> (R, R) connectivity matrix using nilearn ConnectivityMeasure."""
    from nilearn.connectome import ConnectivityMeasure

    cm = ConnectivityMeasure(kind=kind)
    mat = cm.fit_transform([np.asarray(timeseries, dtype=float)])[0]
    np.fill_diagonal(mat, 0.0)
    return mat


# --------------------------------------------------------------------------- topology


def persistent_homology(conn: np.ndarray) -> dict:
    """Betti b0/b1 and total H1 persistence from the connectivity graph via ripser.

    Distance = 1 - |corr| (strong connections => short distance). Betti numbers are counted
    as features alive across the filtration (number of finite H1 bars; b0 = number of points
    minus merges, reported as count of H0 bars).
    """
    import ripser

    R = conn.shape[0]
    dist = 1.0 - np.abs(conn)
    np.fill_diagonal(dist, 0.0)
    dist = np.clip((dist + dist.T) / 2.0, 0.0, None)
    dgms = ripser.ripser(dist, distance_matrix=True, maxdim=1)["dgms"]
    h0 = dgms[0] if len(dgms) > 0 else np.empty((0, 2))
    h1 = dgms[1] if len(dgms) > 1 else np.empty((0, 2))
    finite_h1 = h1[np.isfinite(h1[:, 1])] if h1.size else h1
    total_persistence = float(np.sum(finite_h1[:, 1] - finite_h1[:, 0])) if len(finite_h1) else 0.0
    return {
        "betti0": int(h0.shape[0]),
        "betti1": int(h1.shape[0]),
        "total_persistence_h1": total_persistence,
    }


def graph_metrics(conn: np.ndarray, density: float = 0.15) -> dict:
    """Classical graph metrics on a density-thresholded absolute-connectivity graph."""
    import networkx as nx

    R = conn.shape[0]
    a = np.abs(conn.copy())
    np.fill_diagonal(a, 0.0)
    # keep the top `density` fraction of edges by weight
    iu = np.triu_indices(R, k=1)
    weights = a[iu]
    if weights.size == 0:
        return {"modularity": 0.0, "global_efficiency": 0.0, "mean_degree": 0.0, "small_worldness": 0.0}
    k = max(1, int(density * weights.size))
    thr = np.sort(weights)[-k]
    A = (a >= thr).astype(float)
    G = nx.from_numpy_array(A)

    mean_degree = float(np.mean([d for _, d in G.degree()]))
    try:
        global_eff = float(nx.global_efficiency(G))
    except Exception:
        global_eff = 0.0
    try:
        communities = nx.community.greedy_modularity_communities(G)
        modularity = float(nx.community.modularity(G, communities))
    except Exception:
        modularity = 0.0
    # small-worldness proxy: (C/C_rand) / (L/L_rand) approximated via transitivity & path length
    try:
        C = nx.transitivity(G)
        if nx.is_connected(G):
            L = nx.average_shortest_path_length(G)
        else:
            comps = (G.subgraph(c) for c in nx.connected_components(G))
            L = np.mean([nx.average_shortest_path_length(c) for c in comps if c.number_of_nodes() > 1])
        n, m = G.number_of_nodes(), G.number_of_edges()
        p = (2 * m) / (n * (n - 1)) if n > 1 else 0
        C_rand = p
        L_rand = (np.log(n) / np.log(max(mean_degree, 1.001))) if mean_degree > 1 else 1.0
        small_world = float((C / C_rand) / (L / L_rand)) if (C_rand > 0 and L > 0 and L_rand > 0) else 0.0
    except Exception:
        small_world = 0.0

    return {
        "modularity": modularity,
        "global_efficiency": global_eff,
        "mean_degree": mean_degree,
        "small_worldness": small_world,
    }


# --------------------------------------------------------------------------- per subject


def run_subject(
    subject_id: str,
    group: str,
    bold_path: str,
    atlas_labels_img: Optional[str] = None,
    t_r: Optional[float] = 2.5,
    confounds: Optional[str] = None,
    connectivity_kind: str = "correlation",
    provenance: str = "real_fmri",
) -> SubjectResult:
    """Full per-subject pipeline. Returns a SubjectResult (with error set on failure)."""
    try:
        ts = parcellate_bold(bold_path, atlas_labels_img=atlas_labels_img, t_r=t_r, confounds=confounds)
        conn = connectivity_matrix(ts, kind=connectivity_kind)
        ph = persistent_homology(conn)
        gm = graph_metrics(conn)
        return SubjectResult(
            subject_id=subject_id, group=group,
            n_regions=conn.shape[0], n_timepoints=ts.shape[0],
            betti0=ph["betti0"], betti1=ph["betti1"],
            total_persistence_h1=ph["total_persistence_h1"],
            modularity=gm["modularity"], global_efficiency=gm["global_efficiency"],
            mean_degree=gm["mean_degree"], small_worldness=gm["small_worldness"],
            provenance=provenance,
        )
    except Exception as exc:  # never fabricate -- record the failure
        return SubjectResult(
            subject_id=subject_id, group=group, n_regions=0, n_timepoints=0,
            betti0=0, betti1=0, total_persistence_h1=0.0, modularity=0.0,
            global_efficiency=0.0, mean_degree=0.0, small_worldness=0.0,
            provenance=provenance, error=str(exc),
        )


# --------------------------------------------------------------------------- group stats


def group_compare(results: list[SubjectResult], metric: str) -> dict:
    """One-way ANOVA + eta-squared effect size across groups for a chosen metric."""
    from scipy import stats

    ok = [r for r in results if not r.error]
    groups: dict[str, list] = {}
    for r in ok:
        groups.setdefault(r.group, []).append(getattr(r, metric))
    arrays = [np.asarray(v, dtype=float) for v in groups.values() if len(v) > 0]
    if len(arrays) < 2:
        return {"metric": metric, "n_groups": len(arrays), "note": "insufficient groups"}
    F, p = stats.f_oneway(*arrays)
    grand = np.concatenate(arrays)
    ss_between = sum(len(a) * (a.mean() - grand.mean()) ** 2 for a in arrays)
    ss_total = np.sum((grand - grand.mean()) ** 2)
    eta_sq = float(ss_between / ss_total) if ss_total > 0 else 0.0
    return {
        "metric": metric,
        "group_means": {g: float(np.mean(v)) for g, v in groups.items()},
        "group_n": {g: len(v) for g, v in groups.items()},
        "F": float(F), "p_value": float(p), "eta_squared": eta_sq,
    }


# --------------------------------------------------------------------------- aggregation


_STAT_METRICS = ("betti1", "total_persistence_h1", "modularity", "global_efficiency")


def build_cohort_payload(results: list[SubjectResult], provenance: str = "real_fmri") -> dict:
    """Assemble the canonical cohort result dict (per-subject records + group statistics)."""
    stats = {m: group_compare(results, m) for m in _STAT_METRICS}
    n_ok = sum(1 for r in results if not r.error)
    return {
        "pipeline": "fmri_tda_v1",
        "provenance": provenance,
        "n_subjects": len(results),
        "n_ok": n_ok,
        "n_errors": len(results) - n_ok,
        "subjects": [r.to_dict() for r in results],
        "group_stats": stats,
    }


def aggregate_subject_files(paths: list, provenance: str = "real_fmri") -> dict:
    """Merge one-or-more `subjects_*.json` files (each a list of subject dicts) into a cohort.

    Used by the CI fan-out/aggregate flow: each per-group job emits a subjects list, then a
    single aggregate step merges them and computes the cross-group ANOVA + effect sizes.
    """
    results: list[SubjectResult] = []
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        rows = data["subjects"] if isinstance(data, dict) and "subjects" in data else data
        for row in rows:
            results.append(SubjectResult.from_dict(row))
    return build_cohort_payload(results, provenance=provenance)


def render_markdown_summary(payload: dict) -> str:
    """Render a compact Markdown group-comparison table (for the GitHub run-page summary)."""
    prov = payload.get("provenance", "?")
    n = payload.get("n_subjects", len(payload.get("subjects", [])))
    n_err = payload.get("n_errors", sum(1 for s in payload.get("subjects", []) if s.get("error")))
    lines = [
        f"## fMRI-TDA cohort result ({prov})",
        "",
        f"- **Subjects:** {n}  |  **errored:** {n_err}",
        "",
        "| Metric | CTL | ODN | ODP | F | p | η² |",
        "|---|---|---|---|---|---|---|",
    ]
    for m in _STAT_METRICS:
        s = payload.get("group_stats", {}).get(m, {})
        means = s.get("group_means", {})

        def _fmt(g, _means=means):
            return f"{_means[g]:.3f}" if g in _means else "—"

        F = s.get("F")
        p = s.get("p_value")
        eta = s.get("eta_squared")
        lines.append(
            f"| {m} | {_fmt('CTL')} | {_fmt('ODN')} | {_fmt('ODP')} | "
            f"{'%.2f' % F if F is not None else '—'} | "
            f"{'%.4f' % p if p is not None else '—'} | "
            f"{'%.3f' % eta if eta is not None else '—'} |"
        )
    # error notes, if any
    errored = [s for s in payload.get("subjects", []) if s.get("error")]
    if errored:
        lines += ["", "<details><summary>Errored subjects</summary>", ""]
        for s in errored[:20]:
            lines.append(f"- `{s.get('subject_id')}` ({s.get('group')}): {s.get('error', '')[:120]}")
        lines += ["", "</details>"]
    if prov != "real_fmri":
        lines += ["", "> ⚠️ Not a real-data run — provenance is not `real_fmri`."]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- synthetic fixture


def synthetic_bold_fixture(path: str, group: str = "CTL", n_t: int = 60, dim: int = 16,
                           seed: int = 0) -> str:
    """Write a small synthetic 4D NIfTI so the pipeline can be verified fully offline.

    The signal is synthetic (structured spatiotemporal noise with a few correlated blocks
    whose coupling strength depends on `group`), labelled synthetic_proxy by every consumer.
    NOT real fMRI.
    """
    import nibabel as nib

    rng = np.random.default_rng(seed)
    coupling = {"CTL": 0.9, "ODN": 0.6, "ODP": 0.3}.get(group, 0.5)
    # 4 latent networks driving blocks of voxels
    latents = rng.standard_normal((4, n_t))
    data = rng.standard_normal((dim, dim, dim, n_t)) * 0.5
    blocks = np.array_split(np.arange(dim), 4)
    for li, bx in enumerate(blocks):
        for x in bx:
            data[x, :, :, :] += coupling * latents[li][None, None, :]
    data = data.astype(np.float32)
    affine = np.eye(4)
    nib.save(nib.Nifti1Image(data, affine), path)
    return path


def _self_test(out_dir: str = "outputs/fmri_tda", per_group: int = 4) -> dict:
    """Run the full pipeline on a synthetic fixture (`per_group` subjects per group).

    Uses several subjects per group so the Stage-4 group statistics (ANOVA + effect size)
    actually exercise instead of degenerating on n=1. All data are synthetic_proxy.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for gi, grp in enumerate(("CTL", "ODN", "ODP")):
        for i in range(per_group):
            seed = gi * 100 + i  # deterministic, reproducible across runs
            p = str(out / f"synthetic_{grp}_{i}.nii.gz")
            synthetic_bold_fixture(p, group=grp, seed=seed)
            res = run_subject(f"synthetic-{grp}{i}", grp, p, t_r=2.5, provenance="synthetic_proxy")
            results.append(res)
    stats = {m: group_compare(results, m) for m in
             ("betti1", "total_persistence_h1", "modularity", "global_efficiency")}
    payload = {
        "pipeline": "fmri_tda_v1",
        "provenance": "synthetic_proxy",
        "real_data_run": False,
        "note": "Verified on synthetic fixture only; not run on real ds000245 (see module docstring).",
        "subjects": [r.to_dict() for r in results],
        "group_stats": stats,
    }
    (out / "self_test_result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _infer_group(subject_name: str) -> str:
    name = subject_name.replace("sub-", "")
    return "CTL" if "CTL" in name else "ODN" if "ODN" in name else "ODP" if "ODP" in name else "UNK"


def _write_summary(payload: dict, out: Path, summary_env: Optional[str]) -> None:
    """Write the JSON payload plus a Markdown summary (to a file and, if set, $GITHUB_STEP_SUMMARY)."""
    md = render_markdown_summary(payload)
    (out / "summary.md").write_text(md, encoding="utf-8")
    if summary_env:
        try:
            with open(summary_env, "a", encoding="utf-8") as fh:
                fh.write(md)
        except OSError:
            pass


def main(argv=None) -> int:
    import os

    ap = argparse.ArgumentParser(description="Resting-state fMRI FC + persistent homology pipeline")
    ap.add_argument("--self-test", action="store_true", help="Run offline synthetic self-test")
    ap.add_argument("--bids-root", default=None, help="Local BIDS root with sub-*/func/*_bold.nii.gz")
    ap.add_argument("--atlas", default=None, help="Atlas labels NIfTI (e.g. Schaefer-200); required for real anatomical parcellation")
    ap.add_argument("--t-r", type=float, default=2.5)
    ap.add_argument("--group", default=None, help="Process only subjects in this group (CTL/ODN/ODP) -- used by the CI fan-out")
    ap.add_argument("--emit-subjects", default=None, help="Write per-subject results (list) to this JSON path instead of a full cohort")
    ap.add_argument("--aggregate", nargs="+", default=None, help="Merge these subjects_*.json files into a cohort_result.json (+ stats)")
    ap.add_argument("--out", default="outputs/fmri_tda")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary_env = os.getenv("GITHUB_STEP_SUMMARY")

    # ---- aggregate mode: merge per-group subject files into the final cohort result ----
    if args.aggregate:
        payload = aggregate_subject_files(args.aggregate, provenance="real_fmri")
        (out / "cohort_result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        _write_summary(payload, out, summary_env)
        gs = payload["group_stats"]["total_persistence_h1"]
        print(f"[aggregate] {payload['n_subjects']} subjects -> {out/'cohort_result.json'}")
        if "group_means" in gs:
            print(f"  total_persistence_h1 means: {gs['group_means']}  F={gs.get('F'):.2f} p={gs.get('p_value'):.4f}")
        return 0

    # ---- offline self-test ----
    if args.self_test or not args.bids_root:
        payload = _self_test(args.out)
        print(f"[self-test] provenance={payload['provenance']} real_data_run={payload['real_data_run']}")
        for r in payload["subjects"]:
            print(f"  {r['subject_id']}: regions={r['n_regions']} b1={r['betti1']} "
                  f"totpers={r['total_persistence_h1']:.3f} mod={r['modularity']:.3f} err={r['error'][:40]}")
        print(f"-> {Path(args.out)/'self_test_result.json'}")
        return 0

    # ---- real run: discover sub-*/func/*_bold.nii.gz, infer group, attach covariates ----
    root = Path(args.bids_root)
    covariates = load_participants(args.bids_root)
    results = []
    for sub in sorted(root.glob("sub-*")):
        func = list((sub / "func").glob("*_bold.nii.gz"))
        if not func:
            continue
        group = _infer_group(sub.name)
        if args.group and group != args.group:
            continue
        res = run_subject(sub.name, group, str(func[0]),
                          atlas_labels_img=args.atlas, t_r=args.t_r,
                          provenance="real_fmri")
        res.covariates = covariates.get(sub.name, {})
        results.append(res)
        print(f"  {sub.name} ({group}): b1={res.betti1} err={res.error[:40]}")

    if args.emit_subjects:
        # fan-out mode: dump just the per-subject records (no cross-group ANOVA yet)
        Path(args.emit_subjects).parent.mkdir(parents=True, exist_ok=True)
        Path(args.emit_subjects).write_text(json.dumps(
            {"provenance": "real_fmri", "group": args.group,
             "subjects": [r.to_dict() for r in results]}, indent=2), encoding="utf-8")
        print(f"-> {args.emit_subjects} ({len(results)} subjects, group={args.group})")
        return 0

    payload = build_cohort_payload(results, provenance="real_fmri")
    (out / "cohort_result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_summary(payload, out, summary_env)
    print(f"-> {out/'cohort_result.json'} ({len(results)} subjects)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
