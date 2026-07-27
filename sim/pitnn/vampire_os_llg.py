"""Small deterministic open-system LLG lattice model.

The implementation is intentionally a transparent surrogate for external
Vampire/Spirit/MuMax3 solvers.  It normalizes every spin after each Heun step
and exposes the assumptions used to estimate an effective decoherence time.
"""
from dataclasses import dataclass
import numpy as np

from .pitnn_constants import PITNNConstants
from .topological_invariants import TopologicalInvariantTracker


class OpenSystemLLGSimulator:
    """Low-level deterministic-step API for long-horizon stability audits.

    This compatibility facade uses SI-like LLG scaling for the explicit
    ``step`` benchmark while preserving unit-spin projection after each step.
    It is a local surrogate and does not claim to reproduce an external
    Vampire solver.
    """

    def __init__(self, num_spins: int = 32, alpha: float = 0.05,
                 dt: float = 1e-15, temperature: float = 310.0,
                 exchange: float = 0.8, dmi: float = 0.15,
                 thermal_scale: float = 1e-3, ciss_scale: float = 1e-3):
        if num_spins < 3 or alpha < 0.0 or dt <= 0.0 or temperature <= 0.0:
            raise ValueError("invalid OpenSystemLLGSimulator parameters")
        self.num_spins = int(num_spins)
        self.alpha = float(alpha)
        self.dt = float(dt)
        self.temperature = float(temperature)
        self.exchange = float(exchange)
        self.dmi = float(dmi)
        self.thermal_scale = float(thermal_scale)
        self.ciss_scale = float(ciss_scale)
        self.S = np.zeros((self.num_spins, 3), dtype=float)
        self.S[:, 2] = 1.0

    def compute_effective_field(self, H_ext: np.ndarray) -> np.ndarray:
        """Return external plus nearest-neighbour exchange/DMI field."""
        external = np.asarray(H_ext, dtype=float)
        if external.shape != self.S.shape:
            raise ValueError(f"H_ext must have shape {self.S.shape}")
        cfg = LLGConfig(n_spins=self.num_spins, exchange=self.exchange, dmi=self.dmi)
        return external + _effective_field(self.S, cfg)

    def get_thermal_noise(self) -> np.ndarray:
        """Draw bounded thermal noise using NumPy's explicitly seeded RNG."""
        scale = self.thermal_scale * np.sqrt(self.temperature / 310.0)
        return np.random.normal(0.0, scale, size=self.S.shape)

    def get_ciss_torque(self) -> np.ndarray:
        """Return a chiral-axis torque in the same units as the field term."""
        axis = np.array([0.0, 0.0, 1.0])
        return self.ciss_scale * np.cross(self.S, axis)

    def step(self, H_ext: np.ndarray) -> np.ndarray:
        """Advance one explicit Heun step and project each spin to S²."""
        gamma = 1.76e11
        H_total = self.compute_effective_field(H_ext) + self.get_thermal_noise()
        factor = -gamma / (1.0 + self.alpha ** 2)
        precession = np.cross(self.S, H_total)
        damping = np.cross(self.S, precession)
        derivative = factor * (precession + self.alpha * damping) + self.get_ciss_torque()
        predictor = self.S + derivative * self.dt
        predictor /= np.linalg.norm(predictor, axis=1, keepdims=True)
        predictor_field = np.asarray(H_ext, dtype=float) + _effective_field(
            predictor, LLGConfig(n_spins=self.num_spins, exchange=self.exchange, dmi=self.dmi)
        ) + self.get_thermal_noise()
        predictor_precession = np.cross(predictor, predictor_field)
        predictor_damping = np.cross(predictor, predictor_precession)
        predictor_derivative = factor * (predictor_precession + self.alpha * predictor_damping)
        predictor_derivative += self.ciss_scale * np.cross(predictor, np.array([0.0, 0.0, 1.0]))
        self.S += 0.5 * (derivative + predictor_derivative) * self.dt
        self.S /= np.linalg.norm(self.S, axis=1, keepdims=True)
        return self.S


@dataclass(frozen=True)
class LLGConfig:
    n_spins: int = 32
    steps: int = 500
    dt_s: float = 1e-5
    exchange: float = 0.8
    dmi: float = 0.15
    damping: float = 0.05
    ciss_torque: float = 0.02
    thermal_noise: float = 0.01
    seed: int = 0


