"""Run changed Round 6 candidate suites against their checked-in implementations.

This helper is invoked only from the Required Checks workflow. It uses explicit
file mappings so a test-only PR cannot pass by skipping an import that is not
present on main. Every selected file runs in a fresh bounded pytest process.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


COMPONENTS: dict[str, dict[str, Any]] = {
    "planar_geometry": {
        "triggers": (
            "neurotopology_sim/experimental/geometry/",
            "tests/neurotopology_sim/experimental/geometry/",
            "tests/experimental/test_planar_triangulation.py",
        ),
        "implementation": "neurotopology_sim/experimental/geometry/planar_triangulation.py",
        "tests": (
            "tests/neurotopology_sim/experimental/geometry/test_planar_triangulation.py",
            "tests/experimental/test_planar_triangulation.py",
        ),
        "candidate_pairs": (
            {"implementation": "neurotopology_sim/experimental/geometry/planar_triangulation.py", "test": "tests/neurotopology_sim/experimental/geometry/test_planar_triangulation.py"},
            {"implementation": "neurotopology_sim/experimental/geometry/planar_triangulation.py", "test": "tests/experimental/test_planar_triangulation.py"},
        ),
        "implementation_roots": ("neurotopology_sim/experimental/geometry/",),
        "test_roots": ("tests/neurotopology_sim/experimental/geometry/", "tests/experimental/"),
    },
    "hodge_2d": {
        "triggers": (
            "neurotopology_sim/experimental/topology/hodge_2d.py",
            "tests/neurotopology_sim/experimental/topology/test_hodge_2d.py",
            "tools/hodge_decomposition_audit/",
            "tests/tools/hodge_decomposition_audit/",
            "experimental/phase_cochain_reference/",
            "tests/experimental/phase_cochain_reference/",
        ),
        "implementation_any": (
            "neurotopology_sim/experimental/topology/hodge_2d.py",
            "tools/hodge_decomposition_audit/audit.py",
            "experimental/phase_cochain_reference/hodge.py",
        ),
        "tests": (
            "tests/neurotopology_sim/experimental/topology/test_hodge_2d.py",
            "tests/tools/hodge_decomposition_audit/test_hodge_audit.py",
            "tests/experimental/phase_cochain_reference/test_charge_moments_and_centroids.py",
            "tests/experimental/phase_cochain_reference/test_coboundary_exactness.py",
            "tests/experimental/phase_cochain_reference/test_weighted_hodge_decomposition.py",
            "tests/experimental/phase_cochain_reference/test_wrapped_phase_charges.py",
        ),
        "candidate_pairs": (
            {"implementation": "neurotopology_sim/experimental/topology/hodge_2d.py", "test": "tests/neurotopology_sim/experimental/topology/test_hodge_2d.py"},
            {"implementation": "tools/hodge_decomposition_audit/audit.py", "test": "tests/tools/hodge_decomposition_audit/test_hodge_audit.py"},
            {"implementation": "tools/hodge_decomposition_audit/__main__.py", "test": "tests/tools/hodge_decomposition_audit/test_hodge_audit.py"},
            {"implementation": "experimental/phase_cochain_reference/hodge.py", "test": "tests/experimental/phase_cochain_reference/test_weighted_hodge_decomposition.py"},
            {"implementation": "tools/hodge_decomposition_audit/charges.py", "test": "tests/tools/hodge_decomposition_audit/test_hodge_audit.py"},
            {"implementation": "tools/hodge_decomposition_audit/fixtures.py", "test": "tests/tools/hodge_decomposition_audit/test_hodge_audit.py"},
            {"implementation": "tools/hodge_decomposition_audit/hodge_oracle.py", "test": "tests/tools/hodge_decomposition_audit/test_hodge_audit.py"},
            {"implementation": "tools/hodge_decomposition_audit/incidence.py", "test": "tests/tools/hodge_decomposition_audit/test_hodge_audit.py"},
            {"implementation": "tools/hodge_decomposition_audit/report.py", "test": "tests/tools/hodge_decomposition_audit/test_hodge_audit.py"},
            {"implementation": "tools/hodge_decomposition_audit/schema.py", "test": "tests/tools/hodge_decomposition_audit/test_hodge_audit.py"},
            {"implementation": "experimental/phase_cochain_reference/cochain.py", "test": "tests/experimental/phase_cochain_reference/test_coboundary_exactness.py"},
            {"implementation": "experimental/phase_cochain_reference/complex.py", "test": "tests/experimental/phase_cochain_reference/test_coboundary_exactness.py"},
            {"implementation": "experimental/phase_cochain_reference/fixtures.py", "test": "tests/experimental/phase_cochain_reference/test_charge_moments_and_centroids.py"},
            {"implementation": "experimental/phase_cochain_reference/hodge.py", "test": "tests/experimental/phase_cochain_reference/test_wrapped_phase_charges.py"},
        ),
        "implementation_roots": ("neurotopology_sim/experimental/topology/", "tools/hodge_decomposition_audit/", "experimental/phase_cochain_reference/"),
        "test_roots": ("tests/neurotopology_sim/experimental/topology/", "tests/tools/hodge_decomposition_audit/", "tests/experimental/phase_cochain_reference/"),
    },
    "spherical_csd": {
        "triggers": (
            "neurotopology_sim/experimental/preprocessing/",
            "tests/neurotopology_sim/experimental/preprocessing/",
            "tests/experimental/test_spherical_csd_parity.py",
            "tools/mne_csd_reference_audit/",
            "tests/mne_csd_reference_audit/",
        ),
        "implementation_any": (
            "neurotopology_sim/experimental/preprocessing/spherical_csd.py",
            "tools/mne_csd_reference_audit/kkt.py",
        ),
        "tests": (
            "tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py",
            "tests/experimental/test_spherical_csd_parity.py",
            "tests/mne_csd_reference_audit/test_kkt_operator.py",
            "tests/mne_csd_reference_audit/test_legendre_constants.py",
            "tests/mne_csd_reference_audit/test_isolation_and_pin.py",
            "tests/mne_csd_reference_audit/test_mne_integration_optional.py",
        ),
        "candidate_pairs": (
            {"implementation": "neurotopology_sim/experimental/preprocessing/spherical_csd.py", "test": "tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py"},
            {"implementation": "neurotopology_sim/experimental/preprocessing/spherical_csd.py", "test": "tests/experimental/test_spherical_csd_parity.py"},
            {"implementation": "tools/mne_csd_reference_audit/kkt.py", "test": "tests/mne_csd_reference_audit/test_kkt_operator.py"},
            {"implementation": "tools/mne_csd_reference_audit/kkt.py", "test": "tests/mne_csd_reference_audit/test_legendre_constants.py"},
            {"implementation": "tools/mne_csd_reference_audit/__main__.py", "test": "tests/mne_csd_reference_audit/test_kkt_operator.py"},
            {"implementation": "tools/mne_csd_reference_audit/legendre.py", "test": "tests/mne_csd_reference_audit/test_legendre_constants.py"},
            {"implementation": "tools/mne_csd_reference_audit/montages.py", "test": "tests/mne_csd_reference_audit/test_kkt_operator.py"},
            {"implementation": "tools/mne_csd_reference_audit/pin.py", "test": "tests/mne_csd_reference_audit/test_isolation_and_pin.py"},
            {"implementation": "tools/mne_csd_reference_audit/report.py", "test": "tests/mne_csd_reference_audit/test_isolation_and_pin.py"},
            {"implementation": "tools/mne_csd_reference_audit/kkt.py", "test": "tests/mne_csd_reference_audit/test_mne_integration_optional.py"},
        ),
        "implementation_roots": ("neurotopology_sim/experimental/preprocessing/", "tools/mne_csd_reference_audit/"),
        "test_roots": ("tests/neurotopology_sim/experimental/preprocessing/", "tests/experimental/", "tests/mne_csd_reference_audit/"),
    },
    "four_sphere": {
        "triggers": (
            "physics/eeg_forward/",
            "tests/physics/eeg_forward/",
            "tests/physics/test_four_sphere_oracle.py",
            "tools/experimental_audits/four_shell_bvp_oracle.py",
            "tests/experimental_audits/test_four_shell_bvp_oracle.py",
        ),
        "implementation_any": (
            "physics/eeg_forward/four_sphere.py",
            "tools/experimental_audits/four_shell_bvp_oracle.py",
        ),
        "tests": (
            "tests/physics/eeg_forward/test_four_sphere.py",
            "tests/physics/test_four_sphere_oracle.py",
            "tests/experimental_audits/test_four_shell_bvp_oracle.py",
        ),
        "candidate_pairs": (
            {"implementation": "physics/eeg_forward/four_sphere.py", "test": "tests/physics/eeg_forward/test_four_sphere.py"},
            {"implementation": "physics/eeg_forward/four_sphere.py", "test": "tests/physics/test_four_sphere_oracle.py"},
            {"implementation": "tools/experimental_audits/four_shell_bvp_oracle.py", "test": "tests/experimental_audits/test_four_shell_bvp_oracle.py"},
        ),
        "implementation_roots": ("physics/eeg_forward/", "tools/experimental_audits/"),
        "test_roots": ("tests/physics/eeg_forward/", "tests/physics/test_four_sphere_oracle.py", "tests/experimental_audits/"),
    },
    "phase_winding": {
        "triggers": (
            "neurotopology_sim/experimental/topology/winding.py",
            "tests/neurotopology_sim/experimental/topology/test_phase_winding.py",
        ),
        "implementation": "neurotopology_sim/experimental/topology/winding.py",
        "tests": ("tests/neurotopology_sim/experimental/topology/test_phase_winding.py",),
        "candidate_pairs": (
            {"implementation": "neurotopology_sim/experimental/topology/winding.py", "test": "tests/neurotopology_sim/experimental/topology/test_phase_winding.py"},
        ),
        "implementation_roots": ("neurotopology_sim/experimental/topology/",),
        "test_roots": ("tests/neurotopology_sim/experimental/topology/",),
    },
    "surrogate_nulls": {
        "triggers": ("tools/surrogate_nulls/", "tests/surrogate_nulls/"),
        "implementation_any": (
            "tools/surrogate_nulls/nulls.py",
            "tools/surrogate_nulls/spectral.py",
            "tools/surrogate_nulls/csd.py",
        ),
        "tests": (
            "tests/surrogate_nulls/test_phase_nulls.py",
            "tests/surrogate_nulls/test_mv_iaaft.py",
            "tests/surrogate_nulls/test_csd_estimators.py",
            "tests/surrogate_nulls/test_cholesky_csd.py",
            "tests/surrogate_nulls/test_edge_cases.py",
            "tests/surrogate_nulls/test_hardening_diagnostics.py",
            "tests/surrogate_nulls/test_real_part_and_validity.py",
        ),
        "candidate_pairs": (
            {"implementation": "tools/surrogate_nulls/nulls.py", "test": "tests/surrogate_nulls/test_phase_nulls.py"},
            {"implementation": "tools/surrogate_nulls/spectral.py", "test": "tests/surrogate_nulls/test_mv_iaaft.py"},
            {"implementation": "tools/surrogate_nulls/csd.py", "test": "tests/surrogate_nulls/test_csd_estimators.py"},
            {"implementation": "tools/surrogate_nulls/csd.py", "test": "tests/surrogate_nulls/test_cholesky_csd.py"},
            {"implementation": "tools/surrogate_nulls/nulls.py", "test": "tests/surrogate_nulls/test_edge_cases.py"},
            {"implementation": "tools/surrogate_nulls/nulls.py", "test": "tests/surrogate_nulls/test_hardening_diagnostics.py"},
            {"implementation": "tools/surrogate_nulls/csd.py", "test": "tests/surrogate_nulls/test_real_part_and_validity.py"},
            {"implementation": "tools/surrogate_nulls/nulls.py", "test": "tests/surrogate_nulls/test_real_part_and_validity.py"},
            {"implementation": "tools/surrogate_nulls/spectral.py", "test": "tests/surrogate_nulls/test_real_part_and_validity.py"},
        ),
        "implementation_roots": ("tools/surrogate_nulls/",),
        "test_roots": ("tests/surrogate_nulls/",),
    },
    "phase_uncertainty": {
        "triggers": ("tools/phase_uncertainty/", "tests/phase_uncertainty/"),
        "implementation": "tools/phase_uncertainty/candidate_estimator.py",
        "tests": (
            "tests/phase_uncertainty/test_candidate_contract.py",
            "tests/phase_uncertainty/test_calibration_coverage.py",
            "tests/phase_uncertainty/test_synthetic_fixtures.py",
        ),
        "candidate_pairs": (
            {"implementation": "tools/phase_uncertainty/candidate_estimator.py", "test": "tests/phase_uncertainty/test_candidate_contract.py"},
            {"implementation": "tools/phase_uncertainty/candidate_estimator.py", "test": "tests/phase_uncertainty/test_calibration_coverage.py"},
            {"implementation": "tools/phase_uncertainty/candidate_estimator.py", "test": "tests/phase_uncertainty/test_synthetic_fixtures.py"},
            {"implementation": "tools/phase_uncertainty/calibration.py", "test": "tests/phase_uncertainty/test_calibration_coverage.py"},
            {"implementation": "tools/phase_uncertainty/cli.py", "test": "tests/phase_uncertainty/test_candidate_contract.py"},
            {"implementation": "tools/phase_uncertainty/fixtures.py", "test": "tests/phase_uncertainty/test_synthetic_fixtures.py"},
        ),
        "implementation_roots": ("tools/phase_uncertainty/",),
        "test_roots": ("tests/phase_uncertainty/",),
    },
    "surrogate_audit": {
        "triggers": ("tools/surrogate_audit/", "tests/surrogate_audit/"),
        "implementation_any": (
            "tools/surrogate_audit/mv_fpr.py",
            "tools/surrogate_audit/mv_iaaft.py",
        ),
        "tests": (
            "tests/surrogate_audit/test_mv_fpr.py",
            "tests/surrogate_audit/test_mv_iaaft.py",
            "tests/surrogate_audit/test_invalid_inputs.py",
        ),
        "candidate_pairs": (
            {"implementation": "tools/surrogate_audit/mv_fpr.py", "test": "tests/surrogate_audit/test_mv_fpr.py"},
            {"implementation": "tools/surrogate_audit/mv_iaaft.py", "test": "tests/surrogate_audit/test_mv_iaaft.py"},
            {"implementation": "tools/surrogate_audit/mv_iaaft.py", "test": "tests/surrogate_audit/test_invalid_inputs.py"},
            {"implementation": "tools/surrogate_audit/errors.py", "test": "tests/surrogate_audit/test_invalid_inputs.py"},
            {"implementation": "tools/surrogate_audit/metrics.py", "test": "tests/surrogate_audit/test_mv_fpr.py"},
            {"implementation": "tools/surrogate_audit/report.py", "test": "tests/surrogate_audit/test_invalid_inputs.py"},
            {"implementation": "tools/surrogate_audit/status.py", "test": "tests/surrogate_audit/test_invalid_inputs.py"},
        ),
        "implementation_roots": ("tools/surrogate_audit/",),
        "test_roots": ("tests/surrogate_audit/",),
    },
    "synthetic_roc": {
        "triggers": (
            "neurotopology_sim/experimental/benchmarks/",
            "tests/neurotopology_sim/experimental/benchmarks/",
            "tests/experimental/test_synthetic_roc_calibration_split.py",
        ),
        "implementation": "neurotopology_sim/experimental/benchmarks/synthetic_forward_roc.py",
        "tests": (
            "tests/neurotopology_sim/experimental/benchmarks/test_synthetic_forward_roc.py",
            "tests/experimental/test_synthetic_roc_calibration_split.py",
        ),
        "candidate_pairs": (
            {"implementation": "neurotopology_sim/experimental/benchmarks/synthetic_forward_roc.py", "test": "tests/neurotopology_sim/experimental/benchmarks/test_synthetic_forward_roc.py"},
            {"implementation": "neurotopology_sim/experimental/benchmarks/synthetic_forward_roc.py", "test": "tests/experimental/test_synthetic_roc_calibration_split.py"},
        ),
        "implementation_roots": ("neurotopology_sim/experimental/benchmarks/",),
        "test_roots": ("tests/neurotopology_sim/experimental/benchmarks/", "tests/experimental/"),
    },
    "simulation_grid_planner": {
        "triggers": ("tools/simulation_runtime/", "tests/simulation_runtime/"),
        "implementation": "tools/simulation_runtime/grid_plan.py",
        "tests": ("tests/simulation_runtime/test_grid_plan.py",),
        "candidate_pairs": (
            {"implementation": "tools/simulation_runtime/grid_plan.py", "test": "tests/simulation_runtime/test_grid_plan.py"},
        ),
        "implementation_roots": ("tools/simulation_runtime/",),
        "test_roots": ("tests/simulation_runtime/",),
    },
    "report_firewall": {
        "triggers": ("tools/batch3_report_firewall/", "tests/tools/batch3_report_firewall/", "scripts/check_batch3_report_language.py"),
        "implementation": "tools/batch3_report_firewall/checker.py",
        "tests": ("tests/tools/batch3_report_firewall/test_checker.py",),
        "candidate_pairs": (
            {"implementation": "tools/batch3_report_firewall/checker.py", "test": "tests/tools/batch3_report_firewall/test_checker.py"},
        ),
        "implementation_roots": ("tools/batch3_report_firewall/",),
        "test_roots": ("tests/tools/batch3_report_firewall/",),
    },
    "provenance_join": {
        "triggers": ("tools/batch3_provenance_join/", "tests/tools/batch3_provenance_join/", "scripts/run_batch3_provenance_join.py"),
        "implementation_any": (
            "tools/batch3_provenance_join/auditor.py",
            "tools/batch3_provenance_join/models.py",
        ),
        "tests": (
            "tests/tools/batch3_provenance_join/test_audit.py",
            "tests/tools/batch3_provenance_join/test_safety_and_cycles.py",
        ),
        "candidate_pairs": (
            {"implementation": "tools/batch3_provenance_join/auditor.py", "test": "tests/tools/batch3_provenance_join/test_audit.py"},
            {"implementation": "tools/batch3_provenance_join/models.py", "test": "tests/tools/batch3_provenance_join/test_safety_and_cycles.py"},
        ),
        "implementation_roots": ("tools/batch3_provenance_join/",),
        "test_roots": ("tests/tools/batch3_provenance_join/",),
    },
    "topology_backend_conformance": {
        "triggers": ("tools/topology_backend_conformance/", "tests/topology_backend_conformance/"),
        "implementation_any": (
            "tools/topology_backend_conformance/adapters.py",
            "tools/topology_backend_conformance/cli.py",
            "tools/topology_backend_conformance/comparator.py",
            "tools/topology_backend_conformance/fixtures.py",
            "tools/topology_backend_conformance/models.py",
            "tools/topology_backend_conformance/reference_engine.py",
        ),
        "tests": (
            "tests/topology_backend_conformance/test_comparability_gates.py",
            "tests/topology_backend_conformance/test_invariants_and_serialization.py",
            "tests/topology_backend_conformance/test_optional_backends_graceful.py",
            "tests/topology_backend_conformance/test_repo_topology_integration.py",
            "tests/topology_backend_conformance/test_synthetic_fixtures.py",
        ),
        "candidate_pairs": (
            {"implementation": "tools/topology_backend_conformance/adapters.py", "test": "tests/topology_backend_conformance/test_comparability_gates.py"},
            {"implementation": "tools/topology_backend_conformance/cli.py", "test": "tests/topology_backend_conformance/test_repo_topology_integration.py"},
            {"implementation": "tools/topology_backend_conformance/comparator.py", "test": "tests/topology_backend_conformance/test_comparability_gates.py"},
            {"implementation": "tools/topology_backend_conformance/fixtures.py", "test": "tests/topology_backend_conformance/test_synthetic_fixtures.py"},
            {"implementation": "tools/topology_backend_conformance/models.py", "test": "tests/topology_backend_conformance/test_invariants_and_serialization.py"},
            {"implementation": "tools/topology_backend_conformance/reference_engine.py", "test": "tests/topology_backend_conformance/test_comparability_gates.py"},
            {"implementation": "tools/topology_backend_conformance/adapters.py", "test": "tests/topology_backend_conformance/test_optional_backends_graceful.py"},
        ),
        "implementation_roots": ("tools/topology_backend_conformance/",),
        "test_roots": ("tests/topology_backend_conformance/",),
    },
    "finite_chain_audit": {
        "triggers": ("tools/batch2_chain_complex_audit/", "tests/batch2_chain_complex_audit/"),
        "implementation_any": (
            "tools/batch2_chain_complex_audit/complex.py",
            "tools/batch2_chain_complex_audit/errors.py",
            "tools/batch2_chain_complex_audit/fixtures.py",
            "tools/batch2_chain_complex_audit/rank.py",
        ),
        "tests": (
            "tests/batch2_chain_complex_audit/test_betti_fixtures.py",
            "tests/batch2_chain_complex_audit/test_boundary_composition.py",
            "tests/batch2_chain_complex_audit/test_cell_boundary_signed.py",
            "tests/batch2_chain_complex_audit/test_empty_edge_cases.py",
            "tests/batch2_chain_complex_audit/test_malformed_inputs.py",
            "tests/batch2_chain_complex_audit/test_svd_sensitivity.py",
        ),
        "candidate_pairs": (
            {"implementation": "tools/batch2_chain_complex_audit/complex.py", "test": "tests/batch2_chain_complex_audit/test_boundary_composition.py"},
            {"implementation": "tools/batch2_chain_complex_audit/errors.py", "test": "tests/batch2_chain_complex_audit/test_malformed_inputs.py"},
            {"implementation": "tools/batch2_chain_complex_audit/fixtures.py", "test": "tests/batch2_chain_complex_audit/test_betti_fixtures.py"},
            {"implementation": "tools/batch2_chain_complex_audit/rank.py", "test": "tests/batch2_chain_complex_audit/test_svd_sensitivity.py"},
            {"implementation": "tools/batch2_chain_complex_audit/complex.py", "test": "tests/batch2_chain_complex_audit/test_cell_boundary_signed.py"},
            {"implementation": "tools/batch2_chain_complex_audit/complex.py", "test": "tests/batch2_chain_complex_audit/test_empty_edge_cases.py"},
        ),
        "implementation_roots": ("tools/batch2_chain_complex_audit/",),
        "test_roots": ("tests/batch2_chain_complex_audit/",),
    },
    "winding_charge_audit": {
        "triggers": ("tools/experimental_audits/winding_charge_round6/", "tests/experimental_audits/test_winding_charge_round6_oracle.py"),
        "implementation_any": (
            "tools/experimental_audits/winding_charge_round6/__main__.py",
            "tools/experimental_audits/winding_charge_round6/audit.py",
            "tools/experimental_audits/winding_charge_round6/conventions.py",
            "tools/experimental_audits/winding_charge_round6/fixtures.py",
            "tools/experimental_audits/winding_charge_round6/oracle.py",
        ),
        "tests": ("tests/experimental_audits/test_winding_charge_round6_oracle.py",),
        "candidate_pairs": (
            {"implementation": "tools/experimental_audits/winding_charge_round6/__main__.py", "test": "tests/experimental_audits/test_winding_charge_round6_oracle.py"},
            {"implementation": "tools/experimental_audits/winding_charge_round6/audit.py", "test": "tests/experimental_audits/test_winding_charge_round6_oracle.py"},
            {"implementation": "tools/experimental_audits/winding_charge_round6/conventions.py", "test": "tests/experimental_audits/test_winding_charge_round6_oracle.py"},
            {"implementation": "tools/experimental_audits/winding_charge_round6/fixtures.py", "test": "tests/experimental_audits/test_winding_charge_round6_oracle.py"},
            {"implementation": "tools/experimental_audits/winding_charge_round6/oracle.py", "test": "tests/experimental_audits/test_winding_charge_round6_oracle.py"},
        ),
        "implementation_roots": ("tools/experimental_audits/winding_charge_round6/",),
        "test_roots": ("tests/experimental_audits/",),
    },
    "dmd_crouzeix": {
        "triggers": (
            "neurotopology_sim/experimental/dynamics/",
            "tests/dmd_crouzeix_contract/",
            "tests/experimental/test_dmd_crouzeix.py",
        ),
        "implementation": "neurotopology_sim/experimental/dynamics/dmd_crouzeix.py",
        "tests": (
            "tests/dmd_crouzeix_contract/test_production_contract.py",
            "tests/experimental/test_dmd_crouzeix.py",
        ),
        "candidate_pairs": (
            {"implementation": "neurotopology_sim/experimental/dynamics/dmd_crouzeix.py", "test": "tests/dmd_crouzeix_contract/test_production_contract.py"},
            {"implementation": "neurotopology_sim/experimental/dynamics/dmd_crouzeix.py", "test": "tests/experimental/test_dmd_crouzeix.py"},
        ),
        "implementation_roots": ("neurotopology_sim/experimental/dynamics/",),
        "test_roots": (
            "tests/dmd_crouzeix_contract/",
            "tests/experimental/test_dmd_crouzeix.py",
        ),
    },
}


def normalize_repo_path(path: str) -> str:
    """Normalize Git's POSIX paths and Windows-style test inputs consistently."""
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _trigger_matches(path: str, trigger: str) -> bool:
    path = normalize_repo_path(path).casefold()
    trigger = normalize_repo_path(trigger).casefold()
    return path == trigger or trigger.endswith("/") and path.startswith(trigger)


