"""Offline streaming EEG topology analysis; graph persistence and spatial charge stay distinct."""
from __future__ import annotations

import argparse, csv, json, os, sys, tempfile
from pathlib import Path
from typing import Any, Iterator

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import hilbert

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from shared.data_loaders.eeg_bids_loader import read_local_raw
from topo_monitor.anomaly_detection import consensus_residual, rolling_alerts
from topo_monitor.graph_persistence import analyze_adjacency
from topo_monitor.spatial_phase import sensor_spatial_charge, spatial_winding_charge


def _safe(value: Any) -> Any:
    if isinstance(value, float) and not np.isfinite(value): return None
    if isinstance(value, dict): return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_safe(v) for v in value]
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    fd, temp = tempfile.mkstemp(prefix=path.stem + "_", suffix=".tmp", dir=path.parent); os.close(fd)
    try: Path(temp).write_text(json.dumps(_safe(payload), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"); os.replace(temp, path)
    finally:
        if Path(temp).exists(): Path(temp).unlink()


def synthetic_chunks(channels: int, samples: int, chunk_samples: int, sample_rate_hz: float, seed: int) -> Iterator[np.ndarray]:
    """Yield deterministic `(channels, samples)` synthetic EEG chunks; units are arbitrary voltage."""
    if channels < 4 or int(np.sqrt(channels)) ** 2 != channels: raise ValueError("synthetic channels must be a square >= 4")
    rng = np.random.default_rng(seed); side = int(np.sqrt(channels)); yy, xx = np.mgrid[:side, :side]; vortex = np.arctan2(yy-(side-1)/2, xx-(side-1)/2).ravel()
    for start in range(0, samples, chunk_samples):
        time = np.arange(start, min(start + chunk_samples, samples)) / sample_rate_hz; regime = 1.0 if start < samples // 2 else .25
        phase = 2 * np.pi * 40.0 * time[None, :] + regime * vortex[:, None]
        yield regime * np.sin(phase) + .08 * rng.standard_normal(phase.shape)


def _input_chunks(args: argparse.Namespace) -> tuple[Iterator[np.ndarray], float, str, np.ndarray|None]:
    if args.input_file is None: return synthetic_chunks(args.channels, args.synthetic_samples, args.chunk_samples, args.sample_rate_hz, args.seed), args.sample_rate_hz, "synthetic_eeg_demo", None
    path = Path(args.input_file)
    if path.suffix.lower() == ".npy":
        values = np.load(path, mmap_mode="r"); data = values if values.ndim == 2 else (_ for _ in ()).throw(ValueError(".npy EEG must be (channels, samples)"))
        def chunks() -> Iterator[np.ndarray]:
            for start in range(0, data.shape[1], args.chunk_samples): yield np.asarray(data[:, start:start+args.chunk_samples], float)
        return chunks(), args.sample_rate_hz, "local_npy_eeg", None
    stream = read_local_raw(path, preload=False); return stream.iter_chunks(args.chunk_samples), stream.metadata.sfreq_hz, "empirical_eeg", stream.metadata.montage_coordinates


def run(args: argparse.Namespace) -> dict[str, Any]:
    """Compute PLV persistence, spatial phase charge, and conservative drift alerts per stream window."""
    chunks, sfreq, source, montage_coordinates = _input_chunks(args); out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True); metrics: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        if index >= args.max_windows: break
        if chunk.shape[1] < 8: continue
        phase = np.angle(hilbert(chunk, axis=1)); plv = np.abs(np.mean(np.exp(1j * (phase[:, None, :] - phase[None, :, :])), axis=2)); np.fill_diagonal(plv, 0.0)
        result = analyze_adjacency(plv, threshold=args.plv_threshold, n_layers=args.landscape_layers); channels = chunk.shape[0]; side = int(np.sqrt(channels)); q = None
        if montage_coordinates is not None:
            try: q = sensor_spatial_charge(phase[:, -1], montage_coordinates)
            except ValueError: q = None
        elif side * side == channels:
            grid_phase = phase[:, -1].reshape(side, side); coords = np.stack(np.mgrid[:side, :side], axis=-1).astype(float); q = spatial_winding_charge(grid_phase, coords)
        metrics.append({"window": index, "start_s": index * args.chunk_samples / sfreq, "channels": channels, "beta1": int(np.max(result.beta_curve)), "filtration_beta1_max": int(np.max(result.sweep_beta1)), "persistence_landscape_l1": float(np.sum(result.landscape)), "integrated_landscape_area": result.integrated_landscape_area, "q_spatial": q, "consensus_residual": consensus_residual(plv, np.mean(chunk, axis=1))})
    beta = [float(m["beta1"]) for m in metrics]; alerts = [a.__dict__ for a in rolling_alerts(beta, window=min(args.alert_window, max(2, len(beta)//2)), z_threshold=args.alert_z) ] if len(beta) >= 4 else []
    for record in metrics: record["alert_count"] = sum(a["index"] == record["window"] for a in alerts)
    payload = {"schema": "NeuroTopologySim.EEGTopologyMonitoring.v2", "source": source, "sample_rate_hz": sfreq, "metrics": metrics, "alerts": alerts, "scientific_note": "beta1 is graph persistent homology over a filtration sweep; Q_spatial is calculated only from sensor geometry and is not a graph-cycle count."}
    _write_json(out / "eeg_topology_results.json", payload)
    with (out / "eeg_topology_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metrics[0]) if metrics else ["window"]); writer.writeheader(); writer.writerows(_safe(metrics))
    fig, axes = plt.subplots(2, 1, figsize=(8, 5), sharex=True); x = [m["start_s"] for m in metrics]
    axes[0].plot(x, beta, "o-", label="graph beta1"); axes[0].set_ylabel("beta1"); axes[0].grid(alpha=.3); axes[0].legend()
    axes[1].plot(x, [m["q_spatial"] if m["q_spatial"] is not None else np.nan for m in metrics], "o-", label="spatial Q"); axes[1].set(xlabel="Time (s)", ylabel="Q spatial"); axes[1].grid(alpha=.3); axes[1].legend(); fig.tight_layout(); fig.savefig(out / "eeg_topology_results.png", dpi=200); plt.close(fig)
    return payload


def run_comparative(args: argparse.Namespace) -> dict[str, Any]:
    """Run bounded awake/sedated streams and compare persistent-topology summaries."""
    if args.awake_file is None or args.sedated_file is None: raise ValueError("both --awake-file and --sedated-file are required")
    out=Path(args.output_dir); awake_args=argparse.Namespace(**vars(args)); sedated_args=argparse.Namespace(**vars(args)); awake_args.input_file=Path(args.awake_file); sedated_args.input_file=Path(args.sedated_file); awake_args.output_dir=out/"awake"; sedated_args.output_dir=out/"sedated"
    awake=run(awake_args); sedated=run(sedated_args)
    def summary(payload:dict[str,Any])->dict[str,float|int|None]:
        metrics=payload["metrics"]; q=[m["q_spatial"] for m in metrics if m["q_spatial"] is not None]
        return {"windows":len(metrics),"mean_beta1":float(np.mean([m["filtration_beta1_max"] for m in metrics])) if metrics else 0.,"mean_landscape_area":float(np.mean([m["integrated_landscape_area"] for m in metrics])) if metrics else 0.,"mean_q_spatial":float(np.mean(q)) if q else None}
    a,s=summary(awake),summary(sedated); comparison={"schema":"NeuroTopologySim.AwakeSedatedTopology.v1","awake":{"source":awake["source"],**a},"sedated":{"source":sedated["source"],**s},"persistence_distance_proxy":abs(a["mean_landscape_area"]-s["mean_landscape_area"]),"scientific_note":"The persistence-distance proxy is an integrated persistence-landscape shift, not a clinical inference."}
    _write_json(out/"awake_vs_sedated.json",comparison)
    rows=[{"condition":"awake",**a},{"condition":"sedated",**s}]
    with (out/"awake_vs_sedated.csv").open("w",newline="",encoding="utf-8") as handle: writer=csv.DictWriter(handle,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(_safe(rows))
    fig,axis=plt.subplots(figsize=(6,4)); axis.bar(["awake","sedated"],[a["mean_landscape_area"],s["mean_landscape_area"]]); axis.set(ylabel="Integrated persistence landscape area",title="Awake vs sedated topology"); fig.tight_layout(); fig.savefig(out/"awake_vs_sedated.png",dpi=200); plt.close(fig)
    return comparison


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-file", type=Path); p.add_argument("--awake-file",type=Path); p.add_argument("--sedated-file",type=Path); p.add_argument("--output-dir", type=Path, default=Path("artifacts/topology_monitoring/eeg_run")); p.add_argument("--sample-rate-hz", type=float, default=1000.0); p.add_argument("--chunk-samples", type=int, default=500); p.add_argument("--max-windows", type=int, default=20, help="bounded streaming work budget"); p.add_argument("--channels", type=int, default=16); p.add_argument("--synthetic-samples", type=int, default=4000); p.add_argument("--seed", type=int, default=20260725); p.add_argument("--plv-threshold", type=float, default=.5); p.add_argument("--landscape-layers", type=int, default=3); p.add_argument("--alert-window", type=int, default=3); p.add_argument("--alert-z", type=float, default=2.5); return p


if __name__ == "__main__":
    args=parser().parse_args(); result=run_comparative(args) if args.awake_file else run(args); print(json.dumps({"result_schema":result["schema"]}))
