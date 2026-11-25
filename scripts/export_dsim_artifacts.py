"""Export PITNN artifacts as offline dashboard payload bundles."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Any
import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path: sys.path.insert(0, str(_ROOT))
from sim.pitnn.api_bridge import (export_falsification_payload, export_liouvillian_ep_payload,
    export_rg_magnetization_payload, export_topology_trace_payload, json_safe, rg_binary_arrays)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(json_safe(payload), indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None: return {}
    if not path.is_file(): raise FileNotFoundError(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("run summary must be a JSON object")
    return value


def _topology_from_records(directory: Path) -> list[dict[str, Any]]:
    records_file = directory / "campaign_records.jsonl"
    if not records_file.is_file(): return []
    result = []
    for index, line in enumerate(records_file.open(encoding="utf-8")):
        if not line.strip(): continue
        record = json.loads(line)
        spin = record.get("spin", {})
        result.append({"time_s": float(index), "winding_number": spin.get("winding_number", 0.0),
                       "topological_charge": spin.get("topological_charge", 0.0), "beta1_loops": spin.get("beta1_loops", 0)})
    return result


def _load_field(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with np.load(path, allow_pickle=False) as bundle:
        if "magnetization" in bundle: field = np.asarray(bundle["magnetization"], dtype=float)
        elif "spins_history" in bundle: field = np.asarray(bundle["spins_history"], dtype=float)
        elif "spin_final" in bundle: field = np.asarray(bundle["spin_final"], dtype=float)
        else: raise ValueError("NPZ must contain magnetization, spins_history, or spin_final")
        if field.ndim != 3 or field.shape[-1] != 3: raise ValueError("field array must have shape (frames, sites, 3)")
        times = np.asarray(bundle["timestamps_s" if "timestamps_s" in bundle else "time_stamps"], dtype=float) if ("timestamps_s" in bundle or "time_stamps" in bundle) else np.arange(field.shape[0], dtype=float)
    return field, times


def export_artifacts(run_summary_json: str | Path | None = None, magnetization_npz: str | Path | None = None,
                     output_dir: str | Path = "artifacts/pitnn/dsim_export", downsample_factor: int = 1) -> dict[str, Any]:
    """Build a manifest and independent dashboard payloads without network access."""
    if downsample_factor < 1: raise ValueError("downsample_factor must be positive")
    summary_path = Path(run_summary_json) if run_summary_json else None
    summary = _load_json(summary_path)
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"schema": "PITNN.DSIM.Manifest.v1", "offline": True, "payloads": {}}
    source_dir = summary_path.parent if summary_path else Path.cwd()
    trace = _topology_from_records(source_dir)
    if not trace and "conditions" in summary:
        trace = [{"time_s": float(index), "winding_number": item.get("topology", {}).get("mean_winding", 0.0),
                  "topological_charge": item.get("topology", {}).get("mean_q", 0.0), "beta1_loops": item.get("topology", {}).get("mean_beta_1", 0)}
                 for index, item in enumerate(summary.get("conditions", {}).values())]
    if trace:
        _write_json(output / "topology_series.json", export_topology_trace_payload(trace))
        manifest["payloads"]["topology_series"] = "topology_series.json"
    field_path = Path(magnetization_npz) if magnetization_npz else None
    if field_path is not None:
        field, times = _load_field(field_path)
        payload = export_rg_magnetization_payload(field, times, downsample_factor)
        arrays = rg_binary_arrays(field, times, downsample_factor)
        np.savez_compressed(output / "rg_magnetization_frames.npz", **arrays)
        _write_json(output / "rg_magnetization_frames.json", payload)
        manifest["payloads"]["rg_magnetization"] = {"metadata": "rg_magnetization_frames.json", "binary": "rg_magnetization_frames.npz"}
    ep = summary.get("ep_boundary", summary.get("ep", {}))
    if ep:
        _write_json(output / "liouvillian_ep_map.json", export_liouvillian_ep_payload(ep))
        manifest["payloads"]["liouvillian_ep_map"] = "liouvillian_ep_map.json"
    falsification = summary if ("comparison" in summary or "bayes_factor" in summary) else None
    if falsification is None:
        candidate = source_dir.parent / "empirical_smoke" / "empirical_falsification_report.json"
        if candidate.is_file(): falsification = _load_json(candidate)
    if falsification is not None:
        _write_json(output / "falsification_summary.json", export_falsification_payload(falsification))
        manifest["payloads"]["falsification_summary"] = "falsification_summary.json"
    _write_json(output / "dsim_manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-summary-json", type=Path)
    parser.add_argument("--magnetization-npz", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/pitnn/dsim_export"))
    parser.add_argument("--downsample-factor", type=int, default=1)
    args = parser.parse_args()
    manifest = export_artifacts(args.run_summary_json, args.magnetization_npz, args.output_dir, args.downsample_factor)
    print(json.dumps(manifest, sort_keys=True))
    return 0

if __name__ == "__main__": raise SystemExit(main())
