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
from functools import lru_cache
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
MAX_JUNIT_FAILURE_CASES = 50
MAX_JUNIT_FAILURE_NAME_CHARS = 512
# Only this non-sensitive opt-in is allowed into candidate test processes.
SAFE_CANDIDATE_ENVIRONMENT_OVERRIDES = {
    "DMD_EP2_REQUIRE_PRODUCTION": frozenset({"1"}),
}
# This exact historical test blob has six two-case unittest.subTest loops (12
# outcomes), while pytest emits one parent testcase record per loop. Run
# 39382340982 verified the 53/41 delta with a clean test process, but the
# candidate gate correctly failed because the delta was not yet registered.
# The exception below records that failure explicitly; the later #438 test blob
# is different and does not inherit the exception. Any other delta is rejected
# unless the pytest stdout summary independently reconciles it.
REGISTERED_JUNIT_SUBTEST_DELTAS = {
    "tests/adapters/mne_signal_blocks/test_mne_signal_blocks.py": {
        "blob_sha": "b37cc987b1e369295552c574ac2bbd1312ecc733",
        "delta": 12,
        "component": "mne_signal_blocks",
        "owner_pr": 438,
        "source_head_sha": "ab9090bb023695e32915a8f0302f086dc92fa780",
        "verification": {
            "run_id": 39382340982,
            "run_url": "https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39382340982",
            "tested_checkout_sha": "224a92303b08277ea0885d54be68b82e475f951f",
            "workflow_conclusion": "failure",
            "candidate_status": "FAIL",
            "failure_classification": "missing_or_invalid_junit",
            "junit_reconciliation": "mismatch",
            "test_process_outcome": "passed",
            "junit_reported_total": 53,
            "junit_testcase_records": 41,
            "runner_exit_code": 0,
            "runner_telemetry_valid": True,
            "skipped": 0,
            "failed": 0,
            "errors": 0,
            "timeouts": 0,
        },
    },
}
PINNED_OUTPUT_PROBE_MARKER = b"round6-pinned-output-probe-v1"
PINNED_OUTPUT_PROBE_TIMEOUT_S = 3
_PROBE_SUBPROCESS_RUN = subprocess.run


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
    "higher_order_runtime": {
        "triggers": (
            "tools/higher_order_runtime/",
            "tests/higher_order_runtime_contract/",
        ),
        "tests": (
            "tests/higher_order_runtime_contract/test_bounds_and_failures.py",
            "tests/higher_order_runtime_contract/test_chunk_boundaries.py",
            "tests/higher_order_runtime_contract/test_state_reset_and_parity.py",
            "tests/higher_order_runtime_contract/test_timeline_and_shape.py",
        ),
        "candidate_pairs": tuple(
            {"implementation": implementation, "test": test}
            for implementation in (
                "tools/higher_order_runtime/__init__.py",
                "tools/higher_order_runtime/stream_contract.py",
            )
            for test in (
                "tests/higher_order_runtime_contract/test_bounds_and_failures.py",
                "tests/higher_order_runtime_contract/test_chunk_boundaries.py",
                "tests/higher_order_runtime_contract/test_state_reset_and_parity.py",
                "tests/higher_order_runtime_contract/test_timeline_and_shape.py",
            )
        ) + (
            {
                "implementation": "tools/higher_order_runtime/planner.py",
                "test": "tests/higher_order_runtime_contract/test_bounds_and_failures.py",
            },
        ),
        "support_files": {
            "tests/higher_order_runtime_contract/conftest.py": (
                "tests/higher_order_runtime_contract/test_bounds_and_failures.py",
                "tests/higher_order_runtime_contract/test_chunk_boundaries.py",
                "tests/higher_order_runtime_contract/test_state_reset_and_parity.py",
                "tests/higher_order_runtime_contract/test_timeline_and_shape.py",
            ),
        },
        "implementation_roots": ("tools/higher_order_runtime/",),
        "candidate_test_roots": ("tests/higher_order_runtime_contract/",),
    },
    "synthetic_pipeline_replay": {
        "triggers": (
            "tools/synthetic_pipeline_replay/",
            "tests/integration/synthetic_pipeline_replay/",
        ),
        "tests": (
            "tests/integration/synthetic_pipeline_replay/test_replay_harness.py",
            "tests/integration/synthetic_pipeline_replay/test_replay_negative_cases.py",
        ),
        "candidate_pairs": tuple(
            {"implementation": implementation, "test": test}
            for implementation in (
                "tools/synthetic_pipeline_replay/__init__.py",
                "tools/synthetic_pipeline_replay/checker.py",
                "tools/synthetic_pipeline_replay/contracts.py",
                "tools/synthetic_pipeline_replay/runner.py",
                "tools/synthetic_pipeline_replay/stages.py",
            )
            for test in (
                "tests/integration/synthetic_pipeline_replay/test_replay_harness.py",
                "tests/integration/synthetic_pipeline_replay/test_replay_negative_cases.py",
            )
        ),
        "support_files": {
            "tests/integration/synthetic_pipeline_replay/fixtures.py": (
                "tests/integration/synthetic_pipeline_replay/test_replay_harness.py",
                "tests/integration/synthetic_pipeline_replay/test_replay_negative_cases.py",
            ),
        },
        "implementation_roots": ("tools/synthetic_pipeline_replay/",),
        "candidate_test_roots": ("tests/integration/synthetic_pipeline_replay/",),
    },
    "hodge_2d": {
        "triggers": (
            "neurotopology_sim/experimental/topology/hodge_2d.py",
            "tests/neurotopology_sim/experimental/topology/test_hodge_2d.py",
        ),
        "tests": ("tests/neurotopology_sim/experimental/topology/test_hodge_2d.py",),
        "candidate_pairs": (
            {"implementation": "neurotopology_sim/experimental/topology/hodge_2d.py", "test": "tests/neurotopology_sim/experimental/topology/test_hodge_2d.py"},
        ),
        "implementation": "neurotopology_sim/experimental/topology/hodge_2d.py",
        "implementation_roots": ("neurotopology_sim/experimental/topology/hodge_2d.py",),
        "candidate_test_roots": ("tests/neurotopology_sim/experimental/topology/test_hodge_2d.py",),
    },
    "phase_cochain_reference": {
        "triggers": (
            "experimental/phase_cochain_reference/",
            "tests/experimental/phase_cochain_reference/",
        ),
        "tests": (
            "tests/experimental/phase_cochain_reference/test_charge_moments_and_centroids.py",
            "tests/experimental/phase_cochain_reference/test_coboundary_exactness.py",
            "tests/experimental/phase_cochain_reference/test_weighted_hodge_decomposition.py",
            "tests/experimental/phase_cochain_reference/test_wrapped_phase_charges.py",
        ),
        "candidate_pairs": (
            {"implementation": "experimental/phase_cochain_reference/__init__.py", "test": "tests/experimental/phase_cochain_reference/test_charge_moments_and_centroids.py"},
            {"implementation": "experimental/phase_cochain_reference/__init__.py", "test": "tests/experimental/phase_cochain_reference/test_coboundary_exactness.py"},
            {"implementation": "experimental/phase_cochain_reference/__init__.py", "test": "tests/experimental/phase_cochain_reference/test_weighted_hodge_decomposition.py"},
            {"implementation": "experimental/phase_cochain_reference/__init__.py", "test": "tests/experimental/phase_cochain_reference/test_wrapped_phase_charges.py"},
            {"implementation": "experimental/phase_cochain_reference/cochain.py", "test": "tests/experimental/phase_cochain_reference/test_charge_moments_and_centroids.py"},
            {"implementation": "experimental/phase_cochain_reference/cochain.py", "test": "tests/experimental/phase_cochain_reference/test_wrapped_phase_charges.py"},
            {"implementation": "experimental/phase_cochain_reference/complex.py", "test": "tests/experimental/phase_cochain_reference/test_charge_moments_and_centroids.py"},
            {"implementation": "experimental/phase_cochain_reference/complex.py", "test": "tests/experimental/phase_cochain_reference/test_coboundary_exactness.py"},
            {"implementation": "experimental/phase_cochain_reference/complex.py", "test": "tests/experimental/phase_cochain_reference/test_weighted_hodge_decomposition.py"},
            {"implementation": "experimental/phase_cochain_reference/fixtures.py", "test": "tests/experimental/phase_cochain_reference/test_charge_moments_and_centroids.py"},
            {"implementation": "experimental/phase_cochain_reference/fixtures.py", "test": "tests/experimental/phase_cochain_reference/test_coboundary_exactness.py"},
            {"implementation": "experimental/phase_cochain_reference/fixtures.py", "test": "tests/experimental/phase_cochain_reference/test_weighted_hodge_decomposition.py"},
            {"implementation": "experimental/phase_cochain_reference/fixtures.py", "test": "tests/experimental/phase_cochain_reference/test_wrapped_phase_charges.py"},
            {"implementation": "experimental/phase_cochain_reference/hodge.py", "test": "tests/experimental/phase_cochain_reference/test_weighted_hodge_decomposition.py"},
        ),
        "implementation_roots": ("experimental/phase_cochain_reference/",),
        "candidate_test_roots": ("tests/experimental/phase_cochain_reference/",),
    },
    "hodge_decomposition_audit": {
        "triggers": (
            "tools/hodge_decomposition_audit/",
            "tests/tools/hodge_decomposition_audit/",
        ),
        "tests": ("tests/tools/hodge_decomposition_audit/test_hodge_audit.py",),
        "candidate_pairs": tuple(
            {"implementation": implementation, "test": "tests/tools/hodge_decomposition_audit/test_hodge_audit.py"}
            for implementation in (
                "tools/hodge_decomposition_audit/__init__.py",
                "tools/hodge_decomposition_audit/__main__.py",
                "tools/hodge_decomposition_audit/audit.py",
                "tools/hodge_decomposition_audit/charges.py",
                "tools/hodge_decomposition_audit/fixtures.py",
                "tools/hodge_decomposition_audit/hodge_oracle.py",
                "tools/hodge_decomposition_audit/incidence.py",
                "tools/hodge_decomposition_audit/report.py",
                "tools/hodge_decomposition_audit/schema.py",
            )
        ),
        "implementation_roots": ("tools/hodge_decomposition_audit/",),
        "candidate_test_roots": ("tests/tools/hodge_decomposition_audit/",),
    },
    "spherical_csd": {
        "triggers": (
            "neurotopology_sim/experimental/preprocessing/spherical_csd.py",
            "tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py",
            "tests/experimental/test_spherical_csd_parity.py",
            "tests/experimental/fixtures/spherical_csd_mne_1_13_2_reference.json",
            "tests/mne_csd_reference_audit/test_kkt_operator.py",
        ),
        "tests": (
            "tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py",
            "tests/experimental/test_spherical_csd_parity.py",
            # This exact KKT test is shared with the independent reference
            # audit. The selector assigns a test-only change here for legacy
            # CSD parity; audit implementation changes remain separately owned.
            "tests/mne_csd_reference_audit/test_kkt_operator.py",
            "tests/mne_csd_reference_audit/test_mne_integration_optional.py",
        ),
        "candidate_pairs": (
            {"implementation": "neurotopology_sim/experimental/preprocessing/spherical_csd.py", "test": "tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py"},
            {"implementation": "neurotopology_sim/experimental/preprocessing/spherical_csd.py", "test": "tests/experimental/test_spherical_csd_parity.py"},
            {"implementation": "tools/mne_csd_reference_audit/kkt.py", "test": "tests/mne_csd_reference_audit/test_kkt_operator.py"},
        ),
        "implementation": "neurotopology_sim/experimental/preprocessing/spherical_csd.py",
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
        },
        "implementation_roots": ("neurotopology_sim/experimental/preprocessing/spherical_csd.py",),
        "test_roots": (
            "tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py",
            "tests/experimental/test_spherical_csd_parity.py",
        ),
        "candidate_test_roots": (
            "tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py",
            "tests/experimental/test_spherical_csd_parity.py",
        ),
    },
    "mne_csd_reference_audit": {
        "triggers": (
            "tools/mne_csd_reference_audit/",
            "tests/mne_csd_reference_audit/",
            "tests/optional_live_mne/test_mne_csd_live_parity.py",
        ),
        "tests": (
            "tests/mne_csd_reference_audit/test_isolation_and_pin.py",
            "tests/mne_csd_reference_audit/test_kkt_operator.py",
            "tests/mne_csd_reference_audit/test_legendre_constants.py",
            "tests/mne_csd_reference_audit/test_mne_integration_optional.py",
            "tests/optional_live_mne/test_mne_csd_live_parity.py",
        ),
        "candidate_pairs": tuple(
            {"implementation": implementation, "test": test}
            for implementation, tests in {
                "tools/mne_csd_reference_audit/__init__.py": (
                    "tests/mne_csd_reference_audit/test_isolation_and_pin.py",
                    "tests/mne_csd_reference_audit/test_kkt_operator.py",
                    "tests/mne_csd_reference_audit/test_legendre_constants.py",
                    "tests/mne_csd_reference_audit/test_mne_integration_optional.py",
                ),
                "tools/mne_csd_reference_audit/__main__.py": (
                    "tests/mne_csd_reference_audit/test_isolation_and_pin.py",
                ),
                "tools/mne_csd_reference_audit/kkt.py": (
                    "tests/mne_csd_reference_audit/test_kkt_operator.py",
                    "tests/mne_csd_reference_audit/test_mne_integration_optional.py",
                    "tests/optional_live_mne/test_mne_csd_live_parity.py",
                ),
                "tools/mne_csd_reference_audit/legendre.py": (
                    "tests/mne_csd_reference_audit/test_kkt_operator.py",
                    "tests/mne_csd_reference_audit/test_legendre_constants.py",
                    "tests/optional_live_mne/test_mne_csd_live_parity.py",
                ),
                "tools/mne_csd_reference_audit/montages.py": (
                    "tests/mne_csd_reference_audit/test_kkt_operator.py",
                    "tests/mne_csd_reference_audit/test_mne_integration_optional.py",
                    "tests/optional_live_mne/test_mne_csd_live_parity.py",
                ),
                "tools/mne_csd_reference_audit/pin.py": (
                    "tests/mne_csd_reference_audit/test_isolation_and_pin.py",
                    "tests/mne_csd_reference_audit/test_mne_integration_optional.py",
                    "tests/optional_live_mne/test_mne_csd_live_parity.py",
                ),
                "tools/mne_csd_reference_audit/report.py": (
                    "tests/mne_csd_reference_audit/test_isolation_and_pin.py",
                ),
            }.items()
            for test in tests
        ),
        "support_files": {
            "tests/mne_csd_reference_audit/conftest.py": (
                "tests/mne_csd_reference_audit/test_isolation_and_pin.py",
                "tests/mne_csd_reference_audit/test_kkt_operator.py",
                "tests/mne_csd_reference_audit/test_legendre_constants.py",
                "tests/mne_csd_reference_audit/test_mne_integration_optional.py",
            ),
            "tests/mne_csd_reference_audit/fixtures/mne_code_path_transcription.json": (
                "tests/mne_csd_reference_audit/test_mne_integration_optional.py",
            ),
        },
        "implementation_roots": ("tools/mne_csd_reference_audit/",),
        "candidate_test_roots": (
            "tests/mne_csd_reference_audit/",
            "tests/optional_live_mne/test_mne_csd_live_parity.py",
        ),
        # The live operator parity test runs in the EEG job, which pins MNE
        # 1.13.2; it is never silently counted as core evidence.
        "external_test_paths": {
            "tests/optional_live_mne/test_mne_csd_live_parity.py": "optional-eeg-suite",
        },
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
            "tests/surrogate_audit/test_metrics_scale_invariance.py",
        ),
        "candidate_pairs": tuple(
            {"implementation": implementation, "test": test}
            for implementation, tests in {
                "tools/surrogate_audit/__init__.py": (
                    "tests/surrogate_audit/test_invalid_inputs.py",
                    "tests/surrogate_audit/test_metrics_scale_invariance.py",
                    "tests/surrogate_audit/test_mv_fpr.py",
                    "tests/surrogate_audit/test_mv_iaaft.py",
                ),
                "tools/surrogate_audit/errors.py": (
                    "tests/surrogate_audit/test_invalid_inputs.py",
                    "tests/surrogate_audit/test_metrics_scale_invariance.py",
                ),
                "tools/surrogate_audit/metrics.py": (
                    "tests/surrogate_audit/test_metrics_scale_invariance.py",
                    "tests/surrogate_audit/test_mv_fpr.py",
                    "tests/surrogate_audit/test_mv_iaaft.py",
                ),
                "tools/surrogate_audit/mv_fpr.py": (
                    "tests/surrogate_audit/test_invalid_inputs.py",
                    "tests/surrogate_audit/test_metrics_scale_invariance.py",
                    "tests/surrogate_audit/test_mv_fpr.py",
                ),
                "tools/surrogate_audit/mv_iaaft.py": (
                    "tests/surrogate_audit/test_invalid_inputs.py",
                    "tests/surrogate_audit/test_metrics_scale_invariance.py",
                    "tests/surrogate_audit/test_mv_iaaft.py",
                ),
                "tools/surrogate_audit/report.py": (
                    "tests/surrogate_audit/test_invalid_inputs.py",
                    "tests/surrogate_audit/test_metrics_scale_invariance.py",
                    "tests/surrogate_audit/test_mv_fpr.py",
                    "tests/surrogate_audit/test_mv_iaaft.py",
                ),
                "tools/surrogate_audit/status.py": (
                    "tests/surrogate_audit/test_invalid_inputs.py",
                    "tests/surrogate_audit/test_metrics_scale_invariance.py",
                    "tests/surrogate_audit/test_mv_fpr.py",
                    "tests/surrogate_audit/test_mv_iaaft.py",
                ),
            }.items()
            for test in tests
        ),
        "support_files": {
            "tests/surrogate_audit/fixtures.py": (
                "tests/surrogate_audit/test_mv_fpr.py",
                "tests/surrogate_audit/test_mv_iaaft.py",
                "tests/surrogate_audit/test_invalid_inputs.py",
                "tests/surrogate_audit/test_metrics_scale_invariance.py",
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
    "fusion_validation_null_models": {
        # Registered from the exact implementation/test paths and command in
        # PR #374. Keep this component narrow; the candidate remains open and
        # must be present in the tested checkout before its tests can pass.
        "triggers": (
            "dual_engine/fusion_validation.py",
            "tests/test_fusion_null_models.py",
            "tests/test_fusion_validation.py",
        ),
        "implementation": "dual_engine/fusion_validation.py",
        "tests": (
            "tests/test_fusion_null_models.py",
            "tests/test_fusion_validation.py",
        ),
        "candidate_pairs": (
            {"implementation": "dual_engine/fusion_validation.py", "test": "tests/test_fusion_null_models.py"},
            {"implementation": "dual_engine/fusion_validation.py", "test": "tests/test_fusion_validation.py"},
        ),
        "implementation_roots": ("dual_engine/fusion_validation.py",),
        "test_roots": (
            "tests/test_fusion_null_models.py",
            "tests/test_fusion_validation.py",
        ),
        "candidate_test_roots": (
            "tests/test_fusion_null_models.py",
            "tests/test_fusion_validation.py",
        ),
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
        "triggers": (
            "tools/experimental_audits/winding_charge_round6/",
            "tests/experimental_audits/test_winding_charge_round6_oracle.py",
            "neurotopology_sim/experimental/topology/winding.py",
            "tests/experimental_audits/test_winding_charge_production_import.py",
        ),
        "implementation_any": (
            "tools/experimental_audits/winding_charge_round6/__main__.py",
            "tools/experimental_audits/winding_charge_round6/audit.py",
            "tools/experimental_audits/winding_charge_round6/conventions.py",
            "tools/experimental_audits/winding_charge_round6/fixtures.py",
            "tools/experimental_audits/winding_charge_round6/oracle.py",
        ),
        "tests": (
            "tests/experimental_audits/test_winding_charge_round6_oracle.py",
            "tests/experimental_audits/test_winding_charge_production_import.py",
        ),
        "candidate_pairs": (
            {"implementation": "tools/experimental_audits/winding_charge_round6/__main__.py", "test": "tests/experimental_audits/test_winding_charge_round6_oracle.py"},
            {"implementation": "tools/experimental_audits/winding_charge_round6/audit.py", "test": "tests/experimental_audits/test_winding_charge_round6_oracle.py"},
            {"implementation": "tools/experimental_audits/winding_charge_round6/conventions.py", "test": "tests/experimental_audits/test_winding_charge_round6_oracle.py"},
            {"implementation": "tools/experimental_audits/winding_charge_round6/fixtures.py", "test": "tests/experimental_audits/test_winding_charge_round6_oracle.py"},
            {"implementation": "tools/experimental_audits/winding_charge_round6/oracle.py", "test": "tests/experimental_audits/test_winding_charge_round6_oracle.py"},
            {"implementation": "tools/experimental_audits/winding_charge_round6/oracle.py", "test": "tests/experimental_audits/test_winding_charge_production_import.py"},
            {"implementation": "neurotopology_sim/experimental/topology/winding.py", "test": "tests/experimental_audits/test_winding_charge_production_import.py"},
        ),
        "implementation_roots": (
            "tools/experimental_audits/winding_charge_round6/",
            "neurotopology_sim/experimental/topology/winding.py",
        ),
        "test_roots": (
            "tests/experimental_audits/test_winding_charge_round6_oracle.py",
            "tests/experimental_audits/test_winding_charge_production_import.py",
        ),
        "candidate_test_roots": (
            "tests/experimental_audits/test_winding_charge_round6_oracle.py",
            "tests/experimental_audits/test_winding_charge_production_import.py",
        ),
    },
    "dmd_crouzeix": {
        "triggers": (
            "neurotopology_sim/experimental/dynamics/",
            "tests/dmd_crouzeix_contract/",
            "tests/experimental/test_dmd_crouzeix.py",
            "tests/dmd_ep2_oracle/test_production_bridge.py",
        ),
        "implementation": "neurotopology_sim/experimental/dynamics/dmd_crouzeix.py",
        "tests": (
            "tests/dmd_crouzeix_contract/test_production_contract.py",
            "tests/experimental/test_dmd_crouzeix.py",
            "tests/dmd_ep2_oracle/test_production_bridge.py",
            "tests/dmd_ep2_oracle/test_oracle.py",
        ),
        "candidate_pairs": (
            {"implementation": "neurotopology_sim/experimental/dynamics/dmd_crouzeix.py", "test": "tests/dmd_crouzeix_contract/test_production_contract.py"},
            {"implementation": "neurotopology_sim/experimental/dynamics/dmd_crouzeix.py", "test": "tests/experimental/test_dmd_crouzeix.py"},
            {"implementation": "neurotopology_sim/experimental/dynamics/dmd_crouzeix.py", "test": "tests/dmd_ep2_oracle/test_production_bridge.py"},
        ),
        "support_files": {
            "tests/dmd_ep2_oracle/test_oracle.py": (
                "tests/dmd_ep2_oracle/test_production_bridge.py",
            ),
        },
        "support_file_requires_changed": {
            "tests/dmd_ep2_oracle/test_oracle.py": (
                "tests/dmd_ep2_oracle/test_production_bridge.py",
            ),
        },
        "independent_reference_tests": (
            "tests/dmd_ep2_oracle/test_oracle.py",
        ),
        "environment_overrides": {"DMD_EP2_REQUIRE_PRODUCTION": "1"},
        "implementation_roots": ("neurotopology_sim/experimental/dynamics/",),
        "test_roots": (
            "tests/dmd_crouzeix_contract/",
            "tests/experimental/test_dmd_crouzeix.py",
            "tests/dmd_ep2_oracle/test_production_bridge.py",
            "tests/dmd_ep2_oracle/test_oracle.py",
        ),
        "candidate_test_roots": (
            "tests/dmd_crouzeix_contract/",
            "tests/experimental/test_dmd_crouzeix.py",
            "tests/dmd_ep2_oracle/test_production_bridge.py",
            "tests/dmd_ep2_oracle/test_oracle.py",
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
        "external_test_paths": {
            "tests/docker_context/test_docker_engine_build_context.py": "docker-context-engine",
        },
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
    "public_repo_source_pack": {
        "triggers": (
            "tools/public_repo_harvest/",
            "tests/tools/test_public_repo_harvest_source_pack.py",
        ),
        "implementation_any": (
            "tools/public_repo_harvest/source_pack.py",
            "tools/public_repo_harvest/external_systems_scorecard.py",
            "tools/public_repo_harvest/license_scanner.py",
            "tools/public_repo_harvest/pattern_classifier.py",
        ),
        "tests": ("tests/tools/test_public_repo_harvest_source_pack.py",),
        "candidate_pairs": tuple(
            {
                "implementation": path,
                "test": "tests/tools/test_public_repo_harvest_source_pack.py",
            }
            for path in (
                "tools/public_repo_harvest/source_pack.py",
                "tools/public_repo_harvest/external_systems_scorecard.py",
                "tools/public_repo_harvest/license_scanner.py",
                "tools/public_repo_harvest/pattern_classifier.py",
            )
        ),
        "implementation_roots": ("tools/public_repo_harvest/",),
        "candidate_test_roots": ("tests/tools/test_public_repo_harvest_source_pack.py",),
    },
    "batch2_pipeline_benchmark": {
        "triggers": (
            "tools/benchmarks/batch2_pipeline/",
            "tools/benchmarks/__init__.py",
            "scripts/benchmark_batch2_pipeline.py",
            "tests/benchmarks/batch2_pipeline/",
        ),
        # This regression test belongs to the workflow itself. Its changes run
        # in core-tests and must not select an absent unmerged benchmark source.
        "non_selecting_test_paths": (
            "tests/ci/test_round6_benchmark_makefile.py",
        ),
        "tests": (
            "tests/benchmarks/batch2_pipeline/test_cli_and_reporting.py",
            "tests/benchmarks/batch2_pipeline/test_failure_modes.py",
            "tests/benchmarks/batch2_pipeline/test_governance_compile.py",
            "tests/benchmarks/batch2_pipeline/test_harness_and_targets.py",
            "tests/benchmarks/batch2_pipeline/test_isolation_and_network.py",
            "tests/ci/test_round6_benchmark_makefile.py",
        ),
        "candidate_pairs": tuple(
            {"implementation": implementation, "test": test}
            for implementation, tests in {
                "tools/benchmarks/__init__.py": (
                    "tests/benchmarks/batch2_pipeline/test_cli_and_reporting.py",
                    "tests/benchmarks/batch2_pipeline/test_failure_modes.py",
                    "tests/benchmarks/batch2_pipeline/test_governance_compile.py",
                    "tests/benchmarks/batch2_pipeline/test_harness_and_targets.py",
                    "tests/benchmarks/batch2_pipeline/test_isolation_and_network.py",
                ),
                "tools/benchmarks/batch2_pipeline/__init__.py": (
                    "tests/benchmarks/batch2_pipeline/test_cli_and_reporting.py",
                    "tests/benchmarks/batch2_pipeline/test_failure_modes.py",
                    "tests/benchmarks/batch2_pipeline/test_governance_compile.py",
                    "tests/benchmarks/batch2_pipeline/test_harness_and_targets.py",
                    "tests/benchmarks/batch2_pipeline/test_isolation_and_network.py",
                ),
                "tools/benchmarks/batch2_pipeline/budgets.py": (
                    "tests/benchmarks/batch2_pipeline/test_cli_and_reporting.py",
                    "tests/benchmarks/batch2_pipeline/test_failure_modes.py",
                    "tests/benchmarks/batch2_pipeline/test_governance_compile.py",
                    "tests/benchmarks/batch2_pipeline/test_harness_and_targets.py",
                    "tests/benchmarks/batch2_pipeline/test_isolation_and_network.py",
                ),
                "tools/benchmarks/batch2_pipeline/fixtures.py": (
                    "tests/benchmarks/batch2_pipeline/test_cli_and_reporting.py",
                    "tests/benchmarks/batch2_pipeline/test_failure_modes.py",
                    "tests/benchmarks/batch2_pipeline/test_governance_compile.py",
                    "tests/benchmarks/batch2_pipeline/test_harness_and_targets.py",
                    "tests/benchmarks/batch2_pipeline/test_isolation_and_network.py",
                ),
                "tools/benchmarks/batch2_pipeline/harness.py": (
                    "tests/benchmarks/batch2_pipeline/test_cli_and_reporting.py",
                    "tests/benchmarks/batch2_pipeline/test_failure_modes.py",
                    "tests/benchmarks/batch2_pipeline/test_governance_compile.py",
                    "tests/benchmarks/batch2_pipeline/test_harness_and_targets.py",
                    "tests/benchmarks/batch2_pipeline/test_isolation_and_network.py",
                ),
                "tools/benchmarks/batch2_pipeline/reporting.py": (
                    "tests/benchmarks/batch2_pipeline/test_cli_and_reporting.py",
                ),
                "tools/benchmarks/batch2_pipeline/schema.py": (
                    "tests/benchmarks/batch2_pipeline/test_cli_and_reporting.py",
                    "tests/benchmarks/batch2_pipeline/test_governance_compile.py",
                    "tests/benchmarks/batch2_pipeline/test_harness_and_targets.py",
                    "tests/benchmarks/batch2_pipeline/test_isolation_and_network.py",
                ),
                "tools/benchmarks/batch2_pipeline/telemetry.py": (
                    "tests/benchmarks/batch2_pipeline/test_cli_and_reporting.py",
                    "tests/benchmarks/batch2_pipeline/test_failure_modes.py",
                    "tests/benchmarks/batch2_pipeline/test_governance_compile.py",
                    "tests/benchmarks/batch2_pipeline/test_harness_and_targets.py",
                    "tests/benchmarks/batch2_pipeline/test_isolation_and_network.py",
                ),
                "tools/benchmarks/batch2_pipeline/validator.py": (
                    "tests/benchmarks/batch2_pipeline/test_cli_and_reporting.py",
                    "tests/benchmarks/batch2_pipeline/test_isolation_and_network.py",
                ),
                "tools/benchmarks/batch2_pipeline/workloads.py": (
                    "tests/benchmarks/batch2_pipeline/test_cli_and_reporting.py",
                    "tests/benchmarks/batch2_pipeline/test_failure_modes.py",
                    "tests/benchmarks/batch2_pipeline/test_governance_compile.py",
                    "tests/benchmarks/batch2_pipeline/test_harness_and_targets.py",
                    "tests/benchmarks/batch2_pipeline/test_isolation_and_network.py",
                ),
                "scripts/benchmark_batch2_pipeline.py": (
                    "tests/benchmarks/batch2_pipeline/test_cli_and_reporting.py",
                    "tests/benchmarks/batch2_pipeline/test_isolation_and_network.py",
                ),
            }.items()
            for test in tests
        ) + (
            {
                "implementation": "tools/benchmarks/batch2_pipeline/Makefile",
                "test": "tests/ci/test_round6_benchmark_makefile.py",
            },
        ),
        "implementation_roots": (
            "tools/benchmarks/batch2_pipeline/",
            "tools/benchmarks/__init__.py",
            "scripts/benchmark_batch2_pipeline.py",
        ),
        "test_roots": (
            "tests/benchmarks/batch2_pipeline/",
        ),
        "candidate_test_roots": (
            "tests/benchmarks/batch2_pipeline/",
        ),
    },
    "release_readiness_security": {
        "triggers": (
            "tools/release_readiness/batch2_security/",
            "scripts/run_batch2_security_audit.py",
            "tests/release_readiness/batch2_security/",
        ),
        "tests": (
            "tests/release_readiness/batch2_security/test_artifact_states.py",
            "tests/release_readiness/batch2_security/test_evidence_boundary.py",
            "tests/release_readiness/batch2_security/test_finite_json.py",
            "tests/release_readiness/batch2_security/test_network_policy.py",
            "tests/release_readiness/batch2_security/test_path_containment.py",
            "tests/release_readiness/batch2_security/test_static_scan.py",
            "tests/release_readiness/batch2_security/test_subprocess_isolation.py",
            "tests/release_readiness/batch2_security/test_suite_and_governance.py",
        ),
        "candidate_pairs": tuple(
            {"implementation": implementation, "test": test}
            for implementation, tests in {
                "tools/release_readiness/batch2_security/artifact_states.py": (
                    "tests/release_readiness/batch2_security/test_artifact_states.py",
                ),
                "tools/release_readiness/batch2_security/evidence_boundary.py": (
                    "tests/release_readiness/batch2_security/test_evidence_boundary.py",
                ),
                "tools/release_readiness/batch2_security/finite_json.py": (
                    "tests/release_readiness/batch2_security/test_finite_json.py",
                ),
                "tools/release_readiness/batch2_security/network_policy.py": (
                    "tests/release_readiness/batch2_security/test_network_policy.py",
                ),
                "tools/release_readiness/batch2_security/path_containment.py": (
                    "tests/release_readiness/batch2_security/test_path_containment.py",
                ),
                "tools/release_readiness/batch2_security/static_scan.py": (
                    "tests/release_readiness/batch2_security/test_static_scan.py",
                ),
                "tools/release_readiness/batch2_security/subprocess_guard.py": (
                    "tests/release_readiness/batch2_security/test_subprocess_isolation.py",
                ),
                "tools/release_readiness/batch2_security/report.py": (
                    "tests/release_readiness/batch2_security/test_suite_and_governance.py",
                ),
                "tools/release_readiness/batch2_security/runner.py": (
                    "tests/release_readiness/batch2_security/test_suite_and_governance.py",
                ),
                "scripts/run_batch2_security_audit.py": (
                    "tests/release_readiness/batch2_security/test_suite_and_governance.py",
                ),
                # The schema is exercised by every focused suite module.
                "tools/release_readiness/batch2_security/schema.py": (
                    "tests/release_readiness/batch2_security/test_artifact_states.py",
                    "tests/release_readiness/batch2_security/test_evidence_boundary.py",
                    "tests/release_readiness/batch2_security/test_finite_json.py",
                    "tests/release_readiness/batch2_security/test_network_policy.py",
                    "tests/release_readiness/batch2_security/test_path_containment.py",
                    "tests/release_readiness/batch2_security/test_static_scan.py",
                    "tests/release_readiness/batch2_security/test_subprocess_isolation.py",
                    "tests/release_readiness/batch2_security/test_suite_and_governance.py",
                ),
                "tools/release_readiness/batch2_security/fixtures.py": (
                    "tests/release_readiness/batch2_security/test_artifact_states.py",
                    "tests/release_readiness/batch2_security/test_evidence_boundary.py",
                    "tests/release_readiness/batch2_security/test_finite_json.py",
                    "tests/release_readiness/batch2_security/test_network_policy.py",
                    "tests/release_readiness/batch2_security/test_static_scan.py",
                ),
            }.items()
            for test in tests
        ),
        "support_files": {
            "tests/release_readiness/batch2_security/conftest.py": (
                "tests/release_readiness/batch2_security/test_artifact_states.py",
                "tests/release_readiness/batch2_security/test_evidence_boundary.py",
                "tests/release_readiness/batch2_security/test_finite_json.py",
                "tests/release_readiness/batch2_security/test_network_policy.py",
                "tests/release_readiness/batch2_security/test_path_containment.py",
                "tests/release_readiness/batch2_security/test_static_scan.py",
                "tests/release_readiness/batch2_security/test_subprocess_isolation.py",
                "tests/release_readiness/batch2_security/test_suite_and_governance.py",
            ),
        },
        "implementation_roots": (
            "tools/release_readiness/batch2_security/",
            "scripts/run_batch2_security_audit.py",
        ),
        "candidate_test_roots": ("tests/release_readiness/batch2_security/",),
    },
    "source_mining_evidence_boundary": {
        "triggers": (
            "tools/evidence_promotion_gate/adapters.py",
            "tools/evidence_promotion_gate/evaluator.py",
            "tools/public_repo_harvest/schema.py",
            "tests/source_mining_integration/test_source_mining_evidence_boundary.py",
        ),
        "tests": (
            "tests/source_mining_integration/test_source_mining_evidence_boundary.py",
        ),
        "candidate_pairs": (
            {
                "implementation": "tools/evidence_promotion_gate/adapters.py",
                "test": "tests/source_mining_integration/test_source_mining_evidence_boundary.py",
            },
            {
                "implementation": "tools/evidence_promotion_gate/evaluator.py",
                "test": "tests/source_mining_integration/test_source_mining_evidence_boundary.py",
            },
            {
                "implementation": "tools/public_repo_harvest/schema.py",
                "test": "tests/source_mining_integration/test_source_mining_evidence_boundary.py",
            },
        ),
        "implementation_roots": (
            "tools/evidence_promotion_gate/adapters.py",
            "tools/evidence_promotion_gate/evaluator.py",
            "tools/public_repo_harvest/schema.py",
        ),
        "candidate_test_roots": (
            "tests/source_mining_integration/test_source_mining_evidence_boundary.py",
        ),
    },
    "measurement_hypothesis_contract": {
        "triggers": (
            "shared/measurement_hypothesis/",
            "tools/research_claim_gate/gate.py",
            "tests/research_claim_gate/test_claim_gate.py",
            "tests/measurement_hypothesis/",
        ),
        "tests": (
            "tests/measurement_hypothesis/test_boundary_regressions.py",
            "tests/measurement_hypothesis/test_five_level_contract.py",
            "tests/measurement_hypothesis/test_gate_reference_and_promotion.py",
            "tests/measurement_hypothesis/test_implementation_resolution.py",
            "tests/measurement_hypothesis/test_interpretation_language.py",
            "tests/measurement_hypothesis/test_measurement_and_operator.py",
            "tests/measurement_hypothesis/test_namespace_and_renaming.py",
            "tests/measurement_hypothesis/test_provenance_and_sources.py",
            "tests/measurement_hypothesis/test_valid_hypothetical_mapping.py",
            "tests/research_claim_gate/test_claim_gate.py",
        ),
        "candidate_pairs": tuple(
            {"implementation": implementation, "test": test}
            for implementation in (
                "shared/measurement_hypothesis/validate.py",
                "shared/measurement_hypothesis/schema.py",
                "shared/measurement_hypothesis/resolve.py",
                "shared/measurement_hypothesis/language.py",
            )
            for test in (
                "tests/measurement_hypothesis/test_boundary_regressions.py",
                "tests/measurement_hypothesis/test_five_level_contract.py",
                "tests/measurement_hypothesis/test_gate_reference_and_promotion.py",
                "tests/measurement_hypothesis/test_implementation_resolution.py",
                "tests/measurement_hypothesis/test_interpretation_language.py",
                "tests/measurement_hypothesis/test_measurement_and_operator.py",
                "tests/measurement_hypothesis/test_namespace_and_renaming.py",
                "tests/measurement_hypothesis/test_provenance_and_sources.py",
                "tests/measurement_hypothesis/test_valid_hypothetical_mapping.py",
            )
        ) + (
            {
                "implementation": "shared/measurement_hypothesis/__main__.py",
                "test": "tests/measurement_hypothesis/test_gate_reference_and_promotion.py",
            },
            {
                "implementation": "tools/research_claim_gate/gate.py",
                "test": "tests/measurement_hypothesis/test_valid_hypothetical_mapping.py",
            },
            {
                "implementation": "tools/research_claim_gate/gate.py",
                "test": "tests/research_claim_gate/test_claim_gate.py",
            },
        ),
        "support_files": {
            "tests/measurement_hypothesis/conftest.py": (
                "tests/measurement_hypothesis/test_boundary_regressions.py",
                "tests/measurement_hypothesis/test_five_level_contract.py",
                "tests/measurement_hypothesis/test_gate_reference_and_promotion.py",
                "tests/measurement_hypothesis/test_implementation_resolution.py",
                "tests/measurement_hypothesis/test_interpretation_language.py",
                "tests/measurement_hypothesis/test_measurement_and_operator.py",
                "tests/measurement_hypothesis/test_namespace_and_renaming.py",
                "tests/measurement_hypothesis/test_provenance_and_sources.py",
                "tests/measurement_hypothesis/test_valid_hypothetical_mapping.py",
            ),
            "tests/measurement_hypothesis/fixtures/empirical_support_implied.json": (
                "tests/measurement_hypothesis/test_interpretation_language.py",
            ),
            "tests/measurement_hypothesis/fixtures/missing_provenance.json": (
                "tests/measurement_hypothesis/test_provenance_and_sources.py",
            ),
            "tests/measurement_hypothesis/fixtures/origin_shift_cortical_wave_equivalence.json": (
                "tests/measurement_hypothesis/test_boundary_regressions.py",
            ),
            "tests/measurement_hypothesis/fixtures/theory_term_leak.json": (
                "tests/measurement_hypothesis/test_namespace_and_renaming.py",
            ),
            "tests/measurement_hypothesis/fixtures/valid_hypothetical_mapping.json": (
                "tests/measurement_hypothesis/test_boundary_regressions.py",
                "tests/measurement_hypothesis/test_five_level_contract.py",
                "tests/measurement_hypothesis/test_gate_reference_and_promotion.py",
                "tests/measurement_hypothesis/test_implementation_resolution.py",
                "tests/measurement_hypothesis/test_interpretation_language.py",
                "tests/measurement_hypothesis/test_measurement_and_operator.py",
                "tests/measurement_hypothesis/test_namespace_and_renaming.py",
                "tests/measurement_hypothesis/test_provenance_and_sources.py",
                "tests/measurement_hypothesis/test_valid_hypothetical_mapping.py",
            ),
        },
        "implementation_roots": (
            "shared/measurement_hypothesis/",
            "tools/research_claim_gate/gate.py",
        ),
        "candidate_test_roots": (
            "tests/measurement_hypothesis/",
            "tests/research_claim_gate/test_claim_gate.py",
        ),
    },
    "dandi_nwb_bounded": {
        "triggers": (
            "data/dandi_nwb_ingest.py",
            "tools/stream_process_dandi000458.py",
            "tests/data_access/dandi_nwb_bounded/",
        ),
        "implementation_any": (
            "data/dandi_nwb_ingest.py",
            "tools/stream_process_dandi000458.py",
        ),
        "tests": (
            "tests/data_access/dandi_nwb_bounded/test_dandi_nwb_bounded_contract.py",
            "tests/data_access/dandi_nwb_bounded/test_isolation_and_network.py",
            "tests/data_access/dandi_nwb_bounded/test_nwb_local_fixture.py",
        ),
        "candidate_pairs": (
            {"implementation": "data/dandi_nwb_ingest.py", "test": "tests/data_access/dandi_nwb_bounded/test_dandi_nwb_bounded_contract.py"},
            {"implementation": "data/dandi_nwb_ingest.py", "test": "tests/data_access/dandi_nwb_bounded/test_isolation_and_network.py"},
            {"implementation": "data/dandi_nwb_ingest.py", "test": "tests/data_access/dandi_nwb_bounded/test_nwb_local_fixture.py"},
            {"implementation": "tools/stream_process_dandi000458.py", "test": "tests/data_access/dandi_nwb_bounded/test_dandi_nwb_bounded_contract.py"},
            {"implementation": "tools/stream_process_dandi000458.py", "test": "tests/data_access/dandi_nwb_bounded/test_isolation_and_network.py"},
        ),
        "support_files": {
            "tests/data_access/dandi_nwb_bounded/__init__.py": (
                "tests/data_access/dandi_nwb_bounded/test_dandi_nwb_bounded_contract.py",
                "tests/data_access/dandi_nwb_bounded/test_isolation_and_network.py",
                "tests/data_access/dandi_nwb_bounded/test_nwb_local_fixture.py",
            ),
        },
        "implementation_roots": (
            "data/dandi_nwb_ingest.py",
            "tools/stream_process_dandi000458.py",
        ),
        "candidate_test_roots": ("tests/data_access/dandi_nwb_bounded/",),
    },
    "streaming_s3_transfer": {
        "triggers": (
            "tools/streaming/base_runner.py",
            "tests/streaming/test_sync_s3_subject_fail_closed.py",
            "tests/performance/streaming_optimization/test_s3_transfers.py",
        ),
        "implementation": "tools/streaming/base_runner.py",
        "tests": (
            "tests/streaming/test_sync_s3_subject_fail_closed.py",
            "tests/performance/streaming_optimization/test_s3_transfers.py",
        ),
        "candidate_pairs": (
            {"implementation": "tools/streaming/base_runner.py", "test": "tests/streaming/test_sync_s3_subject_fail_closed.py"},
            {"implementation": "tools/streaming/base_runner.py", "test": "tests/performance/streaming_optimization/test_s3_transfers.py"},
        ),
        "support_files": {
            "tests/streaming/conftest.py": (
                "tests/streaming/test_sync_s3_subject_fail_closed.py",
            ),
            "tests/performance/streaming_optimization/conftest.py": (
                "tests/performance/streaming_optimization/test_s3_transfers.py",
            ),
        },
        "implementation_roots": ("tools/streaming/base_runner.py",),
        "candidate_test_roots": (
            "tests/streaming/test_sync_s3_subject_fail_closed.py",
            "tests/performance/streaming_optimization/test_s3_transfers.py",
        ),
    },
    "ds005620_cohort_stream": {
        "triggers": (
            "tools/stream_pitnn_cohort_ds005620.py",
            "tests/test_pitnn_cohort_ds005620.py",
        ),
        "implementation": "tools/stream_pitnn_cohort_ds005620.py",
        "tests": ("tests/test_pitnn_cohort_ds005620.py",),
        "candidate_pairs": (
            {
                "implementation": "tools/stream_pitnn_cohort_ds005620.py",
                "test": "tests/test_pitnn_cohort_ds005620.py",
            },
        ),
        "implementation_roots": ("tools/stream_pitnn_cohort_ds005620.py",),
        "candidate_test_roots": ("tests/test_pitnn_cohort_ds005620.py",),
    },
    "moabb_protocol_conformance": {
        "triggers": (
            "tools/moabb_protocol_conformance/",
            "tests/tools/moabb_protocol_conformance/",
        ),
        "implementation_any": (
            "tools/moabb_protocol_conformance/__main__.py",
            "tools/moabb_protocol_conformance/leakage.py",
            "tools/moabb_protocol_conformance/manifest.py",
            "tools/moabb_protocol_conformance/metadata.py",
            "tools/moabb_protocol_conformance/schema.py",
            "tools/moabb_protocol_conformance/serialization.py",
            "tools/moabb_protocol_conformance/upstream.py",
            "tools/moabb_protocol_conformance/validation.py",
        ),
        "tests": ("tests/tools/moabb_protocol_conformance/test_manifest_and_validation.py",),
        "candidate_pairs": tuple(
            {
                "implementation": path,
                "test": "tests/tools/moabb_protocol_conformance/test_manifest_and_validation.py",
            }
            for path in (
                "tools/moabb_protocol_conformance/__main__.py",
                "tools/moabb_protocol_conformance/leakage.py",
                "tools/moabb_protocol_conformance/manifest.py",
                "tools/moabb_protocol_conformance/metadata.py",
                "tools/moabb_protocol_conformance/schema.py",
                "tools/moabb_protocol_conformance/serialization.py",
                "tools/moabb_protocol_conformance/upstream.py",
                "tools/moabb_protocol_conformance/validation.py",
            )
        ),
        "support_files": {
            "tools/moabb_protocol_conformance/fixtures/moabb_metadata_fixture.json": (
                "tests/tools/moabb_protocol_conformance/test_manifest_and_validation.py",
            ),
            "tools/moabb_protocol_conformance/fixtures/protocol_conforming.json": (
                "tests/tools/moabb_protocol_conformance/test_manifest_and_validation.py",
            ),
            "tools/moabb_protocol_conformance/fixtures/protocol_leaky.json": (
                "tests/tools/moabb_protocol_conformance/test_manifest_and_validation.py",
            ),
        },
        "implementation_roots": ("tools/moabb_protocol_conformance/",),
        "candidate_test_roots": ("tests/tools/moabb_protocol_conformance/",),
    },
    "mne_signal_blocks": {
        "triggers": (
            "adapters/mne_signal_blocks/",
            "tests/adapters/mne_signal_blocks/",
        ),
        "implementation_any": (
            "adapters/mne_signal_blocks/converter.py",
            "adapters/mne_signal_blocks/fixtures.py",
            "adapters/mne_signal_blocks/reporting.py",
            "adapters/mne_signal_blocks/schema.py",
            "adapters/mne_signal_blocks/validate.py",
        ),
        "tests": ("tests/adapters/mne_signal_blocks/test_mne_signal_blocks.py",),
        "candidate_pairs": tuple(
            {
                "implementation": path,
                "test": "tests/adapters/mne_signal_blocks/test_mne_signal_blocks.py",
            }
            for path in (
                "adapters/mne_signal_blocks/converter.py",
                "adapters/mne_signal_blocks/fixtures.py",
                "adapters/mne_signal_blocks/reporting.py",
                "adapters/mne_signal_blocks/schema.py",
                "adapters/mne_signal_blocks/validate.py",
            )
        ),
        "implementation_roots": ("adapters/mne_signal_blocks/",),
        "candidate_test_roots": ("tests/adapters/mne_signal_blocks/",),
        "external_test_paths": {
            "tests/adapters/mne_signal_blocks/test_mne_signal_blocks.py": "optional-eeg-suite",
        },
        # The CPU/base runner exercises pure contract cases without converting
        # unavailable optional MNE bridge cases into skips. The full bridge
        # cases remain separately owned by the optional EEG profile.
        "test_markers": {
            "tests/adapters/mne_signal_blocks/test_mne_signal_blocks.py": "not requires_mne",
        },
    },
    "mne_csd_adapter": {
        "triggers": (
            "adapters/mne_csd/",
            "tests/adapters/mne_csd/",
        ),
        "tests": (
            "tests/adapters/mne_csd/test_governance_and_availability.py",
            "tests/adapters/mne_csd/test_optional_mne_integration.py",
            "tests/adapters/mne_csd/test_parameter_forwarding.py",
            "tests/adapters/mne_csd/test_preconditions.py",
            "tests/adapters/mne_csd/test_provenance_and_units.py",
        ),
        "candidate_pairs": tuple(
            {"implementation": implementation, "test": test}
            for implementation, tests in {
                "adapters/mne_csd/__init__.py": (
                    "tests/adapters/mne_csd/test_governance_and_availability.py",
                    "tests/adapters/mne_csd/test_parameter_forwarding.py",
                    "tests/adapters/mne_csd/test_preconditions.py",
                    "tests/adapters/mne_csd/test_provenance_and_units.py",
                ),
                "adapters/mne_csd/constants.py": (
                    "tests/adapters/mne_csd/test_parameter_forwarding.py",
                    "tests/adapters/mne_csd/test_provenance_and_units.py",
                ),
                "adapters/mne_csd/errors.py": (
                    "tests/adapters/mne_csd/test_governance_and_availability.py",
                    "tests/adapters/mne_csd/test_parameter_forwarding.py",
                    "tests/adapters/mne_csd/test_preconditions.py",
                ),
                "adapters/mne_csd/preconditions.py": (
                    "tests/adapters/mne_csd/test_parameter_forwarding.py",
                    "tests/adapters/mne_csd/test_preconditions.py",
                    "tests/adapters/mne_csd/test_provenance_and_units.py",
                ),
                "adapters/mne_csd/provenance.py": (
                    "tests/adapters/mne_csd/test_governance_and_availability.py",
                    "tests/adapters/mne_csd/test_parameter_forwarding.py",
                    "tests/adapters/mne_csd/test_provenance_and_units.py",
                ),
                "adapters/mne_csd/transform.py": (
                    "tests/adapters/mne_csd/test_governance_and_availability.py",
                    "tests/adapters/mne_csd/test_parameter_forwarding.py",
                    "tests/adapters/mne_csd/test_preconditions.py",
                    "tests/adapters/mne_csd/test_provenance_and_units.py",
                ),
            }.items()
            for test in tests
        ) + tuple(
            {
                "implementation": implementation,
                "test": "tests/adapters/mne_csd/test_optional_mne_integration.py",
            }
            for implementation in (
                "adapters/mne_csd/__init__.py",
                "adapters/mne_csd/constants.py",
                "adapters/mne_csd/errors.py",
                "adapters/mne_csd/preconditions.py",
                "adapters/mne_csd/provenance.py",
                "adapters/mne_csd/transform.py",
            )
        ),
        "support_files": {
            "tests/adapters/mne_csd/conftest.py": (
                "tests/adapters/mne_csd/test_governance_and_availability.py",
                "tests/adapters/mne_csd/test_parameter_forwarding.py",
                "tests/adapters/mne_csd/test_preconditions.py",
                "tests/adapters/mne_csd/test_provenance_and_units.py",
            ),
        },
        "implementation_roots": ("adapters/mne_csd/",),
        "candidate_test_roots": ("tests/adapters/mne_csd/",),
        # The file imports MNE at collection time. Keep it out of the CPU
        # candidate run and execute it only in the existing installed EEG job.
        "external_test_paths": {
            "tests/adapters/mne_csd/test_optional_mne_integration.py": "optional-eeg-suite",
        },
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
    "finite_jitter_production_bridge": {
        "triggers": (
            "tools/audit_finite_jitter_triangulation.py",
            "tests/test_finite_jitter_production_import.py",
        ),
        "tests": ("tests/test_finite_jitter_production_import.py",),
        "candidate_pairs": (
            {
                "implementation": "tools/audit_finite_jitter_triangulation.py",
                "test": "tests/test_finite_jitter_production_import.py",
            },
        ),
        "implementation_roots": ("tools/audit_finite_jitter_triangulation.py",),
        "candidate_test_roots": ("tests/test_finite_jitter_production_import.py",),
    },
    "bids_adapter": {
        "triggers": (
            "data/bids_ingest.py",
            "data/openneuro_loader.py",
            "tests/data_access/bids_adapter/test_bids_adapter.py",
        ),
        "implementation_any": (
            "data/bids_ingest.py",
            "data/openneuro_loader.py",
        ),
        "tests": ("tests/data_access/bids_adapter/test_bids_adapter.py",),
        "candidate_pairs": tuple(
            {
                "implementation": implementation,
                "test": "tests/data_access/bids_adapter/test_bids_adapter.py",
            }
            for implementation in (
                "data/bids_ingest.py",
                "data/openneuro_loader.py",
            )
        ),
        "support_files": {
            path: ("tests/data_access/bids_adapter/test_bids_adapter.py",)
            for path in (
                "tests/data_access/bids_adapter/fixtures/condition_manifest_ambiguous.json",
                "tests/data_access/bids_adapter/fixtures/condition_manifest_ok.json",
                "tests/data_access/bids_adapter/fixtures/invalid_bids/README",
                "tests/data_access/bids_adapter/fixtures/missing_entities/dataset_description.json",
                "tests/data_access/bids_adapter/fixtures/missing_entities/sub-01/eeg/sub-01_task-rest_eeg.edf",
                "tests/data_access/bids_adapter/fixtures/valid_bids/dataset_description.json",
                "tests/data_access/bids_adapter/fixtures/valid_bids/participants.tsv",
                "tests/data_access/bids_adapter/fixtures/valid_bids/sub-01/eeg/sub-01_task-rest_run-01_channels.tsv",
                "tests/data_access/bids_adapter/fixtures/valid_bids/sub-01/eeg/sub-01_task-rest_run-01_eeg.edf",
                "tests/data_access/bids_adapter/fixtures/valid_bids/sub-01/eeg/sub-01_task-rest_run-01_eeg.json",
            )
        },
        "implementation_roots": (
            "data/bids_ingest.py",
            "data/openneuro_loader.py",
        ),
        "candidate_test_roots": (
            "tests/data_access/bids_adapter/test_bids_adapter.py",
        ),
    },
    "level_t_missingness": {
        "triggers": (
            "sciencer_d/btc_icft/level_t/base_real_topology.py",
            "tests/btc_icft/test_ds001787_t_real_topology.py",
            "tests/btc_icft/test_ds003816_t_real_topology.py",
            "tests/btc_icft/test_ds003969_t_real_topology.py",
            "tests/btc_icft/test_ds005620_t_real_topology.py",
            "tests/test_base_real_topology_missingness.py",
            "tests/test_cohort_missingness.py",
        ),
        "implementation": "sciencer_d/btc_icft/level_t/base_real_topology.py",
        "tests": (
            "tests/btc_icft/test_ds001787_t_real_topology.py",
            "tests/btc_icft/test_ds003816_t_real_topology.py",
            "tests/btc_icft/test_ds003969_t_real_topology.py",
            "tests/btc_icft/test_ds005620_t_real_topology.py",
            "tests/test_base_real_topology_missingness.py",
            "tests/test_cohort_missingness.py",
        ),
        "candidate_pairs": tuple(
            {
                "implementation": "sciencer_d/btc_icft/level_t/base_real_topology.py",
                "test": test_path,
            }
            for test_path in (
                "tests/btc_icft/test_ds001787_t_real_topology.py",
                "tests/btc_icft/test_ds003816_t_real_topology.py",
                "tests/btc_icft/test_ds003969_t_real_topology.py",
                "tests/btc_icft/test_ds005620_t_real_topology.py",
                "tests/test_base_real_topology_missingness.py",
                "tests/test_cohort_missingness.py",
            )
        ),
        "implementation_roots": (
            "sciencer_d/btc_icft/level_t/base_real_topology.py",
        ),
        "candidate_test_roots": (
            "tests/btc_icft/test_ds001787_t_real_topology.py",
            "tests/btc_icft/test_ds003816_t_real_topology.py",
            "tests/btc_icft/test_ds003969_t_real_topology.py",
            "tests/btc_icft/test_ds005620_t_real_topology.py",
            "tests/test_base_real_topology_missingness.py",
            "tests/test_cohort_missingness.py",
        ),
    },
    "batch3_source_registry": {
        "triggers": (
            "configs/research/batch3_source_registry.yaml",
            "tests/research/test_batch3_source_registry.py",
        ),
        "implementation": "configs/research/batch3_source_registry.yaml",
        "tests": ("tests/research/test_batch3_source_registry.py",),
        "candidate_pairs": (
            {
                "implementation": "configs/research/batch3_source_registry.yaml",
                "test": "tests/research/test_batch3_source_registry.py",
            },
        ),
        "implementation_roots": ("configs/research/batch3_source_registry.yaml",),
        "candidate_test_roots": ("tests/research/test_batch3_source_registry.py",),
    },
    # These candidate pairs are declarative artifacts, not production modules.
    # Their dedicated tests validate the exact artifact contract without
    # promoting the artifact into scientific evidence or PASS.
    "batch3_claim_matrix_artifact": {
        "triggers": (
            "reports/batch3/grok_chat_a/claim_matrix.json",
            "tests/research/batch3/test_claim_matrix.py",
        ),
        "implementation": "reports/batch3/grok_chat_a/claim_matrix.json",
        "tests": ("tests/research/batch3/test_claim_matrix.py",),
        "candidate_pairs": (
            {
                "implementation": "reports/batch3/grok_chat_a/claim_matrix.json",
                "test": "tests/research/batch3/test_claim_matrix.py",
            },
        ),
        "implementation_roots": ("reports/batch3/grok_chat_a/claim_matrix.json",),
        "candidate_test_roots": ("tests/research/batch3/test_claim_matrix.py",),
    },
    # Declarative research artifacts are admitted only when their dedicated
    # tests validate the exact checked-in schema/contract. These remain
    # synthetic/review artifacts and do not count as scientific evidence.
    "oss_compatibility_inventory_artifact": {
        "triggers": (
            "docs/oss_compat/compatibility_inventory_20261017.json",
            "tests/oss_compat/test_compatibility_inventory.py",
        ),
        "implementation": "docs/oss_compat/compatibility_inventory_20261017.json",
        "tests": ("tests/oss_compat/test_compatibility_inventory.py",),
        "candidate_pairs": (
            {
                "implementation": "docs/oss_compat/compatibility_inventory_20261017.json",
                "test": "tests/oss_compat/test_compatibility_inventory.py",
            },
        ),
        "implementation_roots": (
            "docs/oss_compat/compatibility_inventory_20261017.json",
        ),
        "candidate_test_roots": ("tests/oss_compat/test_compatibility_inventory.py",),
    },
    "batch3_dataset_feasibility_artifact": {
        "triggers": (
            "docs/research/batch3/replication_dataset_feasibility.md",
            "reports/batch3/grok_chat_b/dataset_candidates.json",
            "tests/research/batch3/test_replication_dataset_feasibility.py",
        ),
        "implementation": "reports/batch3/grok_chat_b/dataset_candidates.json",
        "tests": ("tests/research/batch3/test_replication_dataset_feasibility.py",),
        "candidate_pairs": (
            {
                "implementation": "reports/batch3/grok_chat_b/dataset_candidates.json",
                "test": "tests/research/batch3/test_replication_dataset_feasibility.py",
            },
        ),
        "support_files": {
            "docs/research/batch3/replication_dataset_feasibility.md": (
                "tests/research/batch3/test_replication_dataset_feasibility.py",
            ),
        },
        "implementation_roots": (
            "reports/batch3/grok_chat_b/dataset_candidates.json",
        ),
        "candidate_test_roots": (
            "tests/research/batch3/test_replication_dataset_feasibility.py",
        ),
    },
    "batch3_metadata_audit_artifact": {
        "triggers": (
            "docs/research/batch3/grok_chat_b_dataset_feasibility.md",
            "reports/batch3/grok_chat_b/dataset_candidates_metadata_audit.json",
            "tests/research/batch3/test_dataset_metadata_audit.py",
        ),
        "implementation": "reports/batch3/grok_chat_b/dataset_candidates_metadata_audit.json",
        "tests": ("tests/research/batch3/test_dataset_metadata_audit.py",),
        "candidate_pairs": (
            {
                "implementation": "reports/batch3/grok_chat_b/dataset_candidates_metadata_audit.json",
                "test": "tests/research/batch3/test_dataset_metadata_audit.py",
            },
        ),
        "support_files": {
            "docs/research/batch3/grok_chat_b_dataset_feasibility.md": (
                "tests/research/batch3/test_dataset_metadata_audit.py",
            ),
        },
        "implementation_roots": (
            "reports/batch3/grok_chat_b/dataset_candidates_metadata_audit.json",
        ),
        "candidate_test_roots": (
            "tests/research/batch3/test_dataset_metadata_audit.py",
        ),
    },
    # PR #357 changes these code/test pairs alongside the claim-gate work.
    # Keep each production source paired with the tests that import/exercise it;
    # source-only edits still select their unchanged companion tests.
    "empirical_higher_order": {
        "triggers": (
            "analysis/empirical_higher_order/runner.py",
            "analysis/empirical_higher_order/schema.py",
            "analysis/empirical_higher_order/validation.py",
            "tests/empirical_higher_order/test_runner.py",
        ),
        "implementation": "analysis/empirical_higher_order/runner.py",
        "tests": ("tests/empirical_higher_order/test_runner.py",),
        "candidate_pairs": tuple(
            {
                "implementation": implementation,
                "test": "tests/empirical_higher_order/test_runner.py",
            }
            for implementation in (
                "analysis/empirical_higher_order/runner.py",
                "analysis/empirical_higher_order/schema.py",
                "analysis/empirical_higher_order/validation.py",
            )
        ),
        "implementation_roots": (
            "analysis/empirical_higher_order/runner.py",
            "analysis/empirical_higher_order/schema.py",
            "analysis/empirical_higher_order/validation.py",
        ),
        "candidate_test_roots": ("tests/empirical_higher_order/test_runner.py",),
    },
    "transition_forecasting_benchmark": {
        "triggers": (
            "analysis/transition_forecasting/benchmark.py",
            "scripts/run_transition_benchmark.py",
            "tests/transition_forecasting/test_benchmark.py",
        ),
        "implementation": "analysis/transition_forecasting/benchmark.py",
        "tests": ("tests/transition_forecasting/test_benchmark.py",),
        "candidate_pairs": (
            {
                "implementation": "analysis/transition_forecasting/benchmark.py",
                "test": "tests/transition_forecasting/test_benchmark.py",
            },
            {
                "implementation": "scripts/run_transition_benchmark.py",
                "test": "tests/transition_forecasting/test_benchmark.py",
            },
        ),
        "implementation_roots": (
            "analysis/transition_forecasting/benchmark.py",
            "scripts/run_transition_benchmark.py",
        ),
        "candidate_test_roots": ("tests/transition_forecasting/test_benchmark.py",),
    },
    "release_manifest": {
        "triggers": (
            "tools/release_manifest/manifest_builder.py",
            "tools/release_manifest/merge_state.py",
            "tools/release_manifest/models.py",
            "tools/release_manifest/reporting.py",
            "scripts/build_release_manifest.py",
            "tests/release_manifest/test_build_release_manifest_cli.py",
            "tests/release_manifest/test_manifest_builder.py",
            "tests/release_manifest/test_merge_state.py",
            "tests/release_manifest/test_reporting.py",
        ),
        "implementation": "tools/release_manifest/manifest_builder.py",
        "tests": (
            "tests/release_manifest/test_build_release_manifest_cli.py",
            "tests/release_manifest/test_manifest_builder.py",
            "tests/release_manifest/test_merge_state.py",
            "tests/release_manifest/test_reporting.py",
        ),
        "candidate_pairs": (
            {
                "implementation": "tools/release_manifest/manifest_builder.py",
                "test": "tests/release_manifest/test_manifest_builder.py",
            },
            {
                "implementation": "tools/release_manifest/merge_state.py",
                "test": "tests/release_manifest/test_merge_state.py",
            },
            {
                "implementation": "tools/release_manifest/merge_state.py",
                "test": "tests/release_manifest/test_manifest_builder.py",
            },
            {
                "implementation": "tools/release_manifest/models.py",
                "test": "tests/release_manifest/test_manifest_builder.py",
            },
            {
                "implementation": "tools/release_manifest/models.py",
                "test": "tests/release_manifest/test_merge_state.py",
            },
            {
                "implementation": "tools/release_manifest/models.py",
                "test": "tests/release_manifest/test_reporting.py",
            },
            {
                "implementation": "tools/release_manifest/reporting.py",
                "test": "tests/release_manifest/test_reporting.py",
            },
            {
                "implementation": "tools/release_manifest/reporting.py",
                "test": "tests/release_manifest/test_build_release_manifest_cli.py",
            },
            {
                "implementation": "scripts/build_release_manifest.py",
                "test": "tests/release_manifest/test_build_release_manifest_cli.py",
            },
        ),
        "implementation_roots": (
            "tools/release_manifest/manifest_builder.py",
            "tools/release_manifest/merge_state.py",
            "tools/release_manifest/models.py",
            "tools/release_manifest/reporting.py",
            "scripts/build_release_manifest.py",
        ),
        "candidate_test_roots": (
            "tests/release_manifest/test_build_release_manifest_cli.py",
            "tests/release_manifest/test_manifest_builder.py",
            "tests/release_manifest/test_merge_state.py",
            "tests/release_manifest/test_reporting.py",
        ),
    },
    "oss_adoption_gates": {
        "triggers": (
            "oss_opportunities/opportunity_batch.py",
            "oss_opportunities/license_review.py",
            "oss_opportunities/repository_candidate.py",
            "oss_opportunities/source_ingestion.py",
            "oss_opportunities/scoring.py",
            "oss_opportunities/validation.py",
            "tests/test_oss_license_review.py",
            "tests/test_oss_adoption_gates.py",
            "tests/test_oss_opportunity_batch.py",
            "tests/test_oss_opportunity_scoring.py",
            "tests/test_oss_repository_candidate.py",
            "tests/test_oss_integration_opportunity.py",
        ),
        "implementation": "oss_opportunities/opportunity_batch.py",
        "tests": (
            "tests/test_oss_adoption_gates.py",
            "tests/test_oss_license_review.py",
            "tests/test_oss_opportunity_batch.py",
            "tests/test_oss_opportunity_scoring.py",
            "tests/test_oss_repository_candidate.py",
            "tests/test_oss_integration_opportunity.py",
        ),
        "candidate_pairs": tuple(
            {
                "implementation": implementation,
                "test": test,
            }
            for implementation, test in (
                ("oss_opportunities/opportunity_batch.py", "tests/test_oss_adoption_gates.py"),
                ("oss_opportunities/opportunity_batch.py", "tests/test_oss_opportunity_batch.py"),
                ("oss_opportunities/repository_candidate.py", "tests/test_oss_adoption_gates.py"),
                ("oss_opportunities/repository_candidate.py", "tests/test_oss_repository_candidate.py"),
                ("oss_opportunities/scoring.py", "tests/test_oss_adoption_gates.py"),
                ("oss_opportunities/scoring.py", "tests/test_oss_opportunity_scoring.py"),
                ("oss_opportunities/validation.py", "tests/test_oss_adoption_gates.py"),
                ("oss_opportunities/validation.py", "tests/test_oss_opportunity_scoring.py"),
                ("oss_opportunities/validation.py", "tests/test_oss_integration_opportunity.py"),
                ("oss_opportunities/license_review.py", "tests/test_oss_license_review.py"),
            )
        ),
        # The owner-requested suite includes a license-review regression as a
        # component-level companion, not as a false pair to a changed file.
        "suite_companion_tests": ("tests/test_oss_license_review.py",),
        "implementation_roots": (
            "oss_opportunities/opportunity_batch.py",
            "oss_opportunities/license_review.py",
            "oss_opportunities/repository_candidate.py",
            "oss_opportunities/source_ingestion.py",
            "oss_opportunities/scoring.py",
            "oss_opportunities/validation.py",
        ),
        "candidate_test_roots": (
            "tests/test_oss_adoption_gates.py",
            "tests/test_oss_license_review.py",
            "tests/test_oss_opportunity_batch.py",
            "tests/test_oss_opportunity_scoring.py",
            "tests/test_oss_repository_candidate.py",
            "tests/test_oss_integration_opportunity.py",
        ),
    },
    "whitening_audit": {
        "triggers": (
            "scripts/audit_round6_whitening.py",
            "tools/whitening_audit/audit_reporter.py",
            "tools/whitening_audit/leakage_detector.py",
            "tools/whitening_audit/matrix_ops.py",
            "tools/whitening_audit/synthetic_data.py",
            "tools/whitening_audit/types.py",
            "tools/whitening_audit/whitening_verifier.py",
            "tools/whitening_audit/__init__.py",
            "tests/whitening_audit/__init__.py",
            "tests/whitening_audit/test_whitening_audit.py",
        ),
        "implementation": "tools/whitening_audit/whitening_verifier.py",
        "tests": ("tests/whitening_audit/test_whitening_audit.py",),
        "candidate_pairs": tuple(
            {
                "implementation": implementation,
                "test": "tests/whitening_audit/test_whitening_audit.py",
            }
            for implementation in (
                "scripts/audit_round6_whitening.py",
                "tools/whitening_audit/audit_reporter.py",
                "tools/whitening_audit/leakage_detector.py",
                "tools/whitening_audit/matrix_ops.py",
                "tools/whitening_audit/synthetic_data.py",
                "tools/whitening_audit/types.py",
                "tools/whitening_audit/whitening_verifier.py",
            )
        ),
        # These are exact support paths for one suite, not a package-wide
        # initializer rule. Importing the tools package executes its exports.
        "support_files": {
            "tools/whitening_audit/__init__.py": (
                "tests/whitening_audit/test_whitening_audit.py",
            ),
            "tests/whitening_audit/__init__.py": (
                "tests/whitening_audit/test_whitening_audit.py",
            ),
        },
        "implementation_roots": (
            "scripts/audit_round6_whitening.py",
            "tools/whitening_audit/audit_reporter.py",
            "tools/whitening_audit/leakage_detector.py",
            "tools/whitening_audit/matrix_ops.py",
            "tools/whitening_audit/synthetic_data.py",
            "tools/whitening_audit/types.py",
            "tools/whitening_audit/whitening_verifier.py",
            "tools/whitening_audit/__init__.py",
        ),
        "candidate_test_roots": (
            "tests/whitening_audit/test_whitening_audit.py",
            "tests/whitening_audit/__init__.py",
        ),
    },
    "batch3_falsification_matrix_artifact": {
        "triggers": (
            "configs/scientific_falsification/batch3_falsification_matrix.yaml",
            "tests/scientific_falsification/test_batch3_falsification_matrix.py",
        ),
        "implementation": "configs/scientific_falsification/batch3_falsification_matrix.yaml",
        "tests": (
            "tests/scientific_falsification/test_batch3_falsification_matrix.py",
        ),
        "candidate_pairs": (
            {
                "implementation": "configs/scientific_falsification/batch3_falsification_matrix.yaml",
                "test": "tests/scientific_falsification/test_batch3_falsification_matrix.py",
            },
        ),
        "implementation_roots": (
            "configs/scientific_falsification/batch3_falsification_matrix.yaml",
        ),
        "candidate_test_roots": (
            "tests/scientific_falsification/test_batch3_falsification_matrix.py",
        ),
    },
    "batch3_offline_integration": {
        "triggers": (
            "scripts/run_batch3_offline_integration.py",
            "tools/batch3_offline_integration/",
            "tests/tools/batch3_offline_integration/",
        ),
        "implementation": "tools/batch3_offline_integration/runner.py",
        "tests": (
            "tests/tools/batch3_offline_integration/test_offline_integration.py",
        ),
        "candidate_pairs": tuple(
            {
                "implementation": implementation,
                "test": "tests/tools/batch3_offline_integration/test_offline_integration.py",
            }
            for implementation in (
                "scripts/run_batch3_offline_integration.py",
                "tools/batch3_offline_integration/__init__.py",
                "tools/batch3_offline_integration/__main__.py",
                "tools/batch3_offline_integration/allowlist.py",
                "tools/batch3_offline_integration/fixture_producers.py",
                "tools/batch3_offline_integration/guards.py",
                "tools/batch3_offline_integration/runner.py",
                "tools/batch3_offline_integration/schema.py",
                "tools/batch3_offline_integration/serialization.py",
                "tools/batch3_offline_integration/stages.py",
            )
        ),
        "support_files": {
            "tests/tools/batch3_offline_integration/__init__.py": (
                "tests/tools/batch3_offline_integration/test_offline_integration.py",
            ),
            "tools/batch3_offline_integration/fixtures/complete_plan_request.json": (
                "tests/tools/batch3_offline_integration/test_offline_integration.py",
            ),
            "tools/batch3_offline_integration/fixtures/incomplete_plan_request.json": (
                "tests/tools/batch3_offline_integration/test_offline_integration.py",
            ),
            "tools/batch3_offline_integration/fixtures/nonfinite_probe.json": (
                "tests/tools/batch3_offline_integration/test_offline_integration.py",
            ),
            "tools/batch3_offline_integration/fixtures/release_bundle_synthetic.json": (
                "tests/tools/batch3_offline_integration/test_offline_integration.py",
            ),
            "tools/batch3_offline_integration/fixtures/workflow_request.json": (
                "tests/tools/batch3_offline_integration/test_offline_integration.py",
            ),
        },
        "implementation_roots": (
            "scripts/run_batch3_offline_integration.py",
            "tools/batch3_offline_integration/",
        ),
        "candidate_test_roots": ("tests/tools/batch3_offline_integration/",),
    },
    "research_plan_quality_eval": {
        "triggers": (
            "tools/research_plan_quality_eval/",
            "tests/research_plan_quality_eval/",
        ),
        "tests": (
            "tests/research_plan_quality_eval/test_cli.py",
            "tests/research_plan_quality_eval/test_held_out_boundary.py",
            "tests/research_plan_quality_eval/test_isolation.py",
            "tests/research_plan_quality_eval/test_leakage.py",
            "tests/research_plan_quality_eval/test_manifest.py",
            "tests/research_plan_quality_eval/test_records.py",
            "tests/research_plan_quality_eval/test_report.py",
            "tests/research_plan_quality_eval/test_splits.py",
            "tests/research_plan_quality_eval/test_line_endings.py",
        ),
        "candidate_pairs": tuple(
            {"implementation": implementation, "test": test_path}
            for implementation, test_paths in {
                "tools/research_plan_quality_eval/__init__.py": (
                    "tests/research_plan_quality_eval/test_cli.py",
                    "tests/research_plan_quality_eval/test_held_out_boundary.py",
                    "tests/research_plan_quality_eval/test_isolation.py",
                    "tests/research_plan_quality_eval/test_leakage.py",
                    "tests/research_plan_quality_eval/test_manifest.py",
                    "tests/research_plan_quality_eval/test_records.py",
                    "tests/research_plan_quality_eval/test_report.py",
                    "tests/research_plan_quality_eval/test_splits.py",
                ),
                "tools/research_plan_quality_eval/__main__.py": (
                    "tests/research_plan_quality_eval/test_cli.py",
                    "tests/research_plan_quality_eval/test_held_out_boundary.py",
                ),
                "tools/research_plan_quality_eval/errors.py": (
                    "tests/research_plan_quality_eval/test_held_out_boundary.py",
                    "tests/research_plan_quality_eval/test_isolation.py",
                    "tests/research_plan_quality_eval/test_leakage.py",
                    "tests/research_plan_quality_eval/test_manifest.py",
                    "tests/research_plan_quality_eval/test_records.py",
                    "tests/research_plan_quality_eval/test_report.py",
                    "tests/research_plan_quality_eval/test_splits.py",
                    "tests/research_plan_quality_eval/test_line_endings.py",
                ),
                "tools/research_plan_quality_eval/harness.py": (
                    "tests/research_plan_quality_eval/test_cli.py",
                    "tests/research_plan_quality_eval/test_held_out_boundary.py",
                    "tests/research_plan_quality_eval/test_isolation.py",
                    "tests/research_plan_quality_eval/test_manifest.py",
                    "tests/research_plan_quality_eval/test_report.py",
                ),
                "tools/research_plan_quality_eval/isolation.py": (
                    "tests/research_plan_quality_eval/test_held_out_boundary.py",
                    "tests/research_plan_quality_eval/test_isolation.py",
                ),
                "tools/research_plan_quality_eval/leakage.py": (
                    "tests/research_plan_quality_eval/test_leakage.py",
                ),
                "tools/research_plan_quality_eval/manifest.py": (
                    "tests/research_plan_quality_eval/test_cli.py",
                    "tests/research_plan_quality_eval/test_held_out_boundary.py",
                    "tests/research_plan_quality_eval/test_isolation.py",
                    "tests/research_plan_quality_eval/test_manifest.py",
                    "tests/research_plan_quality_eval/test_report.py",
                    "tests/research_plan_quality_eval/test_line_endings.py",
                ),
                "tools/research_plan_quality_eval/records.py": (
                    "tests/research_plan_quality_eval/test_leakage.py",
                    "tests/research_plan_quality_eval/test_line_endings.py",
                    "tests/research_plan_quality_eval/test_records.py",
                    "tests/research_plan_quality_eval/test_splits.py",
                ),
                "tools/research_plan_quality_eval/splits.py": (
                    "tests/research_plan_quality_eval/test_held_out_boundary.py",
                    "tests/research_plan_quality_eval/test_isolation.py",
                    "tests/research_plan_quality_eval/test_leakage.py",
                    "tests/research_plan_quality_eval/test_report.py",
                    "tests/research_plan_quality_eval/test_splits.py",
                ),
            }.items()
            for test_path in test_paths
        ),
        "support_files": {
            path: (
                "tests/research_plan_quality_eval/test_cli.py",
                "tests/research_plan_quality_eval/test_held_out_boundary.py",
                "tests/research_plan_quality_eval/test_isolation.py",
                "tests/research_plan_quality_eval/test_leakage.py",
                "tests/research_plan_quality_eval/test_manifest.py",
                "tests/research_plan_quality_eval/test_records.py",
                "tests/research_plan_quality_eval/test_report.py",
                "tests/research_plan_quality_eval/test_splits.py",
                *(
                    ("tests/research_plan_quality_eval/test_line_endings.py",)
                    if path in (
                        "tools/research_plan_quality_eval/fixtures/v1/manifest.json",
                        "tools/research_plan_quality_eval/fixtures/v1/plans/P01.json",
                    )
                    else ()
                ),
            )
            for path in (
                "tests/research_plan_quality_eval/conftest.py",
                "tools/research_plan_quality_eval/fixtures/v1/labels.json",
                "tools/research_plan_quality_eval/fixtures/v1/manifest.json",
                "tools/research_plan_quality_eval/fixtures/v1/plans/P01.json",
                "tools/research_plan_quality_eval/fixtures/v1/plans/P02.json",
                "tools/research_plan_quality_eval/fixtures/v1/plans/P03.json",
                "tools/research_plan_quality_eval/fixtures/v1/plans/P04.json",
                "tools/research_plan_quality_eval/fixtures/v1/plans/P05.json",
                "tools/research_plan_quality_eval/fixtures/v1/plans/P06.json",
                "tools/research_plan_quality_eval/fixtures/v1/plans/P07.json",
                "tools/research_plan_quality_eval/fixtures/v1/plans/P08.json",
                "tools/research_plan_quality_eval/fixtures/v1/plans/P09.json",
                "tools/research_plan_quality_eval/fixtures/v1/plans/P10.json",
            )
        },
        "implementation_roots": ("tools/research_plan_quality_eval/",),
        "candidate_test_roots": ("tests/research_plan_quality_eval/",),
    },
    "forward_model_contract": {
        "triggers": (
            "dual_engine/forward_model_contract.py",
            "tests/forward_model_contract/",
        ),
        "implementation": "dual_engine/forward_model_contract.py",
        "tests": ("tests/forward_model_contract/test_forward_model_contract.py",),
        "candidate_pairs": (
            {
                "implementation": "dual_engine/forward_model_contract.py",
                "test": "tests/forward_model_contract/test_forward_model_contract.py",
            },
        ),
        "implementation_roots": ("dual_engine/forward_model_contract.py",),
        "candidate_test_roots": ("tests/forward_model_contract/",),
    },
    "nuisance_scenarios": {
        "triggers": (
            "sim/nuisance_scenarios/",
            "tests/nuisance_scenarios/",
        ),
        "tests": (
            "tests/nuisance_scenarios/test_colored_noise.py",
            "tests/nuisance_scenarios/test_config_serialization.py",
            "tests/nuisance_scenarios/test_coordinate_jitter.py",
            "tests/nuisance_scenarios/test_factory_and_grid.py",
            "tests/nuisance_scenarios/test_fail_closed_and_labels.py",
            "tests/nuisance_scenarios/test_seed_reproducibility.py",
            "tests/nuisance_scenarios/test_target_snr.py",
        ),
        "candidate_pairs": tuple(
            {"implementation": implementation, "test": test_path}
            for implementation, test_paths in {
                # The package initializer re-exports the entire public API;
                # each candidate test imports through that package surface.
                "sim/nuisance_scenarios/__init__.py": (
                    "tests/nuisance_scenarios/test_colored_noise.py",
                    "tests/nuisance_scenarios/test_config_serialization.py",
                    "tests/nuisance_scenarios/test_coordinate_jitter.py",
                    "tests/nuisance_scenarios/test_factory_and_grid.py",
                    "tests/nuisance_scenarios/test_fail_closed_and_labels.py",
                    "tests/nuisance_scenarios/test_seed_reproducibility.py",
                    "tests/nuisance_scenarios/test_target_snr.py",
                ),
                "sim/nuisance_scenarios/colored_noise.py": (
                    "tests/nuisance_scenarios/test_colored_noise.py",
                    "tests/nuisance_scenarios/test_seed_reproducibility.py",
                ),
                "sim/nuisance_scenarios/config.py": (
                    "tests/nuisance_scenarios/test_config_serialization.py",
                    "tests/nuisance_scenarios/test_factory_and_grid.py",
                    "tests/nuisance_scenarios/test_fail_closed_and_labels.py",
                    "tests/nuisance_scenarios/test_seed_reproducibility.py",
                ),
                "sim/nuisance_scenarios/factory.py": (
                    "tests/nuisance_scenarios/test_config_serialization.py",
                    "tests/nuisance_scenarios/test_coordinate_jitter.py",
                    "tests/nuisance_scenarios/test_factory_and_grid.py",
                    "tests/nuisance_scenarios/test_fail_closed_and_labels.py",
                    "tests/nuisance_scenarios/test_seed_reproducibility.py",
                ),
                "sim/nuisance_scenarios/jitter.py": (
                    "tests/nuisance_scenarios/test_coordinate_jitter.py",
                    "tests/nuisance_scenarios/test_seed_reproducibility.py",
                ),
                "sim/nuisance_scenarios/models.py": (
                    "tests/nuisance_scenarios/test_factory_and_grid.py",
                ),
                "sim/nuisance_scenarios/snr_mixer.py": (
                    "tests/nuisance_scenarios/test_fail_closed_and_labels.py",
                    "tests/nuisance_scenarios/test_target_snr.py",
                ),
            }.items()
            for test_path in test_paths
        ),
        "implementation_roots": ("sim/nuisance_scenarios/",),
        "candidate_test_roots": ("tests/nuisance_scenarios/",),
    },
}

# Keep the historical spherical-CSD inventory aware of the exact NumPy
# reference-audit tests and their support files. Selection remains source-aware
# above: an audit implementation/test diff runs only mne_csd_reference_audit,
# while a spherical-CSD diff requires only its own source/test pairs.
_spherical_csd_spec = COMPONENTS["spherical_csd"]
_mne_csd_audit_spec = COMPONENTS["mne_csd_reference_audit"]
_mne_audit_external_tests = set(_mne_csd_audit_spec.get("external_test_paths", {}))
_shared_mne_audit_tests = tuple(
    test for test in _mne_csd_audit_spec["tests"]
    if test not in _mne_audit_external_tests
)
_spherical_csd_spec["tests"] = tuple(dict.fromkeys((
    *_spherical_csd_spec["tests"],
    *_shared_mne_audit_tests,
)))
_spherical_csd_pair_ids = {
    (pair["implementation"], pair["test"])
    for pair in _spherical_csd_spec["candidate_pairs"]
}
_spherical_csd_spec["candidate_pairs"] = (
    *_spherical_csd_spec["candidate_pairs"],
    *(
        pair for pair in _mne_csd_audit_spec["candidate_pairs"]
        if pair["test"] in _shared_mne_audit_tests
        and (pair["implementation"], pair["test"]) not in _spherical_csd_pair_ids
    ),
)
for _support_path, _mapped_tests in _mne_csd_audit_spec.get("support_files", {}).items():
    _shared_mapped_tests = tuple(
        test for test in _mapped_tests if test in _shared_mne_audit_tests
    )
    if _shared_mapped_tests:
        _spherical_csd_spec["support_files"][_support_path] = _shared_mapped_tests


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
        "neurotopology_sim/experimental/topology/__init__.py",
        "tests/neurotopology_sim/experimental/topology/__init__.py",
    ),
    "phase_cochain_reference": (
        "experimental/phase_cochain_reference/__init__.py",
        "tests/experimental/phase_cochain_reference/__init__.py",
    ),
    "hodge_decomposition_audit": (
        "tools/hodge_decomposition_audit/__init__.py",
        "tests/tools/hodge_decomposition_audit/__init__.py",
    ),
    "higher_order_runtime": (
        "tools/higher_order_runtime/__init__.py",
        "tests/higher_order_runtime_contract/__init__.py",
    ),
    "synthetic_pipeline_replay": (
        "tools/synthetic_pipeline_replay/__init__.py",
        "tests/integration/synthetic_pipeline_replay/__init__.py",
    ),
    "spherical_csd": (
        "neurotopology_sim/experimental/preprocessing/__init__.py",
        "tests/neurotopology_sim/experimental/preprocessing/__init__.py",
    ),
    "mne_csd_reference_audit": (
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
    ),
    "bids_inventory_audit": (
        "shared/bids_inventory_audit/__init__.py",
        "tests/bids_inventory_audit/__init__.py",
    ),
    "public_repo_source_pack": (),
    "batch2_pipeline_benchmark": (
        "tools/benchmarks/__init__.py",
        "tools/benchmarks/batch2_pipeline/__init__.py",
    ),
    "release_readiness_security": (
        "tools/release_readiness/batch2_security/__init__.py",
        "tests/release_readiness/batch2_security/__init__.py",
    ),
    "measurement_hypothesis_contract": (
        "shared/measurement_hypothesis/__init__.py",
    ),
    "dandi_nwb_bounded": (
        "tests/data_access/dandi_nwb_bounded/__init__.py",
    ),
    "moabb_protocol_conformance": (
        "tools/moabb_protocol_conformance/__init__.py",
        "tests/tools/moabb_protocol_conformance/__init__.py",
    ),
    "mne_signal_blocks": (
        "adapters/mne_signal_blocks/__init__.py",
        "tests/adapters/mne_signal_blocks/__init__.py",
    ),
    "mne_csd_adapter": (
        "adapters/mne_csd/__init__.py",
        "tests/adapters/mne_csd/__init__.py",
    ),
    "bids_adapter": (
        "tests/data_access/bids_adapter/__init__.py",
    ),
    "research_plan_quality_eval": (
        "tools/research_plan_quality_eval/__init__.py",
        "tests/research_plan_quality_eval/__init__.py",
    ),
    "forward_model_contract": (
        "tests/forward_model_contract/__init__.py",
    ),
    "nuisance_scenarios": (
        "sim/nuisance_scenarios/__init__.py",
        "tests/nuisance_scenarios/__init__.py",
    ),
    "streaming_s3_transfer": (),
    "ds005620_cohort_stream": (),
}
for _component_name, _initializer_paths in PACKAGE_INITIALIZER_SUPPORT_PATHS.items():
    _component_spec = COMPONENTS[_component_name]
    _initializer_tests = tuple(dict.fromkeys(
        pair["test"] for pair in _component_spec.get("candidate_pairs", ())
        if pair["test"] in _component_spec.get("tests", ())
        and (
            pair["test"] not in _component_spec.get("external_test_paths", {})
            or pair["test"] in _component_spec.get("test_markers", {})
        )
    ))
    _component_spec["package_initializers"] = {
        _initializer_path: _initializer_tests
        for _initializer_path in _initializer_paths
    }


# These PR numbers identify implementation/test provenance for registered
# pairs, including merged implementation PRs and open independent-test PRs.
# They are ownership evidence, not approval or merge state.
COMPONENT_OWNER_PRS = {
    "planar_geometry": (416,),
    "higher_order_runtime": (377, 450),
    "synthetic_pipeline_replay": (387,),
    "hodge_2d": (423,),
    "phase_cochain_reference": (385,),
    "hodge_decomposition_audit": (396,),
    "spherical_csd": (402, 414, 419),
    "mne_csd_reference_audit": (402,),
    "four_sphere": (418, 409),
    "phase_winding": (413, 453),
    "surrogate_nulls": (417, 430),
    "phase_uncertainty": (403,),
    "surrogate_audit": (398,),
    "synthetic_roc": (426, 427),
    "simulation_grid_planner": (424,),
    "fusion_validation_null_models": (374,),
    "report_firewall": (390,),
    "provenance_join": (392,),
    "topology_backend_conformance": (389,),
    "finite_chain_audit": (397,),
    "winding_charge_audit": (399,),
    "dmd_crouzeix": (415, 420, 400, 452),
    "batch2_pipeline_benchmark": (371, 445),
    "docker_context_policy": (431, 434),
    "bids_inventory_audit": (401,),
    "finite_jitter_geometry_audit": (410,),
    "finite_jitter_production_bridge": (410,),
    "release_readiness_security": (370,),
    "source_mining_evidence_boundary": (382,),
    "batch3_claim_matrix_artifact": (393,),
    "oss_compatibility_inventory_artifact": (406,),
    "batch3_dataset_feasibility_artifact": (394,),
    "batch3_metadata_audit_artifact": (411,),
    "oss_adoption_gates": (386,),
    "whitening_audit": (407,),
    "batch3_falsification_matrix_artifact": (376, 444, 447),
    "batch3_offline_integration": (381, 449),
    "measurement_hypothesis_contract": (384, 357),
    "empirical_higher_order": (357,),
    "transition_forecasting_benchmark": (357,),
    "release_manifest": (357,),
    "public_repo_source_pack": (391,),
    "dandi_nwb_bounded": (437,),
    "streaming_s3_transfer": (437,),
    "ds005620_cohort_stream": (437,),
    "moabb_protocol_conformance": (379,),
    "mne_signal_blocks": (380, 438),
    "mne_csd_adapter": (378,),
    "bids_adapter": (369,),
    "level_t_missingness": (373,),
    "batch3_source_registry": (375,),
    "research_plan_quality_eval": (383,),
    "forward_model_contract": (388, 446),
    "nuisance_scenarios": (408, 448),
}


# Known candidate suites in the live open-PR inventory that do not yet have a
# reviewed implementation/test pair. Explicit pair/support mappings override
# these guard roots; any other changed Python source/test path under a guard
# root blocks discovery until an owner registers a pair. Such changes are never
# silently classified NOT_APPLICABLE.
UNMAPPED_CANDIDATE_ROOTS = (
    # tests/experimental is a shared namespace, not an ownership root. Exact
    # registered paths there select components; unrelated tests remain
    # NOT_APPLICABLE instead of being attributed by directory alone.
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
    "tests/research/batch3/",  # PRs #393, #394, and #411; exact mappings override
    "tests/oss_compat/test_compatibility_inventory.py",  # PR #406
    "reports/batch3/grok_chat_a/claim_matrix.json",  # PR #393 declarative artifact
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
    "docs/oss_compat/compatibility_inventory_20261017.json",
    "reports/batch3/grok_chat_b/dataset_candidates.json",
    "reports/batch3/grok_chat_b/dataset_candidates_metadata_audit.json",
    "tests/research/test_batch3_source_registry.py",  # PR #375
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
    "scripts/run_transition_benchmark.py",
    "tools/release_manifest/",
    "scripts/run_registered_fhn.py",
    "scripts/validate_research_cycle_preflight.py",
)

# Narrow guards for known candidate families that live under the shared
# tests/experimental namespace. These are prefixes for a single candidate
# family, not a directory-wide ownership assumption.
UNMAPPED_CANDIDATE_PREFIXES = (
    "tests/experimental/test_planar_triangulation_",
)


def normalize_repo_path(path: str) -> str:
    """Normalize Git's POSIX paths and Windows-style test inputs consistently."""
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    # Git -z paths are repository-relative, but keep this boundary explicit:
    # malformed or injected names must never alias registered paths or escape
    # the checkout during a later file read.
    parts = normalized.split("/")
    path_segments = parts[:-1] if parts and parts[-1] == "" else parts
    if (
        normalized.startswith("/")
        or re.match(r"^[A-Za-z]:", normalized)
        or any(part in {".", ".."} for part in path_segments)
        or any(not part for part in path_segments)
    ):
        raise ValueError("path must be a normalized relative repository path")
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


@lru_cache(maxsize=1)
def _supports_pinned_output_transport() -> bool:
    """Whether a child process can read a descriptor pinned by this process."""
    if os.name != "posix" or not sys.platform.startswith("linux"):
        return False
    if not Path("/proc/self/fd").is_dir():
        return False

    try:
        with tempfile.TemporaryFile(mode="w+b") as probe_file:
            probe_file.write(PINNED_OUTPUT_PROBE_MARKER)
            probe_file.flush()
            parent_fd_path = _proc_fd_path(probe_file.fileno(), pid=os.getpid())
            completed = _PROBE_SUBPROCESS_RUN(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-c",
                    (
                        "import os, sys; "
                        "fd = os.open(sys.argv[1], os.O_RDONLY); "
                        "data = os.read(fd, 4096); os.close(fd); "
                        "sys.stdout.write(data.hex())"
                    ),
                    parent_fd_path,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=PINNED_OUTPUT_PROBE_TIMEOUT_S,
                env={},
            )
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    return (
        completed.returncode == 0
        and completed.stdout.strip() == PINNED_OUTPUT_PROBE_MARKER.hex()
    )


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


def _is_documentation_path(path: str) -> bool:
    return Path(normalize_repo_path(path)).suffix.casefold() in _DOCUMENTATION_SUFFIXES


def _is_candidate_file(path: str, roots: tuple[str, ...], explicit_paths: set[str] | None = None) -> bool:
    """Treat files under candidate roots as inputs unless they are documentation."""
    normalized = normalize_repo_path(path)
    if explicit_paths and normalized.casefold() in explicit_paths:
        return True
    if not any(_path_in_root(normalized, root) for root in roots):
        return False
    return not _is_documentation_path(normalized)


def _active_support_paths(spec: dict[str, Any], changed_paths: set[str]) -> set[str]:
    """Return support paths whose declared changed-path prerequisites are met."""
    changed = {normalize_repo_path(path).casefold() for path in changed_paths}
    requirements = spec.get("support_file_requires_changed", {})
    if not isinstance(requirements, dict):
        return set()
    active = set()
    for support_path in spec.get("support_files", {}):
        if support_path not in requirements:
            active.add(normalize_repo_path(support_path))
            continue
        companions = requirements[support_path]
        if (
            isinstance(companions, (tuple, list))
            and companions
            and all(
                isinstance(path, str)
                and normalize_repo_path(path).casefold() in changed
                for path in companions
            )
        ):
            active.add(normalize_repo_path(support_path))
    return active


def _is_component_relevant(
    name: str,
    changed_paths: set[str],
    *,
    include_package_initializers: bool = True,
    context_paths: set[str] | None = None,
) -> bool:
    spec = COMPONENTS[name]
    if any(
        not _is_documentation_path(path) and _trigger_matches(path, trigger)
        for path in changed_paths
        for trigger in spec["triggers"]
    ):
        return True
    mapped = {
        normalize_repo_path(path).casefold()
        for pair in spec.get("candidate_pairs", ())
        for path in (pair["implementation"], pair["test"])
    }
    mapped.update(
        path.casefold()
        for path in _active_support_paths(spec, context_paths or changed_paths)
    )
    mapped.update(normalize_repo_path(path).casefold() for path in spec.get("external_test_paths", {}))
    non_selecting_test_paths = {
        normalize_repo_path(path).casefold()
        for path in spec.get("non_selecting_test_paths", ())
    }
    mapped.difference_update(non_selecting_test_paths)
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
    # The KKT test and its pinned transcription fixture are shared legacy CSD
    # probes. Select either through the spherical-CSD compatibility mapping
    # when changed alone. If any other reference-audit path changes, the audit
    # component owns the run and the sphere component is suppressed to avoid
    # requiring an unrelated PR's implementation files.
    shared_csd_alias_paths = {
        "tests/mne_csd_reference_audit/test_kkt_operator.py",
        "tests/mne_csd_reference_audit/fixtures/mne_code_path_transcription.json",
    }
    shared_csd_alias_paths_casefold = {
        path.casefold() for path in shared_csd_alias_paths
    }
    shared_csd_alias_changed = bool(changed_casefold & shared_csd_alias_paths_casefold)
    other_audit_paths_changed = any(
        _path_in_root(path, "tools/mne_csd_reference_audit/")
        or (
            _path_in_root(path, "tests/mne_csd_reference_audit/")
            and normalize_repo_path(path).casefold()
            not in shared_csd_alias_paths_casefold
        )
        or normalize_repo_path(path).casefold()
        == "tests/optional_live_mne/test_mne_csd_live_parity.py"
        for path in changed_paths
    )
    if other_audit_paths_changed:
        direct.discard("spherical_csd")
    elif shared_csd_alias_changed:
        direct.discard("mne_csd_reference_audit")
        direct.add("spherical_csd")
    initializer_owners = {
        name
        for name, spec in COMPONENTS.items()
        if changed_casefold
        & {
            normalize_repo_path(initializer).casefold()
            for initializer in spec.get("package_initializers", {})
        }
    }
    shared_experimental_audit_initializers = {
        "tools/experimental_audits/__init__.py",
        "tests/experimental_audits/__init__.py",
    }
    if changed_casefold & {
        path.casefold() for path in shared_experimental_audit_initializers
    }:
        # These parent-package initializers are shared by two independent
        # audit components. When the same diff contains a component-specific
        # source/test pair, that pair disambiguates the initializer; otherwise
        # both owners remain selected and the missing companion blocks.
        if "winding_charge_audit" in direct and "four_sphere" not in direct:
            initializer_owners.discard("four_sphere")
        elif "four_sphere" in direct and "winding_charge_audit" not in direct:
            initializer_owners.discard("winding_charge_audit")
    # A mixed diff must validate both directly changed pairs and every owner of
    # a changed package initializer. Dropping initializer owners just because a
    # direct component also changed can silently omit shared import/API effects.
    # inspect_component keeps each selected component fail-closed on its exact
    # implementation/test and initializer mappings.
    selected = direct | initializer_owners
    return [name for name in COMPONENTS if name in selected]


def _changed_candidate_paths(spec: dict[str, Any], changed_paths: set[str]) -> list[str]:
    pairs = spec.get("candidate_pairs", ())
    active_support_paths = _active_support_paths(spec, changed_paths)
    globally_registered_paths = {
        normalize_repo_path(path).casefold()
        for candidate_spec in COMPONENTS.values()
        for pair in candidate_spec.get("candidate_pairs", ())
        for path in (pair["implementation"], pair["test"])
    } | {
        normalize_repo_path(path).casefold()
        for candidate_spec in COMPONENTS.values()
        for path in (
            *_active_support_paths(candidate_spec, changed_paths),
            *candidate_spec.get("package_initializers", {}).keys(),
        )
    }
    known = {
        normalize_repo_path(path).casefold()
        for pair in pairs
        for path in (pair["implementation"], pair["test"])
    }
    support_paths = {path.casefold() for path in active_support_paths}
    external_test_paths = {
        normalize_repo_path(path).casefold()
        for path in spec.get("external_test_paths", {})
    }
    package_initializer_paths = {
        normalize_repo_path(path).casefold()
        for path in spec.get("package_initializers", {})
    }
    mapped_support_paths = support_paths | package_initializer_paths
    known.update(support_paths)
    known.update(external_test_paths)
    known.update(package_initializer_paths)
    known_exact = {
        normalize_repo_path(path)
        for pair in pairs
        for path in (pair["implementation"], pair["test"])
    } | {
        normalize_repo_path(path)
        for path in (
            *active_support_paths,
            *spec.get("package_initializers", {}).keys(),
            *spec.get("external_test_paths", {}).keys(),
        )
    }
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
        for candidate in _active_support_paths(spec, changed_paths)
    } | {
        normalize_repo_path(candidate)
        for spec in COMPONENTS.values()
        for candidate in spec.get("package_initializers", {})
    } | {
        normalize_repo_path(candidate)
        for spec in COMPONENTS.values()
        for candidate in spec.get("external_test_paths", {})
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
        belongs_to_unmapped_candidate_prefix = any(
            path.casefold().startswith(prefix.casefold())
            and Path(path).suffix.casefold() == ".py"
            for prefix in UNMAPPED_CANDIDATE_PREFIXES
        )
        mapped = path.casefold() in mapped_paths_casefold
        if (
            path in mapped_case_mismatches
            or belongs_to_unmapped_candidate_root and not mapped
            or belongs_to_unmapped_candidate_prefix and not mapped
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
    changed_paths = changed_paths or set()
    changes = {normalize_repo_path(path).casefold() for path in changed_paths}
    active_support_paths = _active_support_paths(spec, changed_paths)
    active_support_paths_casefold = {path.casefold() for path in active_support_paths}
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
        if normalize_repo_path(support_path).casefold() in active_support_paths_casefold
        and normalize_repo_path(support_path).casefold() in changes
        for test in mapped_tests
    }
    changed_initializer_tests = {
        normalize_repo_path(test).casefold()
        for initializer_path, mapped_tests in spec.get("package_initializers", {}).items()
        if normalize_repo_path(initializer_path).casefold() in changes
        for test in mapped_tests
    }
    changed_initializer_test_order = list(dict.fromkeys(
        test
        for initializer_path, mapped_tests in spec.get("package_initializers", {}).items()
        if normalize_repo_path(initializer_path).casefold() in changes
        for test in mapped_tests
    ))
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

    external_tests = {
        normalize_repo_path(path).casefold()
        for path in spec.get("external_test_paths", {})
    }
    if (
        any(normalize_repo_path(pair["test"]).casefold() in external_tests for pair in selected_pairs)
        and not any(normalize_repo_path(pair["test"]).casefold() not in external_tests for pair in selected_pairs)
    ):
        selected_implementations = {
            normalize_repo_path(pair["implementation"]).casefold()
            for pair in selected_pairs
        }
        generic_pair = next(
            (
                pair for pair in pairs
                if normalize_repo_path(pair["test"]).casefold() not in external_tests
                and normalize_repo_path(pair["implementation"]).casefold() in selected_implementations
            ),
            None,
        )
        if generic_pair is None:
            generic_pair = next(
                (pair for pair in pairs if normalize_repo_path(pair["test"]).casefold() not in external_tests),
                None,
            )
        if generic_pair is not None:
            selected_pairs.append(generic_pair)

    missing_implementations = sorted({
        pair["implementation"] for pair in selected_pairs
        if not (root / pair["implementation"]).is_file()
    })
    missing_required_tests = sorted({
        pair["test"] for pair in selected_pairs
        if not (root / pair["test"]).is_file()
    } | {pair["test"] for pair in unavailable_companion_pairs})
    raw_suite_companion_tests = spec.get("suite_companion_tests", ())
    invalid_suite_companion_tests = []
    suite_companion_tests = []
    if not isinstance(raw_suite_companion_tests, (tuple, list)):
        invalid_suite_companion_tests.append("<mapping>")
    else:
        candidate_test_paths = {
            normalize_repo_path(pair["test"]).casefold() for pair in pairs
        }
        seen_companion_tests = set()
        for test_path in raw_suite_companion_tests:
            if not isinstance(test_path, str):
                invalid_suite_companion_tests.append(str(test_path))
                continue
            normalized_test_path = normalize_repo_path(test_path)
            casefolded_test_path = normalized_test_path.casefold()
            if (
                normalized_test_path not in spec.get("tests", ())
                or casefolded_test_path not in candidate_test_paths
                or casefolded_test_path in seen_companion_tests
            ):
                invalid_suite_companion_tests.append(normalized_test_path)
                continue
            suite_companion_tests.append(normalized_test_path)
            seen_companion_tests.add(casefolded_test_path)
    selected_suite_companion_tests = list(suite_companion_tests) if selected_pairs else []
    selected_pair_ids = {
        (pair["implementation"], pair["test"]) for pair in selected_pairs
    }
    companion_test_ids = {
        test_path.casefold() for test_path in selected_suite_companion_tests
    }
    # A component-level companion test is still an exact implementation/test
    # pair: require its source in the checked-out tree before it can run.
    selected_pairs.extend(
        pair for pair in pairs
        if normalize_repo_path(pair["test"]).casefold() in companion_test_ids
        and (pair["implementation"], pair["test"]) not in selected_pair_ids
    )
    missing_implementations = sorted({
        pair["implementation"] for pair in selected_pairs
        if not (root / pair["implementation"]).is_file()
    })
    missing_suite_companion_tests = sorted(
        test_path for test_path in selected_suite_companion_tests
        if not (root / test_path).is_file()
    )
    missing_required_tests = sorted(
        set(missing_required_tests) | set(missing_suite_companion_tests)
    )
    tests = [path for path in spec["tests"] if (root / path).is_file()]
    test_markers = {
        normalize_repo_path(path): marker
        for path, marker in spec.get("test_markers", {}).items()
    }
    invalid_test_markers = sorted(
        path for path, marker in test_markers.items()
        if path not in spec.get("tests", ())
        or normalize_repo_path(path).casefold()
        not in {normalize_repo_path(pair["test"]).casefold() for pair in pairs}
        or marker not in {"requires_mne", "not requires_mne"}
    )
    raw_environment_overrides = spec.get("environment_overrides", {})
    invalid_environment_overrides = []
    if not isinstance(raw_environment_overrides, dict):
        invalid_environment_overrides.append("<mapping>")
        environment_overrides: dict[str, str] = {}
    else:
        invalid_environment_overrides = sorted(
            str(key)
            for key, value in raw_environment_overrides.items()
            if not isinstance(key, str)
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)
            or not isinstance(value, str)
            or "\x00" in value
            or value not in SAFE_CANDIDATE_ENVIRONMENT_OVERRIDES.get(key, ())
        )
        environment_overrides = (
            dict(raw_environment_overrides) if not invalid_environment_overrides else {}
        )
    independent_reference_tests = tuple(spec.get("independent_reference_tests", ()))
    raw_support_requirements = spec.get("support_file_requires_changed", {})
    if not isinstance(raw_support_requirements, dict):
        invalid_support_file_requirements = ["<mapping>"]
    else:
        candidate_test_paths = {
            normalize_repo_path(pair["test"]).casefold() for pair in pairs
        }
        invalid_support_file_requirements = sorted(
            str(support_path)
            for support_path, companion_paths in raw_support_requirements.items()
            if support_path not in spec.get("support_files", {})
            or not isinstance(companion_paths, (tuple, list))
            or not companion_paths
            or any(
                not isinstance(path, str)
                or path not in spec.get("tests", ())
                or normalize_repo_path(path).casefold() not in candidate_test_paths
                for path in companion_paths
            )
        )
    invalid_independent_reference_tests = sorted(
        path for path in independent_reference_tests
        if path not in spec.get("tests", ()) or path not in spec.get("support_files", {})
    )
    changed_reference_tests = [
        path for path in independent_reference_tests
        if normalize_repo_path(path).casefold() in changes
        and normalize_repo_path(path).casefold() in active_support_paths_casefold
    ]
    missing_reference_tests = sorted(
        path for path in changed_reference_tests if not (root / path).is_file()
    )
    missing_required_tests = sorted(set(missing_required_tests) | set(missing_reference_tests))
    selected_runnable_test_paths = {
        normalize_repo_path(pair["test"]).casefold()
        for pair in selected_pairs
        if (
            normalize_repo_path(pair["test"]).casefold() not in external_tests
            or normalize_repo_path(pair["test"]) in test_markers
        )
    }
    if changed_initializer_test_order:
        # Initializer-only edits execute tests in the exact order declared by
        # the initializer ownership mapping.
        pair_test_order = [
            *changed_initializer_test_order,
            *(test for test in spec["tests"]
              if normalize_repo_path(test).casefold() in changed_support_tests),
        ]
    elif changed_support_tests:
        # Support-only edits use stable component test order, independent of
        # implementation-pair construction order.
        pair_test_order = list(spec["tests"])
    else:
        pair_test_order = [pair["test"] for pair in selected_pairs]
    pair_tests = list(dict.fromkeys(
        test for test in pair_test_order
        if normalize_repo_path(test).casefold() in selected_runnable_test_paths
        and (root / test).is_file()
    ))
    delegated_tests = sorted({
        pair["test"] for pair in selected_pairs
        if normalize_repo_path(pair["test"]).casefold() in external_tests
    })
    tests_to_run = list(dict.fromkeys([
        *pair_tests,
        *(path for path in changed_reference_tests if (root / path).is_file()),
        *(path for path in selected_suite_companion_tests if (root / path).is_file()),
    ]))
    active_support_files = {
        support_path: mapped_tests
        for support_path, mapped_tests in spec.get("support_files", {}).items()
        if normalize_repo_path(support_path).casefold() in active_support_paths_casefold
        and (
            normalize_repo_path(support_path).casefold() in changes
            or any(
                normalize_repo_path(test_path).casefold()
                in {normalize_repo_path(test).casefold() for test in tests_to_run}
                for test_path in mapped_tests
            )
        )
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
        and normalize_repo_path(support_path).casefold() in active_support_paths_casefold
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
    if invalid_support_file_requirements:
        blockers.append("support-file changed-path prerequisite mapping is invalid")
    if invalid_initializer_test_mappings:
        blockers.append("package initializer mapping is invalid or mapped test is unpaired")
    if invalid_test_markers:
        blockers.append("candidate test marker mapping is invalid or unpaired")
    if invalid_suite_companion_tests:
        blockers.append("component suite companion test mapping is invalid")
    if invalid_environment_overrides:
        blockers.append("candidate environment override mapping is invalid")
    if invalid_independent_reference_tests:
        blockers.append("independent reference test mapping is invalid or unregistered")
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
        } | set(selected_support_files) | set(selected_package_initializers)
          | set(changed_reference_tests) | set(selected_suite_companion_tests)),
        "selected_support_files": selected_support_files,
        "selected_package_initializers": selected_package_initializers,
        "required_pairs": selected_pairs,
        "unavailable_companion_pairs": unavailable_companion_pairs,
        "require_all_pairs": require_all_pairs,
        "implementations": implementations,
        "missing_implementations": missing_implementations,
        "missing_required_tests": missing_required_tests,
        "suite_companion_tests": selected_suite_companion_tests,
        "missing_suite_companion_tests": missing_suite_companion_tests,
        "invalid_suite_companion_tests": sorted(set(invalid_suite_companion_tests)),
        "missing_support_files": missing_support_files,
        "missing_package_initializers": missing_package_initializers,
        "invalid_support_test_mappings": invalid_support_test_mappings,
        "invalid_support_file_requirements": invalid_support_file_requirements,
        "invalid_initializer_test_mappings": invalid_initializer_test_mappings,
        "invalid_test_markers": invalid_test_markers,
        "invalid_environment_overrides": invalid_environment_overrides,
        "environment_overrides": environment_overrides,
        "independent_reference_tests": list(independent_reference_tests),
        "invalid_independent_reference_tests": invalid_independent_reference_tests,
        "missing_reference_tests": missing_reference_tests,
        "unmapped_candidate_paths": unmapped,
        "available_candidate_tests": tests,
        "tests_to_run": tests_to_run,
        "test_markers": {
            test_path: test_markers[test_path]
            for test_path in tests_to_run if test_path in test_markers
        },
        "delegated_tests": delegated_tests,
        "executions": [],
    }


