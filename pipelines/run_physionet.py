from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

from data.physionet_loader import load_physionet_gaba_folder


def run(input_dir: str | Path, output_csv: str | Path) -> pd.DataFrame:
    """Compute Q_proxy / Qabs_proxy from PhysioNet GABA spectral CSVs.

    The spectral files contain power-spectrum values.  We treat the normalised
    std-of-values as a phase-spread proxy (Q_proxy) and the mean absolute value
    as an amplitude proxy (Qabs_proxy) — analogous to the topological Q / Qabs
    computed on EEG/physics fields.
    """
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise FileNotFoundError(f"PhysioNet input directory does not exist: {input_dir}")
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    meta = load_physionet_gaba_folder(input_dir)
    if meta.empty:
        df = pd.DataFrame(columns=["file", "Q_proxy", "Qabs_proxy"])
        df.to_csv(output_csv, index=False)
        return df

    rows = []
    for _, row in meta.iterrows():
        try:
            arr = pd.read_csv(row["file"], header=None).values.astype(float).flatten()
        except Exception:
            continue
        if len(arr) < 4:
            continue
        norm = arr / (np.max(np.abs(arr)) + 1e-12)
        phase_proxy = np.arctan2(np.imag(np.fft.rfft(norm)[:4]),
                                  np.real(np.fft.rfft(norm)[:4]))
        grad = np.diff(phase_proxy)
        Q_proxy = float(np.sum(grad) / (2 * np.pi))
        Qabs_proxy = float(np.sum(np.abs(grad)) / (2 * np.pi))
        rows.append({"file": row["file"], "Q_proxy": Q_proxy, "Qabs_proxy": Qabs_proxy})

    df = pd.DataFrame(rows)
    df.to_csv(output_csv, index=False)
    return df
