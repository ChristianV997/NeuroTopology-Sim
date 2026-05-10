from __future__ import annotations
from pathlib import Path
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from validation.pci_validation import q_pcist_correlation

DEFAULT_N_CLUSTERS = 3

def _safe_read_csv(path: Path) -> pd.DataFrame:
    """Read CSV robustly, returning an empty frame for blank files."""
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()

def run(results_root: str | Path, output_csv: str | Path):
    """Aggregate available domain metrics and attach simple unsupervised clusters."""
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
                })

    f = results_root / "physionet_gaba" / "metrics_physionet_gaba.csv"
    if f.exists():
        df = _safe_read_csv(f)
        if len(df):
            rows.append({
                "dataset": "physionet_gaba",
                "domain": "brain_like_signal",
                "Q": float(df["Q_proxy"].mean()) if "Q_proxy" in df.columns else None,
                "Qabs": float(df["Qabs_proxy"].mean()) if "Qabs_proxy" in df.columns else None,
                "phase_grad": None,
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
            })

    df = pd.DataFrame(rows).dropna()
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
    return df
