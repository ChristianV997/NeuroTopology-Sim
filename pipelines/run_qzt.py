from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

from analysis.qzt import compute_qzt
from analysis.events import detect_events
from tracking.worldlines import WorldlineTracker
from core.defects import detect_defects

def run(checkpoint_dir: str | Path, output_dir: str | Path):
    """Run Q(z,t), event extraction, and defect worldline tracking."""
    checkpoint_dir = Path(checkpoint_dir)
    if not checkpoint_dir.is_dir():
        raise FileNotFoundError(f"checkpoint directory does not exist: {checkpoint_dir}")
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

    with open(output_dir / "worldlines.json", "w", encoding="utf-8") as f:
        json.dump(tracker.get(), f, indent=2)

    return qzt, ev
