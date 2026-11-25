from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from runs.run_record import RunRecordV1, write_json
from validation.pci_validation import q_pcist_correlation

DEFAULT_N_CLUSTERS = 3

# Cross-domain aggregation mixes EEG proxies, physionet spectral proxies, and
# physics demos. Fail closed: never claim empirical / scientific_pass.
_EVIDENCE_CLASS = "cross_domain_aggregate_unvalidated"
_RUN_MODE = "cross_domain_aggregate"
_METRIC_KIND = "cross_domain_mixed_proxy_aggregate"


def cross_domain_evidence_watermarks() -> dict:
    """Fail-closed provenance stamps for cross-domain CSV/meta/RunRecord outputs."""
    return {
        "evidence_class": _EVIDENCE_CLASS,
        "run_mode": _RUN_MODE,
        "metrics_are_empirical": False,
        "scientific_pass": False,
        "metric_kind": _METRIC_KIND,
    }


def _safe_read_csv(path: Path) -> pd.DataFrame:
    """Read CSV robustly, returning an empty frame for blank files."""
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def run(results_root: str | Path, output_csv: str | Path):
    """Aggregate available domain metrics and attach simple unsupervised clusters.

    PhysioNet spectral proxies keep an explicit ``q_source=Q_proxy`` stamp and
    ``metric_kind=physionet_spectral_phase_proxy`` so aggregating them into the
    shared Q/Qabs slots cannot silently look like topology charges.
    """
    results_root = Path(results_root)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    rows = []

    for ds in ["ds002094", "ds005620", "ds001787", "ds003969", "ds003816"]:
        f = results_root / ds / f"metrics_{ds}.csv"
        if not f.exists():
            f = results_root / f"{ds}.csv"
        if f.exists():
            df = _safe_read_csv(f)
            if len(df):
                rows.append({
                    "dataset": ds,
                    "domain": "brain",
                    "Q": float(df["Q"].mean()) if "Q" in df.columns else None,
                    "Qabs": float(df["Qabs"].mean()) if "Qabs" in df.columns else None,
                    "phase_grad": float(df["phase_grad"].mean()) if "phase_grad" in df.columns else None,
                    "q_source": "Q",
                    "metric_kind": "eeg_csv_aggregate_proxy",
                })

    f = results_root / "physionet_gaba" / "metrics_physionet_gaba.csv"
    if f.exists():
        df = _safe_read_csv(f)
        if len(df):
            # Keep _proxy provenance: values may feed the shared Q/Qabs slots for
            # clustering, but q_source + metric_kind remain explicit.
            rows.append({
                "dataset": "physionet_gaba",
                "domain": "brain_like_signal",
                "Q": float(df["Q_proxy"].mean()) if "Q_proxy" in df.columns else None,
                "Qabs": float(df["Qabs_proxy"].mean()) if "Qabs_proxy" in df.columns else None,
                "phase_grad": None,
                "q_source": "Q_proxy",
                "metric_kind": "physionet_spectral_phase_proxy",
            })

    f = results_root / "the_well" / "metrics_the_well.csv"
    if not f.exists():
        f = results_root / "the_well.csv"
    if f.exists():
        df = _safe_read_csv(f)
        if len(df):
            rows.append({
                "dataset": "the_well",
                "domain": "physics",
                "Q": float(df["Q"].mean()) if "Q" in df.columns else None,
                "Qabs": float(df["Qabs"].mean()) if "Qabs" in df.columns else None,
                "phase_grad": None,
                "q_source": "Q",
                "metric_kind": "physics_csv_aggregate",
            })

    raw_n = len(rows)
    df = pd.DataFrame(rows)
    dropped_incomplete = 0
    if len(df):
        before = len(df)
        df = df.dropna(subset=["Q", "Qabs"])
        dropped_incomplete = before - len(df)
    if len(df):
        X = df[["Q", "Qabs"]].values
        X = StandardScaler().fit_transform(X)
        df["cluster"] = KMeans(
            n_clusters=min(DEFAULT_N_CLUSTERS, len(df)),
            random_state=42,
            n_init=10,
        ).fit_predict(X)

    # Compute Q–complexity correlation across EEG datasets, preferring
    # pcist_proxy (current naming) and falling back to legacy PCIst.
    pci_frames = []
    for ds in ["ds002094", "ds005620", "ds001787", "ds003969", "ds003816"]:
        f = results_root / ds / f"metrics_{ds}.csv"
        if not f.exists():
            f = results_root / f"{ds}.csv"
        tmp = _safe_read_csv(f)
        if "Qabs" not in tmp.columns:
            continue
        if "pcist_proxy" in tmp.columns:
            pci_frames.append(tmp[["Qabs", "pcist_proxy"]])
        elif "PCIst" in tmp.columns:
            pci_frames.append(tmp[["Qabs", "PCIst"]].rename(columns={"PCIst": "pcist_proxy"}))
    if pci_frames:
        all_pci = pd.concat(pci_frames, ignore_index=True)
        corr = q_pcist_correlation(all_pci)
        df.attrs["q_pcist_r"] = corr.get("r")
        df.attrs["q_pcist_p"] = corr.get("p")
        df.attrs["q_pcist_n"] = corr.get("n")

    df.to_csv(output_csv, index=False)

    marks = cross_domain_evidence_watermarks()
    meta = {
        "records": int(len(df)),
        "raw_candidate_rows": int(raw_n),
        "dropped_incomplete_q": int(dropped_incomplete),
        "results_root": str(results_root),
        "csv": str(output_csv),
        "cluster_inputs_are_commensurate": False,
        "note": (
            "Mixed proxy/topology aggregate. Physionet rows keep "
            "q_source=Q_proxy; Q/Qabs slots are not empirical topology charges."
        ),
        **marks,
    }
    if "q_pcist_r" in df.attrs:
        meta["q_pcist_r"] = df.attrs.get("q_pcist_r")
        meta["q_pcist_p"] = df.attrs.get("q_pcist_p")
        meta["q_pcist_n"] = df.attrs.get("q_pcist_n")
    Path(str(output_csv) + ".meta.json").write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )

    metrics = {
        "n_rows": int(len(df)),
        "raw_candidate_rows": int(raw_n),
        "dropped_incomplete_q": int(dropped_incomplete),
        "metric_kind": marks["metric_kind"],
        "cluster_inputs_are_commensurate": False,
    }
    blob = json.dumps(
        {"results_root": str(results_root), "metrics": metrics},
        sort_keys=True,
        separators=(",", ":"),
    )
    run_id = hashlib.sha256(blob.encode()).hexdigest()[:16]
    record = RunRecordV1.make(
        run_id=run_id,
        run_kind="cross_domain",
        data_mode="aggregate",
        metrics=metrics,
        artifacts={"csv": str(output_csv), "meta": str(output_csv) + ".meta.json"},
        source="pipelines.run_cross_domain",
        evidence_class=marks["evidence_class"],
        run_mode=marks["run_mode"],
        metrics_are_empirical=marks["metrics_are_empirical"],
        scientific_pass=marks["scientific_pass"],
        metric_kind=marks["metric_kind"],
    )
    record.input = {"results_root": str(results_root)}
    write_json(record, output_csv.parent / "RunRecord.json")

    return df
