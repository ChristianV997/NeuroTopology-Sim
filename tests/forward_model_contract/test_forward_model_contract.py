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

from collections.abc import Sequence
import dataclasses
from fractions import Fraction
import json
import math
from pathlib import Path
import sys
import unittest

import numpy as np

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
    LeadfieldDimensionMismatchError,
    OrientationType,
    SensorGeometry,
    SourceOutOfBoundsError,
    SourceSpace,
    UncertaintyStatus,
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


def _surface_point(direction, radius=0.09):
    """Scale ``direction`` onto the sphere of ``radius`` metres (exactly on the outer surface)."""
    norm = math.sqrt(sum(c * c for c in direction))
    return tuple(radius * c / norm for c in direction)


def _exact_shell_coefficient(n, radii, sigmas):
    """Independent oracle for the multi-shell coefficient c_n.

    Evaluates the classic transfer-matrix product in exact rational arithmetic (integer
    powers of Fractions are exact), so it carries no cancellation error. Used only to
    check the floating-point implementation; it is a numerical oracle, not a physical one.
    """
    radii = [Fraction(r) for r in radii]
    sigmas = [Fraction(s) for s in sigmas]
    if len(radii) == 1:
        return Fraction(1)
    r_scalp = radii[-1]
    m = [[Fraction(1), Fraction(0)], [Fraction(0), Fraction(1)]]
    for k in range(len(radii) - 1):
        ratio = sigmas[k] / sigmas[k + 1]
        c = Fraction(1, 2 * n + 1)
        r_over_big = (radii[k] / r_scalp) ** (2 * n + 1)
        big_over_r = (r_scalp / radii[k]) ** (2 * n + 1)
        t = [
            [c * ((n + 1) + n * ratio), c * (n + 1) * (1 - ratio) * big_over_r],
            [c * n * (1 - ratio) * r_over_big, c * (n + (n + 1) * ratio)],
        ]
        m = [
            [t[0][0] * m[0][0] + t[0][1] * m[1][0], t[0][0] * m[0][1] + t[0][1] * m[1][1]],
            [t[1][0] * m[0][0] + t[1][1] * m[1][0], t[1][0] * m[0][1] + t[1][1] * m[1][1]],
        ]
    den = n * m[0][0] - (n + 1) * m[1][0]
    a1 = ((n + 1) * m[1][1] - n * m[0][1]) / den
    return Fraction(n, n + 1) * (m[0][0] * a1 + m[0][1]) * (sigmas[-1] / sigmas[0])


