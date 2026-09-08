"""Experiment planning builders for specialized neurotopology and awareness domains.

Implements planning factories for:
1. Pairwise versus triadic functional connectivity (FC)
2. Higher-order spectra (bispectrum, bicoherence)
3. Respiration and autonomic modulation
4. Discernment versus nonjudgment operationalization
5. Hypergraph transition forecasting
6. Null and surrogate experiments (phase randomization, IAAFT, modular permutations)
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .schema import ExperimentDomain, ExperimentPlan


def _generate_plan_checksum(plan_dict: dict[str, Any]) -> str:
    """Generate SHA-256 digest over canonical JSON representation."""
    canonical = {k: v for k, v in plan_dict.items() if k != "checksum"}
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class PairwiseVsTriadicFCPlanner:
    """Builder for pairwise vs triadic functional connectivity experiments."""

    @staticmethod
    def build_plan(
        plan_id: str,
        hypothesis_id: str,
        target_sample_size: int = 35,
        target_power: float = 0.85,
        alpha: float = 0.05,
        expected_triadic_effect_dz: float = 0.55,
        data_source: str = "ds005620",
        is_synthetic: bool = False,
    ) -> ExperimentPlan:
        variables = {
            "independent": ["connectivity_order"],
            "orders_compared": ["pairwise_bivariate", "triadic_hypergraph"],
            "dependent": ["betti_1_persistence", "triadic_mutual_information", "topological_efficiency"],
            "confounds": ["motion_fd", "global_signal_fluctuation", "regional_variance"],
        }
        power_analysis = {
            "alpha": alpha,
            "target_power": target_power,
            "effect_size_dz": expected_triadic_effect_dz,
            "design": "within_subject_paired",
            "minimum_n": target_sample_size,
        }
        analysis_protocol = (
            "Extract parcel BOLD time-series. Construct 2-simplex simplicial complexes comparing "
            "standard pairwise Pearson correlation vs 3-node O-information / synergy hyperedges. "
            "Compute persistent homology H1 and evaluate paired contrast across experimental conditions."
        )
        plan = ExperimentPlan(
            plan_id=plan_id,
            hypothesis_id=hypothesis_id,
            domain=ExperimentDomain.PAIRWISE_VS_TRIADIC_FC.value,
            design_type="within_subject_repeated_measures",
            variables=variables,
            target_sample_size=target_sample_size,
            power_analysis=power_analysis,
            analysis_protocol=analysis_protocol,
            surrogate_method="topological_edge_swapping",
            data_source=data_source,
            is_synthetic=is_synthetic,
            provenance={"created_by": "PairwiseVsTriadicFCPlanner", "version": "1.0"},
            checksum="",
        )
        plan.checksum = _generate_plan_checksum(plan.to_dict())
        return plan


class HigherOrderSpectraPlanner:
    """Builder for higher-order spectral analysis (bispectrum, bicoherence)."""

    @staticmethod
    def build_plan(
        plan_id: str,
        hypothesis_id: str,
        target_sample_size: int = 30,
        frequency_range_hz: tuple[float, float] = (0.5, 45.0),
        data_source: str = "ds005620_eeg",
        is_synthetic: bool = False,
    ) -> ExperimentPlan:
        variables = {
            "independent": ["cognitive_state", "bifrequency_pairs"],
            "dependent": ["cross_bispectrum_amplitude", "bicoherence_phase_coupling"],
            "frequency_range_hz": list(frequency_range_hz),
            "confounds": ["cardiac_harmonics", "ocular_artifacts", "line_noise_60hz"],
        }
        power_analysis = {
            "alpha": 0.05,
            "target_power": 0.80,
            "effect_size_dz": 0.50,
            "design": "paired_state_contrast",
            "minimum_n": target_sample_size,
        }
        analysis_protocol = (
            "Estimate third-order cross-cumulants in frequency domain via direct FFT segmenting. "
            "Compute normalized bicoherence to distinguish true quadratic phase coupling from "
            "spurious harmonics. Contrast peak bicoherence across conditions."
        )
        plan = ExperimentPlan(
            plan_id=plan_id,
            hypothesis_id=hypothesis_id,
            domain=ExperimentDomain.HIGHER_ORDER_SPECTRA.value,
            design_type="within_subject_frequency_coupling",
            variables=variables,
            target_sample_size=target_sample_size,
            power_analysis=power_analysis,
            analysis_protocol=analysis_protocol,
            surrogate_method="iaaft_amplitude_adjusted",
            data_source=data_source,
            is_synthetic=is_synthetic,
            provenance={"created_by": "HigherOrderSpectraPlanner", "version": "1.0"},
            checksum="",
        )
        plan.checksum = _generate_plan_checksum(plan.to_dict())
        return plan


class RespirationAutonomicPlanner:
    """Builder for respiration and autonomic modulation experiments."""

    @staticmethod
    def build_plan(
        plan_id: str,
        hypothesis_id: str,
        target_sample_size: int = 40,
        data_source: str = "ds005620_physio",
        is_synthetic: bool = False,
    ) -> ExperimentPlan:
        variables = {
            "independent": ["respiratory_phase", "autonomic_tone"],
            "dependent": ["rsa_amplitude", "heart_rate_variability_rmssd", "neural_topological_winding"],
            "confounds": ["tidal_volume", "end_tidal_co2", "baroreflex_delay"],
        }
        power_analysis = {
            "alpha": 0.05,
            "target_power": 0.85,
            "effect_size_dz": 0.48,
            "design": "phase_locked_cross_correlation",
            "minimum_n": target_sample_size,
        }
        analysis_protocol = (
            "Extract respiratory volume per time (RVT) and inter-beat intervals (IBI). "
            "Compute respiratory sinus arrhythmia (RSA) and phase-lock neural topological charge "
            "to inhalation/exhalation cycles to evaluate visceral-neural coupling."
        )
        plan = ExperimentPlan(
            plan_id=plan_id,
            hypothesis_id=hypothesis_id,
            domain=ExperimentDomain.RESPIRATION_AUTONOMIC_MODULATION.value,
            design_type="cardiorespiratory_neural_coupling",
            variables=variables,
            target_sample_size=target_sample_size,
            power_analysis=power_analysis,
            analysis_protocol=analysis_protocol,
            surrogate_method="circular_shift_null",
            data_source=data_source,
            is_synthetic=is_synthetic,
            provenance={"created_by": "RespirationAutonomicPlanner", "version": "1.0"},
            checksum="",
        )
        plan.checksum = _generate_plan_checksum(plan.to_dict())
        return plan


class DiscernmentNonjudgmentPlanner:
    """Builder for discernment versus nonjudgment operationalization experiments."""

    @staticmethod
    def build_plan(
        plan_id: str,
        hypothesis_id: str,
        target_sample_size: int = 45,
        data_source: str = "ds005620_pheno",
        is_synthetic: bool = False,
    ) -> ExperimentPlan:
        variables = {
            "independent": ["attentional_mode"],
            "attentional_states": ["analytical_discernment", "open_monitoring_nonjudgment"],
            "dependent": ["metastability_index", "graph_modularity_q", "temporal_betti_divergence"],
            "confounds": ["drowsiness", "subjective_effort", "habituation"],
        }
        power_analysis = {
            "alpha": 0.05,
            "target_power": 0.80,
            "effect_size_dz": 0.45,
            "design": "within_subject_block_design",
            "minimum_n": target_sample_size,
        }
        analysis_protocol = (
            "Contrast high-discernment cognitive tasks against receptive non-judgmental open monitoring. "
            "Evaluate dynamical topological stability: non-judgment is hypothesized to yield higher "
            "metastability and broader persistence-landscape distributions without loss of network coherence."
        )
        plan = ExperimentPlan(
            plan_id=plan_id,
            hypothesis_id=hypothesis_id,
            domain=ExperimentDomain.DISCERNMENT_NONJUDGMENT_OPERATIONALIZATION.value,
            design_type="phenomenological_topological_mapping",
            variables=variables,
            target_sample_size=target_sample_size,
            power_analysis=power_analysis,
            analysis_protocol=analysis_protocol,
            surrogate_method="trial_shuffling_null",
            data_source=data_source,
            is_synthetic=is_synthetic,
            provenance={"created_by": "DiscernmentNonjudgmentPlanner", "version": "1.0"},
            checksum="",
        )
        plan.checksum = _generate_plan_checksum(plan.to_dict())
        return plan


class HypergraphTransitionPlanner:
    """Builder for hypergraph transition forecasting experiments."""

    @staticmethod
    def build_plan(
        plan_id: str,
        hypothesis_id: str,
        target_sample_size: int = 35,
        forecast_horizon_seconds: float = 10.0,
        data_source: str = "ds005620_timeseries",
        is_synthetic: bool = False,
    ) -> ExperimentPlan:
        variables = {
            "independent": ["time_to_state_transition", "forecast_horizon_seconds"],
            "dependent": ["critical_slowing_down_autocorrelation", "hypergraph_diameter", "topological_variance_burst"],
            "confounds": ["baseline_drift", "micro_head_movements", "signal_snr"],
        }
        power_analysis = {
            "alpha": 0.05,
            "target_power": 0.85,
            "effect_size_dz": 0.60,
            "design": "out_of_sample_event_forecasting",
            "minimum_n": target_sample_size,
        }
        analysis_protocol = (
            "Sliding-window hypergraph representation of multi-scale brain dynamics. "
            "Evaluate whether critical slowing down and abrupt expansion of 1-homology cycles "
            "forecast state transitions (e.g. loss of responsiveness) with out-of-sample cross-validation."
        )
        plan = ExperimentPlan(
            plan_id=plan_id,
            hypothesis_id=hypothesis_id,
            domain=ExperimentDomain.HYPERGRAPH_TRANSITION_FORECASTING.value,
            design_type="time_series_forecasting",
            variables=variables,
            target_sample_size=target_sample_size,
            power_analysis=power_analysis,
            analysis_protocol=analysis_protocol,
            surrogate_method="ar1_bootstrap_surrogate",
            data_source=data_source,
            is_synthetic=is_synthetic,
            provenance={"created_by": "HypergraphTransitionPlanner", "version": "1.0"},
            checksum="",
        )
        plan.checksum = _generate_plan_checksum(plan.to_dict())
        return plan


class NullSurrogatePlanner:
    """Builder for null and surrogate benchmark experiments."""

    @staticmethod
    def build_plan(
        plan_id: str,
        hypothesis_id: str,
        surrogate_type: str = "iaaft",
        num_surrogates: int = 1000,
        data_source: str = "empirical_pre_post",
        is_synthetic: bool = False,
    ) -> ExperimentPlan:
        variables = {
            "independent": ["null_model_family", "num_surrogates"],
            "surrogate_type": surrogate_type,
            "dependent": ["empirical_vs_surrogate_divergence", "empirical_p_value"],
            "confounds": ["spectral_distortion", "linear_autocorrelation_leakage"],
        }
        power_analysis = {
            "alpha": 0.01,
            "target_power": 0.95,
            "effect_size_dz": 0.80,
            "design": "non_parametric_monte_carlo",
            "minimum_n": num_surrogates,
        }
        analysis_protocol = (
            f"Generate {num_surrogates} surrogate datasets preserving power spectrum and amplitude "
            f"distribution using method '{surrogate_type}'. Recompute persistent homology on all "
            f"surrogates to construct strict empirical null distribution."
        )
        plan = ExperimentPlan(
            plan_id=plan_id,
            hypothesis_id=hypothesis_id,
            domain=ExperimentDomain.NULL_AND_SURROGATE.value,
            design_type="monte_carlo_surrogate_null",
            variables=variables,
            target_sample_size=num_surrogates,
            power_analysis=power_analysis,
            analysis_protocol=analysis_protocol,
            surrogate_method=surrogate_type,
            data_source=data_source,
            is_synthetic=is_synthetic,
            provenance={"created_by": "NullSurrogatePlanner", "version": "1.0"},
            checksum="",
        )
        plan.checksum = _generate_plan_checksum(plan.to_dict())
        return plan
