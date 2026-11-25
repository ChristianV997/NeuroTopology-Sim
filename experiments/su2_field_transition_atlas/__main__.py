"""CLI: python -m experiments.su2_field_transition_atlas --config ... --output ..."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .mode_probe import ModeProbeConfig, run_mode_probe, write_result


def _load_config(path: Path) -> ModeProbeConfig:
    raw = json.loads(path.read_text())
    return ModeProbeConfig(
        oracle=raw.get("oracle", "periodic_checkerboard"),
        shape=tuple(raw.get("shape", [8, 4, 4])),
        spacing=tuple(raw.get("spacing", [1.0, 1.0, 1.0])),
        f_pi=float(raw.get("f_pi", 1.0)),
        e=float(raw.get("e", 1.0)),
        step_sizes=tuple(float(x) for x in raw.get("step_sizes", [0.02, 0.05, 0.1])),
        n_steps=int(raw.get("n_steps", 8)),
        curvature_probe_step=float(raw.get("curvature_probe_step", 5.0e-3)),
        gradient_stationarity_tol=float(raw.get("gradient_stationarity_tol", 1e-10)),
        seed=int(raw.get("seed", 0)),
        schema_version=str(raw.get("schema_version", "fta.mode_follow.0.1.0")),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bounded SU(2) mode-following probe with finite-difference "
            "directional curvature (not a transition-path certificate)."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / "configs" / "fta_checkerboard.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run_mode_probe(_load_config(args.config))
    write_result(result, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "classification": result.classification,
                "hessian_status": result.hessian_status,
                "initial_gradient_norm": result.initial_gradient_norm,
                "declared_directional_curvature0": result.declared_directional_curvature0,
                "control_directional_curvature0": result.control_directional_curvature0,
                "declared_predicted_larger_drop": result.declared_predicted_larger_drop,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