def _junit_details_from_bytes(
    content: bytes,
    *,
    allow_subtest_totals: bool = False,
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
                if declared > actual:
                    missing_outcome_totals = sorted(
                        field for field in ("skipped", "failures", "errors")
                        if field not in suite.attrib
                    )
                    if missing_outcome_totals:
                        raise ValueError(
                            "JUnit subtest total requires explicit outcome summaries; "
                            f"missing {missing_outcome_totals}"
                        )
                    if not allow_subtest_totals:
                        raise ValueError(
                            "JUnit test total exceeds testcase records without a registered subtest contract"
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


def _junit_details_with_total(
    path: Path,
) -> tuple[tuple[int, int, int, int], list[dict[str, str]], int]:
    """Validate bounded JUnit bytes and retain the declared pytest test total."""
    if path.stat().st_size > MAX_JUNIT_XML_BYTES:
        raise ValueError(f"JUnit report exceeds the {MAX_JUNIT_XML_BYTES}-byte read limit")
    with path.open("rb") as stream:
        content = stream.read(MAX_JUNIT_XML_BYTES + 1)
    if len(content) > MAX_JUNIT_XML_BYTES:
        raise ValueError(f"JUnit report exceeds the {MAX_JUNIT_XML_BYTES}-byte read limit")
    return _junit_details_from_bytes(content)


def junit_details(path: Path) -> tuple[tuple[int, int, int, int], list[dict[str, str]]]:
    """Validate a JUnit file and return explicit testcase-element outcomes."""
    counts, details, _ = _junit_details_with_total(path)
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


def _git_tree_blob_sha(root: Path, commit_sha: str, relative_path: str) -> str | None:
    """Read a path's Git blob identity without following a worktree symlink."""
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        return None
    try:
        normalized = normalize_repo_path(relative_path)
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"{commit_sha}:{normalized}"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    blob_sha = result.stdout.strip()
    return blob_sha if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", blob_sha) else None


def _registered_junit_subtest_contract(
    root: Path, commit_sha: str | None, test_file: str
) -> dict[str, Any] | None:
    """Return evidence only for the exact reviewed test content and count."""
    try:
        normalized = normalize_repo_path(test_file)
    except ValueError:
        return None
    contract = REGISTERED_JUNIT_SUBTEST_DELTAS.get(normalized)
    if not isinstance(contract, dict) or not isinstance(commit_sha, str):
        return None
    component = contract.get("component")
    owner_pr = contract.get("owner_pr")
    blob_sha = contract.get("blob_sha")
    source_head_sha = contract.get("source_head_sha")
    verification = contract.get("verification")
    delta = contract.get("delta")
    if (
        not isinstance(component, str)
        or type(owner_pr) is not int
        or owner_pr not in COMPONENT_OWNER_PRS.get(component, ())
        or not isinstance(blob_sha, str)
        or not re.fullmatch(r"[0-9a-f]{40}", blob_sha)
        or not isinstance(source_head_sha, str)
        or not re.fullmatch(r"[0-9a-f]{40}", source_head_sha)
        or not isinstance(verification, dict)
        or type(verification.get("run_id")) is not int
        or verification["run_id"] <= 0
        or not isinstance(verification.get("tested_checkout_sha"), str)
        or not re.fullmatch(r"[0-9a-f]{40}", verification["tested_checkout_sha"])
        or verification.get("workflow_conclusion") != "failure"
        or verification.get("candidate_status") != "FAIL"
        or verification.get("failure_classification") != "missing_or_invalid_junit"
        or verification.get("junit_reconciliation") != "mismatch"
        or verification.get("test_process_outcome") != "passed"
        or type(delta) is not int
        or delta <= 0
        or not any(
            normalize_repo_path(pair.get("test", "")) == normalized
            for pair in COMPONENTS.get(component, {}).get("candidate_pairs", ())
        )
    ):
        return None
    observed_blob_sha = _git_tree_blob_sha(root, commit_sha, normalized)
    source_blob_sha = _git_tree_blob_sha(root, source_head_sha, normalized)
    if observed_blob_sha != blob_sha or source_blob_sha != blob_sha:
        return None
    junit_total = verification.get("junit_reported_total")
    testcase_records = verification.get("junit_testcase_records")
    runner_exit_code = verification.get("runner_exit_code")
    outcomes = tuple(verification.get(key) for key in ("skipped", "failed", "errors", "timeouts"))
    if (
        type(junit_total) is not int
        or junit_total <= 0
        or type(testcase_records) is not int
        or testcase_records < 0
        or junit_total - testcase_records != delta
        or type(runner_exit_code) is not int
        or runner_exit_code != 0
        or verification.get("runner_telemetry_valid") is not True
        or any(type(value) is not int or value != 0 for value in outcomes)
    ):
        return None
    return {
        "test_path": normalized,
        "tested_tree_blob_sha": observed_blob_sha,
        "source_head_sha": source_head_sha,
        "verification_run_id": verification["run_id"],
        "verification_run_url": verification.get("run_url"),
        "tested_checkout_sha": verification["tested_checkout_sha"],
        "workflow_conclusion": verification["workflow_conclusion"],
        "candidate_status": verification["candidate_status"],
        "failure_classification": verification["failure_classification"],
        "junit_reconciliation": verification["junit_reconciliation"],
        "test_process_outcome": verification["test_process_outcome"],
        "expected_delta": delta,
        "verified_junit_total": junit_total,
        "verified_junit_testcase_records": testcase_records,
        "component": component,
        "owner_pr": owner_pr,
    }


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
    # --no-renames lists the removed side of a rename as well as the new name.
    # Rename detection would otherwise hide moving a registered implementation
    # out of its candidate root.
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "-z", f"{base}...{head}"],
        cwd=root,
        check=True,
        capture_output=True,
        text=False,
        timeout=30,
    )
    changed = set()
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        name = os.fsdecode(raw)
        # Backslash is an ordinary filename byte on POSIX runners. Rewriting it
        # would alias a root-level file to a registered repository path, so
        # reject it instead of normalizing it.
        if "\\" in name:
            raise ValueError("git changed path contains a backslash; refusing ambiguous repository path")
        changed.add(normalize_repo_path(name))
    return changed


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

    def parse_finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("non-finite JSON number")
        return parsed

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key: {key}")
            result[key] = value
        return result

    return json.loads(
        raw,
        parse_constant=reject_constant,
        parse_float=parse_finite_float,
        object_pairs_hook=reject_duplicate_keys,
    )


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
    # Pytest's stdout summary is useful corroboration, but it is not emitted in
    # every valid profile (for example, some test modules redirect/capture it).
    # The required process status plus the bounded, structurally validated
    # JUnit report below remain authoritative. If a summary is present, it must
    # reconcile exactly with JUnit before the execution can pass.
    batch["_round6_pytest_summary_available"] = pytest_summary is not None
    if pytest_summary is not None:
        if pytest_summary[0] < 1:
            return False, "runner pytest output contains an empty pass summary", batches
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


