"""Zero-dependency-on-disk state serialization for PITNN runs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np


class PITNNStateExporter:
    """Write compressed trajectories and JSON metadata under one artifact root."""

    def __init__(self, output_dir: str | Path = "artifacts/pitnn"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_npz(self, filename: str, spins_history: np.ndarray,
                   time_stamps: np.ndarray, metadata: dict[str, Any] | None = None) -> str:
        spins = np.asarray(spins_history, dtype=float)
        times = np.asarray(time_stamps, dtype=float)
        if spins.ndim != 3 or spins.shape[-1] != 3:
            raise ValueError("spins_history must have shape (time, spins, 3)")
        if times.ndim != 1 or times.shape[0] != spins.shape[0]:
            raise ValueError("time_stamps must have one value per trajectory frame")
        if not np.all(np.isfinite(spins)) or not np.all(np.isfinite(times)):
            raise ValueError("trajectory and timestamps must be finite")
        if metadata is not None:
            json.dumps(metadata)
        path = self.output_dir / (filename if filename.endswith(".npz") else f"{filename}.npz")
        payload: dict[str, Any] = {"spins_history": spins, "time_stamps": times}
        if metadata is not None:
            payload["metadata_json"] = np.array(json.dumps(metadata, sort_keys=True))
        np.savez_compressed(path, **payload)
        return str(path)

    def export_json(self, filename: str, data: dict[str, Any]) -> str:
        json.dumps(data)
        path = self.output_dir / (filename if filename.endswith(".json") else f"{filename}.json")
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return str(path)

    def export_array_bundle(self, filename: str, arrays: Mapping[str, np.ndarray],
                            metadata: dict[str, Any] | None = None) -> str:
        """Export named real/complex arrays plus JSON metadata to compressed NPZ."""
        if not arrays:
            raise ValueError("arrays must not be empty")
        payload = {name: np.asarray(value) for name, value in arrays.items()}
        if any(np.asarray(value).dtype == object for value in payload.values()):
            raise ValueError("object arrays are not supported")
        if metadata is not None:
            json.dumps(metadata)
            payload["metadata_json"] = np.array(json.dumps(metadata, sort_keys=True))
        path = self.output_dir / (filename if filename.endswith(".npz") else f"{filename}.npz")
        np.savez_compressed(path, **payload)
        return str(path)

    @staticmethod
    def load_npz(filepath: str | Path) -> dict[str, Any]:
        with np.load(filepath, allow_pickle=False) as data:
            result: dict[str, Any] = {
                "spins_history": data["spins_history"],
                "time_stamps": data["time_stamps"],
            }
            if "metadata_json" in data:
                result["metadata"] = json.loads(str(data["metadata_json"]))
        if result["spins_history"].ndim != 3 or result["spins_history"].shape[-1] != 3:
            raise ValueError("serialized spins_history has invalid shape")
        if result["time_stamps"].shape[0] != result["spins_history"].shape[0]:
            raise ValueError("serialized trajectory and timestamps have different lengths")
        return result

    @staticmethod
    def load_array_bundle(filepath: str | Path) -> dict[str, Any]:
        """Load a generic named real/complex NPZ bundle and optional metadata."""
        with np.load(filepath, allow_pickle=False) as data:
            result = {name: data[name] for name in data.files if name != "metadata_json"}
            if "metadata_json" in data:
                result["metadata"] = json.loads(str(data["metadata_json"]))
        return result
