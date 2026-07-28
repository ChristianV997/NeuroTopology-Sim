"""Cohort-level subject-blocked statistics over a streamed dataset's output.

Loads every `sub-*_features_m.csv` + `sub-*_features_t.csv` a streaming run
produced, joins them by `row_id` (Level-T rows carry the topology metrics but
not the semantic `state_label`, which lives on the Level-M row -- the same
join `build_group_significance_report` does), and runs BOTH the
subject-blocked permutation test and the mixed-effects model from
`analysis/permutation.py` on each requested 2-group contrast.

The subject-blocked result is the honest one for a multi-subject cohort: it
aggregates each subject to a single value first, so pseudoreplication (many
windows from one subject inflating significance) is structurally impossible.
The window-pooled test is reported alongside only to make the difference
visible, never on its own.

For ds004917 (TMS-EEG PCIst) the unit is (subject, site) not a window, so a
separate `--pcist-jsonl` mode reads that streamer's `pcist_by_site.jsonl` and
runs the site contrasts directly.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_METRICS = ("q_net", "q_abs", "f_dress", "defect_density")


def _load_joined_rows(stream_dir: str) -> list[dict]:
    """Join Level-M (state_label) and Level-T (topology metrics) by row_id."""
    m_by_id: dict[str, dict] = {}
    for f in glob.glob(str(Path(stream_dir) / "sub-*_features_m.csv")):
        if Path(f).stat().st_size == 0:
            continue
        for r in csv.DictReader(open(f, encoding="utf-8")):
            m_by_id[r["row_id"]] = r

    joined: list[dict] = []
    for f in glob.glob(str(Path(stream_dir) / "sub-*_features_t.csv")):
        if Path(f).stat().st_size == 0:
            continue
        for t in csv.DictReader(open(f, encoding="utf-8")):
            m = m_by_id.get(t["row_id"])
            if m is None:
                continue
            state = m.get("state_label")
            if not state:
                continue
            row = {"subject_id": t["subject_id"], "state_label": state}
            ok = True
            for metric in _METRICS:
                try:
                    row[metric] = float(t[metric])
                except (KeyError, ValueError):
                    ok = False
                    break
            if ok:
                joined.append(row)
    return joined


def _contrast_stats(rows: list[dict], class0: str, class1: str) -> dict:
    import pandas as pd

    from analysis.permutation import (
        mixedlm_group_effect,
        permutation_test,
        subject_blocked_permutation_test,
    )

    sub = [r for r in rows if r["state_label"] in (class0, class1)]
    df = pd.DataFrame(sub)
    if df.empty:
        return {"status": "no_data"}
    n_subjects = df["subject_id"].nunique()
    per_state = {s: int((df["state_label"] == s).sum()) for s in (class0, class1)}

    out: dict = {
        "n_windows": len(df), "n_subjects": n_subjects,
        "windows_per_state": per_state, "metrics": {},
    }
    for metric in _METRICS:
        a = df.loc[df["state_label"] == class0, metric].to_numpy(dtype=float)
        b = df.loc[df["state_label"] == class1, metric].to_numpy(dtype=float)
        if len(a) < 2 or len(b) < 2:
            out["metrics"][metric] = {"status": "insufficient_data"}
            continue
        pooled = permutation_test(a, b, n_permutations=5000, seed=0)
        blocked = subject_blocked_permutation_test(
            df.rename(columns={metric: "value", "state_label": "grp"}),
            "value", "grp", "subject_id", n_permutations=5000, seed=0,
        )
        entry = {
            "window_pooled_p": pooled.p_value,
            "subject_blocked_p": blocked.p_value,
            "effect_size_d": pooled.effect_size_d,
        }
        try:
            mlm = mixedlm_group_effect(
                df.rename(columns={metric: "value", "state_label": "grp"}),
                "value", "grp", "subject_id",
            )
            entry["mixedlm_p"] = mlm.p_value
            entry["mixedlm_converged"] = mlm.converged
            entry["mixedlm_convergence_warning"] = mlm.convergence_warning
        except Exception as exc:  # keep the permutation results even if MixedLM fails
            entry["mixedlm_error"] = str(exc)
        out["metrics"][metric] = entry
    return out


def analyze_windowed(stream_dir: str, contrasts: list[tuple[str, str]], output: str) -> None:
    rows = _load_joined_rows(stream_dir)
    result = {
        "stream_dir": stream_dir,
        "n_joined_windows": len(rows),
        "n_subjects": len({r["subject_id"] for r in rows}),
        "contrasts": {f"{c0}_vs_{c1}": _contrast_stats(rows, c0, c1) for c0, c1 in contrasts},
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"wrote {output}: {result['n_subjects']} subjects, {result['n_joined_windows']} windows")


def analyze_pcist(jsonl_path: str, contrasts: list[tuple[str, str]], output: str) -> None:
    import pandas as pd

    from analysis.permutation import subject_blocked_permutation_test

    rows = [json.loads(l) for l in Path(jsonl_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    df = pd.DataFrame([r for r in rows if r.get("pcist") is not None])
    result: dict = {
        "jsonl": jsonl_path,
        "n_subjects": int(df["subject_id"].nunique()) if not df.empty else 0,
        "n_site_rows": len(df),
        "contrasts": {},
    }
    for c0, c1 in contrasts:
        sub = df[df["site"].isin((c0, c1))][["subject_id", "site", "pcist"]].rename(
            columns={"pcist": "value", "site": "grp"})
        if sub["grp"].nunique() < 2:
            result["contrasts"][f"{c0}_vs_{c1}"] = {"status": "insufficient_groups"}
            continue
        res = subject_blocked_permutation_test(sub, "value", "grp", "subject_id", n_permutations=5000, seed=0)
        result["contrasts"][f"{c0}_vs_{c1}"] = res.to_dict()
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"wrote {output}: {result['n_subjects']} subjects, {result['n_site_rows']} site rows")


def _parse_contrasts(specs: list[str]) -> list[tuple[str, str]]:
    out = []
    for s in specs:
        a, b = s.split(":")
        out.append((a, b))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stream-dir", default=None, help="Windowed-dataset stream output dir")
    ap.add_argument("--pcist-jsonl", default=None, help="ds004917 pcist_by_site.jsonl")
    ap.add_argument("--contrasts", nargs="+", required=True, help="e.g. wake:rem awake:sedated")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    contrasts = _parse_contrasts(args.contrasts)
    if args.pcist_jsonl:
        analyze_pcist(args.pcist_jsonl, contrasts, args.output)
    else:
        analyze_windowed(args.stream_dir, contrasts, args.output)


if __name__ == "__main__":
    main()
