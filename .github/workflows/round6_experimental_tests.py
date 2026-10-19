"""Run changed Round 6 candidate suites against their checked-in implementations.

This helper is invoked only from the Required Checks workflow. It uses explicit
file mappings so a test-only PR cannot pass by skipping an import that is not
present on main. Every selected file runs in a fresh bounded pytest process.

Artifact-path checks protect the helper from following redirected report and
log paths. The isolated runner and pytest also receive temporary telemetry and
JUnit outputs. On Linux, report writers use pinned descriptor paths so replacing
the corresponding workspace pathname cannot redirect their write. Candidate
tests still run with the workflow job's OS permissions and can mutate files
they can access; this helper is not a security sandbox. The Windows local
fallback rejects observed reparse points and checks file identity after the
run, but cannot eliminate a concurrent check-then-open race.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

MAX_RUNNER_TELEMETRY_BYTES = 4 * 1024 * 1024
MAX_JUNIT_XML_BYTES = 32 * 1024 * 1024
MAX_RUNNER_STDERR_TAIL_BYTES = 4096


COMPONENTS: dict[str, dict[str, Any]] = {
    "planar_geometry": {
        "triggers": (
            "neurotopology_sim/experimental/geometry/",
            "tests/neurotopology_sim/experimental/geometry/",
            "tests/experimental/test_planar_triangulation.py",
            "tests/experimental/planar_mesh_test_helpers.py",
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
        "support_files": {
            "tests/experimental/planar_mesh_test_helpers.py": (
                "tests/experimental/test_planar_triangulation.py",
            ),
        },
        "implementation_roots": ("neurotopology_sim/experimental/geometry/",),
        "test_roots": ("tests/neurotopology_sim/experimental/geometry/", "tests/experimental/"),
        "candidate_test_roots": ("tests/neurotopology_sim/experimental/geometry/",),
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
            "tests/experimental/fixtures/spherical_csd_mne_1_13_2_reference.json",
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
        "support_files": {
            "tests/neurotopology_sim/experimental/preprocessing/fixtures/tetrahedron_csd_matrix_mne_1_13_2.json": (
                "tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py",
            ),
            "tests/neurotopology_sim/experimental/preprocessing/fixtures/tetrahedron_csd_matrix_mne_1_13_2.npy": (
                "tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py",
            ),
            "tests/experimental/fixtures/spherical_csd_mne_1_13_2_reference.json": (
                "tests/experimental/test_spherical_csd_parity.py",
            ),
            "tests/mne_csd_reference_audit/conftest.py": (
                "tests/mne_csd_reference_audit/test_kkt_operator.py",
                "tests/mne_csd_reference_audit/test_legendre_constants.py",
                "tests/mne_csd_reference_audit/test_isolation_and_pin.py",
                "tests/mne_csd_reference_audit/test_mne_integration_optional.py",
            ),
        },
        "implementation_roots": ("neurotopology_sim/experimental/preprocessing/", "tools/mne_csd_reference_audit/"),
        "test_roots": ("tests/neurotopology_sim/experimental/preprocessing/", "tests/experimental/", "tests/mne_csd_reference_audit/"),
        "candidate_test_roots": (
            "tests/neurotopology_sim/experimental/preprocessing/",
            "tests/mne_csd_reference_audit/",
        ),
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
        "implementation_roots": ("physics/eeg_forward/", "tools/experimental_audits/four_shell_bvp_oracle.py"),
        "test_roots": ("tests/physics/eeg_forward/", "tests/physics/test_four_sphere_oracle.py", "tests/experimental_audits/"),
        "candidate_test_roots": ("tests/physics/eeg_forward/", "tests/physics/test_four_sphere_oracle.py"),
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
            "tests/surrogate_nulls/test_adversarial_contracts.py",
        ),
        "module_imports": {
            "tools.surrogate_nulls.nulls": "tools/surrogate_nulls/nulls.py",
            "tools.surrogate_nulls.spectral": "tools/surrogate_nulls/spectral.py",
            "tools.surrogate_nulls.csd": "tools/surrogate_nulls/csd.py",
        },
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
            {"implementation": "tools/surrogate_nulls/nulls.py", "test": "tests/surrogate_nulls/test_adversarial_contracts.py"},
            {"implementation": "tools/surrogate_nulls/spectral.py", "test": "tests/surrogate_nulls/test_adversarial_contracts.py"},
            {"implementation": "tools/surrogate_nulls/csd.py", "test": "tests/surrogate_nulls/test_adversarial_contracts.py"},
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
        "support_files": {
            "tests/surrogate_audit/fixtures.py": (
                "tests/surrogate_audit/test_mv_fpr.py",
                "tests/surrogate_audit/test_mv_iaaft.py",
                "tests/surrogate_audit/test_invalid_inputs.py",
            ),
        },
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
        # tests/experimental is shared by unrelated suites; only its explicitly
        # mapped ROC file belongs to this lane.
        "candidate_test_roots": ("tests/neurotopology_sim/experimental/benchmarks/",),
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
        "support_files": {
            "tests/tools/batch3_provenance_join/helpers.py": (
                "tests/tools/batch3_provenance_join/test_audit.py",
                "tests/tools/batch3_provenance_join/test_safety_and_cycles.py",
            ),
        },
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
        "candidate_test_roots": ("tests/experimental_audits/test_winding_charge_round6_oracle.py",),
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
    "docker_context_policy": {
        "triggers": (
            ".dockerignore",
            "tests/docker_context/",
        ),
        "implementation": ".dockerignore",
        "tests": (
            "tests/docker_context/test_build_context_policy.py",
            "tests/docker_context/test_docker_engine_build_context.py",
        ),
        "candidate_pairs": (
            {"implementation": ".dockerignore", "test": "tests/docker_context/test_build_context_policy.py"},
            {"implementation": ".dockerignore", "test": "tests/docker_context/test_docker_engine_build_context.py"},
        ),
        "implementation_roots": (".dockerignore",),
        "test_roots": ("tests/docker_context/",),
        "candidate_test_roots": ("tests/docker_context/",),
    },
    "bids_inventory_audit": {
        "triggers": (
            "shared/bids_inventory_audit/",
            "tests/bids_inventory_audit/",
        ),
        "implementation_any": (
            "shared/bids_inventory_audit/checksum.py",
            "shared/bids_inventory_audit/findings.py",
            "shared/bids_inventory_audit/inventory.py",
            "shared/bids_inventory_audit/license.py",
            "shared/bids_inventory_audit/manifest.py",
            "shared/bids_inventory_audit/paths.py",
            "shared/bids_inventory_audit/schema.py",
            "shared/bids_inventory_audit/tsv.py",
        ),
        "tests": (
            "tests/bids_inventory_audit/test_analysis_record.py",
            "tests/bids_inventory_audit/test_bids_paths.py",
            "tests/bids_inventory_audit/test_boundary_guards.py",
            "tests/bids_inventory_audit/test_checksum_boundary.py",
            "tests/bids_inventory_audit/test_inventory_audit.py",
            "tests/bids_inventory_audit/test_license_reconciliation.py",
            "tests/bids_inventory_audit/test_license_sources.py",
            "tests/bids_inventory_audit/test_listing_digest.py",
            "tests/bids_inventory_audit/test_privacy_boundary.py",
            "tests/bids_inventory_audit/test_registration_scope.py",
            "tests/bids_inventory_audit/test_tsv_parsing.py",
        ),
        "candidate_pairs": (
            {"implementation": "shared/bids_inventory_audit/checksum.py", "test": "tests/bids_inventory_audit/test_checksum_boundary.py"},
            {"implementation": "shared/bids_inventory_audit/checksum.py", "test": "tests/bids_inventory_audit/test_listing_digest.py"},
            {"implementation": "shared/bids_inventory_audit/findings.py", "test": "tests/bids_inventory_audit/test_analysis_record.py"},
            {"implementation": "shared/bids_inventory_audit/findings.py", "test": "tests/bids_inventory_audit/test_inventory_audit.py"},
            {"implementation": "shared/bids_inventory_audit/inventory.py", "test": "tests/bids_inventory_audit/test_inventory_audit.py"},
            {"implementation": "shared/bids_inventory_audit/inventory.py", "test": "tests/bids_inventory_audit/test_registration_scope.py"},
            {"implementation": "shared/bids_inventory_audit/license.py", "test": "tests/bids_inventory_audit/test_license_reconciliation.py"},
            {"implementation": "shared/bids_inventory_audit/license.py", "test": "tests/bids_inventory_audit/test_license_sources.py"},
            {"implementation": "shared/bids_inventory_audit/manifest.py", "test": "tests/bids_inventory_audit/test_analysis_record.py"},
            {"implementation": "shared/bids_inventory_audit/manifest.py", "test": "tests/bids_inventory_audit/test_inventory_audit.py"},
            {"implementation": "shared/bids_inventory_audit/paths.py", "test": "tests/bids_inventory_audit/test_bids_paths.py"},
            {"implementation": "shared/bids_inventory_audit/paths.py", "test": "tests/bids_inventory_audit/test_boundary_guards.py"},
            {"implementation": "shared/bids_inventory_audit/paths.py", "test": "tests/bids_inventory_audit/test_privacy_boundary.py"},
            {"implementation": "shared/bids_inventory_audit/schema.py", "test": "tests/bids_inventory_audit/test_analysis_record.py"},
            {"implementation": "shared/bids_inventory_audit/schema.py", "test": "tests/bids_inventory_audit/test_registration_scope.py"},
            {"implementation": "shared/bids_inventory_audit/inventory.py", "test": "tests/bids_inventory_audit/test_privacy_boundary.py"},
            {"implementation": "shared/bids_inventory_audit/tsv.py", "test": "tests/bids_inventory_audit/test_tsv_parsing.py"},
            {"implementation": "shared/bids_inventory_audit/tsv.py", "test": "tests/bids_inventory_audit/test_privacy_boundary.py"},
        ),
        "support_files": {
            "tests/bids_inventory_audit/conftest.py": (
                "tests/bids_inventory_audit/test_analysis_record.py",
                "tests/bids_inventory_audit/test_bids_paths.py",
                "tests/bids_inventory_audit/test_boundary_guards.py",
                "tests/bids_inventory_audit/test_checksum_boundary.py",
                "tests/bids_inventory_audit/test_inventory_audit.py",
                "tests/bids_inventory_audit/test_license_reconciliation.py",
                "tests/bids_inventory_audit/test_license_sources.py",
                "tests/bids_inventory_audit/test_listing_digest.py",
                "tests/bids_inventory_audit/test_privacy_boundary.py",
                "tests/bids_inventory_audit/test_registration_scope.py",
                "tests/bids_inventory_audit/test_tsv_parsing.py",
            ),
        },
        "implementation_roots": ("shared/bids_inventory_audit/",),
        "test_roots": ("tests/bids_inventory_audit/",),
        "candidate_test_roots": ("tests/bids_inventory_audit/",),
    },
    "finite_jitter_geometry_audit": {
        "triggers": (
            "tools/audit_finite_jitter_triangulation.py",
            "tests/test_finite_jitter_triangulation_audit.py",
        ),
        "implementation": "tools/audit_finite_jitter_triangulation.py",
        "tests": ("tests/test_finite_jitter_triangulation_audit.py",),
        "candidate_pairs": (
            {
                "implementation": "tools/audit_finite_jitter_triangulation.py",
                "test": "tests/test_finite_jitter_triangulation_audit.py",
            },
        ),
        "implementation_roots": ("tools/audit_finite_jitter_triangulation.py",),
        "candidate_test_roots": ("tests/test_finite_jitter_triangulation_audit.py",),
    },
}


# Package initializers are executable import surfaces, not automatic exemptions.
# These exact paths are mapped to the registered tests for their component.
# A newly added initializer under a candidate root remains unmapped and blocks.
PACKAGE_INITIALIZER_SUPPORT_PATHS: dict[str, tuple[str, ...]] = {
    "planar_geometry": (
        "neurotopology_sim/experimental/geometry/__init__.py",
        "tests/experimental/__init__.py",
        "tests/neurotopology_sim/__init__.py",
        "tests/neurotopology_sim/experimental/__init__.py",
        "tests/neurotopology_sim/experimental/geometry/__init__.py",
    ),
    "hodge_2d": (
        "experimental/phase_cochain_reference/__init__.py",
        "tests/experimental/phase_cochain_reference/__init__.py",
        "tools/hodge_decomposition_audit/__init__.py",
        "tests/tools/hodge_decomposition_audit/__init__.py",
        "neurotopology_sim/experimental/topology/__init__.py",
        "tests/neurotopology_sim/experimental/topology/__init__.py",
    ),
    "spherical_csd": (
        "neurotopology_sim/experimental/preprocessing/__init__.py",
        "tests/neurotopology_sim/experimental/preprocessing/__init__.py",
        "tools/mne_csd_reference_audit/__init__.py",
        "tests/mne_csd_reference_audit/__init__.py",
    ),
    "four_sphere": (
        "physics/eeg_forward/__init__.py",
        "tests/physics/eeg_forward/__init__.py",
        "tests/experimental_audits/__init__.py",
        "tools/experimental_audits/__init__.py",
    ),
    "phase_winding": (
        "neurotopology_sim/__init__.py",
        "neurotopology_sim/experimental/__init__.py",
        "neurotopology_sim/experimental/topology/__init__.py",
        "tests/neurotopology_sim/__init__.py",
        "tests/neurotopology_sim/experimental/__init__.py",
        "tests/neurotopology_sim/experimental/topology/__init__.py",
    ),
    "surrogate_nulls": (
        "tools/surrogate_nulls/__init__.py",
        "tests/surrogate_nulls/__init__.py",
    ),
    "phase_uncertainty": (
        "tools/phase_uncertainty/__init__.py",
        "tests/phase_uncertainty/__init__.py",
    ),
    "surrogate_audit": (
        "tools/surrogate_audit/__init__.py",
        "tests/surrogate_audit/__init__.py",
    ),
    "synthetic_roc": (
        "neurotopology_sim/__init__.py",
        "neurotopology_sim/experimental/__init__.py",
        "neurotopology_sim/experimental/benchmarks/__init__.py",
        "tests/neurotopology_sim/__init__.py",
        "tests/neurotopology_sim/experimental/__init__.py",
        "tests/neurotopology_sim/experimental/benchmarks/__init__.py",
    ),
    "report_firewall": (
        "tools/batch3_report_firewall/__init__.py",
        "tests/tools/batch3_report_firewall/__init__.py",
    ),
    "provenance_join": (
        "tools/batch3_provenance_join/__init__.py",
        "tests/tools/batch3_provenance_join/__init__.py",
    ),
    "topology_backend_conformance": (
        "tools/topology_backend_conformance/__init__.py",
        "tests/topology_backend_conformance/__init__.py",
    ),
    "finite_chain_audit": (
        "tools/batch2_chain_complex_audit/__init__.py",
        "tests/batch2_chain_complex_audit/__init__.py",
    ),
    "winding_charge_audit": (
        "tools/experimental_audits/__init__.py",
        "tests/experimental_audits/__init__.py",
        "tools/experimental_audits/winding_charge_round6/__init__.py",
    ),
    "dmd_crouzeix": (
        "neurotopology_sim/experimental/dynamics/__init__.py",
        "tests/dmd_crouzeix_contract/__init__.py",
        "tests/experimental/__init__.py",
    ),
    "bids_inventory_audit": (
        "shared/bids_inventory_audit/__init__.py",
        "tests/bids_inventory_audit/__init__.py",
    ),
}
for _component_name, _initializer_paths in PACKAGE_INITIALIZER_SUPPORT_PATHS.items():
    _component_spec = COMPONENTS[_component_name]
    _initializer_tests = tuple(dict.fromkeys(
        pair["test"] for pair in _component_spec.get("candidate_pairs", ())
    ))
    _component_spec["package_initializers"] = {
        _initializer_path: _initializer_tests
        for _initializer_path in _initializer_paths
    }


# These PR numbers identify implementation/test provenance for registered
# pairs, including merged implementation PRs and open independent-test PRs.
# They are ownership evidence, not approval or merge state.
COMPONENT_OWNER_PRS = {
    "planar_geometry": (416, 421),
    "hodge_2d": (423, 396, 385),
    "spherical_csd": (414, 419, 402),
    "four_sphere": (418, 409),
    "phase_winding": (413,),
    "surrogate_nulls": (417, 430),
    "phase_uncertainty": (403,),
    "surrogate_audit": (398,),
    "synthetic_roc": (426, 427),
    "simulation_grid_planner": (424,),
    "report_firewall": (390,),
    "provenance_join": (392,),
    "topology_backend_conformance": (389,),
    "finite_chain_audit": (397,),
    "winding_charge_audit": (399,),
    "dmd_crouzeix": (415, 420),
    "docker_context_policy": (431, 434),
    "bids_inventory_audit": (401,),
    "finite_jitter_geometry_audit": (410,),
}


# Known candidate suites in the live open-PR inventory that do not yet have a
# reviewed implementation/test pair. Explicit pair/support mappings override
# these guard roots; any other changed Python source/test path under a guard
# root blocks discovery until an owner registers a pair. Such changes are never
# silently classified NOT_APPLICABLE.
UNMAPPED_CANDIDATE_ROOTS = (
    "sim/nuisance_scenarios/",
    "tests/nuisance_scenarios/",
    "tools/whitening_audit/",
    "tests/whitening_audit/",
    "adapters/mne_csd/",
    "tests/adapters/mne_csd/",
    "adapters/mne_signal_blocks/",
    "tests/adapters/mne_signal_blocks/",
    "tools/moabb_protocol_conformance/",
    "tests/tools/moabb_protocol_conformance/",
    "tools/higher_order_runtime/",
    "tests/higher_order_runtime_contract/",
    "dual_engine/forward_model_contract.py",
    "tests/forward_model_contract/",
    "tools/synthetic_pipeline_replay/",
    "tests/integration/synthetic_pipeline_replay/",
    "tools/batch3_offline_integration/",
    "tests/tools/batch3_offline_integration/",
    "tools/benchmarks/batch2_pipeline/",
    "tests/benchmarks/batch2_pipeline/",
    "tools/release_readiness/batch2_security/",
    "tests/release_readiness/batch2_security/",
    "shared/bids_inventory_audit/",
    "tests/bids_inventory_audit/",
    "data/bids_ingest.py",
    "data/dandi_nwb_ingest.py",
    "tests/data_access/bids_adapter/",
    "tests/data_access/dandi_nwb_bounded/",
    "tools/streaming/base_runner.py",
    "tests/streaming/",
    "tests/performance/streaming_optimization/",
    "tools/export_ds005620_evidence_packet.py",
    "tests/btc_icft/test_ds005620_evidence_packet.py",
    "data/openneuro_loader.py",
    "tools/stream_process_dandi000458.py",
    "tools/stream_pitnn_cohort_ds005620.py",
    "tests/test_pitnn_cohort_ds005620.py",
    "tests/dmd_ep2_oracle/",
    "scripts/audit_round6_whitening.py",
    "scripts/run_batch2_security_audit.py",
    "scripts/benchmark_batch2_pipeline.py",
    "scripts/run_batch3_offline_integration.py",
    # Open PR test gaps outside the currently assigned experimental pairs.
    "tests/research/batch3/test_dataset_metadata_audit.py",  # PR #411
    "tests/oss_compat/test_compatibility_inventory.py",  # PR #406
    "tests/research/batch3/test_replication_dataset_feasibility.py",  # PR #394
    "tests/research/batch3/test_claim_matrix.py",  # PR #393
    "tools/public_repo_harvest/",
    "tests/tools/test_public_repo_harvest_source_pack.py",  # PR #391
    "oss_opportunities/",
    "tests/test_oss_adoption_gates.py",  # PR #386
    "shared/measurement_hypothesis/",
    "tests/measurement_hypothesis/",  # PR #384
    "tools/research_plan_quality_eval/",
    "tests/research_plan_quality_eval/",  # PR #383
    "tests/source_mining_integration/",  # PR #382
    "configs/scientific_falsification/batch3_falsification_matrix.yaml",
    "tests/scientific_falsification/test_batch3_falsification_matrix.py",  # PR #376
    "configs/research/batch3_source_registry.yaml",
    "tests/research/test_batch3_source_registry.py",  # PR #375
    "dual_engine/fusion_validation.py",
    "tests/test_fusion_null_models.py",
    "tests/test_fusion_validation.py",  # PR #374
    "sciencer_d/btc_icft/level_t/base_real_topology.py",
    "tests/test_base_real_topology_missingness.py",
    "tests/test_cohort_missingness.py",  # PR #373
    "tools/higher_order_integration/",
    "tests/higher_order_integration/",  # PR #357
    "analysis/empirical_higher_order/",
    "tests/empirical_higher_order/",
    "analysis/transition_forecasting/",
    "tests/transition_forecasting/",
    "tests/research_claim_gate/",
    "tests/literature_evidence/",
    "tests/release_manifest/",
    "tests/science_contracts/",
    "tests/test_bayesian_falsification_consumers.py",
    "tests/test_bayesian_falsification_hardening.py",
    "tests/test_falsification_artifact_semantics.py",
    "tests/test_bids_provenance.py",
    "tests/test_dandi_nwb_ingest.py",
    "tests/test_fetch_ds000245.py",
    "tests/test_test_isolation.py",
    "shared/data_loaders/physiology_stream.py",
    "tests/data_loaders/",
    "sciencer_d/btc_icft/level_m/dandi000458_windows_real.py",
    "tools/data_access/policy_enforcement/",
    "tests/data_access/policy_enforcement/",
    "tests/data_access/legacy_migration_streaming/",
    "sim/pitnn/api_bridge.py",
    "sim/pitnn/bayesian_falsification.py",
    "tests/simulation_execution/",
    "tests/research_cycle_preflight/",
    "tests/research_cycle_release/",
    "tests/integration_reconciliation/",
    "scripts/build_release_manifest.py",
    "scripts/run_registered_fhn.py",
    "scripts/validate_research_cycle_preflight.py",
)


def normalize_repo_path(path: str) -> str:
    """Normalize Git's POSIX paths and Windows-style test inputs consistently."""
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _lexically_contained_path(root: Path, path: Path, label: str) -> Path:
    """Normalize a path without resolving links, and require it to be below root."""
    resolved_root = root.resolve()
    candidate = path if path.is_absolute() else resolved_root / path
    lexical = Path(os.path.abspath(candidate))
    try:
        relative = lexical.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"{label} must remain inside the checked-out repository") from exc
    if any(part in {".", ".."} for part in relative.parts):
        raise ValueError(f"{label} must use a normalized path below the checked-out repository")
    return lexical


