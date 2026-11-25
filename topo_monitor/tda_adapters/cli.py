"""Command-line interface for inspecting TDA capabilities, running persistence, and validating inputs."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any
import numpy as np

from .registry import get_all_capabilities, get_backend
from .types import InputKind, StreamingWindowConfig, TDAConfig
from .validation import validate_distance_matrix, validate_point_cloud
from .streaming import stream_point_cloud_windows


def _generate_synthetic_fixture(name: str, n_points: int = 32) -> np.ndarray:
    """Generate deterministic synthetic test fixtures."""
    rng = np.random.default_rng(42)
    if name == "circle":
        theta = np.linspace(0, 2 * np.pi, n_points, endpoint=False)
        return np.column_stack([np.cos(theta), np.sin(theta)])
    elif name == "noisy_circle":
        theta = np.linspace(0, 2 * np.pi, n_points, endpoint=False)
        noise = rng.normal(0, 0.05, (n_points, 2))
        return np.column_stack([np.cos(theta), np.sin(theta)]) + noise
    elif name == "line":
        x = np.linspace(0, 1, n_points)
        return np.column_stack([x, np.zeros_like(x)])
    else:
        raise ValueError(f"Unknown fixture: {name}. Supported: 'circle', 'noisy_circle', 'line'")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="topo_monitor.tda_adapters",
        description="Persistent homology backend adapters and capability inspector.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # capabilities
    cap_parser = subparsers.add_parser("capabilities", help="Inspect TDA backend capability status.")
    cap_parser.add_argument("--json", action="store_true", help="Output results in JSON format.")

    # compute
    comp_parser = subparsers.add_parser("compute", help="Compute persistent homology on fixture or data file.")
    comp_parser.add_argument("--backend", type=str, default=None, help="Specific backend to use.")
    comp_parser.add_argument("--fixture", type=str, choices=["circle", "noisy_circle", "line"], default="circle")
    comp_parser.add_argument("--points", type=int, default=24, help="Number of points for fixture.")
    comp_parser.add_argument("--max-edge", type=float, default=None, help="Filtration threshold.")
    comp_parser.add_argument("--json", action="store_true", help="Output result as JSON.")

    # streaming
    stream_parser = subparsers.add_parser("streaming", help="Run windowed streaming on point cloud.")
    stream_parser.add_argument("--points", type=int, default=64, help="Total points in synthetic trajectory.")
    stream_parser.add_argument("--window", type=int, default=24, help="Window size.")
    stream_parser.add_argument("--step", type=int, default=8, help="Step size.")
    stream_parser.add_argument("--backend", type=str, default=None, help="TDA backend.")
    stream_parser.add_argument("--json", action="store_true", help="Output streaming summary as JSON.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "capabilities":
        caps = get_all_capabilities()
        if args.json:
            print(json.dumps({k: v.to_dict() for k, v in caps.items()}, indent=2))
        else:
            print("Persistent Homology Backend Capabilities:")
            for name, cap in caps.items():
                print(f"  [{cap.status.value.upper()}] {name}: {cap.description}")
                if cap.details:
                    print(f"      Details: {cap.details}")
        return 0

    elif args.command == "compute":
        backend = get_backend(args.backend)
        pts = _generate_synthetic_fixture(args.fixture, n_points=args.points)
        cfg = TDAConfig(max_edge_length=args.max_edge, max_dimension=1)
        res = backend.compute(pts, InputKind.POINT_CLOUD, cfg)

        if args.json:
            print(res.to_json())
        else:
            print(f"Backend: {res.backend}")
            print(f"Status: {res.scientific_status.value}")
            print(f"Checksum: {res.deterministic_checksum[:16]}...")
            print(f"Runtime: {res.runtime_seconds:.4f}s")
            print(f"H0 Intervals: {len(res.beta_0_intervals)}")
            print(f"H1 Intervals: {len(res.beta_1_intervals)}")
            if res.landscape_integrated_area is not None:
                print(f"Landscape Area: {res.landscape_integrated_area:.4f}")
        return 0

    elif args.command == "streaming":
        pts = _generate_synthetic_fixture("noisy_circle", n_points=args.points)
        stream_cfg = StreamingWindowConfig(
            window_size=args.window,
            step_size=args.step,
            backend=args.backend,
        )
        s_res = stream_point_cloud_windows(pts, stream_cfg)

        if args.json:
            print(s_res.to_json())
        else:
            print(f"Processed {len(s_res.window_results)} windows.")
            print(f"Mean H0: {s_res.mean_beta_0_count:.2f}, Mean H1: {s_res.mean_beta_1_count:.2f}")
            print(f"Max H1: {s_res.max_beta_1_count}")
            print(f"Peak Memory: {s_res.peak_memory_bytes} bytes")
            print(f"Total Runtime: {s_res.total_runtime_seconds:.4f}s")
            print(f"Stream Checksum: {s_res.deterministic_checksum[:16]}...")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
