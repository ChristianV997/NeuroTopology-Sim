"""Validate offline empirical high-density recordings for PITNN streaming input.

Accepted arrays use shape (samples, channels), with samples on axis 0.  The
high-density campaign requires exactly 256 channels.  Values must be finite,
and the supplied sample rate must support the requested analysis band.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_array(path: Path) -> np.ndarray:
    """Load a local NPY/NPZ matrix without network access.

    Parameters
    ----------
    path:
        Local NPY or NPZ file containing a numerical recording in arbitrary
        amplitude units.  NPY is memory-mapped to avoid copying large arrays.
    """
    suffix = path.suffix.lower()
    if suffix == ".npy":
        return np.load(path, mmap_mode="r")
    if suffix == ".npz":
        with np.load(path) as bundle:
            keys = list(bundle.files)
            if not keys:
                raise ValueError("NPZ input contains no arrays")
            preferred = next((key for key in ("data", "signals", "recording") if key in bundle), keys[0])
            return np.asarray(bundle[preferred])
    if suffix in {".fif", ".edf", ".vhdr"}:
        raise ValueError(
            f"{suffix} validation requires conversion to a local (samples, 256) NPY/NPZ matrix; "
            "this high-density runner deliberately has no mandatory MNE dependency."
        )
    raise ValueError("supported input formats are .npy and .npz")


def validate_dataset(path: str | Path, sample_rate_hz: float, *, expected_channels: int = 256,
                     max_band_hz: float = 80.0, chunk_samples: int = 65536) -> dict[str, Any]:
    """Validate shape, finite values and Nyquist margin in a bounded-memory stream.

    Sampling frequency is in Hz.  The Nyquist frequency must exceed the upper
    requested band edge (default gamma-band 80 Hz).  The finite-value scan is
    performed chunkwise and returns JSON-serializable metadata.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"empirical recording does not exist: {source}")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be a positive finite value")
    if max_band_hz <= 0:
        raise ValueError("max_band_hz must be positive")
    if sample_rate_hz / 2.0 < max_band_hz:
        raise ValueError(f"Nyquist frequency {sample_rate_hz / 2.0:g} Hz is below requested {max_band_hz:g} Hz")
    recording = _load_array(source)
    if recording.ndim != 2:
        raise ValueError(f"expected a 2D (samples, channels) matrix; received shape {recording.shape}")
    n_samples, n_channels = map(int, recording.shape)
    if n_samples < 4:
        raise ValueError("recording must contain at least four samples")
    if n_channels != expected_channels:
        raise ValueError(f"high-density campaign requires {expected_channels} channels; received {n_channels}")
    finite = True
    observed_min, observed_max = float("inf"), float("-inf")
    for start in range(0, n_samples, chunk_samples):
        part = np.asarray(recording[start : start + chunk_samples], dtype=np.float64)
        if not np.all(np.isfinite(part)):
            finite = False
            break
        observed_min = min(observed_min, float(part.min()))
        observed_max = max(observed_max, float(part.max()))
    if not finite:
        raise ValueError("recording contains NaN or Inf values")
    return {
        "schema": "PITNN.EmpiricalDatasetValidation.v1",
        "input_file": str(source.resolve()),
        "shape": [n_samples, n_channels],
        "sample_rate_hz": float(sample_rate_hz),
        "nyquist_hz": float(sample_rate_hz / 2.0),
        "max_band_hz": float(max_band_hz),
        "finite": True,
        "value_min": observed_min,
        "value_max": observed_max,
        "status": "VALID",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", required=True, type=Path)
    parser.add_argument("--sample-rate-hz", required=True, type=float)
    parser.add_argument("--max-band-hz", type=float, default=80.0)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    try:
        result = validate_dataset(args.input_file, args.sample_rate_hz, max_band_hz=args.max_band_hz)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(json.dumps({"status": "INVALID", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