def _is_reparse_path(path: Path) -> bool:
    """Return whether an existing path component is a symlink or Windows junction."""
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction()) if callable(is_junction) else False


def _contained_path(root: Path, path: Path, label: str) -> Path:
    """Resolve symlinks and reject paths that escape the checked-out repository."""
    resolved_root = root.resolve()
    candidate = path if path.is_absolute() else resolved_root / path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"{label} must remain inside the checked-out repository") from exc
    return resolved


def _open_contained_file(
    root: Path, path: Path, flags: int, label: str, *, mode: int = 0o600
) -> int:
    """Open a regular-file candidate without following path components on POSIX."""
    resolved_root = root.resolve()
    lexical = _lexically_contained_path(resolved_root, path, label)
    relative = lexical.relative_to(resolved_root)
    if not relative.parts or any(part in {".", ".."} for part in relative.parts):
        raise ValueError(f"{label} must name a file below the checked-out repository")

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    supports_dir_fd = os.open in getattr(os, "supports_dir_fd", set())
    if os.name != "nt" and nofollow and directory and supports_dir_fd:
        parent_fd = os.open(
            os.fspath(resolved_root), os.O_RDONLY | directory | nofollow
        )
        try:
            for part in relative.parts[:-1]:
                next_fd = os.open(
                    part, os.O_RDONLY | directory | nofollow, dir_fd=parent_fd
                )
                os.close(parent_fd)
                parent_fd = next_fd
            return os.open(relative.parts[-1], flags | nofollow, mode, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)

    # Windows does not expose openat/dir_fd. Reject every existing link/reparse
    # component before resolving and containing the candidate. This is a
    # best-effort check on Windows; POSIX CI uses descriptor-relative no-follow.
    probe = resolved_root
    for part in relative.parts:
        probe = probe / part
        if _is_reparse_path(probe):
            raise ValueError(f"{label} must not traverse a symlink or reparse point")
    resolved = _contained_path(resolved_root, lexical, label)
    return os.open(
        os.fspath(resolved), flags | nofollow | getattr(os, "O_BINARY", 0), mode
    )