def _is_component_relevant(name: str, changed_paths: set[str]) -> bool:
    spec = COMPONENTS[name]
    return any(
        _trigger_matches(path, trigger)
        for path in changed_paths
        for trigger in spec["triggers"]
    )


def select_components(changed_paths: set[str]) -> list[str]:
    """Return deterministic component names touched by source or test changes."""
    return [name for name in COMPONENTS if _is_component_relevant(name, changed_paths)]


def _changed_candidate_paths(spec: dict[str, Any], changed_paths: set[str]) -> list[str]:
    pairs = spec.get("candidate_pairs", ())
    known = {
        normalize_repo_path(path).casefold()
        for pair in pairs
        for path in (pair["implementation"], pair["test"])
    }
    unmapped = []
    for original in changed_paths:
        path = normalize_repo_path(original)
        lower = path.casefold()
        in_candidate_root = any(
            lower.startswith(normalize_repo_path(root).casefold())
            for root in (*spec.get("implementation_roots", ()), *spec.get("test_roots", ()))
        )
        if not in_candidate_root or not path.endswith(".py") or path.rsplit("/", 1)[-1] == "__init__.py":
            continue
        is_test = path.rsplit("/", 1)[-1].startswith("test_")
        if is_test or any(lower.startswith(normalize_repo_path(root).casefold()) for root in spec.get("implementation_roots", ())):
            if lower not in known:
                unmapped.append(path)
    return sorted(unmapped)


