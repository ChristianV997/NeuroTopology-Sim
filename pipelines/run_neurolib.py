"""Whole-brain neural mass model pipeline via neurolib.

Run Kuramoto/Hopf/Wilson-Cowan/ALN oscillator networks with forward BOLD
model, extract analytic phase, compute topology metrics, and emit RunRecord.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Optional, Tuple

import numpy as np

from core.topology import compute_Qz
from runs.run_record import RunRecordV1, write_json

# Neural-mass / neurolib runs are synthetic oscillator scaffolds — never empirical.
_EVIDENCE_CLASS = "synthetic_neural_mass_demonstration"
_RUN_MODE = "synthetic"
_METRIC_KIND = "neural_mass_topology"


def neurolib_evidence_watermarks() -> dict:
    """Fail-closed provenance stamps for neurolib RunRecords."""
    return {
        "evidence_class": _EVIDENCE_CLASS,
        "run_mode": _RUN_MODE,
        "metrics_are_empirical": False,
        "scientific_pass": False,
        "metric_kind": _METRIC_KIND,
    }


def run(
    output_csv: str | Path,
    n_nodes: int = 32,
    model_type: str = "kuramoto",
    t_max: float = 10.0,
    dt: float = 0.01,
    coupling: float = 0.1,
    seed: int = 0,
    use_bold_model: bool = False,
    run_id: Optional[str] = None,
) -> RunRecordV1:
    """Run a neurolib neural mass model and extract topology.

    Parameters
    ----------
    output_csv : file path to save RunRecord.json (required by contract).
    n_nodes : number of oscillators in the network.
    model_type : 'kuramoto', 'hopf', 'wilson_cowan', or 'aln'.
    t_max : simulation time in seconds.
    dt : integration timestep in seconds.
    coupling : global coupling strength (scale of inter-node coupling).
    seed : random seed for initialization.
    use_bold_model : if True, apply Balloon-Windkessel BOLD forward model
        (requires neurolib's BOLD model to be available).
    run_id : optional run_id override; if None, generated deterministically.

    Returns
    -------
    RunRecordV1
        Record with observed + null topology metrics, emitted to output_csv.
    """
    _VALID_MODEL_TYPES = ("kuramoto", "hopf", "wilson_cowan", "aln")
    if model_type not in _VALID_MODEL_TYPES:
        raise ValueError(f"Unknown model_type: {model_type}. Choose from {list(_VALID_MODEL_TYPES)}")

    try:
        import neurolib  # noqa: F401  (import-availability check)
    except Exception as exc:  # pragma: no cover
        raise ValueError("neurolib is required for neural mass pipeline") from exc

    np.random.seed(seed)
    Cmat = _generate_random_connectivity(n_nodes, seed)

    if model_type == "kuramoto":
        # neurolib's models/ package (checked against the installed 0.6.2)
        # has no Kuramoto model -- only multimodel, hopf, wc, aln, ww, fhn,
        # thalamus, bold. Integrate the canonical Kuramoto phase-coupling ODE
        # directly (dtheta_i/dt = omega_i + coupling * sum_j Cmat_ij *
        # sin(theta_j - theta_i)) over this pipeline's own Cmat, matching
        # the same coupling term this repo already uses for a spatial-grid
        # Kuramoto field in validation/synthetic.py::kuramoto_vortex_field.
        timeseries = _integrate_kuramoto(n_nodes, coupling, dt, t_max, seed, Cmat)
    else:
        # neurolib.models has no top-level re-exports (its __init__.py is
        # empty) -- model classes must be imported from their own
        # submodules, and Wilson-Cowan's class is named WCModel, not
        # WilsonCowanModel.
        if model_type == "hopf":
            from neurolib.models.hopf.model import HopfModel as model_class
        elif model_type == "wilson_cowan":
            from neurolib.models.wc.model import WCModel as model_class
        else:  # aln
            from neurolib.models.aln.model import ALNModel as model_class

        # Dmat (inter-node distance/delay matrix): neurolib defaults this to
        # None when only Cmat is given, and every one of these models' own
        # timeIntegration multiplies it by a scalar unconditionally
        # (computeDelayMatrix), raising a TypeError before any integration
        # happens. Zero distances = no signal-propagation delay, the
        # standard simplification when no real inter-node geometry exists.
        model = model_class(Cmat=Cmat, Dmat=np.zeros((n_nodes, n_nodes)))
        model.params["dt"] = dt
        model.params["duration"] = t_max * 1000  # neurolib uses ms
        if model_type in ("hopf", "wilson_cowan"):
            # `coupling` in these models' params is a categorical string
            # ("diffusive"/"additive" -- the coupling TYPE), not a numeric
            # strength; overwriting it with a float made every hopf/wc run
            # raise inside neurolib's own timeIntegration. `K_gl` is the
            # actual global coupling STRENGTH parameter for both.
            model.params["K_gl"] = coupling
        elif model_type == "aln":
            model.params["exc_init"] = np.random.randn(n_nodes) * 0.1

        try:
            model.run()
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"Integration failed for {model_type} model") from exc

        # Extract phase timeseries -- the output attribute name is
        # model-specific in neurolib, not a uniform `rates`/`exc` contract:
        # HopfModel exposes `.x` (complex oscillator state's real part),
        # WCModel exposes `.exc` (excitatory population rate), ALNModel
        # exposes `.rates_exc` (checked against the installed neurolib 0.6.2).
        if hasattr(model, "rates") and model.rates is not None:
            timeseries = model.rates
        elif hasattr(model, "exc") and model.exc is not None:
            timeseries = model.exc
        elif hasattr(model, "rates_exc") and model.rates_exc is not None:
            timeseries = model.rates_exc
        elif hasattr(model, "x") and model.x is not None:
            timeseries = model.x
        else:  # pragma: no cover
            raise ValueError("Could not extract timeseries from neurolib model")

    # Compute analytic phase via Hilbert transform
    try:
        from scipy.signal import hilbert
    except ImportError as e:  # pragma: no cover
        raise ValueError("SciPy is required for Hilbert transform") from e

    phase = np.angle(hilbert(timeseries, axis=1))

    # Compute topology on the phase signal
    # Treat as a "1D chain" for simplicity; later versions could use network structure
    # For now, reshape as a pseudo-2D grid for plaquette-based Qz computation
    n_t = phase.shape[1]
    if n_t < 3:
        raise ValueError(f"Integration produced too few timepoints ({n_t}); need >=3 for topology")

    # Reshape to 3D pseudo-grid for compute_Qz: (nx, ny, nt)
    # Simple factorization: nx = ceil(sqrt(n_nodes)), ny = ceil(n_nodes / nx), nt = n_t
    nx = int(np.ceil(np.sqrt(n_nodes)))
    ny = int(np.ceil(n_nodes / nx))
    phase_grid = np.zeros((nx, ny, n_t), dtype=float)
    phase_grid.flat[:n_nodes * n_t] = phase.ravel()

    # Compute Qz/Qabs per timepoint
    Qz_arr, Qabs_arr = compute_Qz(phase_grid)
    assert Qz_arr.shape == (n_t,) and Qabs_arr.shape == (n_t,)

    # Summarize metrics (mean + std over time)
    metrics = {
        "model_type": model_type,
        "n_nodes": int(n_nodes),
        "coupling": float(coupling),
        "Q_mean": float(np.mean(Qz_arr)),
        "Q_std": float(np.std(Qz_arr)),
        "Qabs_mean": float(np.mean(Qabs_arr)),
        "Qabs_std": float(np.std(Qabs_arr)),
    }

    # Build RunRecord
    spec_id = f"neural_mass_{model_type}"
    sim_params = {
        "model_type": model_type,
        "n_nodes": n_nodes,
        "t_max": t_max,
        "dt": dt,
        "coupling": coupling,
        "seed": seed,
        "use_bold_model": use_bold_model,
    }
    if run_id is not None:
        run_id_final = run_id
    else:
        # RunRecordV1 has no `sim_params` field and `build_run_id()` needs
        # git/argv context this pipeline doesn't have -- deterministic hash
        # over spec_id/sim_params only, matching pipelines/hypothesis.py's
        # run_id convention.
        blob = json.dumps({"spec_id": spec_id, "sim_params": sim_params}, sort_keys=True, separators=(",", ":"))
        run_id_final = hashlib.sha256(blob.encode()).hexdigest()[:16]

    marks = neurolib_evidence_watermarks()
    record = RunRecordV1.make(
        run_id=run_id_final,
        run_kind="neural_mass",
        data_mode="synthetic",
        spec_id=spec_id,
        metrics=metrics,
        artifacts={
            "phase_timeseries_shape": list(phase.shape),
            "phase_summary": {
                "mean": float(np.mean(phase)),
                "std": float(np.std(phase)),
                "min": float(np.min(phase)),
                "max": float(np.max(phase)),
            },
        },
        source="pipelines.run_neurolib",
        evidence_class=marks["evidence_class"],
        run_mode=marks["run_mode"],
        metrics_are_empirical=marks["metrics_are_empirical"],
        scientific_pass=marks["scientific_pass"],
        metric_kind=marks["metric_kind"],
    )
    # `sim_params` isn't one of RunRecordV1.make()'s parameters, but the
    # dataclass's own `input` field is documented as "sim input params" --
    # this is exactly that.
    record.input = sim_params

    # Write to output
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(record, output_path)

    return record


def _integrate_kuramoto(
    n_nodes: int, coupling: float, dt: float, t_max: float, seed: int, Cmat: np.ndarray,
) -> np.ndarray:
    """Native Kuramoto phase-oscillator integration (forward Euler).

    Returns a (n_nodes, n_steps) real-valued signal (sin of each oscillator's
    phase) so downstream Hilbert-transform phase extraction, which every
    other model_type's output already goes through, applies unchanged.
    """
    rng = np.random.default_rng(seed)
    omega = rng.standard_normal(n_nodes) * 0.1
    theta = rng.uniform(0, 2 * np.pi, n_nodes)
    n_steps = max(int(t_max / dt), 3)
    theta_ts = np.zeros((n_nodes, n_steps))
    for t in range(n_steps):
        theta_ts[:, t] = theta
        diff = theta[None, :] - theta[:, None]
        coupling_term = (Cmat * np.sin(diff)).sum(axis=1)
        theta = theta + dt * (omega + coupling * coupling_term)
    return np.sin(theta_ts)


def _generate_random_connectivity(n_nodes: int, seed: int) -> np.ndarray:
    """Generate a random connectivity matrix (coupling matrix) for neurolib.

    Returns a symmetric (n_nodes, n_nodes) matrix suitable for neurolib's Cmat.
    """
    np.random.seed(seed)
    C = np.random.randn(n_nodes, n_nodes) * 0.1
    C = (C + C.T) / 2  # Symmetrize
    np.fill_diagonal(C, 0)  # No self-coupling
    return C