def _effective_field(spins: np.ndarray, cfg: LLGConfig) -> np.ndarray:
    field = np.zeros_like(spins)
    field[1:-1] += cfg.exchange * (spins[:-2] + spins[2:])
    field[0] += cfg.exchange * spins[1]
    field[-1] += cfg.exchange * spins[-2]
    # Discrete chiral DMI field around the lattice axis.
    field[1:-1, 1] += cfg.dmi * (spins[2:, 2] - spins[:-2, 2])
    field[1:-1, 2] -= cfg.dmi * (spins[2:, 1] - spins[:-2, 1])
    return field


def _rhs(spins: np.ndarray, cfg: LLGConfig, rng: np.random.Generator) -> np.ndarray:
    field = _effective_field(spins, cfg)
    precession = -np.cross(spins, field)
    damping = -cfg.damping * np.cross(spins, np.cross(spins, field))
    torque = cfg.ciss_torque * np.cross(spins, np.array([0.0, 0.0, 1.0]))
    noise = cfg.thermal_noise * rng.normal(size=spins.shape)
    return precession + damping + torque + noise


def simulate_os_llg(cfg: LLGConfig = LLGConfig(), constants: PITNNConstants | None = None,
                    record_states: bool = False, backend: str = "numpy") -> dict:
    """Run a seeded lattice simulation and return summary metrics and trace."""
    constants = constants or PITNNConstants()
    if cfg.n_spins < 3 or cfg.steps < 1 or cfg.dt_s <= 0:
        raise ValueError("n_spins >= 3, steps >= 1 and dt_s > 0 are required")
    rng = np.random.default_rng(cfg.seed)
    spins = np.zeros((cfg.n_spins, 3), dtype=float)
    spins[:, 2] = 1.0
    magnetization = []
    topology_trace = []
    spins_history = []
    tracker = TopologicalInvariantTracker(cfg.n_spins)
    if backend not in {"numpy", "fast", "auto"}:
        raise ValueError("backend must be numpy, fast, or auto")
    workspace = None
    fast_step = None
    if backend in {"fast", "auto"}:
        from .kernels_fast import LLGWorkspace, heun_step
        workspace = LLGWorkspace.create(cfg.n_spins)
        fast_step = heun_step
    norm_error = 0.0
    for _ in range(cfg.steps):
        if workspace is None:
            k1 = _rhs(spins, cfg, rng)
            predictor = spins + cfg.dt_s * k1
            predictor /= np.linalg.norm(predictor, axis=1, keepdims=True)
            k2 = _rhs(predictor, cfg, rng)
            spins += 0.5 * cfg.dt_s * (k1 + k2)
            spins /= np.linalg.norm(spins, axis=1, keepdims=True)
        else:
            spins = fast_step(spins, cfg.thermal_noise * rng.normal(size=spins.shape),
                              cfg.thermal_noise * rng.normal(size=spins.shape), dt=cfg.dt_s,
                              exchange=cfg.exchange, dmi=cfg.dmi, damping=cfg.damping,
                              ciss_torque=cfg.ciss_torque, workspace=workspace)
        norm_error = max(norm_error, float(np.max(np.abs(np.linalg.norm(spins, axis=1) - 1.0))))
        magnetization.append(float(np.linalg.norm(np.mean(spins, axis=0))))
        topology_trace.append(tracker.audit_snapshot(spins))
        if record_states:
            spins_history.append(spins.copy())
    baseline_rate = cfg.thermal_noise / max(cfg.damping, 1e-15)
    protected_rate = baseline_rate * constants.arrhenius_factor / constants.ciss_suppression_ratio
    tau_eff = float(1.0 / max(protected_rate, np.finfo(float).tiny))
    result = {
        "tau_eff_s": tau_eff,
        "final_magnetization": magnetization[-1],
        "mean_magnetization": float(np.mean(magnetization)),
        "max_spin_norm_error": norm_error,
        "gamma_band_hz": constants.gamma_band_hz,
        "arrhenius_factor": constants.arrhenius_factor,
        "trace_magnetization": magnetization,
        "topology_trace": topology_trace,
        "topology_final": topology_trace[-1],
        "assumptions": {"model": "deterministic surrogate", "temperature_K": constants.temperature_K},
    }
    if record_states:
        result["spins_history"] = np.asarray(spins_history)
        result["time_stamps"] = np.arange(1, cfg.steps + 1, dtype=float) * cfg.dt_s
    return result
