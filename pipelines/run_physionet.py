from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data.physionet_loader import load_physionet_gaba_folder
from runs.run_record import RunRecordV1, write_json

# PhysioNet GABA spectral CSVs yield spectral phase-spread proxies only —
# never empirical topology charges. Fail closed on evidence watermarks.
_EVIDENCE_CLASS = "physionet_spectral_proxy_unvalidated"
_RUN_MODE = "physionet_spectral_proxy"
_METRIC_KIND = "physionet_spectral_phase_proxy"


def physionet_evidence_watermarks() -> dict:
    """Fail-closed provenance stamps for physionet CSV/meta/RunRecord outputs."""
    return {
        "evidence_class": _EVIDENCE_CLASS,
        "run_mode": _RUN_MODE,
        "metrics_are_empirical": False,
        "scientific_pass": False,
        "metric_kind": _METRIC_KIND,
    }


def run(input_dir: str | Path, output_csv: str | Path) -> pd.DataFrame:
    """Compute Q_proxy / Qabs_proxy from PhysioNet GABA spectral CSVs.

    The spectral files contain power-spectrum values.  We treat the normalised
    std-of-values as a phase-spread proxy (Q_proxy) and the mean absolute value
    as an amplitude proxy (Qabs_proxy) — analogous to the topological Q / Qabs
    computed on EEG/physics fields. Column names keep the ``_proxy`` suffix so
    downstream aggregators cannot silently treat them as topology charges.
    """
    input_dir = Path(input_dir)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    meta = load_physionet_gaba_folder(input_dir)
    if meta.empty:
        df = pd.DataFrame(columns=["file", "Q_proxy", "Qabs_proxy", "metric_kind"])
        df.to_csv(output_csv, index=False)
        _write_evidence_artifacts(df, input_dir, output_csv)
        return df

    rows = []
    skipped_unreadable = 0
    skipped_short = 0
    for _, row in meta.iterrows():
        try:
            arr = pd.read_csv(row["file"], header=None).values.astype(float).flatten()
        except Exception:
            skipped_unreadable += 1
            continue
        if len(arr) < 4:
            skipped_short += 1
            continue
        norm = arr / (np.max(np.abs(arr)) + 1e-12)
        phase_proxy = np.arctan2(np.imag(np.fft.rfft(norm)[:4]),
                                  np.real(np.fft.rfft(norm)[:4]))
        grad = np.diff(phase_proxy)
        Q_proxy = float(np.sum(grad) / (2 * np.pi))
        Qabs_proxy = float(np.sum(np.abs(grad)) / (2 * np.pi))
        rows.append(
            {
                "file": row["file"],
                "Q_proxy": Q_proxy,
                "Qabs_proxy": Qabs_proxy,
                "metric_kind": _METRIC_KIND,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["file", "Q_proxy", "Qabs_proxy", "metric_kind"])
    df.to_csv(output_csv, index=False)
    _write_evidence_artifacts(
        df,
        input_dir,
        output_csv,
        skipped_unreadable=skipped_unreadable,
        skipped_short=skipped_short,
    )
    return df


def _write_evidence_artifacts(
    df: pd.DataFrame,
    input_dir: Path,
    output_csv: Path,
    *,
    skipped_unreadable: int = 0,
    skipped_short: int = 0,
) -> None:
    marks = physionet_evidence_watermarks()
    sidecar = {
        "records": int(len(df)),
        "input_dir": str(input_dir),
        "csv": str(output_csv),
        "skipped_unreadable": int(skipped_unreadable),
        "skipped_short": int(skipped_short),
        "note": (
            "Q_proxy/Qabs_proxy are spectral phase-spread proxies only; "
            "do not promote to topology Q/Qabs without an explicit gate."
        ),
        **marks,
    }
    Path(str(output_csv) + ".meta.json").write_text(
        json.dumps(sidecar, indent=2),
        encoding="utf-8",
    )

    metrics: dict = {
        "n_rows": int(len(df)),
        "metric_kind": marks["metric_kind"],
        "skipped_unreadable": int(skipped_unreadable),
        "skipped_short": int(skipped_short),
    }
    if len(df) and "Q_proxy" in df.columns:
        metrics["Q_proxy_mean"] = float(df["Q_proxy"].mean()) if len(df) else 0.0
    if len(df) and "Qabs_proxy" in df.columns:
        metrics["Qabs_proxy_mean"] = float(df["Qabs_proxy"].mean()) if len(df) else 0.0

    blob = json.dumps(
        {"input_dir": str(input_dir), "metrics": metrics},
        sort_keys=True,
        separators=(",", ":"),
    )
    run_id = hashlib.sha256(blob.encode()).hexdigest()[:16]
    record = RunRecordV1.make(
        run_id=run_id,
        run_kind="physionet",
        data_mode="physionet",
        metrics=metrics,
        artifacts={"csv": str(output_csv), "meta": str(output_csv) + ".meta.json"},
        source="pipelines.run_physionet",
        evidence_class=marks["evidence_class"],
        run_mode=marks["run_mode"],
        metrics_are_empirical=marks["metrics_are_empirical"],
        scientific_pass=marks["scientific_pass"],
        metric_kind=marks["metric_kind"],
    )
    record.input = {"input_dir": str(input_dir)}
    write_json(record, output_csv.parent / "RunRecord.json")