def inspect_component(name: str, root: Path, changed_paths: set[str] | None = None) -> dict[str, Any]:
    """Require a concrete implementation/test pair for every selected candidate path."""
    spec = COMPONENTS[name]
    pairs = list(spec.get("candidate_pairs", ()))
    changes = {normalize_repo_path(path).casefold() for path in (changed_paths or set())}
    unmapped = _changed_candidate_paths(spec, changed_paths or set())
    selected_pairs = [
        pair for pair in pairs
        if normalize_repo_path(pair["test"]).casefold() in changes
    ]
    if not selected_pairs:
        changed_sources = {
            normalize_repo_path(pair["implementation"]).casefold()
            for pair in pairs
            if normalize_repo_path(pair["implementation"]).casefold() in changes
        }
        for source in sorted(changed_sources):
            source_pairs = [
                pair for pair in pairs
                if normalize_repo_path(pair["implementation"]).casefold() == source
            ]
            if source_pairs:
                selected_pairs.append(source_pairs[0])
    # A docs/init-only touch still validates an extant implementation/test pair;
    # an absent candidate never turns this fallback into a pass.
    if not selected_pairs:
        selected_pairs = [
            pair for pair in pairs
            if (root / pair["implementation"]).is_file() and (root / pair["test"]).is_file()
        ]
        if not selected_pairs and pairs:
            selected_pairs = [pairs[0]]

    missing_implementations = sorted({
        pair["implementation"] for pair in selected_pairs
        if not (root / pair["implementation"]).is_file()
    })
    missing_required_tests = sorted({
        pair["test"] for pair in selected_pairs
        if not (root / pair["test"]).is_file()
    })
    tests = [path for path in spec["tests"] if (root / path).is_file()]
    pair_tests = [pair["test"] for pair in selected_pairs if (root / pair["test"]).is_file()]
    tests_to_run = list(dict.fromkeys([*pair_tests, *tests]))
    implementations = sorted({
        pair["implementation"] for pair in selected_pairs
        if (root / pair["implementation"]).is_file()
    })
    blockers = []
    if missing_implementations:
        blockers.append("required candidate implementation is absent")
    if missing_required_tests:
        blockers.append("required candidate test is absent")
    if unmapped:
        blockers.append("changed candidate source/test path has no explicit implementation-test mapping")
    if not selected_pairs:
        blockers.append("no registered implementation-test pair exists")
    return {
        "component": name,
        "status": "BLOCKED" if blockers else "READY_TO_RUN",
        "blockers": blockers,
        "selected_paths": sorted({
            path for pair in selected_pairs for path in (pair["implementation"], pair["test"])
        }),
        "required_pairs": selected_pairs,
        "implementations": implementations,
        "missing_implementations": missing_implementations,
        "missing_required_tests": missing_required_tests,
        "unmapped_candidate_paths": unmapped,
        "available_candidate_tests": tests,
        "tests_to_run": tests_to_run,
        "executions": [],
    }


