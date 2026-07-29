"""Immutable protocol and deterministic subject-allocation primitives."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
import hashlib
from typing import Any, Iterable


@dataclass(frozen=True)
class ProtocolSpec:
    protocol_id: str
    hypothesis_id: str
    dataset_id: str
    external_dataset_id: str
    split_seed: int = 20260729
    development_fraction: float = 0.70
    feature_names: tuple[str, ...] = (
        "q_net",
        "q_abs",
        "f_dress",
        "defect_density",
        "mean_plv",
        "phase_discontinuity_proxy",
        "beta_spectral_topology_mass",
    )
    n_states: int = 4
    surrogate_draws: int = 200
    permutation_draws: int = 5000
    phenomenology_status: str = "state_proxy_only"
    cloud_enabled: bool = False
    braket_enabled: bool = False
    thresholds: dict[str, float] = field(default_factory=lambda: {
        "minimum_valid_fraction": 0.90,
        "confirmatory_abs_dz": 0.30,
        "confirmatory_p": 0.05,
        "confirmatory_tsnr_lower": 1.0,
        "external_abs_dz": 0.20,
        "external_p": 0.10,
        "external_tsnr": 1.0,
    })

    def validate(self) -> None:
        if not self.protocol_id or not self.hypothesis_id or not self.dataset_id or not self.external_dataset_id:
            raise ValueError("protocol and dataset identifiers are required")
        if not 0.0 < self.development_fraction < 1.0:
            raise ValueError("development_fraction must be between zero and one")
        if self.n_states < 2 or self.surrogate_draws < 1 or self.permutation_draws < 1:
            raise ValueError("state and draw counts must be positive")
        if not self.feature_names or len(set(self.feature_names)) != len(self.feature_names):
            raise ValueError("feature_names must be non-empty and unique")
        if self.cloud_enabled or self.braket_enabled:
            raise ValueError("cloud and Braket execution are disabled for this protocol")
        required = {
            "minimum_valid_fraction", "confirmatory_abs_dz", "confirmatory_p",
            "confirmatory_tsnr_lower", "external_abs_dz", "external_p", "external_tsnr",
        }
        if set(self.thresholds) != required:
            raise ValueError("threshold keys do not match the governed promotion policy")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        data = asdict(self)
        data["feature_names"] = list(self.feature_names)
        return data


def deterministic_subject_split(
    dataset_id: str,
    subject_ids: Iterable[str],
    *,
    seed: int,
    development_fraction: float,
) -> dict[str, list[str]]:
    """Allocate subjects by hash without exposing ordering or RNG state."""
    if not 0.0 < development_fraction < 1.0:
        raise ValueError("development_fraction must be between zero and one")
    subjects = sorted({str(subject) for subject in subject_ids})
    if len(subjects) < 2:
        raise ValueError("at least two subjects are required")
    ranked = sorted(
        subjects,
        key=lambda subject: hashlib.sha256(f"{dataset_id}|{seed}|{subject}".encode()).hexdigest(),
    )
    cut = min(max(int(round(len(ranked) * development_fraction)), 1), len(ranked) - 1)
    return {"development": ranked[:cut], "confirmatory": ranked[cut:]}
