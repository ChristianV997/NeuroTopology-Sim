from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.events import detect_events
from analysis.qzt import compute_qzt
from core.defects import detect_defects
from runs.run_record import RunRecordV1, write_json
from tracking.worldlines import WorldlineTracker

# Checkpoint Q(z,t) demos are sim-derived topology outputs — never empirical.
_EVIDENCE_CLASS = "synthetic_qzt_checkpoint_demonstration"
_RUN_MODE = "synthetic"
_METRIC_KIND = "qzt_checkpoint_topology"


def qzt_evidence_watermarks() -> dict:
    """Fail-closed provenance stamps for qzt CSV/meta/RunRecord outputs."""
    return {
        "evidence_class": _EVIDENCE_CLASS,
        "run_mode": _RUN_MODE,
        "metrics_are_empirical": False,
        "scientific_pass": False,
        "metric_kind": _METRIC_KIND,
    }


def run(checkpoint_dir: str | Path, output_dir: str | Path):
    """Run Q(z,t), event extraction, and defect worldline tracking."""
    checkpoint_dir = Path(checkpoint_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    checkpoints = []
    for p in sorted(checkpoint_dir.rglob("psi.npy")):
        psi = np.load(p)
        meta_p = p.parent / "meta.json"
        t = float(len(checkpoints))
        if meta_p.exists():
            try:
                meta = json.loads(meta_p.read_text())
                t = float(meta.get("t", meta.get("step", t)))
            except Exception:
                pass
        checkpoints.append((t, psi))

    qzt = compute_qzt(checkpoints)
    qzt.to_csv(output_dir / "qzt.csv", index=False)

    ev = detect_events(qzt)
    ev.to_csv(output_dir / "events.csv", index=False)

    tracker = WorldlineTracker()
    for t, psi in checkpoints:
        defects = detect_defects(psi)
        tracker.update(defects, t)

    worldlines = tracker.get()
    with open(output_dir / "worldlines.json", "w", encoding="utf-8") as f:
        json.dump(worldlines, f, indent=2)

    marks = qzt_evidence_watermarks()
    meta = {
        "checkpoint_dir": str(checkpoint_dir),
        "n_checkpoints": len(checkpoints),
        "n_qzt_rows": int(len(qzt)),
        "n_events": int(len(ev)),
        "artifacts": ["qzt.csv", "events.csv", "worldlines.json", "RunRecord.json"],
        **marks,
    }
    (output_dir / "evidence_meta.json").write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )

    metrics = {
        "n_checkpoints": len(checkpoints),
        "n_qzt_rows": int(len(qzt)),
        "n_events": int(len(ev)),
        "metric_kind": marks["metric_kind"],
    }
    if len(qzt) and "Q" in qzt.columns:
        metrics["Q_mean"] = float(qzt["Q"].mean())
    if len(qzt) and "Qabs" in qzt.columns:
        metrics["Qabs_mean"] = float(qzt["Qabs"].mean())

    blob = json.dumps(
        {"checkpoint_dir": str(checkpoint_dir), "metrics": metrics},
        sort_keys=True,
        separators=(",", ":"),
    )
    run_id = hashlib.sha256(blob.encode()).hexdigest()[:16]
    record = RunRecordV1.make(
        run_id=run_id,
        run_kind="qzt",
        data_mode="synthetic",
        metrics=metrics,
        artifacts={
            "qzt_csv": str(output_dir / "qzt.csv"),
            "events_csv": str(output_dir / "events.csv"),
            "worldlines_json": str(output_dir / "worldlines.json"),
            "evidence_meta": str(output_dir / "evidence_meta.json"),
        },
        source="pipelines.run_qzt",
        evidence_class=marks["evidence_class"],
        run_mode=marks["run_mode"],
        metrics_are_empirical=marks["metrics_are_empirical"],
        scientific_pass=marks["scientific_pass"],
        metric_kind=marks["metric_kind"],
    )
    record.input = {"checkpoint_dir": str(checkpoint_dir)}
    write_json(record, output_dir / "RunRecord.json")

    return qzt, ev