def _ensure_contained_directories(root: Path, path: Path, label: str) -> None:
    """Create a contained directory path without traversing links where supported."""
    resolved_root = root.resolve()
    lexical = _lexically_contained_path(resolved_root, path, label)
    relative = lexical.relative_to(resolved_root)
    if not relative.parts:
        return

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    supports_dir_fd = os.open in getattr(os, "supports_dir_fd", set())
    if os.name != "nt" and nofollow and directory and supports_dir_fd:
        parent_fd = os.open(
            os.fspath(resolved_root), os.O_RDONLY | directory | nofollow
        )
        try:
            for part in relative.parts:
                try:
                    next_fd = os.open(
                        part, os.O_RDONLY | directory | nofollow, dir_fd=parent_fd
                    )
                except FileNotFoundError:
                    os.mkdir(part, mode=0o700, dir_fd=parent_fd)
                    next_fd = os.open(
                        part, os.O_RDONLY | directory | nofollow, dir_fd=parent_fd
                    )
                os.close(parent_fd)
                parent_fd = next_fd
        finally:
            os.close(parent_fd)
        return

    current = resolved_root
    for part in relative.parts:
        current = current / part
        if _is_reparse_path(current):
            raise ValueError(f"{label} must not traverse a symlink or reparse point")
        try:
            current.mkdir()
        except FileExistsError:
            pass
        if _is_reparse_path(current) or not current.is_dir():
            raise ValueError(f"{label} contains a non-directory or linked path component")


def _prepare_contained_output(root: Path, path: Path, label: str) -> tuple[int, int]:
    """Safely create/truncate a report file and return its pinned file identity."""
    lexical = _lexically_contained_path(root, path, label)
    _ensure_contained_directories(root, lexical.parent, f"{label} parent directory")
    fd = _open_contained_file(
        root, lexical, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, label, mode=0o600
    )
    try:
        opened = _assert_regular_file(fd, label)
        return opened.st_dev, opened.st_ino
    finally:
        os.close(fd)


def _supports_pinned_output_transport() -> bool:
    """Whether child report writers can address parent-pinned descriptors."""
    return os.name == "posix" and Path("/proc/self/fd").is_dir()


def _proc_fd_path(fd: int, *, pid: int | None = None) -> str:
    """Return a Linux procfs path to an already-open descriptor."""
    if type(fd) is not int or fd < 0:
        raise ValueError("file descriptor must be a non-negative integer")
    if pid is None:
        return f"/proc/self/fd/{fd}"
    if type(pid) is not int or pid <= 0:
        raise ValueError("process id must be a positive integer")
    return f"/proc/{pid}/fd/{fd}"


