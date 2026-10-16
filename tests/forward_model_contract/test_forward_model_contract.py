"""Tests for synthetic EEG forward-model contract and verification fixture.

Verifies:
- Explicit coordinate frames (HEAD) and SI units (meters, Volts, A*m).
- Conductor geometry invariants (radii monotonicity, scalp bounds, conductivities).
- Rejection of millimeter coordinates and out-of-bounds sources.
- Dipole potential linearity and superposition.
- Leadfield dimensions for free (M, 3N) and fixed (M, N) orientation.
- Channel ordering consistency and permutation invariance.
- Average reference projection invariants (column zero-sum, rank deduction).
- Conditioning and SVD numerical diagnostics.
- Scalp potential simulation (V = L * q).
- Deterministic replay.
- Non-promotional guardrails (SYNTHETIC_ONLY / ENGINEERING_ONLY labels, disclaimers).
- MNE forward solution auditor with mock MNE Forward dicts.
- Finite JSON serialization.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import unittest

# Ensure repo root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dual_engine.forward_model_contract import (
    CONTRACT_DISCLAIMER,
    ChannelOrderMismatchError,
    ConductorGeometryError,
    ConductorModel,
    ConductorModelType,
    ContractStatus,
    CoordinateFrame,
    CoordinateFrameMismatchError,
    CoordinateUnitMismatchError,
    ForwardModelContractError,
    ForwardModelContractResult,
    LeadfieldDimensionMismatchError,
    SensorGeometry,
    SourceOutOfBoundsError,
    SourceSpace,
    apply_average_reference,
    audit_mne_forward_solution,
    build_synthetic_forward_contract,
    compute_3shell_sphere_potential,
    compute_homogeneous_sphere_potential,
    compute_leadfield_diagnostics,
    make_standard_1020_synthetic_sensors,
    make_synthetic_source_grid,
    verify_average_reference_invariant,
)


class TestForwardModelContract(unittest.TestCase):
    """Test suite for synthetic EEG forward-model contract enforcement."""

    def setUp(self) -> None:
        """Create baseline fixtures."""
        self.conductor = ConductorModel()
        self.sensors = make_standard_1020_synthetic_sensors(self.conductor.scalp_radius_m)
        self.sources_free = make_synthetic_source_grid(n_sources=8, is_fixed_orientation=False)
        self.sources_fixed = make_synthetic_source_grid(n_sources=8, is_fixed_orientation=True)

    # -------------------------------------------------------------------------
    # 1. Coordinate Units & Scaling Enforcement
    # -------------------------------------------------------------------------

    def test_coordinate_units_meters_enforced_in_conductor(self) -> None:
        """Radii specified in millimeters (> 1.0m) must raise CoordinateUnitMismatchError."""
        with self.assertRaises(CoordinateUnitMismatchError):
            bad_conductor = ConductorModel(radii_m=(80.0, 85.0, 90.0))  # in mm
            bad_conductor.validate()

    def test_coordinate_units_meters_enforced_in_sensors(self) -> None:
        """Sensor coordinates specified in mm (> 1.0m) must raise CoordinateUnitMismatchError."""
        with self.assertRaises(CoordinateUnitMismatchError):
            SensorGeometry(
                channel_names=("Fp1", "Fp2", "F3", "F4"),
                positions_m=((0.0, 70.0, 50.0), (0.0, -70.0, 50.0), (-50.0, 0.0, 60.0), (50.0, 0.0, 60.0)),
                coordinate_frame=CoordinateFrame.HEAD,
            ).validate()

    def test_coordinate_units_meters_enforced_in_sources(self) -> None:
        """Source coordinates specified in mm (> 1.0m) must raise CoordinateUnitMismatchError."""
        with self.assertRaises(CoordinateUnitMismatchError):
            SourceSpace(
                positions_m=((0.0, 20.0, 30.0),),  # 36 mm norm > 1.0m
                coordinate_frame=CoordinateFrame.HEAD,
            ).validate()

    # -------------------------------------------------------------------------
    # 2. Coordinate Frames Enforcement
    # -------------------------------------------------------------------------

    def test_coordinate_frame_unknown_rejected(self) -> None:
        """CoordinateFrame.UNKNOWN must fail closed."""
        with self.assertRaises(CoordinateFrameMismatchError):
            SensorGeometry(
                channel_names=("Fp1", "Fp2", "F3", "F4"),
                positions_m=((0.0, 0.07, 0.05), (0.0, -0.07, 0.05), (-0.05, 0.0, 0.06), (0.05, 0.0, 0.06)),
                coordinate_frame=CoordinateFrame.UNKNOWN,
            ).validate()

    # -------------------------------------------------------------------------
    # 3. Conductor Geometry Invariants
    # -------------------------------------------------------------------------

    def test_conductor_geometry_monotonic_radii(self) -> None:
        """Conductor radii must be strictly monotonically increasing."""
        with self.assertRaises(ConductorGeometryError):
            ConductorModel(radii_m=(0.085, 0.080, 0.090)).validate()

    def test_conductor_geometry_positive_conductivities(self) -> None:
        """Conductor conductivities must be strictly positive."""
        with self.assertRaises(ConductorGeometryError):
            ConductorModel(sigmas_sm=(0.33, -0.0042, 0.33)).validate()

    def test_conductor_geometry_scalp_bounds(self) -> None:
        """Outer scalp radius must be within plausible physical bounds."""
        with self.assertRaises(ConductorGeometryError):
            ConductorModel(radii_m=(0.01, 0.02, 0.03)).validate()  # 3cm too small
        with self.assertRaises(ConductorGeometryError):
            ConductorModel(radii_m=(0.10, 0.15, 0.25)).validate()  # 25cm too large

    # -------------------------------------------------------------------------
    # 4. Source Space Containment & Orientation Invariants
    # -------------------------------------------------------------------------

    def test_source_out_of_bounds_rejected(self) -> None:
        """Sources positioned outside brain radius must raise SourceOutOfBoundsError."""
        with self.assertRaises(SourceOutOfBoundsError):
            bad_sources = SourceSpace(
                positions_m=((0.0, 0.0, 0.082),),  # 8.2cm > 8.0cm brain radius
                coordinate_frame=CoordinateFrame.HEAD,
            )
            bad_sources.validate(self.conductor)

    def test_fixed_orientation_requires_unit_vectors(self) -> None:
        """Fixed orientation requires normalized unit vectors."""
        with self.assertRaises(ForwardModelContractError):
            SourceSpace(
                positions_m=((0.0, 0.0, 0.03),),
                orientations=((0.0, 0.0, 2.0),),  # norm = 2.0 != 1.0
                is_fixed_orientation=True,
                coordinate_frame=CoordinateFrame.HEAD,
            ).validate()

    # -------------------------------------------------------------------------
    # 5. Sensor Geometry Invariants
    # -------------------------------------------------------------------------

    def test_sensor_geometry_minimum_channels(self) -> None:
        """Fewer than 4 channels must fail closed."""
        with self.assertRaises(ForwardModelContractError):
            SensorGeometry(
                channel_names=("Fp1", "Fp2", "Fz"),
                positions_m=((0.0, 0.07, 0.05), (0.0, -0.07, 0.05), (0.0, 0.0, 0.09)),
            ).validate()

    def test_sensor_geometry_duplicate_channels_rejected(self) -> None:
        """Duplicate channel names must raise ForwardModelContractError."""
        with self.assertRaises(ForwardModelContractError):
            SensorGeometry(
                channel_names=("Fp1", "Fp2", "Fp1", "Cz"),
                positions_m=(
                    (0.0, 0.07, 0.05),
                    (0.0, -0.07, 0.05),
                    (0.0, 0.07, 0.05),
                    (0.0, 0.0, 0.09),
                ),
            ).validate()

    # -------------------------------------------------------------------------
    # 6. Dipole Potential Linearity and Superposition
    # -------------------------------------------------------------------------

    def test_homogeneous_sphere_dipole_linearity(self) -> None:
        """Dipole potential must satisfy exact linearity: V(q1 + q2) == V(q1) + V(q2)."""
        re = (0.0, 0.0, 0.09)
        rs = (0.015, -0.02, 0.03)
        q1 = (1.5e-9, -0.5e-9, 2.0e-9)
        q2 = (-0.8e-9, 1.2e-9, -1.0e-9)
        q_sum = tuple(q1[i] + q2[i] for i in range(3))

        v1 = compute_homogeneous_sphere_potential(re, rs, q1)
        v2 = compute_homogeneous_sphere_potential(re, rs, q2)
        v_sum = compute_homogeneous_sphere_potential(re, rs, q_sum)

        self.assertAlmostEqual(v_sum, v1 + v2, delta=1e-18)

    def test_3shell_sphere_dipole_linearity(self) -> None:
        """3-shell concentric sphere potential must satisfy exact superposition."""
        re = (0.0, 0.06, 0.067)
        rs = (-0.02, 0.01, 0.035)
        q1 = (1.0e-9, 0.0, 0.0)
        q2 = (0.0, 2.0e-9, 0.5e-9)
        q_sum = (1.0e-9, 2.0e-9, 0.5e-9)

        v1 = compute_3shell_sphere_potential(re, rs, q1, self.conductor)
        v2 = compute_3shell_sphere_potential(re, rs, q2, self.conductor)
        v_sum = compute_3shell_sphere_potential(re, rs, q_sum, self.conductor)

        self.assertAlmostEqual(v_sum, v1 + v2, delta=1e-18)

    # -------------------------------------------------------------------------
    # 7. Leadfield Matrix Dimensions: Free vs Fixed Orientation
    # -------------------------------------------------------------------------

    def test_leadfield_dimensions_free_orientation(self) -> None:
        """Free orientation leadfield dimensions must be (M, 3N)."""
        contract = build_synthetic_forward_contract(
            sensor_geometry=self.sensors,
            source_space=self.sources_free,
            conductor_model=self.conductor,
        )
        self.assertEqual(len(contract.leadfield), self.sensors.n_channels)
        self.assertEqual(len(contract.leadfield[0]), self.sources_free.n_sources * 3)
        self.assertEqual(contract.diagnostics.n_columns, self.sources_free.n_sources * 3)

    def test_leadfield_dimensions_fixed_orientation(self) -> None:
        """Fixed orientation leadfield dimensions must be (M, N)."""
        contract = build_synthetic_forward_contract(
            sensor_geometry=self.sensors,
            source_space=self.sources_fixed,
            conductor_model=self.conductor,
        )
        self.assertEqual(len(contract.leadfield), self.sensors.n_channels)
        self.assertEqual(len(contract.leadfield[0]), self.sources_fixed.n_sources)
        self.assertEqual(contract.diagnostics.n_columns, self.sources_fixed.n_sources)

    # -------------------------------------------------------------------------
    # 8. Average Reference Projection Invariants
    # -------------------------------------------------------------------------

    def test_average_reference_column_zero_sum(self) -> None:
        """Average-referenced leadfield must satisfy zero-sum column invariant."""
        contract = build_synthetic_forward_contract(
            sensor_geometry=self.sensors,
            source_space=self.sources_free,
            apply_avg_ref=True,
        )
        is_avg, max_err = verify_average_reference_invariant(contract.leadfield, tolerance=1e-11)
        self.assertTrue(is_avg)
        self.assertLess(max_err, 1e-11)

    def test_average_reference_projection_idempotency(self) -> None:
        """Average reference projector must be idempotent: P_avg * P_avg == P_avg."""
        raw_leadfield = [[float(i * 3 + j) for j in range(12)] for i in range(8)]
        p1 = apply_average_reference(raw_leadfield)
        p2 = apply_average_reference(p1)

        for i in range(len(p1)):
            for j in range(len(p1[0])):
                self.assertAlmostEqual(p1[i][j], p2[i][j], delta=1e-14)

    def test_average_reference_rank_reduction(self) -> None:
        """Average referencing reduces rank of an M-channel leadfield by at least 1."""
        contract_raw = build_synthetic_forward_contract(
            sensor_geometry=self.sensors,
            source_space=self.sources_free,
            apply_avg_ref=False,
        )
        contract_avg = build_synthetic_forward_contract(
            sensor_geometry=self.sensors,
            source_space=self.sources_free,
            apply_avg_ref=True,
        )
        # In average reference space, rank cannot exceed M - 1
        self.assertLessEqual(contract_avg.diagnostics.numerical_rank, self.sensors.n_channels - 1)
        self.assertGreaterEqual(contract_raw.diagnostics.numerical_rank, contract_avg.diagnostics.numerical_rank)

    # -------------------------------------------------------------------------
    # 9. Channel Ordering Consistency
    # -------------------------------------------------------------------------

    def test_channel_order_matching_and_reordering(self) -> None:
        """Permuting sensor order must permute leadfield rows identically."""
        contract1 = build_synthetic_forward_contract(sensor_geometry=self.sensors)

        # Reverse channel order
        rev_names = tuple(reversed(self.sensors.channel_names))
        rev_pos = tuple(reversed(self.sensors.positions_m))
        rev_sensors = SensorGeometry(channel_names=rev_names, positions_m=rev_pos)

        contract2 = build_synthetic_forward_contract(sensor_geometry=rev_sensors)

        # First row of contract2 should equal last row of contract1
        for j in range(len(contract1.leadfield[0])):
            self.assertAlmostEqual(contract2.leadfield[0][j], contract1.leadfield[-1][j], delta=1e-12)

    # -------------------------------------------------------------------------
    # 10. Diagnostics and Numerical Conditioning
    # -------------------------------------------------------------------------

    def test_leadfield_diagnostics_finite_and_bounded(self) -> None:
        """Diagnostics metrics must be finite, positive, and well-behaved."""
        contract = build_synthetic_forward_contract()
        diag = contract.diagnostics

        self.assertTrue(math.isfinite(diag.condition_number))
        self.assertGreater(diag.condition_number, 1.0)
        self.assertGreater(diag.numerical_rank, 0)
        self.assertLessEqual(diag.numerical_rank, contract.sensor_geometry.n_channels - 1)
        self.assertTrue(all(math.isfinite(s) and s >= 0 for s in diag.singular_values))
        self.assertTrue(all(math.isfinite(n) and n > 0 for n in diag.channel_frobenius_norms))
        self.assertTrue(diag.is_well_conditioned)

    # -------------------------------------------------------------------------
    # 11. Scalp Potential Simulation (V = L * q)
    # -------------------------------------------------------------------------

    def test_simulation_superposition_and_reference(self) -> None:
        """Simulating scalp potentials preserves linear superposition and zero-sum ref."""
        contract = build_synthetic_forward_contract()
        n_col = contract.source_space.n_columns

        q1 = [0.0] * n_col
        q1[0] = 1e-9
        q2 = [0.0] * n_col
        q2[3] = 2e-9
        q_sum = [q1[i] + q2[i] for i in range(n_col)]

        v1 = contract.simulate_scalp_potentials(q1)[0]
        v2 = contract.simulate_scalp_potentials(q2)[0]
        v_sum = contract.simulate_scalp_potentials(q_sum)[0]

        for i in range(len(v1)):
            self.assertAlmostEqual(v_sum[i], v1[i] + v2[i], delta=1e-18)

        # Average reference check on simulated potentials: mean across channels is zero
        mean_v = sum(v_sum) / len(v_sum)
        self.assertAlmostEqual(mean_v, 0.0, delta=1e-18)

    # -------------------------------------------------------------------------
    # 12. Deterministic Replay
    # -------------------------------------------------------------------------

    def test_deterministic_replay(self) -> None:
        """Multiple executions with identical inputs produce identical leadfields bit-for-bit."""
        contract_a = build_synthetic_forward_contract()
        contract_b = build_synthetic_forward_contract()

        self.assertEqual(contract_a.leadfield, contract_b.leadfield)
        self.assertEqual(contract_a.diagnostics.singular_values, contract_b.diagnostics.singular_values)
        self.assertEqual(contract_a.diagnostics.numerical_rank, contract_b.diagnostics.numerical_rank)

    # -------------------------------------------------------------------------
    # 13. Non-Promotional Guardrails
    # -------------------------------------------------------------------------

    def test_non_promotional_guardrails(self) -> None:
        """Artifact status must be SYNTHETIC_ONLY with mandatory disclaimers."""
        contract = build_synthetic_forward_contract()

        self.assertEqual(contract.status, ContractStatus.SYNTHETIC_ONLY)
        self.assertIn("disclaimer", contract.provenance)
        self.assertEqual(contract.provenance["disclaimer"], CONTRACT_DISCLAIMER)

        # Ensure no claims of anatomical MRI or biological truth
        json_repr = contract.to_json()
        self.assertNotIn("anatomical ground truth", json_repr.lower())
        self.assertNotIn("consciousness solved", json_repr.lower())

    # -------------------------------------------------------------------------
    # 14. MNE Forward Solution Auditor
    # -------------------------------------------------------------------------

    def test_audit_mne_forward_solution_mock_valid(self) -> None:
        """Audit MNE forward solution against mock MNE Forward dict."""
        n_ch = 19
        n_src = 8
        mock_data = [[1.0 + i + j for j in range(n_src * 3)] for i in range(n_ch)]
        mock_data_avg = apply_average_reference(mock_data)

        mock_fwd = {
            "coord_frame": 4,  # FIFFV_COORD_HEAD
            "source_ori": 2,   # Free orientation
            "nsource": n_src,
            "nchan": n_ch,
            "sol": {
                "data": mock_data_avg,
                "row_names": list(self.sensors.channel_names),
                "ncol": n_src * 3,
                "nrow": n_ch,
            },
            "src": [
                {
                    "rr": [[0.01 * k, 0.01 * k, 0.02 * k] for k in range(n_src)],
                    "inuse": [1] * n_src,
                }
            ],
        }

        mock_info = {"ch_names": list(self.sensors.channel_names)}

        result = audit_mne_forward_solution(mock_fwd, info=mock_info)
        self.assertEqual(result.status, ContractStatus.ENGINEERING_ONLY)
        self.assertEqual(result.sensor_geometry.n_channels, n_ch)
        self.assertEqual(result.source_space.n_sources, n_src)
        self.assertTrue(result.diagnostics.is_average_referenced)

    def test_audit_mne_forward_solution_rejects_bad_coord_frame(self) -> None:
        """Audit must reject coordinate frames other than HEAD (e.g. unknown or 0)."""
        mock_fwd = {
            "coord_frame": 0,  # Invalid / unknown frame
            "sol": {"data": [[1.0]], "row_names": ["Cz"]},
        }
        with self.assertRaises(CoordinateFrameMismatchError):
            audit_mne_forward_solution(mock_fwd)

    def test_audit_mne_forward_solution_rejects_permuted_channels(self) -> None:
        """Audit must reject permuted channel order between info and leadfield."""
        n_ch = 4
        ch_names = ["Fp1", "Fp2", "F3", "F4"]
        mock_fwd = {
            "coord_frame": 4,
            "source_ori": 1,
            "nsource": 2,
            "sol": {
                "data": [[1.0, 2.0] for _ in range(n_ch)],
                "row_names": ["F4", "F3", "Fp2", "Fp1"],  # Permuted order!
            },
        }
        mock_info = {"ch_names": ch_names}

        with self.assertRaises(ChannelOrderMismatchError):
            audit_mne_forward_solution(mock_fwd, info=mock_info)

    # -------------------------------------------------------------------------
    # 15. Finite JSON Serialization
    # -------------------------------------------------------------------------

    def test_json_serialization_finite(self) -> None:
        """Serialized JSON must be valid, finite, and parseable."""
        contract = build_synthetic_forward_contract()
        json_str = contract.to_json()
        parsed = json.loads(json_str)

        self.assertEqual(parsed["status"], "SYNTHETIC_ONLY")
        self.assertEqual(parsed["n_channels"], 19)
        self.assertIn("diagnostics", parsed)
        self.assertIn("condition_number", parsed["diagnostics"])


if __name__ == "__main__":
    unittest.main()