def junit_details(path: Path) -> tuple[tuple[int, int, int, int], list[dict[str, str]]]:
    """Return counts and explicit testcase outcomes from a JUnit XML report."""
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    details: list[dict[str, str]] = []
    skipped = failed = errors = 0
    for case in cases:
        outcome = "passed"
        for tag, label in (("skipped", "skipped"), ("failure", "failed"), ("error", "error")):
            node = case.find(tag)
            if node is not None:
                outcome = label
                if label == "skipped":
                    skipped += 1
                elif label == "failed":
                    failed += 1
                else:
                    errors += 1
                break
        details.append({
            "name": ".".join(filter(None, (case.attrib.get("classname", ""), case.attrib.get("name", "")))),
            "status": outcome,
        })
    return (len(cases), skipped, failed, errors), details


def junit_counts(path: Path) -> tuple[int, int, int, int]:
    """Return collected, skipped, failed, and errored testcase counts."""
    return junit_details(path)[0]


def junit_status(counts: tuple[int, int, int, int]) -> str:
    """A candidate suite passes only when it collected real tests and skipped none."""
    collected, skipped, failed, errors = counts
    return "PASS" if collected > 0 and skipped == 0 and failed == 0 and errors == 0 else "FAIL"


def collect_changed_paths(base: str, head: str, root: Path) -> set[str]:
    if not re.fullmatch(r"[0-9a-f]{40}", base) or not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("base and head must be full commit SHAs")
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {normalize_repo_path(line) for line in result.stdout.splitlines() if line.strip()}