def _read_pinned_output_bytes(fd: int, label: str, *, max_bytes: int) -> bytes:
    """Read a size-bounded report from its pinned descriptor, independent of its pathname."""
    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")
    before = _assert_regular_file(fd, label)
    if before.st_size > max_bytes:
        raise ValueError(f"{label} exceeds the {max_bytes}-byte limit")
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = max_bytes + 1
    while remaining:
        chunk = os.read(fd, min(1024 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    content = b"".join(chunks)
    after = _assert_regular_file(fd, label)
    if len(content) > max_bytes or after.st_size != before.st_size or len(content) != after.st_size:
        raise ValueError(f"{label} changed while its bounded contents were read")
    return content


def _assert_contained_path_identity(
    root: Path, path: Path, label: str, expected_identity: tuple[int, int]
) -> None:
    """Verify the original pathname still names the pinned regular file."""
    fd = _open_contained_file(root, path, os.O_RDONLY, label)
    try:
        opened = _assert_regular_file(fd, label)
        if (opened.st_dev, opened.st_ino) != expected_identity:
            raise ValueError(f"{label} was replaced during candidate execution")
    finally:
        os.close(fd)


def _close_open_fds(file_descriptors: list[int]) -> None:
    """Close and clear a small per-test set of pinned output descriptors."""
    for fd in file_descriptors:
        try:
            os.close(fd)
        except OSError:
            pass
    file_descriptors.clear()


def _assert_regular_file(fd: int, label: str) -> os.stat_result:
    opened = os.fstat(fd)
    if not stat.S_ISREG(opened.st_mode) or not opened.st_ino:
        raise ValueError(f"{label} is not a verifiable regular file")
    return opened


def _read_contained_bytes(
    root: Path,
    path: Path,
    label: str,
    *,
    max_bytes: int,
    expected_identity: tuple[int, int] | None = None,
) -> bytes:
    """Read a size-bounded file through a descriptor opened beneath the root."""
    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")
    fd = _open_contained_file(root, path, os.O_RDONLY, label)
    try:
        opened = _assert_regular_file(fd, label)
        if expected_identity is not None and (opened.st_dev, opened.st_ino) != expected_identity:
            raise ValueError(f"{label} was replaced during candidate execution")
        if opened.st_size > max_bytes:
            raise ValueError(f"{label} exceeds the {max_bytes}-byte read limit")
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            content = stream.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ValueError(f"{label} grew beyond the {max_bytes}-byte read limit")
        return content
    finally:
        if fd >= 0:
            os.close(fd)


def _read_contained_tail_text(root: Path, path: Path, label: str, *, tail_bytes: int) -> str:
    """Read only a bounded trailing diagnostic window from a contained log."""
    if tail_bytes < 0:
        raise ValueError("tail_bytes must be non-negative")
    fd = _open_contained_file(root, path, os.O_RDONLY, label)
    try:
        opened = _assert_regular_file(fd, label)
        start = max(0, opened.st_size - tail_bytes)
        os.lseek(fd, start, os.SEEK_SET)
        content = os.read(fd, tail_bytes + 1)
        if len(content) > tail_bytes:
            raise ValueError(f"{label} changed while its bounded tail was read")
        return content.decode("utf-8", errors="replace")
    finally:
        os.close(fd)


def _write_contained_text(
    root: Path,
    path: Path,
    content: str,
    label: str,
    expected_identity: tuple[int, int],
) -> None:
    """Write through a pre-created, identity-pinned file, never through a new symlink."""
    fd = _open_contained_file(root, path, os.O_WRONLY, label)
    try:
        opened = _assert_regular_file(fd, label)
        if (opened.st_dev, opened.st_ino) != expected_identity:
            raise ValueError(f"{label} was replaced during candidate execution")
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        payload = content.encode("utf-8")
        offset = 0
        while offset < len(payload):
            offset += os.write(fd, payload[offset:])
    finally:
        os.close(fd)


def _trigger_matches(path: str, trigger: str) -> bool:
    path = normalize_repo_path(path).casefold()
    trigger = normalize_repo_path(trigger).casefold()
    return path == trigger or trigger.endswith("/") and path.startswith(trigger)


def _path_in_root(path: str, root: str) -> bool:
    path = normalize_repo_path(path).casefold()
    root = normalize_repo_path(root).casefold()
    return path.startswith(root) if root.endswith("/") else path == root


def _case_mismatched_known_paths(changed_paths: set[str], known_paths: set[str]) -> list[str]:
    """Return changed paths that only match a registered path by case-folding."""
    known_by_casefold: dict[str, set[str]] = {}
    for known_path in known_paths:
        normalized = normalize_repo_path(known_path)
        known_by_casefold.setdefault(normalized.casefold(), set()).add(normalized)
    return sorted(
        normalized
        for original in changed_paths
        if (normalized := normalize_repo_path(original)) not in known_by_casefold.get(normalized.casefold(), set())
        and normalized.casefold() in known_by_casefold
    )


_DOCUMENTATION_SUFFIXES = {".md", ".mdx", ".rst", ".adoc"}


def _is_candidate_file(path: str, roots: tuple[str, ...], explicit_paths: set[str] | None = None) -> bool:
    """Treat files under candidate roots as inputs unless they are documentation."""
    normalized = normalize_repo_path(path)
    if explicit_paths and normalized.casefold() in explicit_paths:
        return True
    if not any(_path_in_root(normalized, root) for root in roots):
        return False
    return Path(normalized).suffix.casefold() not in _DOCUMENTATION_SUFFIXES


def _is_component_relevant(
    name: str,
    changed_paths: set[str],
    *,
    include_package_initializers: bool = True,
) -> bool:
    spec = COMPONENTS[name]
    if any(
        _trigger_matches(path, trigger)
        for path in changed_paths
        for trigger in spec["triggers"]
    ):
        return True
    mapped = {
        normalize_repo_path(path).casefold()
        for pair in spec.get("candidate_pairs", ())
        for path in (pair["implementation"], pair["test"])
    }
    mapped.update(normalize_repo_path(path).casefold() for path in spec.get("support_files", {}))
    if include_package_initializers:
        mapped.update(normalize_repo_path(path).casefold() for path in spec.get("package_initializers", {}))
    return any(normalize_repo_path(path).casefold() in mapped for path in changed_paths)


def select_components(changed_paths: set[str]) -> list[str]:
    """Return deterministic component names touched by source or test changes."""
    changed_casefold = {
        normalize_repo_path(path).casefold() for path in changed_paths
    }
    direct = {
        name for name in COMPONENTS
        if _is_component_relevant(
            name, changed_paths, include_package_initializers=False
        )
    }
    initializer_owners = {
        name
        for name, spec in COMPONENTS.items()
        if changed_casefold
        & {
            normalize_repo_path(initializer).casefold()
            for initializer in spec.get("package_initializers", {})
        }
    }
    # Shared package initializers can sit above several experimental
    # components. When a PR changes an actual registered implementation/test,
    # select that directly changed component instead of blocking it on
    # unrelated candidate pairs that exist only on other open PR branches.
    # An initializer-only change remains fail-closed by selecting its explicit
    # owners; inspect_component will require an available implementation/test.
    selected = direct if direct else initializer_owners
    return [name for name in COMPONENTS if name in selected]


def _changed_candidate_paths(spec: dict[str, Any], changed_paths: set[str]) -> list[str]:
    pairs = spec.get("candidate_pairs", ())
    globally_registered_paths = {
        normalize_repo_path(path).casefold()
        for candidate_spec in COMPONENTS.values()
        for pair in candidate_spec.get("candidate_pairs", ())
        for path in (pair["implementation"], pair["test"])
    } | {
        normalize_repo_path(path).casefold()
        for candidate_spec in COMPONENTS.values()
        for path in (
            *candidate_spec.get("support_files", {}).keys(),
            *candidate_spec.get("package_initializers", {}).keys(),
        )
    }
    known = {
        normalize_repo_path(path).casefold()
        for pair in pairs
        for path in (pair["implementation"], pair["test"])
    }
    support_paths = {
        normalize_repo_path(path).casefold()
        for path in spec.get("support_files", {})
    }
    package_initializer_paths = {
        normalize_repo_path(path).casefold()
        for path in spec.get("package_initializers", {})
    }
    mapped_support_paths = support_paths | package_initializer_paths
    known.update(support_paths)
    known.update(package_initializer_paths)
    known_exact = {
        normalize_repo_path(path)
        for pair in pairs
        for path in (pair["implementation"], pair["test"])
    } | {normalize_repo_path(path) for path in mapped_support_paths}
    unmapped = _case_mismatched_known_paths(changed_paths, known_exact)
    for original in changed_paths:
        path = normalize_repo_path(original)
        lower = path.casefold()
        in_candidate_root = lower in mapped_support_paths or any(
            _path_in_root(path, root)
            for root in (*spec.get("implementation_roots", ()), *spec.get("candidate_test_roots", spec.get("test_roots", ())))
        )
        if not in_candidate_root or not _is_candidate_file(
            path, tuple((*spec.get("implementation_roots", ()), *spec.get("candidate_test_roots", spec.get("test_roots", ())))),
            mapped_support_paths,
        ):
            continue
        is_test = path.rsplit("/", 1)[-1].startswith("test_")
        is_package_initializer = path.rsplit("/", 1)[-1] == "__init__.py"
        if (
            is_test
            or is_package_initializer
            or lower in mapped_support_paths
            or any(_path_in_root(path, root) for root in spec.get("implementation_roots", ()))
        ):
            if lower not in known:
                # Broad roots can overlap independent registered components
                # (for example, a shared topology package). A path explicitly
                # owned by another component is validated by that component;
                # it is not an unmapped addition to this one.
                if lower in globally_registered_paths and path not in unmapped:
                    continue
                unmapped.append(path)
    return sorted(unmapped)


def _unmapped_candidate_paths(changed_paths: set[str]) -> list[str]:
    """Fail closed on candidate paths without an explicit pair/support mapping."""
    unmapped = []
    registered_roots = tuple(
        root
        for spec in COMPONENTS.values()
        for root in (*spec.get("implementation_roots", ()), *spec.get("candidate_test_roots", spec.get("test_roots", ())))
    )
    mapped_paths = {
        normalize_repo_path(candidate)
        for spec in COMPONENTS.values()
        for pair in spec.get("candidate_pairs", ())
        for candidate in (pair["implementation"], pair["test"])
    } | {
        normalize_repo_path(candidate)
        for spec in COMPONENTS.values()
        for candidate in spec.get("support_files", {})
    } | {
        normalize_repo_path(candidate)
        for spec in COMPONENTS.values()
        for candidate in spec.get("package_initializers", {})
    }
    mapped_paths_casefold = {path.casefold() for path in mapped_paths}
    guard_roots = tuple(UNMAPPED_CANDIDATE_ROOTS)
    mapped_case_mismatches = set(_case_mismatched_known_paths(changed_paths, mapped_paths))
    explicit_guard_files = {
        normalize_repo_path(root).casefold()
        for root in guard_roots
        if not normalize_repo_path(root).endswith("/")
    }
    for original in changed_paths:
        path = normalize_repo_path(original)
        belongs_to_registered_root = _is_candidate_file(path, registered_roots, mapped_paths_casefold)
        belongs_to_unmapped_candidate_root = _is_candidate_file(
            path, guard_roots, explicit_guard_files
        )
        mapped = path.casefold() in mapped_paths_casefold
        if (
            path in mapped_case_mismatches
            or belongs_to_unmapped_candidate_root and not mapped
            or belongs_to_registered_root and not mapped
        ):
            unmapped.append(path)
    return sorted(unmapped)


def inspect_component(
    name: str,
    root: Path,
    changed_paths: set[str] | None = None,
    *,
    require_all_pairs: bool = False,
) -> dict[str, Any]:
    """Require a concrete implementation/test pair for every selected candidate path."""
    spec = COMPONENTS[name]
    pairs = list(spec.get("candidate_pairs", ()))
    changes = {normalize_repo_path(path).casefold() for path in (changed_paths or set())}
    unmapped = _changed_candidate_paths(spec, changed_paths or set())
    selected_pairs = list(pairs) if require_all_pairs else [
        pair for pair in pairs
        if normalize_repo_path(pair["test"]).casefold() in changes
    ]
    changed_sources = {
        normalize_repo_path(pair["implementation"]).casefold()
        for pair in pairs
        if normalize_repo_path(pair["implementation"]).casefold() in changes
    }
    selected_pair_ids = {
        (pair["implementation"], pair["test"]) for pair in selected_pairs
    }
    changed_support_tests = {
        normalize_repo_path(test).casefold()
        for support_path, mapped_tests in spec.get("support_files", {}).items()
        if normalize_repo_path(support_path).casefold() in changes
        for test in mapped_tests
    }
    changed_initializer_tests = {
        normalize_repo_path(test).casefold()
        for initializer_path, mapped_tests in spec.get("package_initializers", {}).items()
        if normalize_repo_path(initializer_path).casefold() in changes
        for test in mapped_tests
    }
    selected_pairs.extend(
        pair for pair in pairs
        if normalize_repo_path(pair["test"]).casefold() in changed_support_tests | changed_initializer_tests
        and (pair["implementation"], pair["test"]) not in selected_pair_ids
    )
    selected_pair_ids = {
        (pair["implementation"], pair["test"]) for pair in selected_pairs
    }
    unavailable_companion_pairs = []
    for pair in pairs:
        pair_id = (pair["implementation"], pair["test"])
        if normalize_repo_path(pair["implementation"]).casefold() not in changed_sources:
            continue
        if pair_id in selected_pair_ids:
            continue
        test_path = normalize_repo_path(pair["test"])
        if (root / test_path).is_file() or test_path.casefold() in changes:
            selected_pairs.append(pair)
            selected_pair_ids.add(pair_id)
        else:
            # A companion test may live in another still-open PR, but a source
            # change cannot pass until every registered pair is present. Keep
            # the missing pair explicit so discovery fails closed.
            unavailable_companion_pairs.append(pair)
    # A docs/init-only touch still validates an extant implementation/test pair;
    # an absent candidate never turns this fallback into a pass.
    if not selected_pairs and changed_sources:
        missing_source_pairs = [
            pair for pair in pairs
            if normalize_repo_path(pair["implementation"]).casefold() in changed_sources
        ]
        if missing_source_pairs:
            selected_pairs = [missing_source_pairs[0]]
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
    } | {pair["test"] for pair in unavailable_companion_pairs})
    tests = [path for path in spec["tests"] if (root / path).is_file()]
    pair_tests = [pair["test"] for pair in selected_pairs if (root / pair["test"]).is_file()]
    tests_to_run = list(dict.fromkeys(pair_tests))
    active_support_files = {
        support_path: mapped_tests
        for support_path, mapped_tests in spec.get("support_files", {}).items()
        if normalize_repo_path(support_path).casefold() in changes
        or any(normalize_repo_path(test_path).casefold() in {normalize_repo_path(test).casefold() for test in tests_to_run}
               for test_path in mapped_tests)
    }
    missing_support_files = sorted({
        support_path for support_path in active_support_files
        if not (root / support_path).is_file()
    })
    selected_package_initializers = sorted(
        initializer_path for initializer_path in spec.get("package_initializers", {})
        if normalize_repo_path(initializer_path).casefold() in changes
    )
    missing_package_initializers = sorted(
        initializer_path for initializer_path in selected_package_initializers
        if not (root / initializer_path).is_file()
    )
    invalid_support_test_mappings = sorted({
        test_path
        for mapped_tests in active_support_files.values()
        for test_path in mapped_tests
        if (
            test_path not in spec.get("tests", ())
            or not (root / test_path).is_file()
            or normalize_repo_path(test_path).casefold()
            not in {normalize_repo_path(pair["test"]).casefold() for pair in pairs}
        )
    } | {
        test_path
        for mapped_tests in spec.get("support_files", {}).values()
        for test_path in mapped_tests
        if (
            test_path not in spec.get("tests", ())
            or normalize_repo_path(test_path).casefold()
            not in {normalize_repo_path(pair["test"]).casefold() for pair in pairs}
        )
    })
    invalid_initializer_test_mappings = sorted({
        test_path
        for mapped_tests in spec.get("package_initializers", {}).values()
        for test_path in mapped_tests
        if (
            test_path not in spec.get("tests", ())
            or normalize_repo_path(test_path).casefold()
            not in {normalize_repo_path(pair["test"]).casefold() for pair in pairs}
        )
    })
    selected_support_files = sorted(
        support_path for support_path in spec.get("support_files", {})
        if normalize_repo_path(support_path).casefold() in changes
    )
    implementations = sorted({
        pair["implementation"] for pair in selected_pairs
        if (root / pair["implementation"]).is_file()
    })
    blockers = []
    if missing_implementations:
        blockers.append("required candidate implementation is absent")
    if missing_required_tests:
        blockers.append("required candidate test is absent")
    if missing_support_files:
        blockers.append("required candidate test support file is absent")
    if missing_package_initializers:
        blockers.append("required candidate package initializer is absent")
    if invalid_support_test_mappings:
        blockers.append("candidate test support mapping is invalid or mapped test is absent")
    if invalid_initializer_test_mappings:
        blockers.append("package initializer mapping is invalid or mapped test is unpaired")
    if unmapped:
        blockers.append("changed candidate source/test path has no explicit implementation-test mapping")
    if not selected_pairs:
        blockers.append("no registered implementation-test pair exists")
    return {
        "component": name,
        "owner_prs": list(COMPONENT_OWNER_PRS.get(name, ())),
        "status": "BLOCKED" if blockers else "READY_TO_RUN",
        "blockers": blockers,
        "selected_paths": sorted({
            path for pair in selected_pairs for path in (pair["implementation"], pair["test"])
        } | set(selected_support_files) | set(selected_package_initializers)),
        "selected_support_files": selected_support_files,
        "selected_package_initializers": selected_package_initializers,
        "required_pairs": selected_pairs,
        "unavailable_companion_pairs": unavailable_companion_pairs,
        "require_all_pairs": require_all_pairs,
        "implementations": implementations,
        "missing_implementations": missing_implementations,
        "missing_required_tests": missing_required_tests,
        "missing_support_files": missing_support_files,
        "missing_package_initializers": missing_package_initializers,
        "invalid_support_test_mappings": invalid_support_test_mappings,
        "invalid_initializer_test_mappings": invalid_initializer_test_mappings,
        "unmapped_candidate_paths": unmapped,
        "available_candidate_tests": tests,
        "tests_to_run": tests_to_run,
        "executions": [],
    }


