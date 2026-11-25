from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from core.topology import compute_Qz
from data.the_well_loader import sample_to_psi
from runs.run_record import RunRecordV1, write_json

# The-Well / physics-field NPY demos are engineering topology outputs — never empirical.
_EVIDENCE_CLASS = "synthetic_physics_field_demonstration"
_RUN_MODE = "synthetic"
_METRIC_KIND = "physics_field_topology"


def physics_evidence_watermarks() -> dict:
    """Fail-closed provenance stamps for physics pipeline CSV/meta/RunRecord outputs."""
    return {
        "evidence_class": _EVIDENCE_CLASS,
        "run_mode": _RUN_MODE,
        "metrics_are_empirical": False,
        "scientific_pass": False,
        "metric_kind": _METRIC_KIND,
    }


def run_from_npy(npy_path: str | Path, output_csv: str | Path):
    npy_path = Path(npy_path)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    sample = np.load(npy_path)
    psi = sample_to_psi(sample)
    psi = np.repeat(psi[:, :, None], 8, axis=2)

    Qz, Qabs = compute_Qz(psi)
    df = pd.DataFrame({"z": np.arange(len(Qz)), "Q": Qz, "Qabs": Qabs})
    df.to_csv(output_csv, index=False)

    marks = physics_evidence_watermarks()
    meta = {
        "records": int(len(df)),
        "npy": str(npy_path),
        "csv": str(output_csv),
        **marks,
    }
    Path(str(output_csv) + ".meta.json").write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )

    metrics = {
        "Q_mean": float(np.mean(Qz)) if len(Qz) else 0.0,
        "Qabs_mean": float(np.mean(Qabs)) if len(Qabs) else 0.0,
        "n_z": int(len(Qz)),
        "metric_kind": marks["metric_kind"],
    }
    blob = json.dumps(
        {"npy": str(npy_path), "metrics": metrics},
        sort_keys=True,
        separators=(",", ":"),
    )
    run_id = hashlib.sha256(blob.encode()).hexdigest()[:16]
    record = RunRecordV1.make(
        run_id=run_id,
        run_kind="physics",
        data_mode="synthetic",
        metrics=metrics,
        artifacts={"csv": str(output_csv), "meta": str(output_csv) + ".meta.json"},
        source="pipelines.run_physics",
        evidence_class=marks["evidence_class"],
        run_mode=marks["run_mode"],
        metrics_are_empirical=marks["metrics_are_empirical"],
        scientific_pass=marks["scientific_pass"],
        metric_kind=marks["metric_kind"],
    )
    record.input = {"npy": str(npy_path)}
    write_json(record, output_csv.parent / "RunRecord.json")

    return df
