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
    ForwardUncertainty,
    LeadfieldDimensionMismatchError,
    SensorGeometry,
    SourceOutOfBoundsError,
    SourceSpace,
    UncertaintyStatus,
    apply_affine_transform,
    apply_average_reference,
    apply_channel_reference,
    audit_mne_forward_solution,
    build_synthetic_forward_contract,
    compute_3shell_sphere_potential,
    compute_concentric_spheres_potential,
    compute_homogeneous_sphere_potential,
    compute_leadfield_diagnostics,
    make_standard_1020_synthetic_sensors,
    make_synthetic_source_grid,
    validate_affine_transform,
    verify_average_reference_invariant,
    verify_channel_reference_invariant,
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

    # -------------------------------------------------------------------------
    # 16. Multi-Shell Layer Sensitivity & Conductor Model Validation
    # -------------------------------------------------------------------------

    def test_multishell_inner_layer_physical_effect(self) -> None:
        """Altering skull conductivity must exert a measurable physical effect on potential."""
        re = (0.0, 0.06, 0.067)
        rs = (-0.02, 0.01, 0.035)
        q = (1.0e-9, -0.5e-9, 2.0e-9)

        cond_default = ConductorModel(
            model_type=ConductorModelType.SPHERICAL_3SHELL,
            radii_m=(0.080, 0.085, 0.090),
            sigmas_sm=(0.33, 0.0042, 0.33),
        )
        cond_high_skull = ConductorModel(
            model_type=ConductorModelType.SPHERICAL_3SHELL,
            radii_m=(0.080, 0.085, 0.090),
            sigmas_sm=(0.33, 0.042, 0.33),
        )

        v_default = compute_3shell_sphere_potential(re, rs, q, cond_default)
        v_high_skull = compute_3shell_sphere_potential(re, rs, q, cond_high_skull)

        self.assertNotEqual(v_default, v_high_skull)
        rel_diff = abs(v_high_skull - v_default) / abs(v_default)
        self.assertGreater(rel_diff, 0.05)

    def test_multishell_brain_radius_physical_effect(self) -> None:
        """Altering brain radius (skull thickness) must exert a measurable physical effect."""
        re = (0.0, 0.06, 0.067)
        rs = (-0.01, 0.01, 0.02)
        q = (1.0e-9, 0.0, 1.0e-9)

        cond_thin_skull = ConductorModel(
            model_type=ConductorModelType.SPHERICAL_3SHELL,
            radii_m=(0.082, 0.086, 0.090),
            sigmas_sm=(0.33, 0.0042, 0.33),
        )
        cond_thick_skull = ConductorModel(
            model_type=ConductorModelType.SPHERICAL_3SHELL,
            radii_m=(0.075, 0.085, 0.090),
            sigmas_sm=(0.33, 0.0042, 0.33),
        )

        v_thin = compute_3shell_sphere_potential(re, rs, q, cond_thin_skull)
        v_thick = compute_3shell_sphere_potential(re, rs, q, cond_thick_skull)

        self.assertNotEqual(v_thin, v_thick)
        self.assertGreater(abs(v_thin - v_thick), 1e-10)

    def test_multishell_layer_count_enforced(self) -> None:
        """ConductorModelType layer count mismatch must fail closed."""
        with self.assertRaises(ConductorGeometryError):
            ConductorModel(
                model_type=ConductorModelType.SPHERICAL_1SHELL,
                radii_m=(0.080, 0.085, 0.090),
                sigmas_sm=(0.33, 0.0042, 0.33),
            ).validate()

        with self.assertRaises(ConductorGeometryError):
            ConductorModel(
                model_type=ConductorModelType.SPHERICAL_3SHELL,
                radii_m=(0.090,),
                sigmas_sm=(0.33,),
            ).validate()

        with self.assertRaises(ConductorGeometryError):
            ConductorModel(
                model_type=ConductorModelType.ANATOMICAL_BEM,
                radii_m=(0.080, 0.085, 0.090),
                sigmas_sm=(0.33, 0.0042, 0.33),
            ).validate()

    # -------------------------------------------------------------------------
    # 17. Coordinate Frame Compatibility & Explicit Transformations
    # -------------------------------------------------------------------------

    def test_coordinate_frame_mismatch_without_transform_rejected(self) -> None:
        """Mismatched coordinate frames without transform must raise CoordinateFrameMismatchError."""
        sources_mni = SourceSpace(
            positions_m=((0.0, 0.02, 0.03),),
            coordinate_frame=CoordinateFrame.MNI,
        )
        with self.assertRaises(CoordinateFrameMismatchError):
            build_synthetic_forward_contract(
                sensor_geometry=self.sensors,
                source_space=sources_mni,
                conductor_model=self.conductor,
            )

    def test_coordinate_transform_affine_applied(self) -> None:
        """Valid 4x4 affine transform successfully aligns MNI sources to HEAD frame."""
        transform_4x4 = (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.005),
            (0.0, 0.0, 0.0, 1.0),
        )
        sources_mni = SourceSpace(
            positions_m=((0.0, 0.02, 0.03), (0.01, -0.01, 0.02)),
            coordinate_frame=CoordinateFrame.MNI,
        )

        contract = build_synthetic_forward_contract(
            sensor_geometry=self.sensors,
            source_space=sources_mni,
            conductor_model=self.conductor,
            coord_transform=transform_4x4,
        )

        self.assertTrue(contract.is_valid)
        self.assertEqual(contract.sensor_geometry.coordinate_frame, CoordinateFrame.HEAD)
        self.assertAlmostEqual(contract.source_space.positions_m[0][2], 0.035, delta=1e-12)

    def test_coordinate_transform_invalid_matrix_rejected(self) -> None:
        """Malformed or non-affine transformation matrices must fail closed."""
        sources_mni = SourceSpace(
            positions_m=((0.0, 0.02, 0.03),),
            coordinate_frame=CoordinateFrame.MNI,
        )
        bad_transform = (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.5, 0.0, 0.0, 1.0),
        )
        with self.assertRaises(CoordinateFrameMismatchError):
            build_synthetic_forward_contract(
                sensor_geometry=self.sensors,
                source_space=sources_mni,
                coord_transform=bad_transform,
            )

    # -------------------------------------------------------------------------
    # 18. Unipolar Channel Referencing & Referencing Policies
    # -------------------------------------------------------------------------

    def test_reference_channel_not_in_montage_fails_closed(self) -> None:
        """Declaring a reference channel not present in sensor montage must raise ForwardModelContractError."""
        with self.assertRaises(ForwardModelContractError):
            SensorGeometry(
                channel_names=("Fp1", "Fp2", "F3", "F4"),
                positions_m=((0.0, 0.07, 0.05), (0.0, -0.07, 0.05), (-0.05, 0.0, 0.06), (0.05, 0.0, 0.06)),
                reference_channel="Cz",
            ).validate()

    def test_reference_channel_applied_and_verified(self) -> None:
        """Unipolar reference channel zeroes that channel's row in leadfield."""
        contract = build_synthetic_forward_contract(
            sensor_geometry=self.sensors,
            source_space=self.sources_free,
            apply_avg_ref=False,
            reference_channel="Cz",
        )

        cz_idx = self.sensors.channel_names.index("Cz")
        cz_row = contract.leadfield[cz_idx]
        for val in cz_row:
            self.assertAlmostEqual(val, 0.0, delta=1e-14)

        diag = contract.diagnostics
        self.assertTrue(diag.is_channel_referenced)
        self.assertEqual(diag.reference_channel, "Cz")
        self.assertLessEqual(diag.reference_channel_error, 1e-14)
        self.assertFalse(diag.is_average_referenced)

    def test_reference_channel_simulated_potentials(self) -> None:
        """Simulating scalp potentials with unipolar reference yields V(ref_ch) == 0."""
        contract = build_synthetic_forward_contract(
            sensor_geometry=self.sensors,
            source_space=self.sources_free,
            apply_avg_ref=False,
            reference_channel="Cz",
        )
        q = [1.0e-9] * contract.source_space.n_columns
        sim_v = contract.simulate_scalp_potentials(q)[0]

        cz_idx = self.sensors.channel_names.index("Cz")
        self.assertAlmostEqual(sim_v[cz_idx], 0.0, delta=1e-18)

    def test_conflicting_referencing_rejected(self) -> None:
        """Simultaneously requesting average reference and reference channel must fail closed."""
        with self.assertRaises(ForwardModelContractError):
            build_synthetic_forward_contract(
                sensor_geometry=self.sensors,
                source_space=self.sources_free,
                apply_avg_ref=True,
                reference_channel="Cz",
            )

    # -------------------------------------------------------------------------
    # 19. Forward Uncertainty Semantics
    # -------------------------------------------------------------------------

    def test_uncertainty_semantics_unavailable_by_default(self) -> None:
        """Uncertainty status must be UNAVAILABLE; default zero error is prohibited."""
        contract = build_synthetic_forward_contract()
        unc = contract.uncertainty

        self.assertEqual(unc.status, UncertaintyStatus.UNAVAILABLE)
        self.assertIsNone(unc.relative_field_uncertainty)
        self.assertIsNone(unc.sensor_position_std_m)
        self.assertIn("UNAVAILABLE", unc.disclaimer)

    def test_uncertainty_serialized_in_json(self) -> None:
        """Serialized contract JSON must explicitly disclose UNAVAILABLE uncertainty."""
        contract = build_synthetic_forward_contract()
        parsed = json.loads(contract.to_json())

        self.assertIn("uncertainty", parsed)
        self.assertEqual(parsed["uncertainty"]["status"], "UNAVAILABLE")
        self.assertIsNone(parsed["uncertainty"]["relative_field_uncertainty"])

    # -------------------------------------------------------------------------
    # 20. Independent Numerical Oracle & Closed-Form Verification
    # -------------------------------------------------------------------------

    def test_analytic_center_dipole_independent_oracle(self) -> None:
        """Center dipole must match exact independent algebraic formula: 3 (q . r_e) / (4 pi sigma R^3)."""
        r_scalp = 0.090
        sigma = 0.33
        re = (0.05, -0.06, math.sqrt(r_scalp**2 - 0.05**2 - 0.06**2))
        rs_center = (0.0, 0.0, 0.0)
        q = (1.5e-9, -2.0e-9, 3.0e-9)

        q_dot_re = sum(q[i] * re[i] for i in range(3))
        v_oracle = 3.0 * q_dot_re / (4.0 * math.pi * sigma * (r_scalp ** 3))

        v_hom = compute_homogeneous_sphere_potential(
            electrode_pos_m=re,
            source_pos_m=rs_center,
            dipole_moment_am=q,
            sphere_radius_m=r_scalp,
            conductivity_sm=sigma,
        )
        self.assertAlmostEqual(v_hom, v_oracle, delta=1e-15)

        cond_1shell = ConductorModel(
            model_type=ConductorModelType.SPHERICAL_1SHELL,
            radii_m=(r_scalp,),
            sigmas_sm=(sigma,),
        )
        v_concentric_1 = compute_concentric_spheres_potential(
            electrode_pos_m=re,
            source_pos_m=rs_center,
            dipole_moment_am=q,
            conductor=cond_1shell,
        )
        self.assertAlmostEqual(v_concentric_1, v_oracle, delta=1e-15)

    def test_hardcoded_analytic_benchmark_fixture(self) -> None:
        """On-axis dipole in homogeneous sphere matches high-precision benchmark to machine precision."""
        re = (0.0, 0.0, 0.090)
        rs = (0.0, 0.0, 0.040)
        q = (0.0, 0.0, 1.0e-9)
        v_benchmark = 1.465475850798419e-07

        v_computed = compute_homogeneous_sphere_potential(
            electrode_pos_m=re,
            source_pos_m=rs,
            dipole_moment_am=q,
            sphere_radius_m=0.090,
            conductivity_sm=0.33,
        )
        self.assertAlmostEqual(v_computed, v_benchmark, delta=1e-14)

    # -------------------------------------------------------------------------
    # 21. Boundary Invariants & Comprehensive Error Coverage
    # -------------------------------------------------------------------------

    def test_conductor_radii_sigmas_length_mismatch(self) -> None:
        """Mismatch in radii and conductivities length must raise ConductorGeometryError."""
        with self.assertRaises(ConductorGeometryError):
            ConductorModel(radii_m=(0.08, 0.085, 0.09), sigmas_sm=(0.33, 0.33)).validate()

    def test_conductor_empty_radii(self) -> None:
        """ConductorModel with empty radii must raise ConductorGeometryError."""
        with self.assertRaises(ConductorGeometryError):
            ConductorModel(radii_m=(), sigmas_sm=()).validate()

    def test_conductor_negative_radius(self) -> None:
        """Non-positive radius in ConductorModel must raise ConductorGeometryError."""
        with self.assertRaises(ConductorGeometryError):
            ConductorModel(radii_m=(-0.08, 0.085, 0.09)).validate()

    def test_source_space_empty(self) -> None:
        """Empty source space must raise ForwardModelContractError."""
        with self.assertRaises(ForwardModelContractError):
            SourceSpace(positions_m=()).validate()

    def test_source_space_fixed_orientation_missing(self) -> None:
        """Fixed orientation without orientation vectors must raise ForwardModelContractError."""
        with self.assertRaises(ForwardModelContractError):
            SourceSpace(
                positions_m=((0.0, 0.0, 0.03),),
                orientations=None,
                is_fixed_orientation=True,
            ).validate()

    def test_source_space_fixed_orientation_count_mismatch(self) -> None:
        """Orientation count mismatching positions count must raise ForwardModelContractError."""
        with self.assertRaises(ForwardModelContractError):
            SourceSpace(
                positions_m=((0.0, 0.0, 0.03), (0.0, 0.0, 0.04)),
                orientations=((0.0, 0.0, 1.0),),
                is_fixed_orientation=True,
            ).validate()

    def test_simulate_potentials_empty_moments(self) -> None:
        """Simulating empty moments returns empty list."""
        contract = build_synthetic_forward_contract()
        self.assertEqual(contract.simulate_scalp_potentials([]), [])

    def test_simulate_potentials_dimension_mismatch(self) -> None:
        """Wrong moment vector length raises LeadfieldDimensionMismatchError."""
        contract = build_synthetic_forward_contract()
        with self.assertRaises(LeadfieldDimensionMismatchError):
            contract.simulate_scalp_potentials([[1.0, 2.0]])

    def test_affine_transform_non_finite(self) -> None:
        """Non-finite values in affine transform raise CoordinateFrameMismatchError."""
        bad_matrix = (
            (1.0, 0.0, float("nan"), 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
        with self.assertRaises(CoordinateFrameMismatchError):
            validate_affine_transform(bad_matrix)

    def test_affine_transform_wrong_dimensions(self) -> None:
        """Non-4x4 affine transform raises CoordinateFrameMismatchError."""
        bad_matrix = ((1.0, 0.0), (0.0, 1.0))
        with self.assertRaises(CoordinateFrameMismatchError):
            validate_affine_transform(bad_matrix)

    def test_audit_mne_forward_solution_missing_sol(self) -> None:
        """MNE forward solution missing 'sol' raises ForwardModelContractError."""
        with self.assertRaises(ForwardModelContractError):
            audit_mne_forward_solution({"coord_frame": 4})

    def test_audit_mne_forward_solution_missing_data_or_row_names(self) -> None:
        """MNE forward solution missing 'data' or 'row_names' raises ForwardModelContractError."""
        with self.assertRaises(ForwardModelContractError):
            audit_mne_forward_solution({"coord_frame": 4, "sol": {"data": None}})

    def test_audit_mne_forward_solution_dimension_mismatch(self) -> None:
        """MNE leadfield column count mismatching nsources raises LeadfieldDimensionMismatchError."""
        mock_fwd = {
            "coord_frame": 4,
            "source_ori": 1,  # Fixed
            "nsource": 5,
            "sol": {
                "data": [[1.0] * 3 for _ in range(4)],  # 3 cols instead of 5
                "row_names": ["Fp1", "Fp2", "F3", "F4"],
            },
        }
        with self.assertRaises(LeadfieldDimensionMismatchError):
            audit_mne_forward_solution(mock_fwd)

    def test_audit_mne_forward_solution_source_unit_mismatch(self) -> None:
        """MNE source vertex coordinates > 1.0m (mm) raises CoordinateUnitMismatchError."""
        mock_fwd = {
            "coord_frame": 4,
            "source_ori": 1,
            "nsource": 1,
            "sol": {"data": [[1.0]], "row_names": ["Cz"]},
            "src": [{"rr": [[0.0, 0.0, 50.0]], "inuse": [1]}],  # 50m > 1m (mm scaling error)
        }
        with self.assertRaises(CoordinateUnitMismatchError):
            audit_mne_forward_solution(mock_fwd)

    def test_audit_mne_forward_solution_sensor_unit_mismatch(self) -> None:
        """MNE sensor location > 1.0m (mm) raises CoordinateUnitMismatchError."""
        mock_fwd = {
            "coord_frame": 4,
            "source_ori": 1,
            "nsource": 1,
            "sol": {"data": [[1.0]], "row_names": ["Cz"]},
        }
        mock_info = {
            "ch_names": ["Cz"],
            "chs": [{"ch_name": "Cz", "loc": [0.0, 0.0, 85.0]}],  # 85m > 1m
        }
        with self.assertRaises(CoordinateUnitMismatchError):
            audit_mne_forward_solution(mock_fwd, info=mock_info)

    # -------------------------------------------------------------------------
    # 22. Fail-closed finite geometry / moments (non-finite and zero-norm)
    # -------------------------------------------------------------------------

    def test_conductor_non_finite_sigma_rejected(self) -> None:
        """NaN/Inf conductivity must fail closed before any forward evaluation."""
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(sigma=bad):
                with self.assertRaises(ConductorGeometryError):
                    ConductorModel(sigmas_sm=(bad, 0.0042, 0.33)).validate()

    def test_conductor_non_finite_radius_rejected(self) -> None:
        """NaN/Inf layer radii must fail closed."""
        for bad in (float("nan"), float("inf")):
            with self.subTest(radius=bad):
                with self.assertRaises(ConductorGeometryError):
                    ConductorModel(radii_m=(bad, 0.085, 0.09)).validate()

    def test_sensor_non_finite_position_rejected(self) -> None:
        """Non-finite electrode coordinates must fail closed with an explicit contract error."""
        with self.assertRaises(ForwardModelContractError):
            SensorGeometry(
                channel_names=("Cz", "Fz", "Pz", "Oz"),
                positions_m=(
                    (float("nan"), 0.0, 0.09),
                    (0.0, 0.05, 0.075),
                    (0.0, -0.05, 0.075),
                    (0.0, 0.0, 0.09),
                ),
            ).validate()

    def test_source_non_finite_position_rejected(self) -> None:
        """Non-finite source coordinates must fail closed."""
        with self.assertRaises(ForwardModelContractError):
            SourceSpace(positions_m=((float("nan"), 0.0, 0.02),)).validate()

    def test_source_non_finite_orientation_rejected(self) -> None:
        """Non-finite fixed-orientation vectors must fail closed."""
        with self.assertRaises(ForwardModelContractError):
            SourceSpace(
                positions_m=((0.0, 0.0, 0.02),),
                orientations=((float("nan"), 0.0, 0.0),),
                is_fixed_orientation=True,
            ).validate()

    def test_zero_norm_electrode_potential_fails_closed(self) -> None:
        """Zero-norm electrode must not raise ZeroDivisionError; contract error instead."""
        with self.assertRaises(ConductorGeometryError):
            compute_homogeneous_sphere_potential(
                electrode_pos_m=(0.0, 0.0, 0.0),
                source_pos_m=(0.0, 0.0, 0.02),
                dipole_moment_am=(0.0, 0.0, 1e-8),
            )
        with self.assertRaises(ConductorGeometryError):
            compute_concentric_spheres_potential(
                electrode_pos_m=(0.0, 0.0, 0.0),
                source_pos_m=(0.0, 0.0, 0.02),
                dipole_moment_am=(0.0, 0.0, 1e-8),
                conductor=ConductorModel(),
            )

    def test_non_finite_dipole_moment_in_potential_rejected(self) -> None:
        """Non-finite dipole moments in analytic potentials must fail closed."""
        with self.assertRaises(ForwardModelContractError):
            compute_homogeneous_sphere_potential(
                electrode_pos_m=(0.0, 0.0, 0.09),
                source_pos_m=(0.0, 0.0, 0.02),
                dipole_moment_am=(float("nan"), 0.0, 0.0),
            )

    def test_simulate_non_finite_dipole_moments_rejected(self) -> None:
        """Leadfield simulation must reject NaN/Inf moments (no silent NaN potentials)."""
        contract = build_synthetic_forward_contract(
            sensor_geometry=self.sensors,
            source_space=make_synthetic_source_grid(n_sources=2, is_fixed_orientation=False),
        )
        n_col = contract.source_space.n_columns
        for bad in (float("nan"), float("inf")):
            moments = [0.0] * n_col
            moments[0] = bad
            with self.subTest(moment=bad):
                with self.assertRaises(ForwardModelContractError):
                    contract.simulate_scalp_potentials(moments)


if __name__ == "__main__":
    unittest.main()