def _junit_details_from_bytes(
    content: bytes,
) -> tuple[tuple[int, int, int, int], list[dict[str, str]], int]:
    """Validate JUnit structure and keep explicit testcase count separate from suite totals."""
    root = ET.fromstring(content)
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError(f"unsupported JUnit root element: {root.tag!r}")
    cases = list(root.iter("testcase"))
    details: list[dict[str, str]] = []
    skipped = failed = errors = 0
    case_outcomes: dict[int, str] = {}
    for case in cases:
        outcomes = []
        for tag, label in (("skipped", "skipped"), ("failure", "failed"), ("error", "error")):
            nodes = case.findall(tag)
            if len(nodes) > 1:
                raise ValueError(f"JUnit testcase has multiple {tag} elements")
            if nodes:
                outcomes.append(label)
        if len(outcomes) > 1:
            raise ValueError("JUnit testcase has conflicting skipped/failure/error outcomes")
        outcome = outcomes[0] if outcomes else "passed"
        skipped += outcome == "skipped"
        failed += outcome == "failed"
        errors += outcome == "error"
        case_outcomes[id(case)] = outcome
        details.append({
            "name": ".".join(filter(None, (case.attrib.get("classname", ""), case.attrib.get("name", "")))),
            "status": outcome,
        })

    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    suite_case_ids = {id(case) for suite in suites for case in suite.iter("testcase")}
    if any(id(case) not in suite_case_ids for case in cases):
        raise ValueError("JUnit report contains testcases outside every testsuite")
    scopes = list(suites)
    if root.tag == "testsuites":
        scopes.append(root)
    declared_tests: dict[int, int] = {}
    for suite in scopes:
        suite_cases = list(suite.iter("testcase"))
        observed = {
            "tests": len(suite_cases),
            "skipped": sum(case_outcomes[id(case)] == "skipped" for case in suite_cases),
            "failures": sum(case_outcomes[id(case)] == "failed" for case in suite_cases),
            "errors": sum(case_outcomes[id(case)] == "error" for case in suite_cases),
        }
        for key, actual in observed.items():
            if key not in suite.attrib:
                continue
            raw = suite.attrib[key]
            if not re.fullmatch(r"\d+", raw):
                raise ValueError(f"JUnit {key} summary must be a non-negative integer")
            declared = int(raw)
            if key == "tests":
                # Pytest's JUnit totals include unittest.subTest outcomes while
                # emitting only the parent unittest testcase element.
                if declared < actual:
                    raise ValueError(
                        f"JUnit tests summary {declared} is below {actual} testcase outcomes"
                    )
                declared_tests[id(suite)] = declared
                continue
            if declared != actual:
                raise ValueError(
                    f"JUnit {key} summary {raw} does not match {actual} testcase outcomes"
                )
    if id(root) in declared_tests:
        total_tests = declared_tests[id(root)]
    elif root.tag == "testsuite":
        total_tests = len(cases)
    else:
        direct_suites = [child for child in list(root) if child.tag == "testsuite"]
        if direct_suites and all(id(suite) in declared_tests for suite in direct_suites):
            total_tests = sum(declared_tests[id(suite)] for suite in direct_suites)
        else:
            total_tests = len(cases)
    if total_tests < len(cases):
        raise ValueError("JUnit test total is below the number of testcase elements")
    return (len(cases), skipped, failed, errors), details, total_tests


def junit_details(path: Path) -> tuple[tuple[int, int, int, int], list[dict[str, str]]]:
    """Validate a JUnit file and return explicit testcase-element outcomes."""
    if path.stat().st_size > MAX_JUNIT_XML_BYTES:
        raise ValueError(f"JUnit report exceeds the {MAX_JUNIT_XML_BYTES}-byte read limit")
    with path.open("rb") as stream:
        content = stream.read(MAX_JUNIT_XML_BYTES + 1)
    if len(content) > MAX_JUNIT_XML_BYTES:
        raise ValueError(f"JUnit report exceeds the {MAX_JUNIT_XML_BYTES}-byte read limit")
    counts, details, _ = _junit_details_from_bytes(content)
    return counts, details


def _pytest_result_summary(stdout_tail: Any) -> tuple[int, int] | None:
    """Parse pytest's final pass/subtest summary without inflating testcase records."""
    if not isinstance(stdout_tail, str):
        return None
    lines = [line.strip() for line in stdout_tail.splitlines() if line.strip()]
    if not lines:
        return None
    match = re.fullmatch(
        r"(\d+)\s+passed(?:,\s*(\d+)\s+subtests passed)?\s+in\s+\d+(?:\.\d+)?s",
        lines[-1],
    )
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2) or 0)


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