def validate_docker_engine_test_artifacts(
    root: Path,
    telemetry_path: Path,
    junit_path: Path,
    test_file: str,
) -> tuple[bool, str | None, int]:
    """Require Docker test telemetry and JUnit to report the same passing total."""
    try:
        telemetry_bytes = _read_contained_bytes(
            root,
            telemetry_path,
            "Docker Engine telemetry path",
            max_bytes=MAX_RUNNER_TELEMETRY_BYTES,
        )
        telemetry = _strict_json_loads(telemetry_bytes.decode("utf-8"))
        valid, error, batches = _isolated_runner_report_is_valid(telemetry, test_file)
        if not valid:
            return False, f"invalid isolated-runner telemetry: {error}", 0
        if len(batches) != 1:
            return False, "expected exactly one isolated-runner batch", 0
        batch = batches[0]
        runner_total = None
        if batch.get("_round6_pytest_summary_available") is True:
            runner_total = (
                batch["_round6_pytest_passed_count"]
                + batch["_round6_pytest_subtests_passed_count"]
            )
        junit_bytes = _read_contained_bytes(
            root,
            junit_path,
            "Docker Engine JUnit path",
            max_bytes=MAX_JUNIT_XML_BYTES,
        )
        counts, _, junit_total = _junit_details_from_bytes(
            junit_bytes, allow_subtest_totals=runner_total is not None
        )
        cases, skipped, failed, errors = counts
        if cases < 1 or skipped or failed or errors:
            return False, (
                "JUnit must contain passing tests only: "
                f"cases={cases} skipped={skipped} failed={failed} errors={errors}"
            ), 0
        if runner_total is None and junit_total != cases:
            return False, (
                "JUnit subtest total cannot be reconciled without a pytest stdout summary: "
                f"junit={junit_total} testcase_records={cases}"
            ), 0
        if runner_total is not None and junit_total != runner_total:
            return False, (
                "JUnit test total does not match isolated-runner pytest pass total: "
                f"junit={junit_total} runner={runner_total}"
            ), 0
        return True, None, junit_total
    except (OSError, ValueError, json.JSONDecodeError, ET.ParseError) as exc:
        return False, f"malformed Docker Engine test artifacts: {exc}", 0


