"""Run the locked transition-forecasting ladder from a local JSON payload."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

# Make direct ``python scripts/run_transition_benchmark.py`` execution use the
# repository root without requiring installation or network access.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.transition_forecasting import BenchmarkDataset, run_benchmark


def _synthetic_demo(seed: int) -> BenchmarkDataset:
    rng = np.random.default_rng(seed)
    n = 48
    triadic = rng.normal(size=(n, 3))
    pairwise = rng.normal(size=(n, 4))
    psd = rng.normal(size=(n, 4))
    hyper = rng.normal(size=(n, 3))
    logits = 1.8 * triadic[:, 0] - 1.2 * triadic[:, 1] + 0.2 * rng.normal(size=n)
    target = (logits > 0).astype(int)
    features = {"psd": psd, "pairwise_fc": pairwise, "triadic_fc": triadic, "directed_hypergraph": hyper}
    timestamps = np.arange(n, dtype=float)
    return BenchmarkDataset(
        features=features,
        target=target,
        subjects=np.repeat(np.arange(6), 8),
        sessions=np.tile(np.arange(8), 6),
        timestamps=timestamps,
        prediction_horizon=1.0,
        target_definition="declared transition at t+Delta_t",
        provenance={"dataset_id": "synthetic-transition-demo", "source": "local deterministic fixture", "complete": False},
        controls={"arousal": rng.normal(size=n), "sampling_rate": np.full(n, 100.0), "window_length": np.full(n, 2.0)},
        feature_times={name: timestamps.copy() for name in features},
        synthetic=True,
    )


def _from_json(path: Path) -> BenchmarkDataset:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return BenchmarkDataset(
        features={key: np.asarray(value, dtype=float) for key, value in payload["features"].items()},
        target=np.asarray(payload["target"], dtype=int),
        subjects=np.asarray(payload["subjects"]),
        sessions=np.asarray(payload["sessions"]),
        timestamps=np.asarray(payload["timestamps"], dtype=float),
        prediction_horizon=float(payload["prediction_horizon"]),
        target_definition=str(payload["target_definition"]),
        provenance=dict(payload.get("provenance", {})),
        controls={key: np.asarray(value, dtype=float) for key, value in payload.get("controls", {}).items()},
        feature_times={key: np.asarray(value, dtype=float) for key, value in payload.get("feature_times", {}).items()},
        synthetic=bool(payload.get("synthetic", False)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-json", type=Path)
    source.add_argument("--synthetic-demo", action="store_true")
    parser.add_argument("--split", default="subject-held-out", choices=("subject-held-out", "session-held-out", "forward-time"))
    parser.add_argument("--cutoff", type=float)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    dataset = _synthetic_demo(args.seed) if args.synthetic_demo else _from_json(args.input_json)
    report = run_benchmark(dataset, split_strategy=args.split, cutoff=args.cutoff, seed=args.seed)
    text = report.to_json() + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if report.status not in {"INVALID_INPUT", "LEAKAGE_DETECTED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