def _oracle_potential(electrode, source, moment, radii, sigmas, n_max_terms=60):
    """Series potential using exact-rational c_n (same truncation rule as the module)."""
    re_norm = math.sqrt(sum(c * c for c in electrode))
    rs_norm = math.sqrt(sum(c * c for c in source))
    re_hat = [c / re_norm for c in electrode]
    rs_hat = [c / rs_norm for c in source]
    cos_th = max(-1.0, min(1.0, sum(a * b for a, b in zip(re_hat, rs_hat))))
    qr = sum(q * c for q, c in zip(moment, rs_hat))
    qt = sum(q * c for q, c in zip(moment, re_hat)) - cos_th * qr
    a = rs_norm / radii[-1]
    c1 = float(_exact_shell_coefficient(1, radii, sigmas))
    sum_r = 3.0 * c1 * cos_th * qr
    sum_t = -1.5 * c1 * qt
    p0, p1, an = 1.0, cos_th, 1.0
    for n in range(2, n_max_terms + 1):
        p2 = ((2 * n - 1) * cos_th * p1 - (n - 1) * p0) / n
        pn_prime = n * (p0 - cos_th * p1) / (1.0 - cos_th * cos_th)
        an *= a
        cn = float(_exact_shell_coefficient(n, radii, sigmas))
        sum_r += (2 * n + 1) / n * an * cn * p2 * qr
        sum_t -= (2 * n + 1) / (n * (n + 1)) * an * cn * pn_prime * qt
        p0, p1 = p1, p2
        if an < 1e-15:
            break
    return (sum_r + sum_t) / (4.0 * math.pi * sigmas[-1] * radii[-1] ** 2)


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
        re = _surface_point((0.0, 0.06, 0.067))
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
        re = _surface_point((0.0, 0.06, 0.067))
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
        re = _surface_point((0.0, 0.06, 0.067))
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


    # -------------------------------------------------------------------------
    # 23. Hardening Regressions: Booleans, Conductor Origin, Affine Singularity,
    #     Helper Generators, and MNE Audit Finite Validation
    # -------------------------------------------------------------------------

    def test_boolean_inputs_rejected_across_contract(self) -> None:
        """Boolean values (True/False) must not coerce to 1.0/0.0 in numeric fields."""
        with self.assertRaises(ConductorGeometryError):
            ConductorModel(radii_m=(True, 0.085, 0.09)).validate()
        with self.assertRaises(ConductorGeometryError):
            ConductorModel(sigmas_sm=(True, 0.0042, 0.33)).validate()
        with self.assertRaises(ForwardModelContractError):
            SourceSpace(positions_m=((True, 0.0, 0.02),)).validate()
        with self.assertRaises(ForwardModelContractError):
            compute_homogeneous_sphere_potential(
                electrode_pos_m=(0.0, 0.0, 0.09),
                source_pos_m=(0.0, 0.0, 0.02),
                dipole_moment_am=(True, 0.0, 0.0),
            )

    def test_conductor_origin_validation_and_shift_invariance(self) -> None:
        """Conductor origin_m must be validated (3D, meters) and respected in containment and potential."""
        with self.assertRaises(ConductorGeometryError):
            ConductorModel(origin_m=(0.0, 0.0)).validate()  # type: ignore[arg-type]
        with self.assertRaises(CoordinateUnitMismatchError):
            ConductorModel(origin_m=(0.0, 0.0, 15.0)).validate()

        shift = (0.01, -0.015, 0.02)
        cond_origin = ConductorModel(origin_m=(0.0, 0.0, 0.0))
        cond_shifted = ConductorModel(origin_m=shift)

        re_0 = (0.0, 0.0, 0.090)
        rs_0 = (0.01, -0.02, 0.03)
        q = (1.0e-9, -2.0e-9, 3.0e-9)

        re_s = (re_0[0] + shift[0], re_0[1] + shift[1], re_0[2] + shift[2])
        rs_s = (rs_0[0] + shift[0], rs_0[1] + shift[1], rs_0[2] + shift[2])

        v_0 = compute_concentric_spheres_potential(re_0, rs_0, q, cond_origin)
        v_s = compute_concentric_spheres_potential(re_s, rs_s, q, cond_shifted)
        self.assertAlmostEqual(v_0, v_s, delta=1e-15)

        cond_down = ConductorModel(origin_m=(0.0, 0.0, -0.01))
        with self.assertRaises(SourceOutOfBoundsError):
            SourceSpace(positions_m=((0.0, 0.0, 0.075),)).validate(cond_down)

    def test_singular_affine_transform_rejected(self) -> None:
        """Affine transform with singular 3x3 linear block (det=0) must fail closed."""
        singular_matrix = (
            (0.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
        with self.assertRaises(CoordinateFrameMismatchError):
            validate_affine_transform(singular_matrix)

    def test_synthetic_generators_validate_parameters(self) -> None:
        """Synthetic sensor and source generators must fail closed on non-finite, non-positive, or mm radii."""
        for bad_r in (float("nan"), float("inf"), 0.0, -0.09):
            with self.subTest(sensor_radius=bad_r):
                with self.assertRaises(ConductorGeometryError):
                    make_standard_1020_synthetic_sensors(radius_m=bad_r)

        with self.assertRaises(CoordinateUnitMismatchError):
            make_synthetic_source_grid(n_sources=4, max_radius_m=65.0)
        for bad_r in (float("nan"), float("inf"), 0.0, -0.05):
            with self.subTest(source_max_radius=bad_r):
                with self.assertRaises(ForwardModelContractError):
                    make_synthetic_source_grid(n_sources=4, max_radius_m=bad_r)
        with self.assertRaises(ForwardModelContractError):
            make_synthetic_source_grid(n_sources=0, max_radius_m=0.065)

    def test_audit_mne_forward_solution_rejects_non_finite_data_and_coords(self) -> None:
        """audit_mne_forward_solution must reject NaN/Inf in leadfield data, source rr, or sensor loc."""
        bad_leadfield_fwd = {
            "coord_frame": 4,
            "source_ori": 1,
            "nsource": 1,
            "sol": {
                "data": [[float("nan")], [1.0], [-0.5], [-0.5]],
                "row_names": ["Fp1", "Fp2", "F3", "F4"],
            },
        }
        with self.assertRaises(ForwardModelContractError):
            audit_mne_forward_solution(bad_leadfield_fwd)

        bad_src_fwd = {
            "coord_frame": 4,
            "source_ori": 1,
            "nsource": 1,
            "sol": {
                "data": [[1.0], [-1.0], [0.5], [-0.5]],
                "row_names": ["Fp1", "Fp2", "F3", "F4"],
            },
            "src": [{"rr": [[float("nan"), 0.0, 0.02]], "inuse": [1]}],
        }
        with self.assertRaises(ForwardModelContractError):
            audit_mne_forward_solution(bad_src_fwd)

        valid_fwd = {
            "coord_frame": 4,
            "source_ori": 1,
            "nsource": 1,
            "sol": {
                "data": [[1.0], [-1.0], [0.5], [-0.5]],
                "row_names": ["Fp1", "Fp2", "F3", "F4"],
            },
        }
        bad_info = {
            "ch_names": ["Fp1", "Fp2", "F3", "F4"],
            "chs": [
                {"ch_name": "Fp1", "loc": [float("nan"), 0.07, 0.05]},
                {"ch_name": "Fp2", "loc": [0.0, -0.07, 0.05]},
                {"ch_name": "F3", "loc": [-0.05, 0.0, 0.06]},
                {"ch_name": "F4", "loc": [0.05, 0.0, 0.06]},
            ],
        }
        with self.assertRaises(ForwardModelContractError):
            audit_mne_forward_solution(valid_fwd, info=bad_info)


class TestForwardModelNumericalAndGeometryHardening(unittest.TestCase):
    """Regressions for numeric-type, geometry, stability, and fabrication defects.

    Each test failed against the previous revision of the contract. They check
    engineering behaviour (stable error types, fail-closed geometry, numerical
    stability against an exact-rational oracle); none of them is evidence that the
    spherical model is physically valid for real heads.
    """

    def setUp(self) -> None:
        self.conductor = ConductorModel()
        self.sensors = make_standard_1020_synthetic_sensors(self.conductor.scalp_radius_m)
        self.electrode = (0.0, 0.0, 0.09)
        self.source = (0.02, 0.01, 0.03)
        self.moment = (1.0e-9, 0.0, 0.0)
        self.identity = (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )

    # -- numeric types ---------------------------------------------------------

    def test_numeric_strings_and_non_vectors_rejected_with_contract_errors(self) -> None:
        with self.assertRaises(ConductorGeometryError):
            ConductorModel(sigmas_sm=("0.33", 0.0042, 0.33)).validate()
        with self.assertRaises(ConductorGeometryError):
            ConductorModel(radii_m=("0.08", 0.085, 0.09)).validate()
        with self.assertRaises(ConductorGeometryError):
            compute_homogeneous_sphere_potential(
                self.electrode, self.source, self.moment, 0.09, "0.33"
            )
        with self.assertRaises(ForwardModelContractError):
            compute_concentric_spheres_potential(
                self.electrode, self.source, ("1.0", 0.0, 0.0), self.conductor
            )
        for bad in ("123", 5, None, 1.5):
            with self.subTest(vector=bad):
                with self.assertRaises(ForwardModelContractError):
                    compute_homogeneous_sphere_potential(bad, self.source, self.moment)

    def test_n_max_terms_must_be_positive_integer(self) -> None:
        for bad in (0, -3, True, 2.5, "9"):
            with self.subTest(n_max_terms=bad):
                with self.assertRaises(ForwardModelContractError):
                    compute_concentric_spheres_potential(
                        self.electrode, self.source, self.moment, self.conductor, n_max_terms=bad
                    )
                with self.assertRaises(ForwardModelContractError):
                    compute_homogeneous_sphere_potential(
                        self.electrode, self.source, self.moment, n_max_terms=bad
                    )
        dipole_only = compute_concentric_spheres_potential(
            self.electrode, self.source, self.moment, self.conductor, n_max_terms=1
        )
        self.assertTrue(math.isfinite(dipole_only))

    # -- geometry of the public potential functions ----------------------------

    def test_public_potential_requires_source_in_innermost_shell(self) -> None:
        brain_r = self.conductor.brain_radius_m
        for radius in (0.083, brain_r):  # skull compartment; exactly on the brain boundary
            with self.subTest(source_radius=radius):
                with self.assertRaises(SourceOutOfBoundsError):
                    compute_concentric_spheres_potential(
                        self.electrode, (radius, 0.0, 0.0), self.moment, self.conductor
                    )
        inside = compute_concentric_spheres_potential(
            self.electrode, (0.0799, 0.0, 0.0), self.moment, self.conductor
        )
        self.assertTrue(math.isfinite(inside))

    def test_public_potential_requires_electrode_on_outer_surface(self) -> None:
        engines = (
            ("homogeneous", lambda e: compute_homogeneous_sphere_potential(e, self.source, self.moment)),
            (
                "concentric",
                lambda e: compute_concentric_spheres_potential(e, self.source, self.moment, self.conductor),
            ),
        )
        for name, evaluate in engines:
            with self.subTest(engine=name, case="inside the head"):
                with self.assertRaises(ConductorGeometryError):
                    evaluate((0.0, 0.0, 0.05))
            with self.subTest(engine=name, case="outside the head"):
                with self.assertRaises(ConductorGeometryError):
                    evaluate((0.0, 0.0, 0.15))
            with self.subTest(engine=name, case="millimetres"):
                with self.assertRaises(CoordinateUnitMismatchError):
                    evaluate((0.0, 0.0, 90.0))
            with self.subTest(engine=name, case="within placement tolerance"):
                self.assertTrue(math.isfinite(evaluate((0.0, 0.0, 0.09 + 5.0e-7))))

    def test_builder_requires_sensors_on_scalp_relative_to_conductor_origin(self) -> None:
        sources = make_synthetic_source_grid(n_sources=4)
        with self.assertRaises(ConductorGeometryError):
            build_synthetic_forward_contract(
                sensor_geometry=make_standard_1020_synthetic_sensors(0.12), source_space=sources
            )

        shift = (0.01, -0.015, 0.02)

        def moved(points):
            return tuple(tuple(c + s for c, s in zip(p, shift)) for p in points)

        shifted_conductor = ConductorModel(origin_m=shift)
        shifted_sources = SourceSpace(positions_m=moved(sources.positions_m))
        with self.assertRaises(ConductorGeometryError):  # montage still centred on (0, 0, 0)
            build_synthetic_forward_contract(
                conductor_model=shifted_conductor,
                sensor_geometry=self.sensors,
                source_space=shifted_sources,
            )

        shifted_sensors = SensorGeometry(
            channel_names=self.sensors.channel_names, positions_m=moved(self.sensors.positions_m)
        )
        base = build_synthetic_forward_contract(sensor_geometry=self.sensors, source_space=sources)
        relocated = build_synthetic_forward_contract(
            conductor_model=shifted_conductor,
            sensor_geometry=shifted_sensors,
            source_space=shifted_sources,
        )
        for row_a, row_b in zip(base.leadfield, relocated.leadfield):
            for a, b in zip(row_a, row_b):
                self.assertAlmostEqual(a, b, delta=1e-9)

    # -- numerical stability and internal consistency --------------------------

    def test_multishell_potential_matches_exact_rational_oracle(self) -> None:
        sigmas = (0.33, 0.0042, 0.33)
        cases = (
            ((0.080, 0.085, 0.090), 0.8),
            ((0.070, 0.085, 0.090), 0.8),
            ((0.060, 0.080, 0.090), 0.9),
            ((0.050, 0.075, 0.090), 0.9),
            ((0.045, 0.070, 0.090), 0.95),
        )
        electrode = _surface_point((0.3, 0.5, 0.8))
        moment = (1.0e-9, -2.0e-9, 3.0e-9)
        for radii, fraction in cases:
            with self.subTest(radii=radii, source_fraction=fraction):
                conductor = ConductorModel(radii_m=radii, sigmas_sm=sigmas)
                source = tuple(fraction * radii[0] * c for c in (0.48, -0.6, 0.64))
                expected = _oracle_potential(electrode, source, moment, radii, sigmas)
                actual = compute_concentric_spheres_potential(electrode, source, moment, conductor)
                self.assertAlmostEqual(actual / expected, 1.0, delta=1e-9)

    def test_single_shell_and_equal_conductivity_shells_reduce_to_homogeneous_sphere(self) -> None:
        electrode = _surface_point((0.3, 0.5, 0.8))
        source = (0.01, -0.02, 0.03)  # inside the 50 mm brain of the equal-shell model below
        moment = (1.0e-9, -2.0e-9, 3.0e-9)
        homogeneous = compute_homogeneous_sphere_potential(
            electrode, source, moment, sphere_radius_m=0.09, conductivity_sm=0.33
        )
        one_shell = ConductorModel(
            model_type=ConductorModelType.SPHERICAL_1SHELL, radii_m=(0.09,), sigmas_sm=(0.33,)
        )
        equal_shells = ConductorModel(radii_m=(0.05, 0.08, 0.09), sigmas_sm=(0.33, 0.33, 0.33))
        for label, conductor in (("1-shell", one_shell), ("3 equal shells", equal_shells)):
            with self.subTest(model=label):
                value = compute_concentric_spheres_potential(electrode, source, moment, conductor)
                self.assertAlmostEqual(value / homogeneous, 1.0, delta=1e-12)

    def test_small_inner_radius_gives_finite_continuous_potential_not_silent_zero(self) -> None:
        z_electrode = (0.0, 0.0, 0.09)
        z_moment = (0.0, 0.0, 1.0)
        centre = {}
        for brain in (1.0e-4, 1.0e-6):
            conductor = ConductorModel(radii_m=(brain, 0.085, 0.09))
            centre[brain] = compute_concentric_spheres_potential(
                z_electrode, (0.0, 0.0, 0.0), z_moment, conductor
            )
            self.assertGreater(centre[brain], 1.0)  # previously exactly 0.0 for brain = 1e-6
        self.assertAlmostEqual(centre[1.0e-6] / centre[1.0e-4], 1.0, delta=1e-3)
        for brain in (1.0e-3, 1.0e-4, 1.0e-6):
            with self.subTest(brain_radius=brain):
                conductor = ConductorModel(radii_m=(brain, 0.085, 0.09))
                reference = compute_concentric_spheres_potential(
                    z_electrode, (0.0, 0.0, 0.0), z_moment, conductor
                )
                offset = compute_concentric_spheres_potential(
                    z_electrode, (0.0, 0.0, 0.5 * brain), z_moment, conductor
                )
                self.assertTrue(math.isfinite(offset))
                self.assertAlmostEqual(offset / reference, 1.0, delta=0.05)

    def test_non_finite_potential_output_rejected(self) -> None:
        huge = (1.7e308, 0.0, 0.0)
        with self.assertRaises(ForwardModelContractError):
            compute_homogeneous_sphere_potential(self.electrode, self.source, huge)
        with self.assertRaises(ForwardModelContractError):
            compute_concentric_spheres_potential(self.electrode, self.source, huge, self.conductor)
        contract = build_synthetic_forward_contract(
            sensor_geometry=self.sensors, source_space=make_synthetic_source_grid(n_sources=2)
        )
        n_col = contract.source_space.n_columns
        with self.assertRaises(ForwardModelContractError):
            contract.simulate_scalp_potentials([1.0e308] * n_col)
        finite = contract.simulate_scalp_potentials([1.0e3] * n_col)
        self.assertTrue(all(math.isfinite(x) for row in finite for x in row))

    # -- fabrication and silent substitution -----------------------------------

    def test_coordinate_transform_validates_fixed_orientations_before_normalising(self) -> None:
        for bad in ((0.0, 0.0, 0.0), (3.0, 0.0, 0.0), (float("nan"), 0.0, 0.0)):
            with self.subTest(orientation=bad):
                mni = SourceSpace(
                    positions_m=((0.02, 0.0, 0.0),),
                    orientations=(bad,),
                    is_fixed_orientation=True,
                    coordinate_frame=CoordinateFrame.MNI,
                )
                with self.assertRaises(ForwardModelContractError):
                    build_synthetic_forward_contract(
                        sensor_geometry=self.sensors, source_space=mni, coord_transform=self.identity
                    )

        quarter_turn = (
            (0.0, -1.0, 0.0, 0.0),
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
        mni = SourceSpace(
            positions_m=((0.02, 0.0, 0.0),),
            orientations=((1.0, 0.0, 0.0),),
            is_fixed_orientation=True,
            coordinate_frame=CoordinateFrame.MNI,
        )
        result = build_synthetic_forward_contract(
            sensor_geometry=self.sensors, source_space=mni, coord_transform=quarter_turn
        )
        self.assertEqual(result.source_space.coordinate_frame, CoordinateFrame.HEAD)
        orientation = result.source_space.orientations[0]
        self.assertAlmostEqual(orientation[0], 0.0, delta=1e-12)
        self.assertAlmostEqual(orientation[1], 1.0, delta=1e-12)

        free = SourceSpace(
            positions_m=((0.02, 0.0, 0.0),),
            orientations=((0.0, 0.0, 0.0),),
            is_fixed_orientation=False,
            coordinate_frame=CoordinateFrame.MNI,
        )
        free_result = build_synthetic_forward_contract(
            sensor_geometry=self.sensors, source_space=free, coord_transform=self.identity
        )
        self.assertNotEqual(free_result.source_space.orientations, ((0.0, 0.0, 1.0),))

    def _audit_fixture(self):
        return {
            "coord_frame": 4,
            "source_ori": 2,
            "nsource": 1,
            "sol": {
                "data": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0], [1.0, 0.0, 1.0]],
                "row_names": ["A", "B", "C", "D"],
            },
            "src": [{"rr": [[0.01, 0.0, 0.0]], "inuse": [1]}],
        }

    def test_audit_aligns_sensor_positions_by_channel_name(self) -> None:
        chs = [
            {"ch_name": name, "loc": [x, 0.0, 0.09, 0.0, 0.0, 0.0]}
            for name, x in (("D", 0.04), ("C", 0.03), ("B", 0.02), ("A", 0.01))
        ]
        result = audit_mne_forward_solution(
            self._audit_fixture(), info={"chs": chs}, expected_conductor=ConductorModel()
        )
        by_name = {
            name: pos[0]
            for name, pos in zip(
                result.sensor_geometry.channel_names, result.sensor_geometry.positions_m
            )
        }
        self.assertEqual(by_name, {"A": 0.01, "B": 0.02, "C": 0.03, "D": 0.04})
        self.assertEqual(result.provenance["sensor_positions"], "info_chs")
        self.assertEqual(result.provenance["source_positions"], "mne_src")
        self.assertEqual(result.warnings, ())

    def test_audit_flags_placeholder_geometry_instead_of_presenting_it_as_measured(self) -> None:
        fwd = self._audit_fixture()
        no_info = audit_mne_forward_solution(fwd)
        self.assertEqual(no_info.provenance["sensor_positions"], "placeholder")
        self.assertTrue(
            any("sensor" in w.lower() and "placeholder" in w.lower() for w in no_info.warnings)
        )

        chs = [{"ch_name": n, "loc": [0.01, 0.0, 0.09, 0.0, 0.0, 0.0]} for n in ("A", "B")]
        partial = audit_mne_forward_solution(fwd, info={"chs": chs})
        self.assertEqual(partial.provenance["sensor_positions"], "placeholder")
        self.assertEqual(
            len(partial.sensor_geometry.positions_m), len(partial.sensor_geometry.channel_names)
        )
        self.assertTrue(any("C" in w and "D" in w for w in partial.warnings))

        without_vertices = dict(fwd, src=[])
        r = audit_mne_forward_solution(without_vertices)
        self.assertEqual(r.provenance["source_positions"], "placeholder")
        self.assertTrue(
            any("source" in w.lower() and "placeholder" in w.lower() for w in r.warnings)
        )

    def test_audit_labels_default_conductor_as_placeholder(self) -> None:
        fwd = self._audit_fixture()
        default = audit_mne_forward_solution(fwd)
        self.assertEqual(default.provenance["conductor_model"], "default_placeholder")
        self.assertTrue(
            any("conductor" in w.lower() and "placeholder" in w.lower() for w in default.warnings)
        )
        expected = ConductorModel(radii_m=(0.07, 0.08, 0.09))
        given = audit_mne_forward_solution(fwd, expected_conductor=expected)
        self.assertEqual(given.provenance["conductor_model"], "expected_conductor")
        self.assertEqual(given.conductor_model, expected)
        self.assertFalse(any("conductor" in w.lower() for w in given.warnings))

    # -- stable error types for malformed leadfield matrices -------------------

    def test_leadfield_helpers_reject_ragged_and_non_finite_matrices(self) -> None:
        helpers = (
            ("apply_average_reference", apply_average_reference),
            ("verify_average_reference_invariant", verify_average_reference_invariant),
            ("compute_leadfield_diagnostics", lambda m: compute_leadfield_diagnostics(m, False, 1)),
            ("apply_channel_reference", lambda m: apply_channel_reference(m, ("a", "b"), "a")),
        )
        malformed = (
            ("ragged short", [[1.0, 2.0], [3.0]]),
            ("ragged long", [[1.0, 2.0], [3.0, 4.0, 5.0]]),
            ("empty rows", [[], []]),
        )
        for name, helper in helpers:
            for label, matrix in malformed:
                with self.subTest(helper=name, case=label):
                    with self.assertRaises(LeadfieldDimensionMismatchError):
                        helper(matrix)
            for bad in (float("nan"), float("inf")):
                with self.subTest(helper=name, value=bad):
                    with self.assertRaises(ForwardModelContractError):
                        helper([[bad, 1.0], [1.0, 1.0]])
        with self.assertRaises(LeadfieldDimensionMismatchError):
            apply_channel_reference([[1.0], [2.0]], ("a", "b", "c"), "a")

    # -- malformed-argument fuzz findings ---------------------------------------

    def test_malformed_container_arguments_raise_contract_errors(self) -> None:
        import dual_engine.forward_model_contract as fmc

        matrix = [[1.0, 2.0], [3.0, 4.0]]
        cases = {
            "average_reference_scalar": lambda: fmc.apply_average_reference(5),
            "verify_average_scalar": lambda: fmc.verify_average_reference_invariant(5),
            "channel_ref_names_none": lambda: fmc.apply_channel_reference(matrix, None, "a"),
            "channel_ref_names_scalar": lambda: fmc.apply_channel_reference(matrix, 5, "a"),
            "verify_channel_names_none": lambda: fmc.verify_channel_reference_invariant(matrix, None, "a"),
            "verify_average_bad_tolerance": lambda: fmc.verify_average_reference_invariant(matrix, (1.0,)),
            "verify_average_nan_tolerance": lambda: fmc.verify_average_reference_invariant(matrix, float("nan")),
            "verify_average_negative_tolerance": lambda: fmc.verify_average_reference_invariant(matrix, -1.0),
            "verify_channel_bad_tolerance": lambda: fmc.verify_channel_reference_invariant(matrix, ("a", "b"), "a", b"x"),
            "sources_validate_string_radii_conductor": lambda: fmc.SourceSpace(
                positions_m=((0.01, 0.0, 0.0),), orientations=None, is_fixed_orientation=False,
                coordinate_frame=fmc.CoordinateFrame.HEAD,
            ).validate(fmc.ConductorModel(radii_m=("0.08", "0.085", "0.09"))),
            "audit_row_names_scalar": lambda: fmc.audit_mne_forward_solution(
                {"coord_frame": 4, "sol": {"data": [[1.0, 2.0, 3.0]], "row_names": 5}, "nsource": 1, "source_ori": 2, "src": []},
                None,
                None,
            ),
            "audit_inuse_longer_than_rr": lambda: fmc.audit_mne_forward_solution(
                {
                    "coord_frame": 4,
                    "sol": {"data": [[1.0]], "row_names": ["a"]},
                    "nsource": 1,
                    "source_ori": 1,
                    "src": [{"rr": [[0.01, 0.0, 0.0]], "inuse": [1, 1]}],
                },
                None,
                None,
            ),
            "audit_nsource_string": lambda: fmc.audit_mne_forward_solution(
                {"coord_frame": 4, "sol": {"data": [[1.0]], "row_names": ["a"]}, "nsource": "x", "source_ori": 1, "src": []},
                None,
                None,
            ),
            "affine_none": lambda: fmc.validate_affine_transform(None),
            "affine_scalar_rows": lambda: fmc.validate_affine_transform([1, 2, 3, 4]),
            "source_grid_huge_count": lambda: fmc.make_synthetic_source_grid(2 ** 70),
            "series_terms_unbounded": lambda: fmc.compute_homogeneous_sphere_potential(
                (0.0, 0.0, 0.09), (0.0, 0.0, 0.02), (0.0, 0.0, 1e-8), 0.09, 0.33, 10 ** 9
            ),
            "audit_scalar_leadfield": lambda: fmc.audit_mne_forward_solution(
                {"coord_frame": 4, "sol": {"data": 5, "row_names": ["a"]}, "nsource": 1, "source_ori": 2, "src": []},
                None,
                None,
            ),
        }
        for label, call in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(ForwardModelContractError):
                    call()

    def test_leadfield_diagnostics_overflowing_magnitudes_fail_closed(self) -> None:
        import dual_engine.forward_model_contract as fmc

        huge = [[1e308, 1e308, 1e308], [-1e308, 1e308, 1e308], [1e308, -1e308, 1e308]]
        with self.assertRaises(ForwardModelContractError):
            fmc.compute_leadfield_diagnostics(huge, False, 3)

    # -- claims -----------------------------------------------------------------

    def test_docs_and_source_do_not_claim_physical_verification(self) -> None:
        module_source = (_REPO_ROOT / "dual_engine" / "forward_model_contract.py").read_text(encoding="utf-8")
        docs = (_REPO_ROOT / "docs" / "forward_model_contract.md").read_text(encoding="utf-8")
        for text, label in ((module_source, "module"), (docs, "docs")):
            with self.subTest(text=label):
                lowered = text.lower()
                self.assertNotIn("verified physical effect", lowered)
                self.assertNotIn("exact spherical boundary-value solution", lowered)


_ACCEPTED_MODEL_TYPE_VALUES = ("spherical_3shell", "spherical_1shell")
_ACCEPTED_FRAME_VALUES = ("head", "mni")


class TestForwardModelEnumMemberValidation(unittest.TestCase):
    """Non-members of the forward-model enums fail closed at validate() and build.

    A plain string is not an enum member, including a string equal to a member
    value, a case or whitespace variant, or a member of a different enum.
    OrientationType is not an input field; the orientation mode is the bool
    ``is_fixed_orientation``. These checks are synthetic-contract hygiene only.
    """

    def setUp(self) -> None:
        self.conductor = ConductorModel()
        self.sensors = make_standard_1020_synthetic_sensors(self.conductor.scalp_radius_m)
        self.interior = ((0.0, 0.0, 0.02),)
        self.unit = ((0.0, 0.0, 1.0),)
        self.electrode = self.sensors.positions_m[0]
        self.moment = (0.0, 0.0, 1.0e-9)

    def _assert_domain_error(self, exc_type, call, field, accepted) -> None:
        with self.assertRaises(exc_type) as caught:
            call()
        message = str(caught.exception)
        self.assertNotIsInstance(caught.exception, AttributeError)
        self.assertIn(field, message)
        self.assertIn("Accepted values:", message)
        for token in accepted:
            self.assertIn(token, message)

    def test_invalid_values_with_unprintable_repr_fail_as_contract_errors(self) -> None:
        """A hostile input representation cannot replace the contract exception."""

        class Unprintable:
            def __repr__(self) -> str:
                raise RuntimeError("synthetic repr probe")

            def __len__(self) -> int:
                raise RuntimeError("synthetic length probe")

        class UncoercibleReal(float):
            def __float__(self) -> float:
                raise RuntimeError("synthetic numeric-conversion probe")

            def __repr__(self) -> str:
                raise RuntimeError("synthetic numeric-repr probe")

        bad = Unprintable()
        bad_real = UncoercibleReal(0.0)
        cases = (
            (ConductorGeometryError, lambda: ConductorModel(model_type=bad).validate()),
            (
                CoordinateFrameMismatchError,
                lambda: dataclasses.replace(self.sensors, coordinate_frame=bad).validate(),
            ),
            (
                CoordinateFrameMismatchError,
                lambda: SourceSpace(positions_m=self.interior, coordinate_frame=bad).validate(),
            ),
            (
                ForwardModelContractError,
                lambda: SourceSpace(
                    positions_m=self.interior,
                    orientations=self.unit,
                    is_fixed_orientation=bad,
                ).validate(),
            ),
            (
                ForwardModelContractError,
                lambda: SourceSpace(
                    positions_m=self.interior,
                    orientations=((bad_real, 0.0, 1.0),),
                    is_fixed_orientation=True,
                ).validate(),
            ),
            (
                ForwardModelContractError,
                lambda: SourceSpace(
                    positions_m=self.interior,
                    orientations=bad,
                    is_fixed_orientation=False,
                ).validate(),
            ),
            (
                ForwardModelContractError,
                lambda: SourceSpace(
                    positions_m=self.interior,
                    orientations=((bad, 0.0, 1.0),),
                    is_fixed_orientation=True,
                ).validate(),
            ),
            (
                ForwardModelContractError,
                lambda: SourceSpace(
                    positions_m=self.interior,
                    orientations=(bad,),
                    is_fixed_orientation=True,
                ).validate(),
            ),
            (
                ForwardModelContractError,
                lambda: build_synthetic_forward_contract(
                    sensor_geometry=self.sensors,
                    source_space=SourceSpace(
                        positions_m=self.interior, is_fixed_orientation=bad
                    ),
                ),
            ),
        )
        for expected_error, call in cases:
            with self.subTest(expected_error=expected_error.__name__):
                with self.assertRaises(expected_error):
                    call()

    def test_invalid_values_are_not_echoed_in_contract_errors(self) -> None:
        """Error text names the contract field but never formats rejected input."""
        marker = "SYNTHETIC-DO-NOT-ECHO"
        cases = (
            (
                ConductorGeometryError,
                lambda value: ConductorModel(model_type=value).validate(),
            ),
            (
                CoordinateFrameMismatchError,
                lambda value: dataclasses.replace(self.sensors, coordinate_frame=value).validate(),
            ),
            (
                ForwardModelContractError,
                lambda value: SourceSpace(
                    positions_m=self.interior, is_fixed_orientation=value
                ).validate(),
            ),
            (
                ForwardModelContractError,
                lambda value: SourceSpace(
                    positions_m=self.interior,
                    orientations=value,
                    is_fixed_orientation=False,
                ).validate(),
            ),
            (
                ForwardModelContractError,
                lambda value: build_synthetic_forward_contract(
                    sensor_geometry=self.sensors,
                    source_space=SourceSpace(
                        positions_m=self.interior, is_fixed_orientation=value
                    ),
                ),
            ),
            (
                ForwardModelContractError,
                lambda value: SourceSpace(
                    positions_m=self.interior,
                    orientations=((value, 0.0, 1.0),),
                    is_fixed_orientation=True,
                ).validate(),
            ),
            (
                ForwardModelContractError,
                lambda value: build_synthetic_forward_contract(
                    sensor_geometry=self.sensors,
                    source_space=SourceSpace(
                        positions_m=self.interior,
                        orientations=((value, 0.0, 1.0),),
                        is_fixed_orientation=True,
                    ),
                ),
            ),
            (
                ForwardModelContractError,
                lambda value: SourceSpace(
                    positions_m=self.interior,
                    orientations=(value,),
                    is_fixed_orientation=True,
                ).validate(),
            ),
        )
        for expected_error, call in cases:
            with self.subTest(expected_error=expected_error.__name__):
                with self.assertRaises(expected_error) as caught:
                    call(marker)
                self.assertNotIn(marker, str(caught.exception))

    def test_model_type_non_member_rejected_at_validate(self) -> None:
        """Unsupported model_type values are rejected before any ``.value`` access."""
        rejected = (
            "unsupported-string",
            "spherical_3shell",
            "SPHERICAL_3SHELL",
            " spherical_3shell",
            "spherical_3shell ",
            "Spherical_3shell",
            "anatomical_bem",
            None,
            1,
            b"spherical_3shell",
            CoordinateFrame.HEAD,
            OrientationType.FREE,
        )
        for bad in rejected:
            with self.subTest(model_type=bad):
                self._assert_domain_error(
                    ConductorGeometryError,
                    lambda bad=bad: ConductorModel(model_type=bad).validate(),
                    "model_type",
                    _ACCEPTED_MODEL_TYPE_VALUES,
                )
        with self.subTest(model_type="spherical_1shell"):
            one_shell = ConductorModel(
                model_type="spherical_1shell",
                radii_m=(0.09,),
                sigmas_sm=(0.33,),
            )
            self._assert_domain_error(
                ConductorGeometryError,
                one_shell.validate,
                "model_type",
                _ACCEPTED_MODEL_TYPE_VALUES,
            )

    def test_coordinate_frame_non_member_rejected_at_validate(self) -> None:
        """Sensor and source frames reject non-members, including the string 'head'."""
        rejected = (
            "bogus-frame",
            "head",
            "mni",
            "HEAD",
            "MNI",
            " head",
            "head ",
            "mni ",
            "unknown",
            None,
            1,
            b"head",
            ConductorModelType.SPHERICAL_3SHELL,
            OrientationType.FREE,
        )
        for bad in rejected:
            with self.subTest(owner="sensor", coordinate_frame=bad):
                sensors = dataclasses.replace(self.sensors, coordinate_frame=bad)
                self._assert_domain_error(
                    CoordinateFrameMismatchError,
                    sensors.validate,
                    "sensor_geometry.coordinate_frame",
                    _ACCEPTED_FRAME_VALUES,
                )
            with self.subTest(owner="source", coordinate_frame=bad):
                sources = SourceSpace(positions_m=self.interior, coordinate_frame=bad)
                self._assert_domain_error(
                    CoordinateFrameMismatchError,
                    sources.validate,
                    "source_space.coordinate_frame",
                    _ACCEPTED_FRAME_VALUES,
                )

    def test_orientation_flag_non_bool_rejected_at_validate(self) -> None:
        """OrientationType and strings are not coerced into is_fixed_orientation."""
        rejected = (
            "free",
            "fixed",
            "FREE",
            "FIXED",
            " fixed",
            "fixed ",
            "unsupported",
            "false",
            "",
            None,
            1,
            0,
            b"fixed",
            OrientationType.FREE,
            OrientationType.FIXED,
            CoordinateFrame.HEAD,
        )
        for bad in rejected:
            with self.subTest(is_fixed_orientation=bad):
                sources = SourceSpace(
                    positions_m=self.interior,
                    orientations=self.unit,
                    is_fixed_orientation=bad,
                )
                self._assert_domain_error(
                    ForwardModelContractError,
                    sources.validate,
                    "source_space.is_fixed_orientation",
                    ("True", "False"),
                )

    def test_orientation_table_rejects_non_sequence(self) -> None:
        """A bare string or scalar is not an orientation table."""
        for bad in ("free", b"free", 5):
            with self.subTest(orientations=bad):
                sources = SourceSpace(
                    positions_m=self.interior,
                    orientations=bad,
                    is_fixed_orientation=False,
                )
                self._assert_domain_error(
                    ForwardModelContractError,
                    sources.validate,
                    "source_space.orientations",
                    ("sequence of length-3 vectors", "None"),
                )

    def test_numpy_orientation_inputs_are_explicitly_not_coerced(self) -> None:
        """The API requires Python Sequence/bool values, not NumPy container scalars."""
        array_source = SourceSpace(
            positions_m=self.interior,
            orientations=np.asarray(self.unit, dtype=float),
            is_fixed_orientation=True,
        )
        with self.assertRaises(ForwardModelContractError) as array_error:
            array_source.validate()
        self.assertIn("source_space.orientations", str(array_error.exception))
        self.assertIn("sequence of length-3 vectors", str(array_error.exception))

        numpy_bool_source = SourceSpace(
            positions_m=self.interior,
            orientations=self.unit,
            is_fixed_orientation=np.bool_(True),
        )
        with self.assertRaises(ForwardModelContractError) as bool_error:
            numpy_bool_source.validate()
        self.assertIn("source_space.is_fixed_orientation", str(bool_error.exception))
        self.assertIn("True, False", str(bool_error.exception))

    def test_build_rejects_non_members_without_attribute_error(self) -> None:
        """build_synthetic_forward_contract fails in validate(), not on ``.value``."""
        cases = {
            "conductor-unsupported": dict(
                conductor_model=ConductorModel(model_type="unsupported-string"),
                sensor_geometry=self.sensors,
                source_space=SourceSpace(positions_m=self.interior),
            ),
            "conductor-value-string": dict(
                conductor_model=ConductorModel(model_type="spherical_3shell"),
                sensor_geometry=self.sensors,
                source_space=SourceSpace(positions_m=self.interior),
            ),
            "sensors-bogus": dict(
                sensor_geometry=dataclasses.replace(self.sensors, coordinate_frame="bogus-frame"),
                source_space=SourceSpace(positions_m=self.interior),
            ),
            "sensors-head-string": dict(
                sensor_geometry=dataclasses.replace(self.sensors, coordinate_frame="head"),
                source_space=SourceSpace(positions_m=self.interior),
            ),
            "sources-bogus": dict(
                sensor_geometry=self.sensors,
                source_space=SourceSpace(positions_m=self.interior, coordinate_frame="bogus-frame"),
            ),
            "sources-head-string": dict(
                sensor_geometry=self.sensors,
                source_space=SourceSpace(positions_m=self.interior, coordinate_frame="head"),
            ),
            "orientation-string": dict(
                sensor_geometry=self.sensors,
                source_space=SourceSpace(
                    positions_m=self.interior,
                    orientations=self.unit,
                    is_fixed_orientation="free",
                ),
            ),
            "orientation-enum": dict(
                sensor_geometry=self.sensors,
                source_space=SourceSpace(
                    positions_m=self.interior,
                    orientations=self.unit,
                    is_fixed_orientation=OrientationType.FREE,
                ),
            ),
        }
        for label, kwargs in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(ForwardModelContractError) as caught:
                    build_synthetic_forward_contract(**kwargs)
                self.assertNotIsInstance(caught.exception, AttributeError)
                self.assertIn("Accepted values:", str(caught.exception))

    def test_compute_3shell_rejects_non_member_model_type(self) -> None:
        """The 3-shell helper does not reach ``model_type.value`` for a non-member."""
        with self.assertRaises(ConductorGeometryError) as caught:
            compute_3shell_sphere_potential(
                self.electrode,
                self.interior[0],
                self.moment,
                ConductorModel(model_type="unsupported-string"),
            )
        self.assertIn("model_type", str(caught.exception))
        self.assertIn("spherical_3shell", str(caught.exception))
        self.assertNotIn("unsupported-string", str(caught.exception))

    def test_documented_enum_members_still_validate_and_build(self) -> None:
        """Every passing enum member still validates, and the rejected members stay rejected."""
        three = ConductorModel(model_type=ConductorModelType.SPHERICAL_3SHELL)
        one = ConductorModel(
            model_type=ConductorModelType.SPHERICAL_1SHELL,
            radii_m=(0.09,),
            sigmas_sm=(0.33,),
        )
        for conductor in (three, one):
            with self.subTest(model_type=conductor.model_type):
                self.assertIsNone(conductor.validate())
                built = build_synthetic_forward_contract(
                    conductor_model=conductor,
                    sensor_geometry=self.sensors,
                    source_space=SourceSpace(positions_m=self.interior),
                )
                self.assertIs(type(built.conductor_model.model_type), ConductorModelType)
                self.assertEqual(built.provenance["model_type"], conductor.model_type.value)
                self.assertEqual(built.status, ContractStatus.SYNTHETIC_ONLY)

        with self.assertRaises(ConductorGeometryError) as anatomical:
            ConductorModel(model_type=ConductorModelType.ANATOMICAL_BEM).validate()
        self.assertIn("Anatomical BEM", str(anatomical.exception))

        with self.assertRaises(ConductorGeometryError) as wrong_layers:
            ConductorModel(
                model_type=ConductorModelType.SPHERICAL_1SHELL,
                radii_m=(0.08, 0.085, 0.09),
                sigmas_sm=(0.33, 0.0042, 0.33),
            ).validate()
        self.assertIn("exactly 1 layer", str(wrong_layers.exception))

        for frame in (CoordinateFrame.HEAD, CoordinateFrame.MNI):
            with self.subTest(coordinate_frame=frame):
                sensors = dataclasses.replace(self.sensors, coordinate_frame=frame)
                sources = SourceSpace(positions_m=self.interior, coordinate_frame=frame)
                self.assertIsNone(sensors.validate())
                self.assertIsNone(sources.validate())
                built = build_synthetic_forward_contract(
                    sensor_geometry=sensors,
                    source_space=sources,
                    conductor_model=self.conductor,
                )
                self.assertIs(type(built.sensor_geometry.coordinate_frame), CoordinateFrame)
                self.assertEqual(built.sensor_geometry.coordinate_frame, frame)
                self.assertEqual(built.source_space.coordinate_frame, frame)
                self.assertEqual(built.provenance["coordinate_frame"], frame.value)

        for owner, call in (
            (
                "sensor",
                lambda: dataclasses.replace(
                    self.sensors, coordinate_frame=CoordinateFrame.UNKNOWN
                ).validate(),
            ),
            (
                "source",
                lambda: SourceSpace(
                    positions_m=self.interior, coordinate_frame=CoordinateFrame.UNKNOWN
                ).validate(),
            ),
        ):
            with self.subTest(owner=owner, coordinate_frame=CoordinateFrame.UNKNOWN):
                with self.assertRaises(CoordinateFrameMismatchError) as unknown:
                    call()
                self.assertIn("UNKNOWN is rejected", str(unknown.exception))

        for fixed, orientations, columns in (
            (False, None, 3),
            (True, self.unit, 1),
        ):
            with self.subTest(is_fixed_orientation=fixed):
                sources = SourceSpace(
                    positions_m=self.interior,
                    orientations=orientations,
                    is_fixed_orientation=fixed,
                )
                self.assertIsNone(sources.validate())
                built = build_synthetic_forward_contract(
                    sensor_geometry=self.sensors,
                    source_space=sources,
                )
                self.assertIs(type(built.source_space.is_fixed_orientation), bool)
                self.assertEqual(built.source_space.is_fixed_orientation, fixed)
                self.assertEqual(built.source_space.n_columns, columns)

        free_vectors = SourceSpace(
            positions_m=self.interior,
            orientations=((0.0, 0.0, 0.0),),
            is_fixed_orientation=False,
        )
        self.assertIsNone(free_vectors.validate())


class _HostileRepr:
    """Each conversion a validator might attempt raises, so any unsafe call fails loudly."""

    def __repr__(self) -> str:
        raise RuntimeError("SYNTHETIC-HOSTILE repr probe")

    def __str__(self) -> str:
        raise RuntimeError("SYNTHETIC-HOSTILE str probe")

    def __format__(self, spec: str) -> str:
        raise RuntimeError("SYNTHETIC-HOSTILE format probe")

    def __len__(self) -> int:
        raise RuntimeError("SYNTHETIC-HOSTILE len probe")

    def __iter__(self):
        raise RuntimeError("SYNTHETIC-HOSTILE iter probe")

    def __getitem__(self, key):
        raise RuntimeError("SYNTHETIC-HOSTILE index probe")

    def __bool__(self) -> bool:
        raise RuntimeError("SYNTHETIC-HOSTILE bool probe")

    def __float__(self) -> float:
        raise RuntimeError("SYNTHETIC-HOSTILE float probe")

    def __hash__(self) -> int:
        return id(self)


class _EchoRepr:
    """Attacker-controlled text that must never be echoed into a contract error."""

    MARKER = "SYNTHETIC-ECHO-MARKER"

    def __repr__(self) -> str:
        return self.MARKER

    def __str__(self) -> str:
        return self.MARKER

    def __format__(self, spec: str) -> str:
        return self.MARKER


class _EchoFloat(float):
    def __repr__(self) -> str:
        return "SYNTHETIC-ECHO-MARKER"


class _BadLenSequence(Sequence):
    def __len__(self) -> int:
        raise RuntimeError("SYNTHETIC-LEN-MARKER")

    def __getitem__(self, index):
        return (0.0, 0.0, 1.0)


class _BadIterSequence(Sequence):
    def __len__(self) -> int:
        return 1

    def __getitem__(self, index):
        raise RuntimeError("SYNTHETIC-INDEX-MARKER")

    def __iter__(self):
        raise RuntimeError("SYNTHETIC-INDEX-MARKER")


HOSTILE_MARKERS = (
    "SYNTHETIC-HOSTILE",
    "SYNTHETIC-ECHO-MARKER",
    "SYNTHETIC-LEN-MARKER",
    "SYNTHETIC-INDEX-MARKER",
)


class TestForwardModelHostileInputSanitization(unittest.TestCase):
    """Hostile caller values fail as field-specific contract errors.

    The contract error must not run the caller's ``__repr__``, ``__format__``, ``__len__``,
    iteration, indexing or truth conversion, and must not echo attacker text. A raw
    RuntimeError, TypeError or ValueError escaping a validator fails these tests, as does a
    message that lacks the field name.
    """

    def setUp(self) -> None:
        self.conductor = ConductorModel()
        self.sensors = make_standard_1020_synthetic_sensors(self.conductor.scalp_radius_m)
        self.interior = ((0.0, 0.0, 0.02),)
        self.unit = ((0.0, 0.0, 1.0),)
        self.identity = (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )

    def _assert_sanitized_contract_error(self, call, field: str) -> None:
        with self.assertRaises(ForwardModelContractError) as caught:
            call()
        message = str(caught.exception)
        self.assertIn(field, message)
        for marker in HOSTILE_MARKERS:
            self.assertNotIn(marker, message)

    def test_n_sources_hostile_values_fail_closed_without_repr(self) -> None:
        for value in (_HostileRepr(), _EchoRepr()):
            with self.subTest(value=type(value).__name__):
                self._assert_sanitized_contract_error(
                    lambda v=value: make_synthetic_source_grid(v), "n_sources"
                )

    def test_n_max_terms_hostile_values_fail_closed_without_repr(self) -> None:
        for value in (_HostileRepr(), _EchoRepr()):
            with self.subTest(value=type(value).__name__):
                self._assert_sanitized_contract_error(
                    lambda v=value: compute_homogeneous_sphere_potential(
                        self.interior[0],
                        (0.0, 0.0, 0.01),
                        (0.0, 0.0, 1e-9),
                        n_max_terms=v,
                    ),
                    "n_max_terms",
                )

    def test_negative_tolerance_is_not_echoed(self) -> None:
        self._assert_sanitized_contract_error(
            lambda: verify_channel_reference_invariant(
                [[0.0]], ("Fp1",), "Fp1", tolerance=_EchoFloat(-1.0)
            ),
            "tolerance",
        )

    def test_channel_name_arguments_fail_closed(self) -> None:
        leadfield = [[0.0, 1.0]]
        for names, field in (
            (_HostileRepr(), "channel_names"),
            (_EchoRepr(), "channel_names"),
            (("Fp1", 2), "channel_names"),
        ):
            with self.subTest(names=type(names).__name__):
                self._assert_sanitized_contract_error(
                    lambda n=names: apply_channel_reference(leadfield, n, "Fp1"), field
                )

    def test_leadfield_rows_that_fail_iteration_are_contract_errors(self) -> None:
        self._assert_sanitized_contract_error(
            lambda: compute_leadfield_diagnostics(
                [_HostileRepr()], is_fixed_orientation=False, n_sources=1
            ),
            "Leadfield",
        )

    def test_hostile_is_fixed_orientation_is_not_truth_tested_by_grid_builder(self) -> None:
        self._assert_sanitized_contract_error(
            lambda: make_synthetic_source_grid(4, is_fixed_orientation=_HostileRepr()),
            "is_fixed_orientation",
        )

    def test_container_methods_on_geometry_fields_are_guarded(self) -> None:
        self._assert_sanitized_contract_error(
            lambda: ConductorModel(radii_m=_BadLenSequence()).validate(), "radii_m"
        )
        self._assert_sanitized_contract_error(
            lambda: SourceSpace(positions_m=_BadLenSequence()).validate(), "positions_m"
        )
        for is_fixed in (True, False):
            with self.subTest(is_fixed=is_fixed):
                self._assert_sanitized_contract_error(
                    lambda f=is_fixed: SourceSpace(
                        positions_m=self.interior,
                        orientations=_BadLenSequence(),
                        is_fixed_orientation=f,
                    ).validate(),
                    "orientations",
                )
                self._assert_sanitized_contract_error(
                    lambda f=is_fixed: SourceSpace(
                        positions_m=self.interior,
                        orientations=_BadIterSequence(),
                        is_fixed_orientation=f,
                    ).validate(),
                    "orientations",
                )

    def test_non_sequence_geometry_shapes_are_contract_errors(self) -> None:
        cases = (
            (lambda: ConductorModel(radii_m=5).validate(), "radii_m"),
            (lambda: ConductorModel(radii_m=None).validate(), "radii_m"),
            (lambda: ConductorModel(sigmas_sm=None).validate(), "sigmas_sm"),
            (
                lambda: dataclasses.replace(self.sensors, channel_names=None, positions_m=()).validate(),
                "channel_names",
            ),
            (lambda: dataclasses.replace(self.sensors, positions_m=5).validate(), "positions_m"),
            (lambda: SourceSpace(positions_m=5).validate(), "positions_m"),
            (
                lambda: SourceSpace(positions_m=np.array([[0.0, 0.0, 0.02]] * 3)).validate(),
                "positions_m",
            ),
            (
                lambda: build_synthetic_forward_contract(
                    sensor_geometry=self.sensors, source_space=SourceSpace(positions_m=5)
                ),
                "positions_m",
            ),
        )
        for call, field in cases:
            with self.subTest(field=field):
                self._assert_sanitized_contract_error(call, field)

    def test_channel_name_entries_must_be_plain_strings(self) -> None:
        names = list(self.sensors.channel_names)
        bad_names = (
            tuple([[names[0]]] + names[1:]),
            tuple([_HostileRepr()] + names[1:]),
            tuple([1] + names[1:]),
        )
        for bad in bad_names:
            with self.subTest(entry=type(bad[0]).__name__):
                self._assert_sanitized_contract_error(
                    lambda b=bad: dataclasses.replace(self.sensors, channel_names=b).validate(),
                    "channel_names",
                )

    def test_reference_channel_must_be_text_and_is_never_formatted(self) -> None:
        for value in (_HostileRepr(), _EchoRepr()):
            with self.subTest(value=type(value).__name__):
                self._assert_sanitized_contract_error(
                    lambda v=value: dataclasses.replace(self.sensors, reference_channel=v).validate(),
                    "reference_channel",
                )
                self._assert_sanitized_contract_error(
                    lambda v=value: build_synthetic_forward_contract(
                        sensor_geometry=self.sensors, reference_channel=v, apply_avg_ref=True
                    ),
                    "reference_channel",
                )

    def test_free_mode_orientation_table_is_validated_like_fixed_mode(self) -> None:
        malformed = (
            ((1.0, 2.0),),
            ((math.nan, 0.0, 0.0),),
            ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
        )
        for orientations in malformed:
            with self.subTest(orientations=orientations):
                source = SourceSpace(
                    positions_m=self.interior,
                    orientations=orientations,
                    is_fixed_orientation=False,
                )
                with self.assertRaises(ForwardModelContractError):
                    source.validate()
                with self.assertRaises(ForwardModelContractError):
                    build_synthetic_forward_contract(
                        sensor_geometry=self.sensors, source_space=source
                    )

    def test_free_mode_non_unit_vectors_remain_accepted(self) -> None:
        source = SourceSpace(
            positions_m=self.interior,
            orientations=((0.0, 0.0, 2.0),),
            is_fixed_orientation=False,
        )
        self.assertIsNone(source.validate())
        built = build_synthetic_forward_contract(sensor_geometry=self.sensors, source_space=source)
        self.assertEqual(built.source_space.n_columns, 3)

    def test_documented_no_coercion_inputs_remain_accepted_or_rejected(self) -> None:
        conductor = ConductorModel(radii_m=[0.07, 0.08, 0.09], sigmas_sm=[0.33, 0.01, 0.43])
        self.assertIsNone(conductor.validate())
        self.assertIsInstance(
            compute_homogeneous_sphere_potential(
                self.sensors.positions_m[0],
                self.interior[0],
                (0.0, 0.0, 1e-9),
                sphere_radius_m=self.conductor.scalp_radius_m,
                n_max_terms=np.int64(8),
            ),
            float,
        )
        numpy_components = SourceSpace(
            positions_m=self.interior,
            orientations=((np.float64(0.0), np.float64(0.0), np.float64(1.0)),),
            is_fixed_orientation=True,
        )
        self.assertIsNone(numpy_components.validate())
        self.assertIsNone(
            SourceSpace(positions_m=[[0.0, 0.0, 0.02]], is_fixed_orientation=False).validate()
        )
        with self.assertRaises(ForwardModelContractError):
            SourceSpace(
                positions_m=self.interior,
                orientations=np.array([[0.0, 0.0, 1.0]]),
                is_fixed_orientation=True,
            ).validate()
        with self.assertRaises(ForwardModelContractError):
            SourceSpace(
                positions_m=self.interior,
                orientations=self.unit,
                is_fixed_orientation=np.bool_(True),
            ).validate()


if __name__ == "__main__":
    unittest.main()