def verify_candidate_source_identity(
    root: Path,
    component: str,
    implementation_paths: list[str],
    commit_sha: str,
) -> dict[str, Any]:
    """Bind selected source files and declared imports to the tested Git tree."""
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise ValueError("tested commit must be a full commit SHA")
    spec = COMPONENTS[component]
    errors: list[str] = []
    files = []
    for relative in implementation_paths:
        normalized = normalize_repo_path(relative)
        source = root / normalized
        if not source.is_file():
            errors.append(f"implementation is absent: {normalized}")
            files.append({"path": normalized, "status": "MISSING"})
            continue
        try:
            tree = subprocess.run(
                ["git", "rev-parse", f"{commit_sha}:{normalized}"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            worktree = subprocess.run(
                ["git", "diff", "--quiet", commit_sha, "--", normalized],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"source identity check failed for {normalized}: {exc}")
            files.append({"path": normalized, "status": "ERROR"})
            continue
        tree_blob_sha = tree.stdout.strip() if tree.returncode == 0 else None
        matches = bool(tree_blob_sha and re.fullmatch(r"[0-9a-f]{40}", tree_blob_sha) and worktree.returncode == 0)
        files.append({
            "path": normalized,
            "tree_blob_sha": tree_blob_sha,
            "matches_tested_commit": matches,
        })
        if not matches:
            errors.append(f"working source does not match tested commit: {normalized}")

    imports: list[dict[str, Any]] = []
    declared_imports = spec.get("module_imports", {})
    if declared_imports:
        probe = "\n".join((
            "import importlib, json, pathlib, sys",
            "root = pathlib.Path.cwd().resolve()",
            "declarations = json.loads(sys.argv[1])",
            "observed = {}",
            "for module_name in sorted(declarations):",
            "    module = importlib.import_module(module_name)",
            "    module_file = getattr(module, '__file__', None)",
            "    resolved = None",
            "    if module_file:",
            "        module_path = pathlib.Path(module_file).resolve()",
            "        try:",
            "            resolved = module_path.relative_to(root).as_posix()",
            "        except ValueError:",
            "            resolved = None",
            "    observed[module_name] = {'resolved_path': resolved}",
            "print(json.dumps(observed, sort_keys=True, allow_nan=False))",
        ))
        try:
            completed = subprocess.run(
                [sys.executable, "-c", probe, json.dumps(declared_imports, sort_keys=True)],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if completed.returncode != 0:
                errors.append(f"module import probe exited {completed.returncode}: {completed.stderr[-1000:]}")
            else:
                observed = json.loads(completed.stdout)
                for module, expected in declared_imports.items():
                    resolved = observed.get(module, {}).get("resolved_path")
                    matches = resolved == normalize_repo_path(expected)
                    imports.append({
                        "module": module,
                        "expected_path": normalize_repo_path(expected),
                        "resolved_path": normalize_repo_path(resolved) if resolved else None,
                        "matches_expected_source": matches,
                    })
                    if not matches:
                        errors.append(f"module {module} did not resolve to {expected}")
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, TypeError, AttributeError, ValueError) as exc:
            errors.append(f"module import probe failed: {exc}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "tested_commit_sha": commit_sha,
        "implementation_files": files,
        "module_imports": imports,
        "errors": errors,
    }


def _strict_json_loads(raw: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    return json.loads(raw, parse_constant=reject_constant)


def _isolated_runner_report_is_valid(batch_report: Any, test_file: str) -> tuple[bool, str | None, list[dict[str, Any]]]:
    """Require one completed, successful singleton batch for the requested test."""
    if not isinstance(batch_report, dict):
        return False, "runner telemetry root is not an object", []
    batches = batch_report.get("batches")
    summary = batch_report.get("summary")
    if not isinstance(batches, list) or not isinstance(summary, dict):
        return False, "runner telemetry is missing batches or summary", []
    if (
        batch_report.get("completed") is not True
        or type(batch_report.get("exit_code")) is not int
        or batch_report.get("exit_code") != 0
    ):
        return False, "runner telemetry does not report completed exit zero", batches
    if len(batches) != 1:
        return False, "runner telemetry is not one complete singleton batch", batches
    integer_fields = {
        "total_batches": 1,
        "total_files": 1,
        "overall_exit_code": 0,
        "passed_batches": 1,
        "skipped_batches": 0,
        "failed_batches": 0,
        "timeout_batches": 0,
    }
    for key, expected in integer_fields.items():
        value = summary.get(key)
        if type(value) is not int:
            return False, f"runner summary field {key} is missing or malformed", batches
        if value != expected:
            return False, f"runner summary field {key} is not the required value", batches
    duration = summary.get("duration_s")
    try:
        duration_is_valid = (
            isinstance(duration, (int, float))
            and not isinstance(duration, bool)
            and math.isfinite(duration)
            and duration >= 0
        )
    except (OverflowError, TypeError):
        duration_is_valid = False
    if not duration_is_valid:
        return False, "runner summary duration_s is missing or malformed", batches
    batch = batches[0]
    if not isinstance(batch, dict):
        return False, "runner batch entry is not an object", batches
    expected_file = normalize_repo_path(test_file)
    files = batch.get("test_files")
    if not isinstance(files, list) or [normalize_repo_path(str(path)) for path in files] != [expected_file]:
        return False, "runner batch did not execute exactly the selected test file", batches
    raw_files = batch.get("files")
    if not isinstance(raw_files, list) or [normalize_repo_path(str(path)) for path in raw_files] != [expected_file]:
        return False, "runner batch files do not match the selected test file", batches
    if any(type(batch.get(key)) is not int or batch.get(key) != 1 for key in ("batch_index", "batch_number")):
        return False, "runner batch identity is missing or malformed", batches
    for key in ("duration_s",):
        value = batch.get(key)
        try:
            valid = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and value >= 0
            )
        except (OverflowError, TypeError):
            valid = False
        if not valid:
            return False, f"runner batch {key} is missing or malformed", batches
    peak_memory = batch.get("peak_memory_mb")
    if "peak_memory_mb" not in batch:
        return False, "runner batch peak_memory_mb telemetry is missing", batches
    if peak_memory is not None:
        try:
            valid = (
                isinstance(peak_memory, (int, float))
                and not isinstance(peak_memory, bool)
                and math.isfinite(peak_memory)
                and peak_memory >= 0
            )
        except (OverflowError, TypeError):
            valid = False
        if not valid:
            return False, "runner batch peak_memory_mb is malformed", batches
    if not isinstance(batch.get("failures"), list) or batch["failures"]:
        return False, "runner batch failures telemetry is missing or non-empty", batches
    if not isinstance(batch.get("stdout_tail"), str) or not isinstance(batch.get("stderr_tail"), str):
        return False, "runner batch output-tail telemetry is missing or malformed", batches
    pytest_summary = _pytest_result_summary(batch["stdout_tail"])
    if pytest_summary is None or pytest_summary[0] < 1:
        return False, "runner pytest output does not contain a valid nonzero pass summary", batches
    batch["_round6_pytest_passed_count"] = pytest_summary[0]
    batch["_round6_pytest_subtests_passed_count"] = pytest_summary[1]
    if (
        batch.get("status") != "passed"
        or type(batch.get("exit_code")) is not int
        or batch.get("exit_code") != 0
    ):
        return False, "runner batch did not report passed exit zero", batches
    if batch.get("timed_out") is not False or batch.get("timeout_status") != "completed":
        return False, "runner batch timeout state is missing or non-completed", batches
    return True, None, batches


def run(
    root: Path,
    diff_base_sha: str,
    diff_head_sha: str,
    report_path: Path,
    *,
    always_components: list[str] | tuple[str, ...] = (),
    tested_checkout_sha: str | None = None,
    workflow_sha: str | None = None,
    event_name: str | None = None,
    require_checkout_match: bool = False,
) -> int:
    root = root.resolve()
    report_path = _lexically_contained_path(root, report_path, "report path")
    always_components = list(dict.fromkeys(always_components))
    unknown_always = sorted(set(always_components) - set(COMPONENTS))
    if unknown_always:
        raise ValueError(f"unknown always-run components: {unknown_always}")
    if tested_checkout_sha is not None and not re.fullmatch(r"[0-9a-f]{40}", tested_checkout_sha):
        raise ValueError("tested checkout must be a full commit SHA")
    if workflow_sha is not None and not re.fullmatch(r"[0-9a-f]{40}", workflow_sha):
        raise ValueError("workflow SHA must be a full commit SHA")
    if event_name == "workflow_dispatch":
        for label, sha in (("diff base", diff_base_sha), ("diff head", diff_head_sha)):
            if not re.fullmatch(r"[0-9a-f]{40}", sha):
                raise ValueError(
                    f"workflow_dispatch requires an explicit full commit SHA for {label}"
                )
    changed = collect_changed_paths(diff_base_sha, diff_head_sha, root)
    selected = select_components(changed)
    relevant_paths = sorted({
        normalize_repo_path(path)
        for path in changed
        if any(_is_component_relevant(name, {path}) for name in COMPONENTS)
    })
    report: dict[str, Any] = {
        "schema_version": "round6-experimental-ci-report-v1",
        "event_name": event_name,
        "diff_base_sha": diff_base_sha,
        "diff_head_sha": diff_head_sha,
        "tested_checkout_sha": tested_checkout_sha,
        "workflow_sha": workflow_sha,
        "status": "NOT_APPLICABLE" if not selected and not relevant_paths else "INCONCLUSIVE",
        "changed_paths": sorted(changed),
        "relevant_paths": relevant_paths,
        "selected_components": selected,
        "always_components": always_components,
        "not_applicable_components": [],
        "unmapped_candidate_paths": _unmapped_candidate_paths(changed),
        "selected_paths": {},
        "executed_commands": [],
        "components": [],
        "statement": "No scientific or empirical validity is assessed by this CI report.",
    }
    try:
        report_file_identity = _prepare_contained_output(
            root, report_path, "report path"
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({
            "status": "BLOCKED",
            "failure_classification": "unsafe_or_unavailable_report_path",
            "report_path_error": str(exc),
        }, sort_keys=True, allow_nan=False))
        return 1
    if require_checkout_match:
        actual = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=False,
            capture_output=True, text=True, timeout=10,
        )
        actual_sha = actual.stdout.strip() if actual.returncode == 0 else None
        report["actual_checkout_sha"] = actual_sha
        if not tested_checkout_sha or actual_sha != tested_checkout_sha:
            report.update({
                "status": "BLOCKED",
                "selection_error": "checked-out commit does not match the declared tested checkout SHA",
            })
            _write_contained_text(
                root, report_path,
                json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n",
                "report path", report_file_identity,
            )
            print(json.dumps({"status": report["status"], "selection_error": report["selection_error"]}, sort_keys=True))
            return 1

    if report["unmapped_candidate_paths"] and not selected and not always_components:
        report.update({
            "status": "BLOCKED",
            "selection_error": "unmapped candidate code, configuration, or fixture paths exist without a registered component selection",
        })
        _write_contained_text(
            root, report_path,
            json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n",
            "report path", report_file_identity,
        )
        print(json.dumps({"status": report["status"], "unmapped_candidate_paths": report["unmapped_candidate_paths"]}, sort_keys=True))
        return 1
    if not selected and not relevant_paths and not always_components and not report["unmapped_candidate_paths"]:
        report["statement"] = (
            "No candidate code or test path changed; this result does not certify any experimental lane."
        )
        _write_contained_text(
            root, report_path,
            json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n",
            "report path", report_file_identity,
        )
        print(json.dumps({
            "status": "NOT_APPLICABLE",
            "diff_base_sha": diff_base_sha,
            "diff_head_sha": diff_head_sha,
            "tested_checkout_sha": tested_checkout_sha,
            "workflow_sha": workflow_sha,
            "event_name": event_name,
            "selected_components": [],
            "candidate_test_executions": 0,
            "statement": "No candidate code or test path changed; this does not certify any experimental lane.",
        }, sort_keys=True, allow_nan=False))
        return 0
    if relevant_paths and not selected and not always_components:
        report["status"] = "BLOCKED"
        report["selection_error"] = "relevant candidate changes produced an empty component selection"
        _write_contained_text(
            root, report_path,
            json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n",
            "report path", report_file_identity,
        )
        print(json.dumps({"status": report["status"], "selection_error": report["selection_error"]}, sort_keys=True))
        return 1

    saw_blocked = bool(report["unmapped_candidate_paths"])
    saw_failure = False

    def block_artifact_read(
        entry: dict[str, Any],
        execution: dict[str, Any],
        exc: BaseException,
    ) -> None:
        nonlocal saw_blocked
        execution.update({
            "status": "BLOCKED",
            "timeout": False,
            "failure_classification": "unsafe_or_unavailable_log_path",
            "log_path_error": str(exc),
            "result_counts": {
                "collected": 0, "skipped": 0, "failed": 0, "errors": 0, "timeouts": 0,
            },
        })
        entry["executions"].append(execution)
        entry["status"] = "BLOCKED"
        entry["blockers"].append("test artifacts could not be safely opened under their checked roots")
        saw_blocked = True
        print(json.dumps({
            "selected_component": execution["selected_component"],
            "test_file": execution["test_file"],
            "status": "BLOCKED",
            "failure_classification": execution["failure_classification"],
        }, sort_keys=True, allow_nan=False))

    run_components = list(selected)
    for name in always_components:
        if name not in run_components:
            run_components.append(name)
    report["selected_components"] = run_components
    with tempfile.TemporaryDirectory(prefix="round6-ci-") as tmp:
        temp = Path(tmp)
        for index, name in enumerate(run_components, start=1):
            component_changes = {
                path for path in changed
                if _is_component_relevant(name, {path})
            }
            spec = COMPONENTS[name]
            require_all_pairs = name in always_components
            if require_all_pairs:
                inventory_paths = {
                    path for pair in spec.get("candidate_pairs", ())
                    for path in (pair["implementation"], pair["test"])
                }
                present_inventory = [path for path in inventory_paths if (root / path).is_file()]
                if not present_inventory and not component_changes:
                    report["not_applicable_components"].append(name)
                    report["components"].append({
                        "component": name,
                        "status": "NOT_APPLICABLE",
                        "reason": "no registered candidate implementation or test files exist in this checkout",
                        "selected_paths": [],
                        "required_pairs": [],
                        "implementations": [],
                        "tests_to_run": [],
                        "executions": [],
                    })
                    continue
            entry = inspect_component(
                name, root, component_changes, require_all_pairs=require_all_pairs
            )
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
            if tested_checkout_sha:
                source_check = verify_candidate_source_identity(
                    root, name, entry["implementations"], tested_checkout_sha
                )
                entry["source_verification"] = source_check
                if source_check["status"] != "PASS":
                    entry["status"] = "BLOCKED"
                    entry["blockers"].append("candidate source identity or direct import verification failed")
                    saw_blocked = True
                    continue
            for test_index, test_file in enumerate(entry["tests_to_run"], start=1):
                logs_candidate = report_path.parent / "round6-experimental-logs" / f"{index:02d}-{name}-{test_index:02d}"
                telemetry = temp / f"{index:02d}-{name}-{test_index:02d}.json"
                junit = temp / f"{index:02d}-{name}-{test_index:02d}.junit.xml"
                pinned_output_fds: list[int] = []
                telemetry_identity: tuple[int, int] | None = None
                junit_identity: tuple[int, int] | None = None
                pinned_output_transport = _supports_pinned_output_transport()
                path_failure_classification = "unsafe_or_unavailable_log_path"
                try:
                    logs = _lexically_contained_path(root, logs_candidate, "test log directory")
                    _ensure_contained_directories(root, logs, "test log directory")
                    stdout_log = _lexically_contained_path(root, logs / "runner.stdout.log", "runner stdout path")
                    stderr_log = _lexically_contained_path(root, logs / "runner.stderr.log", "runner stderr path")
                    path_failure_classification = "unsafe_or_unavailable_output_path"
                    if pinned_output_transport:
                        for output_path, output_label in (
                            (telemetry, "runner telemetry path"),
                            (junit, "JUnit report path"),
                        ):
                            fd = _open_contained_file(
                                temp, output_path,
                                os.O_RDWR | os.O_CREAT | os.O_TRUNC,
                                output_label, mode=0o600,
                            )
                            pinned_output_fds.append(fd)
                        telemetry_stat = _assert_regular_file(pinned_output_fds[0], "runner telemetry path")
                        junit_stat = _assert_regular_file(pinned_output_fds[1], "JUnit report path")
                        telemetry_identity = (telemetry_stat.st_dev, telemetry_stat.st_ino)
                        junit_identity = (junit_stat.st_dev, junit_stat.st_ino)
                    else:
                        telemetry = _lexically_contained_path(temp, telemetry, "runner telemetry path")
                        junit = _lexically_contained_path(temp, junit, "JUnit report path")
                        telemetry_identity = _prepare_contained_output(temp, telemetry, "runner telemetry path")
                        junit_identity = _prepare_contained_output(temp, junit, "JUnit report path")
                except (OSError, RuntimeError, ValueError) as exc:
                    _close_open_fds(pinned_output_fds)
                    execution = {
                        "selected_component": name,
                        "owner_prs": entry["owner_prs"],
                        "implementation_paths": entry["implementations"],
                        "test_file": test_file,
                        "diff_base_sha": diff_base_sha,
                        "diff_head_sha": diff_head_sha,
                        "tested_checkout_sha": tested_checkout_sha,
                        "workflow_sha": workflow_sha,
                        "event_name": event_name,
                        "status": "BLOCKED",
                        "timeout": False,
                        "artifact_path": None,
                        "failure_classification": path_failure_classification,
                        "log_path_error": str(exc),
                        "result_counts": {
                            "collected": 0, "skipped": 0, "failed": 0, "errors": 0, "timeouts": 0,
                        },
                    }
                    entry["executions"].append(execution)
                    entry["status"] = "BLOCKED"
                    entry["blockers"].append("test logs could not be created within the checked-out repository")
                    saw_blocked = True
                    print(json.dumps({
                        "selected_component": name,
                        "test_file": test_file,
                        "status": "BLOCKED",
                        "failure_classification": execution["failure_classification"],
                    }, sort_keys=True, allow_nan=False))
                    continue
                telemetry_arg = (
                    _proc_fd_path(pinned_output_fds[0])
                    if pinned_output_transport else str(telemetry)
                )
                junit_arg = (
                    _proc_fd_path(pinned_output_fds[1], pid=os.getpid())
                    if pinned_output_transport else str(junit)
                )
                cmd = [
                    sys.executable,
                    "scripts/run_tests_isolated.py",
                    "--root", ".",
                    "--batch-size", "1",
                    "--timeout-s", "120",
                    "--report", telemetry_arg,
                    f"--pytest-arg=--junitxml={junit_arg}",
                    test_file,
                ]
                if name == "docker_context_policy":
                    # The host-side Docker Engine probe reports the daemon
                    # version; keep that evidence visible in the job log.
                    cmd.insert(-1, "--pytest-arg=-s")
                report["executed_commands"].append(cmd)
                execution: dict[str, Any] = {
                    "selected_component": name,
                    "owner_prs": entry["owner_prs"],
                    "implementation_paths": entry["implementations"],
                    "test_file": test_file,
                    "diff_base_sha": diff_base_sha,
                    "diff_head_sha": diff_head_sha,
                    "tested_checkout_sha": tested_checkout_sha,
                    "workflow_sha": workflow_sha,
                    "event_name": event_name,
                    "artifact_path": logs.relative_to(root).as_posix(),
                    "stdout_log_path": stdout_log.relative_to(root).as_posix(),
                    "stderr_log_path": stderr_log.relative_to(root).as_posix(),
                    "command": cmd,
                    "output_transport": "pinned_proc_fd" if pinned_output_transport else "path_identity_checked",
                    "timeout": False,
                    "skipped": None,
                    "failed": None,
                    "errors": None,
                }
                stdout_fd = None
                stderr_fd = None
                try:
                    stdout_fd = _open_contained_file(
                        root, stdout_log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                        "runner stdout path", mode=0o600,
                    )
                    stderr_fd = _open_contained_file(
                        root, stderr_log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                        "runner stderr path", mode=0o600,
                    )
                except (OSError, RuntimeError, ValueError) as exc:
                    _close_open_fds(pinned_output_fds)
                    for fd in (stdout_fd, stderr_fd):
                        if fd is not None:
                            os.close(fd)
                    block_artifact_read(entry, execution, exc)
                    continue
                try:
                    with contextlib.ExitStack() as stack:
                        stdout_stream = stack.enter_context(os.fdopen(stdout_fd, "wb"))
                        stdout_fd = None
                        stderr_stream = stack.enter_context(os.fdopen(stderr_fd, "wb"))
                        stderr_fd = None
                        completed = subprocess.run(
                            cmd, cwd=root, timeout=130, check=False,
                            stdout=stdout_stream, stderr=stderr_stream,
                            **({"pass_fds": tuple(pinned_output_fds)} if pinned_output_transport else {}),
                        )
                except subprocess.TimeoutExpired:
                    _close_open_fds(pinned_output_fds)
                    execution.update({"status": "TIMEOUT", "timeout": True, "failure_classification": "timeout"})
                    execution["result_counts"] = {
                        "collected": 0, "skipped": 0, "failed": 0, "errors": 0, "timeouts": 1,
                    }
                    entry["executions"].append(execution)
                    entry["status"] = "FAIL"
                    saw_failure = True
                    print(json.dumps({
                        "selected_component": name,
                        "owner_prs": entry["owner_prs"],
                        "implementation_paths": entry["implementations"],
                        "test_file": test_file,
                        "diff_base_sha": diff_base_sha,
                        "diff_head_sha": diff_head_sha,
                        "tested_checkout_sha": tested_checkout_sha,
                        "workflow_sha": workflow_sha,
                        "event_name": event_name,
                        "tests_collected": 0,
                        "skipped": 0,
                        "failed": 0,
                        "errors": 0,
                        "timeouts": 1,
                        "artifact_path": execution["artifact_path"],
                        "status": "TIMEOUT",
                    }, sort_keys=True, allow_nan=False))
                    continue
                except OSError as exc:
                    _close_open_fds(pinned_output_fds)
                    execution.update({
                        "status": "ERROR",
                        "failure_classification": "runner_launch_failure",
                        "runner_error": str(exc),
                    })
                    execution["result_counts"] = {
                        "collected": 0, "skipped": 0, "failed": 0, "errors": 1, "timeouts": 0,
                    }
                    entry["executions"].append(execution)
                    entry["status"] = "FAIL"
                    saw_failure = True
                    print(json.dumps({
                        "selected_component": name,
                        "owner_prs": entry["owner_prs"],
                        "implementation_paths": entry["implementations"],
                        "test_file": test_file,
                        "diff_base_sha": diff_base_sha,
                        "diff_head_sha": diff_head_sha,
                        "tested_checkout_sha": tested_checkout_sha,
                        "workflow_sha": workflow_sha,
                        "event_name": event_name,
                        "tests_collected": 0,
                        "skipped": 0,
                        "failed": 0,
                        "errors": 1,
                        "timeouts": 0,
                        "artifact_path": execution["artifact_path"],
                        "status": "ERROR",
                    }, sort_keys=True, allow_nan=False))
                    continue
                finally:
                    for fd in (stdout_fd, stderr_fd):
                        if fd is not None:
                            os.close(fd)
                execution["runner_exit_code"] = completed.returncode
                try:
                    # Candidate code can mutate workspace paths while pytest
                    # runs. Keep lexical paths intact so no-follow opens can
                    # detect in-repository symlinks instead of resolving them.
                    logs = _lexically_contained_path(root, logs_candidate, "test log directory")
                    stdout_log = _lexically_contained_path(root, logs / "runner.stdout.log", "runner stdout path")
                    stderr_log = _lexically_contained_path(root, logs / "runner.stderr.log", "runner stderr path")
                    junit = _lexically_contained_path(temp, junit, "JUnit report path")
                    telemetry = _lexically_contained_path(temp, telemetry, "runner telemetry path")
                except (OSError, RuntimeError, ValueError) as exc:
                    _close_open_fds(pinned_output_fds)
                    block_artifact_read(entry, execution, exc)
                    continue
                try:
                    runner_stderr_tail = _read_contained_tail_text(
                        root, stderr_log, "runner stderr path",
                        tail_bytes=MAX_RUNNER_STDERR_TAIL_BYTES,
                    )
                except (OSError, RuntimeError, ValueError) as exc:
                    _close_open_fds(pinned_output_fds)
                    block_artifact_read(entry, execution, exc)
                    continue
                if runner_stderr_tail:
                    execution["runner_stderr_tail"] = runner_stderr_tail[-2000:]
                telemetry_ok = False
                telemetry_error = None
                batches: list[dict[str, Any]] = []
                telemetry_bytes: bytes | None = None
                try:
                    if pinned_output_transport:
                        _assert_contained_path_identity(
                            temp, telemetry, "runner telemetry path", telemetry_identity
                        )
                        telemetry_bytes = _read_pinned_output_bytes(
                            pinned_output_fds[0], "runner telemetry path",
                            max_bytes=MAX_RUNNER_TELEMETRY_BYTES,
                        )
                    else:
                        telemetry_bytes = _read_contained_bytes(
                            temp, telemetry, "runner telemetry path",
                            max_bytes=MAX_RUNNER_TELEMETRY_BYTES,
                            expected_identity=telemetry_identity,
                        )
                except FileNotFoundError:
                    pass
                except (OSError, RuntimeError, ValueError) as exc:
                    _close_open_fds(pinned_output_fds)
                    block_artifact_read(entry, execution, exc)
                    continue
                if telemetry_bytes is not None:
                    try:
                        batch_report = _strict_json_loads(telemetry_bytes.decode("utf-8"))
                        telemetry_ok, telemetry_error, batches = _isolated_runner_report_is_valid(batch_report, test_file)
                        execution["runner_batches"] = [
                            batch.get("status", "unknown") if isinstance(batch, dict) else "malformed"
                            for batch in batches
                        ]
                        summary = batch_report.get("summary", {}) if isinstance(batch_report, dict) else {}
                        execution["runner_timeout_batches"] = summary.get("timeout_batches") if isinstance(summary, dict) else None
                    except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
                        telemetry_error = str(exc)
                execution["isolated_runner_telemetry_valid"] = telemetry_ok
                if telemetry_error:
                    execution["runner_telemetry_error"] = telemetry_error
                junit_bytes: bytes | None = None
                try:
                    if pinned_output_transport:
                        _assert_contained_path_identity(temp, junit, "JUnit report path", junit_identity)
                        junit_bytes = _read_pinned_output_bytes(
                            pinned_output_fds[1], "JUnit report path",
                            max_bytes=MAX_JUNIT_XML_BYTES,
                        )
                    else:
                        junit_bytes = _read_contained_bytes(
                            temp, junit, "JUnit report path", max_bytes=MAX_JUNIT_XML_BYTES,
                            expected_identity=junit_identity,
                        )
                except FileNotFoundError:
                    pass
                except (OSError, RuntimeError, ValueError) as exc:
                    _close_open_fds(pinned_output_fds)
                    block_artifact_read(entry, execution, exc)
                    continue
                _close_open_fds(pinned_output_fds)
                junit_error = False
                if junit_bytes is not None:
                    try:
                        counts, cases, junit_reported_tests = _junit_details_from_bytes(junit_bytes)
                        runner_passed_count = (
                            batches[0].get("_round6_pytest_passed_count")
                            if batches and isinstance(batches[0], dict)
                            else None
                        )
                        runner_subtests_passed_count = (
                            batches[0].get("_round6_pytest_subtests_passed_count")
                            if batches and isinstance(batches[0], dict)
                            else None
                        )
                        if runner_passed_count != counts[0]:
                            raise ValueError(
                                f"JUnit testcase records {counts[0]} do not match pytest passed cases {runner_passed_count}"
                            )
                        if (
                            type(runner_subtests_passed_count) is not int
                            or junit_reported_tests != runner_passed_count + runner_subtests_passed_count
                        ):
                            raise ValueError(
                                "JUnit declared outcome total does not match pytest passed-case and passed-subtest summary"
                            )
                        execution.update({
                            "tests_collected": counts[0],
                            "runner_passed_tests": runner_passed_count,
                            "runner_passed_subtests": runner_subtests_passed_count,
                            "junit_reported_test_outcomes": junit_reported_tests,
                            "skipped": counts[1],
                            "failed": counts[2],
                            "errors": counts[3],
                            "test_cases": cases,
                        })
                    except (ET.ParseError, OSError, ValueError) as exc:
                        execution["junit_error"] = str(exc)
                        junit_error = True
                has_junit = junit_bytes is not None and not junit_error
                counts = (
                    execution.get("tests_collected", 0),
                    execution.get("skipped", 0),
                    execution.get("failed", 0),
                    execution.get("errors", 0),
                )
                runner_timeout_batches = execution.get("runner_timeout_batches")
                if not isinstance(runner_timeout_batches, int):
                    runner_timeout_batches = sum(
                        1 for batch in execution.get("runner_batches", ()) if batch == "timeout"
                    )
                execution["timeout"] = bool(execution["timeout"] or runner_timeout_batches > 0)
                execution["result_counts"] = {
                    "collected": counts[0],
                    "skipped": counts[1],
                    "failed": counts[2],
                    "errors": counts[3],
                    "timeouts": max(int(execution["timeout"]), runner_timeout_batches),
                }
                passed = completed.returncode == 0 and telemetry_ok and has_junit and junit_status(counts) == "PASS"
                if passed:
                    execution["status"] = "PASS"
                    execution["failure_classification"] = None
                else:
                    failure_classification = (
                        "timeout" if execution["timeout"]
                        else "runner_dependency_unavailable" if (
                            "pytest-timeout is required" in runner_stderr_tail
                            or "No module named 'pytest'" in runner_stderr_tail
                        )
                        else "test_or_collection_failure" if counts[2] or counts[3]
                        else "candidate_tests_skipped" if counts[1]
                        else "nonzero_runner_or_test_exit" if completed.returncode
                        else "missing_or_failed_runner_telemetry" if not telemetry_ok
                        else "missing_or_invalid_junit" if not has_junit
                        else "empty_test_collection"
                    )
                    execution["failure_classification"] = failure_classification
                    if failure_classification == "runner_dependency_unavailable":
                        execution["status"] = "BLOCKED"
                        entry["status"] = "BLOCKED"
                        entry["blockers"].append("bounded test-runner dependency is unavailable")
                        saw_blocked = True
                    else:
                        execution["status"] = "FAIL"
                        saw_failure = True
                        entry["status"] = "FAIL"
                entry["executions"].append(execution)
                print(json.dumps({
                    "selected_component": name,
                    "owner_prs": entry["owner_prs"],
                    "implementation_paths": entry["implementations"],
                    "test_file": test_file,
                    "diff_base_sha": diff_base_sha,
                    "diff_head_sha": diff_head_sha,
                    "tested_checkout_sha": tested_checkout_sha,
                    "workflow_sha": workflow_sha,
                    "tests_collected": counts[0],
                    "skipped": counts[1],
                    "failed": counts[2],
                    "errors": counts[3],
                    "timeouts": int(execution["timeout"]),
                    "artifact_path": execution["artifact_path"],
                    "status": execution.get("status"),
                    "failure_classification": execution.get("failure_classification"),
                }, sort_keys=True, allow_nan=False))
            if entry["status"] == "READY_TO_RUN":
                entry["status"] = "PASS" if all(item["status"] == "PASS" for item in entry["executions"]) else "FAIL"

    ran_any = any(item.get("status") in {"PASS", "FAIL"} for item in report["components"])
    report["status"] = (
        "FAIL" if saw_failure else "BLOCKED" if saw_blocked else
        "NOT_APPLICABLE" if not ran_any and report["not_applicable_components"] else
        "NOT_APPLICABLE" if not run_components and not relevant_paths else "PASS"
    )

    try:
        _write_contained_text(
            root,
            report_path,
            json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n",
            "report path",
            report_file_identity,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        report["status"] = "BLOCKED"
        report["report_path_error"] = str(exc)
        print(json.dumps({
            "status": report["status"],
            "report_path_error": report["report_path_error"],
        }, sort_keys=True, allow_nan=False))
        return 1
    print(json.dumps({
        "status": report["status"],
        "diff_base_sha": report["diff_base_sha"],
        "diff_head_sha": report["diff_head_sha"],
        "tested_checkout_sha": report["tested_checkout_sha"],
        "workflow_sha": report["workflow_sha"],
        "selected_components": report["selected_components"],
        "not_applicable_components": report["not_applicable_components"],
        "unmapped_candidate_paths": report["unmapped_candidate_paths"],
        "candidate_test_executions": sum(len(item.get("executions", ())) for item in report["components"]),
        "component_statuses": {item["component"]: item["status"] for item in report["components"]},
    }, sort_keys=True, allow_nan=False))
    return 0 if report["status"] == "PASS" or report["status"] == "NOT_APPLICABLE" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", "--diff-base", dest="diff_base_sha", required=True,
                        help="PR base (or push before) SHA used only for changed-path discovery")
    parser.add_argument("--head", "--diff-head", dest="diff_head_sha", required=True,
                        help="PR head (or push SHA) used only for changed-path discovery")
    parser.add_argument("--tested-checkout", required=True,
                        help="SHA checked out for test execution; may be a PR merge ref")
    parser.add_argument("--workflow-sha", required=True,
                        help="GitHub workflow-file commit SHA, recorded separately from the tested checkout")
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--always-component", action="append", default=[], choices=sorted(COMPONENTS),
        help="Run the registered component when its candidate files exist; absence is NOT_APPLICABLE, not PASS.",
    )
    args = parser.parse_args(argv)
    try:
        return run(
            args.root, args.diff_base_sha, args.diff_head_sha, args.report,
            always_components=args.always_component,
            tested_checkout_sha=args.tested_checkout,
            workflow_sha=args.workflow_sha,
            event_name=args.event_name,
            require_checkout_match=True,
        )
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"Round 6 candidate test discovery failed closed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