def docker_engine_candidate_evidence(
    root: Path,
    telemetry_path: Path,
    junit_path: Path,
    *,
    diff_base_sha: str,
    diff_head_sha: str,
    tested_checkout_sha: str,
    workflow_sha: str,
    event_name: str,
    candidate_changed: bool,
    execution_outcome: str,
) -> dict[str, Any]:
    """Build finite, identity-bound evidence for the dedicated Docker Engine job."""
    for label, sha in (
        ("diff base", diff_base_sha),
        ("diff head", diff_head_sha),
        ("tested checkout", tested_checkout_sha),
        ("workflow", workflow_sha),
    ):
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError(f"Docker Engine evidence requires a full {label} SHA")
    if execution_outcome not in {"success", "failure", "cancelled", "skipped", "unknown"}:
        raise ValueError("Docker Engine execution outcome is invalid")
    exact_test = "tests/docker_context/test_docker_engine_build_context.py"
    evidence: dict[str, Any] = {
        "schema_version": "round6-external-candidate-evidence-v1",
        "workflow": "Required Checks",
        "job": "docker-context-engine",
        "diff_base_sha": diff_base_sha,
        "diff_head_sha": diff_head_sha,
        "tested_checkout_sha": tested_checkout_sha,
        "workflow_sha": workflow_sha,
        "event_name": event_name,
        "selected_component": "docker_context_policy" if candidate_changed else None,
        "implementation_paths": [".dockerignore"] if candidate_changed else [],
        "test_paths": [exact_test] if candidate_changed else [],
        "artifact_path": "outputs/docker_context_candidate_evidence.json",
        "execution_outcome": execution_outcome,
        "counts": {
            "collected": None,
            "passed": None,
            "skipped": None,
            "failures": None,
            "errors": None,
            "timeouts": None,
        },
        "status": "INCONCLUSIVE",
        "failure_reason": None,
    }
    if not candidate_changed:
        evidence["status"] = "NOT_APPLICABLE"
        evidence["failure_reason"] = "no registered Docker candidate path changed"
        return evidence

    valid, reason, test_count = validate_docker_engine_test_artifacts(
        root, telemetry_path, junit_path, exact_test
    )
    if valid:
        evidence["counts"] = {
            "collected": test_count,
            "passed": test_count,
            "skipped": 0,
            "failures": 0,
            "errors": 0,
            "timeouts": 0,
        }
        if execution_outcome == "success":
            evidence["status"] = "PASS"
        else:
            evidence["status"] = "FAIL" if execution_outcome == "failure" else "BLOCKED"
            evidence["failure_reason"] = (
                "Docker test step did not succeed despite valid-looking reports: "
                f"{execution_outcome}"
            )
        return evidence

    evidence["failure_reason"] = reason
    timeout_count: int | None = None
    try:
        telemetry_bytes = _read_contained_bytes(
            root,
            telemetry_path,
            "Docker Engine telemetry path",
            max_bytes=MAX_RUNNER_TELEMETRY_BYTES,
        )
        telemetry = _strict_json_loads(telemetry_bytes.decode("utf-8"))
        if isinstance(telemetry, dict) and isinstance(telemetry.get("summary"), dict):
            raw_timeouts = telemetry["summary"].get("timeout_batches")
            if type(raw_timeouts) is int and raw_timeouts >= 0:
                timeout_count = raw_timeouts
        batches = telemetry.get("batches", []) if isinstance(telemetry, dict) else []
        if isinstance(batches, list) and len(batches) == 1 and isinstance(batches[0], dict):
            pytest_summary = _pytest_result_summary(batches[0].get("stdout_tail"))
            if pytest_summary is not None:
                evidence["counts"]["passed"] = pytest_summary[0] + pytest_summary[1]
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    try:
        junit_bytes = _read_contained_bytes(
            root,
            junit_path,
            "Docker Engine JUnit path",
            max_bytes=MAX_JUNIT_XML_BYTES,
        )
        outcomes, _, total_tests = _junit_details_from_bytes(
            junit_bytes, allow_subtest_totals=type(evidence["counts"].get("passed")) is int
        )
        cases, skipped, failed, errors = outcomes
        evidence["counts"].update({
            "collected": total_tests,
            "skipped": skipped,
            "failures": failed,
            "errors": errors,
        })
        # A declared total may include unittest subtests; only infer passes
        # when the runner independently reports the same nonzero total.
        if evidence["counts"]["passed"] is not None and (
            evidence["counts"]["passed"] + skipped + failed + errors == total_tests
        ):
            evidence["counts"]["passed"] = total_tests - skipped - failed - errors
        elif total_tests == cases:
            evidence["counts"]["passed"] = cases - skipped - failed - errors
    except (OSError, ValueError, UnicodeDecodeError, ET.ParseError):
        pass
    evidence["counts"]["timeouts"] = timeout_count
    known_test_failure = any(
        type(evidence["counts"][key]) is int and evidence["counts"][key] > 0
        for key in ("skipped", "failures", "errors", "timeouts")
    )
    if known_test_failure or execution_outcome == "failure":
        evidence["status"] = "FAIL"
    else:
        evidence["status"] = "BLOCKED"
        if execution_outcome != "success":
            evidence["failure_reason"] = (
                f"Docker test step did not succeed: {execution_outcome}; "
                f"artifact validation: {reason}"
            )
    return evidence


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
    only_components: list[str] | tuple[str, ...] = (),
    pytest_marker: str | None = None,
    external_test_job: str | None = None,
) -> int:
    if event_name == "workflow_dispatch":
        raise ValueError("workflow_dispatch candidate execution is disabled")
    root = root.resolve()
    report_path = _lexically_contained_path(root, report_path, "report path")
    always_components = list(dict.fromkeys(always_components))
    only_components = list(dict.fromkeys(only_components))
    unknown_always = sorted(set(always_components) - set(COMPONENTS))
    if unknown_always:
        raise ValueError(f"unknown always-run components: {unknown_always}")
    unknown_only = sorted(set(only_components) - set(COMPONENTS))
    if unknown_only:
        raise ValueError(f"unknown component filters: {unknown_only}")
    if pytest_marker not in {None, "requires_mne", "not requires_mne"}:
        raise ValueError("unsupported pytest marker profile")
    external_test_jobs = {
        job
        for spec in COMPONENTS.values()
        for job in spec.get("external_test_paths", {}).values()
    }
    if external_test_job is not None and external_test_job not in external_test_jobs:
        raise ValueError(f"unknown external test job: {external_test_job}")
    if external_test_job is not None and not only_components:
        raise ValueError("external test execution requires an explicit --only-component")
    if external_test_job is not None and pytest_marker is not None:
        raise ValueError("external test execution cannot be combined with --pytest-marker")
    if tested_checkout_sha is not None and not re.fullmatch(r"[0-9a-f]{40}", tested_checkout_sha):
        raise ValueError("tested checkout must be a full commit SHA")
    if workflow_sha is not None and not re.fullmatch(r"[0-9a-f]{40}", workflow_sha):
        raise ValueError("workflow SHA must be a full commit SHA")
    changed = collect_changed_paths(diff_base_sha, diff_head_sha, root)
    selected = select_components(changed)
    if only_components:
        selected = [name for name in selected if name in only_components]
    component_scope = only_components or tuple(COMPONENTS)
    changed_casefold = {normalize_repo_path(path).casefold() for path in changed}
    delegated_test_owners = {
        normalize_repo_path(path): job
        for name, spec in COMPONENTS.items()
        if name in component_scope
        for path, job in spec.get("external_test_paths", {}).items()
        if normalize_repo_path(path).casefold() in changed_casefold
    }
    relevant_paths = sorted({
        normalize_repo_path(path)
        for path in changed
        if any(
            _is_component_relevant(name, {path}, context_paths=changed)
            for name in component_scope
        )
    })
    unmapped_candidate_paths = _unmapped_candidate_paths(changed)
    if only_components:
        unmapped_candidate_paths = [
            path for path in unmapped_candidate_paths
            if any(
                _is_component_relevant(name, {path}, context_paths=changed)
                for name in only_components
            )
        ]
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
        "delegated_test_owners": delegated_test_owners,
        "selected_components": selected,
        "always_components": always_components,
        "only_components": only_components,
        "pytest_marker_profile": pytest_marker,
        "external_test_job": external_test_job,
        "not_applicable_components": [],
        "unmapped_candidate_paths": unmapped_candidate_paths,
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
        has_candidate_paths = bool(
            selected or relevant_paths or report["unmapped_candidate_paths"]
        )
        if has_candidate_paths:
            # The PR base/head pair chooses paths, but those paths must not be
            # used to test a checkout that does not contain the candidate head.
            # PR merge refs and pinned canary merges retain this ancestry.
            ancestry = subprocess.run(
                ["git", "merge-base", "--is-ancestor", diff_head_sha, actual_sha],
                cwd=root, check=False, capture_output=True, text=True, timeout=10,
            )
            report["candidate_head_in_tested_checkout"] = ancestry.returncode == 0
            if ancestry.returncode != 0:
                report.update({
                    "status": "BLOCKED",
                    "selection_error": (
                        "candidate diff head is not an ancestor of the tested checkout"
                    ),
                })
                _write_contained_text(
                    root, report_path,
                    json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n",
                    "report path", report_file_identity,
                )
                print(json.dumps({
                    "status": report["status"],
                    "selection_error": report["selection_error"],
                }, sort_keys=True))
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
                if _is_component_relevant(name, {path}, context_paths=changed)
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
            if external_test_job is not None:
                external_tests_to_run = [
                    path for path in entry["delegated_tests"]
                    if spec.get("external_test_paths", {}).get(path) == external_test_job
                ]
                entry["external_tests_selected_for_job"] = external_tests_to_run
                if entry["status"] != "READY_TO_RUN":
                    report["components"].append(entry)
                    report["selected_paths"][name] = sorted({
                        *component_changes,
                        *entry["selected_paths"],
                    })
                    saw_blocked = True
                    continue
                if not external_tests_to_run:
                    entry["status"] = "NOT_APPLICABLE"
                    entry["reason"] = "no changed candidate pair delegates a test to this external job"
                    report["not_applicable_components"].append(name)
                    report["components"].append(entry)
                    report["selected_paths"][name] = sorted({
                        *component_changes,
                        *entry["selected_paths"],
                    })
                    continue
                entry["tests_to_run"] = external_tests_to_run
            if pytest_marker is not None:
                entry["test_markers"] = {
                    test_path: pytest_marker for test_path in entry["tests_to_run"]
                }
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
                test_marker = entry.get("test_markers", {}).get(test_file)
                if test_marker:
                    cmd[-1:-1] = ["--marker", test_marker]
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
                    "pytest_marker": test_marker,
                    "environment_overrides": entry.get("environment_overrides", {}),
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
                            env={**os.environ, **entry.get("environment_overrides", {})},
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
                execution["junit_reconciliation"] = "not_attempted_no_junit"
                if junit_bytes is not None:
                    junit_parsed = False
                    try:
                        pytest_summary_available = (
                            telemetry_ok
                            and bool(batches)
                            and isinstance(batches[0], dict)
                            and batches[0].get("_round6_pytest_summary_available") is True
                        )
                        registered_subtest_contract = _registered_junit_subtest_contract(
                            root, tested_checkout_sha, test_file
                        )
                        registered_subtest_delta = (
                            registered_subtest_contract["expected_delta"]
                            if registered_subtest_contract else 0
                        )
                        counts, cases, junit_reported_tests = _junit_details_from_bytes(
                            junit_bytes,
                            allow_subtest_totals=(
                                pytest_summary_available
                                or registered_subtest_delta > 0
                            ),
                        )
                        junit_parsed = True
                        subtest_delta = junit_reported_tests - counts[0]
                        execution.update({
                            "tests_collected": junit_reported_tests,
                            "junit_testcase_records": counts[0],
                            "registered_subtest_delta": registered_subtest_delta,
                            "registered_subtest_contract": (
                                {
                                    **registered_subtest_contract,
                                    "observed_delta": subtest_delta,
                                    "applied_without_pytest_summary": (
                                        not pytest_summary_available and subtest_delta > 0
                                    ),
                                }
                                if registered_subtest_contract else None
                            ),
                            "skipped": counts[1],
                            "failed": counts[2],
                            "errors": counts[3],
                            "junit_reported_test_outcomes": junit_reported_tests,
                        })
                        if (
                            not pytest_summary_available
                            and subtest_delta not in (0, registered_subtest_delta)
                        ):
                            raise ValueError(
                                "JUnit subtest delta "
                                f"{subtest_delta} does not match registered delta {registered_subtest_delta}"
                            )
                        if registered_subtest_contract and not pytest_summary_available:
                            verified_total = registered_subtest_contract["verified_junit_total"]
                            verified_records = registered_subtest_contract[
                                "verified_junit_testcase_records"
                            ]
                            if (
                                junit_reported_tests != verified_total
                                or counts[0] != verified_records
                            ):
                                execution["junit_reconciliation"] = "mismatch"
                                raise ValueError(
                                    "JUnit counts do not match source-bound verified counts "
                                    f"(reported={junit_reported_tests}, testcase_records={counts[0]}, "
                                    f"expected_reported={verified_total}, expected_testcase_records={verified_records})"
                                )
                        failure_cases = [
                            {
                                "name": case["name"][:MAX_JUNIT_FAILURE_NAME_CHARS],
                                "status": case["status"],
                            }
                            for case in cases
                            if case["status"] != "passed"
                        ]
                        execution["junit_case_failures"] = failure_cases[:MAX_JUNIT_FAILURE_CASES]
                        execution["junit_case_failures_truncated"] = (
                            len(failure_cases) > MAX_JUNIT_FAILURE_CASES
                        )
                        if telemetry_ok:
                            batch = batches[0] if batches and isinstance(batches[0], dict) else {}
                            if batch.get("_round6_pytest_summary_available") is True:
                                runner_passed_count = batch.get("_round6_pytest_passed_count")
                                runner_subtests_passed_count = batch.get("_round6_pytest_subtests_passed_count")
                                if runner_passed_count != counts[0]:
                                    execution["junit_reconciliation"] = "mismatch"
                                    raise ValueError(
                                        f"JUnit testcase records {counts[0]} do not match pytest passed cases {runner_passed_count}"
                                    )
                                if (
                                    type(runner_subtests_passed_count) is not int
                                    or junit_reported_tests != runner_passed_count + runner_subtests_passed_count
                                ):
                                    execution["junit_reconciliation"] = "mismatch"
                                    raise ValueError(
                                        "JUnit declared outcome total does not match pytest passed-case and passed-subtest summary"
                                    )
                                execution.update({
                                    "runner_passed_tests": runner_passed_count,
                                    "runner_passed_subtests": runner_subtests_passed_count,
                                    "junit_reconciliation": "matched",
                                })
                            else:
                                execution["junit_reconciliation"] = (
                                    "matched_junit_declared_subtest_total_no_summary"
                                    if junit_reported_tests > counts[0]
                                    else "matched_junit_authoritative_no_summary"
                                )
                            execution["test_cases"] = cases
                        else:
                            execution["junit_reconciliation"] = "not_attempted_runner_telemetry_invalid"
                    except (ET.ParseError, OSError, ValueError) as exc:
                        execution["junit_error"] = str(exc)
                        if junit_parsed:
                            execution["junit_reconciliation"] = "mismatch"
                        else:
                            execution["junit_reconciliation"] = "invalid_junit"
                        junit_error = True
                has_junit = junit_bytes is not None and not junit_error
                runner_dependency_unavailable = (
                    "pytest-timeout is required" in runner_stderr_tail
                    or "No module named 'pytest'" in runner_stderr_tail
                )
                counts = (
                    (0, 0, 0, 0)
                    if runner_dependency_unavailable
                    else tuple(
                        execution.get(key)
                        for key in ("tests_collected", "skipped", "failed", "errors")
                    )
                )
                runner_timeout_batches = execution.get("runner_timeout_batches")
                if not isinstance(runner_timeout_batches, int):
                    runner_timeout_batches = sum(
                        1 for batch in execution.get("runner_batches", ()) if batch == "timeout"
                    )
                execution["timeout"] = bool(execution["timeout"] or runner_timeout_batches > 0)
                passed_count = (
                    max(0, counts[0] - counts[1] - counts[2] - counts[3])
                    if has_junit and all(type(value) is int for value in counts)
                    else None
                )
                execution["result_counts"] = {
                    "collected": counts[0],
                    "passed": passed_count,
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
                        else "runner_dependency_unavailable" if runner_dependency_unavailable
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
                    "environment_overrides": entry.get("environment_overrides", {}),
                    "diff_base_sha": diff_base_sha,
                    "diff_head_sha": diff_head_sha,
                    "tested_checkout_sha": tested_checkout_sha,
                    "workflow_sha": workflow_sha,
                    "tests_collected": counts[0],
                    "passed": passed_count,
                    "skipped": counts[1],
                    "failed": counts[2],
                    "errors": counts[3],
                    "timeouts": int(execution["timeout"]),
                    "junit_testcase_records": execution.get("junit_testcase_records"),
                    "junit_reconciliation": execution.get("junit_reconciliation"),
                    "registered_subtest_contract": execution.get("registered_subtest_contract"),
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
        "delegated_test_owners": report["delegated_test_owners"],
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
    parser.add_argument(
        "--only-component", action="append", default=[], choices=sorted(COMPONENTS),
        help="Restrict this focused profile to changed paths for the named component.",
    )
    parser.add_argument(
        "--pytest-marker", choices=("requires_mne", "not requires_mne"),
        help="Apply a validated optional-dependency test marker to this focused profile.",
    )
    parser.add_argument(
        "--external-test-job",
        choices=sorted({
            job
            for spec in COMPONENTS.values()
            for job in spec.get("external_test_paths", {}).values()
        }),
        help="Execute only changed tests explicitly delegated to this external job.",
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
            only_components=args.only_component,
            pytest_marker=args.pytest_marker,
            external_test_job=args.external_test_job,
        )
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"Round 6 candidate test discovery failed closed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