def run(root: Path, base: str, head: str, report_path: Path) -> int:
    root = root.resolve()
    changed = collect_changed_paths(base, head, root)
    selected = select_components(changed)
    relevant_paths = sorted({
        normalize_repo_path(path)
        for path in changed
        if any(_is_component_relevant(name, {path}) for name in COMPONENTS)
    })
    report: dict[str, Any] = {
        "schema_version": "round6-experimental-ci-report-v1",
        "base_sha": base,
        "head_sha": head,
        "status": "NOT_APPLICABLE" if not selected and not relevant_paths else "INCONCLUSIVE",
        "changed_paths": sorted(changed),
        "relevant_paths": relevant_paths,
        "selected_components": selected,
        "selected_paths": {},
        "executed_commands": [],
        "components": [],
        "statement": "No scientific or empirical validity is assessed by this CI report.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if not selected and not relevant_paths:
        report_path.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print("No mapped Round 6 candidate files changed; this does not certify any experimental lane.")
        return 0
    if relevant_paths and not selected:
        report["status"] = "BLOCKED"
        report["selection_error"] = "relevant candidate changes produced an empty component selection"
        report_path.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "selection_error": report["selection_error"]}, sort_keys=True))
        return 1

    saw_blocked = False
    saw_failure = False
    with tempfile.TemporaryDirectory(prefix="round6-ci-") as tmp:
        temp = Path(tmp)
        for index, name in enumerate(selected, start=1):
            component_changes = {
                path for path in changed
                if _is_component_relevant(name, {path})
            }
            entry = inspect_component(name, root, component_changes)
            report["components"].append(entry)
            report["selected_paths"][name] = sorted({
                *component_changes,
                *entry["selected_paths"],
            })
            if entry["status"] != "READY_TO_RUN":
                saw_blocked = True
                continue
            if not entry["tests_to_run"]:
                entry["status"] = "BLOCKED"
                entry["blockers"].append("no candidate tests are available to execute")
                saw_blocked = True
                continue
            for test_index, test_file in enumerate(entry["tests_to_run"], start=1):
                junit = temp / f"{index:02d}-{name}-{test_index:02d}.xml"
                telemetry = temp / f"{index:02d}-{name}-{test_index:02d}.json"
                logs = temp / f"{index:02d}-{name}-{test_index:02d}-logs"
                cmd = [
                    sys.executable,
                    "scripts/run_tests_isolated.py",
                    "--root", ".",
                    "--batch-size", "1",
                    "--timeout-s", "120",
                    "--report", str(telemetry),
                    "--report-dir", str(logs),
                    f"--pytest-arg=--junitxml={junit}",
                    test_file,
                ]
                report["executed_commands"].append(cmd)
                execution: dict[str, Any] = {
                    "test_file": test_file,
                    "command": cmd,
                    "timeout": False,
                    "skipped": None,
                    "failed": None,
                    "errors": None,
                }
                try:
                    completed = subprocess.run(cmd, cwd=root, timeout=130, check=False)
                except subprocess.TimeoutExpired:
                    execution.update({"status": "TIMEOUT", "timeout": True, "failure_classification": "timeout"})
                    entry["executions"].append(execution)
                    entry["status"] = "FAIL"
                    saw_failure = True
                    continue
                execution["runner_exit_code"] = completed.returncode
                telemetry_ok = False
                telemetry_error = None
                if telemetry.is_file():
                    try:
                        batch_report = json.loads(telemetry.read_text(encoding="utf-8"))
                        batches = batch_report.get("batches", [])
                        execution["runner_batches"] = [b.get("status", "unknown") for b in batches]
                        summary = batch_report.get("summary", {})
                        telemetry_ok = (
                            batch_report.get("exit_code") == 0
                            and bool(batches)
                            and all(batch.get("status") == "passed" for batch in batches)
                            and summary.get("skipped_batches") == 0
                            and summary.get("failed_batches") == 0
                            and summary.get("timeout_batches") == 0
                        )
                    except (OSError, json.JSONDecodeError, AttributeError, TypeError) as exc:
                        telemetry_error = str(exc)
                execution["isolated_runner_telemetry_valid"] = telemetry_ok
                if telemetry_error:
                    execution["runner_telemetry_error"] = telemetry_error
                if junit.is_file():
                    try:
                        counts, cases = junit_details(junit)
                        execution.update({
                            "tests_collected": counts[0],
                            "skipped": counts[1],
                            "failed": counts[2],
                            "errors": counts[3],
                            "test_cases": cases,
                        })
                    except (ET.ParseError, OSError) as exc:
                        execution["junit_error"] = str(exc)
                has_junit = junit.is_file() and "junit_error" not in execution
                counts = (
                    execution.get("tests_collected", 0),
                    execution.get("skipped", 0),
                    execution.get("failed", 0),
                    execution.get("errors", 0),
                )
                passed = completed.returncode == 0 and telemetry_ok and has_junit and junit_status(counts) == "PASS"
                if passed:
                    execution["status"] = "PASS"
                    execution["failure_classification"] = None
                else:
                    execution["status"] = "FAIL"
                    execution["failure_classification"] = (
                        "test_or_collection_failure" if counts[2] or counts[3]
                        else "candidate_tests_skipped" if counts[1]
                        else "nonzero_runner_or_test_exit" if completed.returncode
                        else "missing_or_failed_runner_telemetry" if not telemetry_ok
                        else "missing_or_invalid_junit" if not has_junit
                        else "empty_test_collection"
                    )
                    saw_failure = True
                    entry["status"] = "FAIL"
                entry["executions"].append(execution)
            if entry["status"] == "READY_TO_RUN":
                entry["status"] = "PASS" if all(item["status"] == "PASS" for item in entry["executions"]) else "FAIL"

    report["status"] = "FAIL" if saw_failure else "BLOCKED" if saw_blocked else "PASS"

    report_path.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "components": report["components"]}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        return run(args.root, args.base, args.head, args.report)
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"Round 6 candidate test discovery failed closed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
