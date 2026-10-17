"""Offline, synthetic tests for the independent four-shell BVP oracle."""
from __future__ import annotations

import json
import math
import unittest

from tools.experimental_audits.four_shell_bvp_oracle import (
    DEFAULT_RADII_M,
    DEFAULT_SIGMAS_SM,
    NAESS_2017_RADII_M,
    NAESS_2017_SIGMAS_SM_BY_K,
    NAESS_2017_SOURCE_RADIUS_M,
    OracleInputError,
    PROMPT_PROPOSAL_RADII_M,
    PROMPT_PROPOSAL_SIGMAS_SM,
    compare_surface_potentials,
    homogeneous_neumann_dipole_reference,
    homogeneous_surface_factors,
    naess_2017_conductivities,
    project_dipole_oracle,
    run_default_audit,
    solve_four_shell_mode,
    solve_naess_basis_mode,
)


class FourShellBvpOracleTests(unittest.TestCase):
    def test_stated_unknowns_and_equations_form_7_by_7(self) -> None:
        solution = solve_four_shell_mode(3)
        self.assertEqual(solution.matrix_shape, (7, 7))
        self.assertEqual(solution.unknown_order, ("a1", "a2", "b2", "a3", "b3", "a4", "b4"))
        self.assertEqual(solution.b1_fixed, 1.0)

    def test_homogeneous_limit_across_degrees_and_independently_varied_radii(self) -> None:
        radius_sets = (
            (0.061, 0.066, 0.074, 0.089),
            (0.070, 0.078, 0.085, 0.100),
            DEFAULT_RADII_M,
        )
        degrees = (1, 2, 3, 7, 16, 32)
        sigmas = (0.33, 0.33, 0.33, 0.33)
        for radii in radius_sets:
            for degree in degrees:
                with self.subTest(radii=radii, degree=degree):
                    solution = solve_four_shell_mode(degree, radii, sigmas)
                    expected = (2.0 * degree + 1.0) / degree
                    self.assertLess(abs(solution.surface_transfer_ratio - expected), 2.0e-14)
                    self.assertLess(solution.residuals.max_linear_row_backward_error, 1.0e-12)
                    self.assertLess(solution.residuals.max_potential_continuity_scaled, 1.0e-12)
                    self.assertLess(solution.residuals.max_current_continuity_scaled, 1.0e-12)

    def test_layered_conductivity_boundary_residuals_are_small(self) -> None:
        for degree in (1, 2, 4, 8, 16):
            with self.subTest(degree=degree):
                solution = solve_four_shell_mode(degree, DEFAULT_RADII_M, DEFAULT_SIGMAS_SM)
                residuals = solution.residuals
                self.assertLess(residuals.max_potential_continuity_abs, 1.0e-12)
                self.assertLess(residuals.max_potential_continuity_scaled, 1.0e-12)
                self.assertLess(residuals.max_current_continuity_abs_sm2, 1.0e-12)
                self.assertLess(residuals.max_current_continuity_scaled, 1.0e-12)
                self.assertLess(residuals.outer_current_abs_sm2, 1.0e-12)
                self.assertLess(residuals.outer_current_scaled, 1.0e-12)
                self.assertLess(residuals.max_linear_row_backward_error, 1.0e-12)

    def test_closed_form_homogeneous_factors_against_independent_legendre_sum(self) -> None:
        for ratio in (0.1, 0.5, 0.8):
            for cosine in (-1.0, -0.7, 0.0, 0.7, 1.0):
                with self.subTest(ratio=ratio, cosine=cosine):
                    expected_a = 0.0
                    expected_b = 0.0
                    p_previous, d_previous = 1.0, 0.0
                    p_current, d_current = cosine, 1.0
                    terms = [(p_previous, d_previous), (p_current, d_current)]
                    for degree in range(1, 511):
                        p_next = ((2 * degree + 1) * cosine * p_current - degree * p_previous) / (degree + 1)
                        d_next = ((2 * degree + 1) * (p_current + cosine * d_current)
                                  - degree * d_previous) / (degree + 1)
                        terms.append((p_next, d_next))
                        p_previous, p_current = p_current, p_next
                        d_previous, d_current = d_current, d_next
                    for degree in range(1, len(terms)):
                        expected_a += (2 * degree + 1) * ratio ** (degree - 1) * terms[degree][0]
                        expected_b += ((2 * degree + 1) / degree
                                       * ratio ** (degree - 1) * terms[degree][1])
                    actual_a, actual_b = homogeneous_surface_factors(ratio, cosine)
                    self.assertLess(abs(actual_a - expected_a), 2.0e-11)
                    self.assertLess(abs(actual_b - expected_b), 2.0e-11)

    def test_complete_oracle_projector_matches_homogeneous_reference(self) -> None:
        radii = DEFAULT_RADII_M
        equal_sigmas = (0.33, 0.33, 0.33, 0.33)
        directions = ((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0),
                      (0.0, 1.0, 0.0), (0.0, -1.0, 0.0),
                      (0.0, 0.0, 1.0), (0.0, 0.0, -1.0))
        directions += tuple((sx, sy, sz) for sx in (-1.0, 1.0)
                            for sy in (-1.0, 1.0) for sz in (-1.0, 1.0))
        sensors = tuple(tuple(radii[3] * item / math.sqrt(sum(c * c for c in direction))
                              for item in direction) for direction in directions)
        source_direction = (0.3, -0.4, math.sqrt(0.75))
        tangent_direction = (-source_direction[1], source_direction[0], 0.0)
        tangent_norm = math.sqrt(sum(value * value for value in tangent_direction))
        tangent_direction = tuple(value / tangent_norm for value in tangent_direction)
        moment_size = 1.0e-9
        source_radii = (0.0, 0.020, 0.050, NAESS_2017_SOURCE_RADIUS_M)
        compared = 0
        for source_radius in source_radii:
            source = tuple(source_radius * value for value in source_direction)
            orientations = (("center", (moment_size, 0.0, 0.0)),) if source_radius == 0.0 else (
                ("radial", tuple(moment_size * value for value in source_direction)),
                ("tangential", tuple(moment_size * value for value in tangent_direction)),
            )
            for orientation, moment in orientations:
                with self.subTest(source_radius=source_radius, orientation=orientation):
                    projection = project_dipole_oracle(source, moment, sensors, radii,
                                                       equal_sigmas, max_degree=512)
                    reference = homogeneous_neumann_dipole_reference(
                        source, moment, sensors, radii[3], equal_sigmas[0])
                    scale = math.sqrt(sum(value * value for value in moment)) / (
                        4.0 * math.pi * equal_sigmas[0] * radii[3] ** 2)
                    scaled_error = max(abs(left - right)
                                       for left, right in zip(projection.surface_potentials_v, reference)) / scale
                    self.assertLess(scaled_error, 1.0e-11)
                    compared += len(sensors)
        self.assertEqual(compared, 98)

    def test_source_radius_harmonics_reproduce_free_space_dipole_green_function(self) -> None:
        source_direction = (0.3, -0.4, math.sqrt(0.75))
        tangent = (-source_direction[1], source_direction[0], 0.0)
        tangent_norm = math.sqrt(sum(value * value for value in tangent))
        tangent = tuple(value / tangent_norm for value in tangent)
        observer_radius = 0.18
        sigma = 0.33
        moment_size = 1.0e-9
        observers = tuple((observer_radius * direction[0], observer_radius * direction[1],
                           observer_radius * direction[2]) for direction in (
            (1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
            (0.0, -1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, -1.0),
        ))
        cases = ((0.0, (moment_size, 0.2 * moment_size, -0.3 * moment_size)),)
        for source_radius in (0.015, 0.040):
            source = tuple(source_radius * value for value in source_direction)
            cases += (
                (source_radius, tuple(moment_size * value for value in source_direction)),
                (source_radius, tuple(moment_size * value for value in tangent)),
            )

        for source_radius, moment in cases:
            source = (0.0, 0.0, 0.0) if source_radius == 0.0 else tuple(
                source_radius * value for value in source_direction
            )
            n_source = (0.0, 0.0, 1.0) if source_radius == 0.0 else source_direction
            for observer in observers:
                with self.subTest(source_radius=source_radius, observer=observer):
                    radius = math.sqrt(sum(value * value for value in observer))
                    e_observer = tuple(value / radius for value in observer)
                    cosine = sum(n_source[index] * e_observer[index] for index in range(3))
                    q_radial = sum(moment[index] * n_source[index] for index in range(3))
                    q_tangent_e = (sum(moment[index] * e_observer[index] for index in range(3))
                                   - cosine * q_radial)
                    p_prev, d_prev = 1.0, 0.0
                    p_curr, d_curr = cosine, 1.0
                    series = 0.0
                    for degree in range(1, 129):
                        if degree == 1:
                            p_value, d_value = p_curr, d_curr
                        else:
                            p_next = ((2 * degree - 1) * cosine * p_curr - (degree - 1) * p_prev) / degree
                            d_next = ((2 * degree - 1) * (p_curr + cosine * d_curr)
                                      - (degree - 1) * d_prev) / degree
                            p_prev, p_curr = p_curr, p_next
                            d_prev, d_curr = d_curr, d_next
                            p_value, d_value = p_curr, d_curr
                        series += source_radius ** (degree - 1) / radius ** (degree + 1) * (
                            degree * q_radial * p_value + d_value * q_tangent_e
                        )
                    series /= 4.0 * math.pi * sigma
                    displacement = tuple(observer[index] - source[index] for index in range(3))
                    distance = math.sqrt(sum(value * value for value in displacement))
                    direct = sum(moment[index] * displacement[index] for index in range(3)) / (
                        4.0 * math.pi * sigma * distance ** 3
                    )
                    scale = math.sqrt(sum(value * value for value in moment)) / (
                        4.0 * math.pi * sigma * radius ** 2
                    )
                    self.assertLess(abs(series - direct) / scale, 1.0e-12)

    def test_layered_dipole_projection_is_finite_and_bounded(self) -> None:
        radii = DEFAULT_RADII_M
        sensors = ((0.0, 0.0, radii[3]), (radii[3], 0.0, 0.0),
                   (0.0, -radii[3], 0.0), (0.0, 0.0, -radii[3]))
        projection = project_dipole_oracle((0.0, 0.0, 0.05), (0.0, 0.0, 1.0e-9),
                                           sensors, radii, DEFAULT_SIGMAS_SM, max_degree=128)
        self.assertEqual(projection.max_degree, 128)
        self.assertTrue(all(math.isfinite(value) for value in projection.surface_potentials_v))
        self.assertTrue(math.isfinite(projection.last_degree_max_abs_v))

    def test_tiny_finite_source_radius_uses_stable_central_dipole_limit(self) -> None:
        radius = DEFAULT_RADII_M[3]
        sigmas = (0.33, 0.33, 0.33, 0.33)
        sensors = ((0.0, 0.0, radius), (radius, 0.0, 0.0), (0.0, radius, 0.0))
        moment = (0.0, 0.0, 1e-7)
        center = project_dipole_oracle(
            (0.0, 0.0, 0.0), moment, sensors, DEFAULT_RADII_M, sigmas, max_degree=32
        )
        tiny = project_dipole_oracle(
            (1e-200, 0.0, 0.0), moment, sensors, DEFAULT_RADII_M, sigmas, max_degree=32
        )
        comparison = compare_surface_potentials(
            center.surface_potentials_v,
            tiny.surface_potentials_v,
            scale_v=1e-7 / (4.0 * math.pi * sigmas[0] * radius**2),
        )
        self.assertLess(comparison.max_scaled_error, 1e-12)

    def test_naess_table_and_prompt_parameters_are_distinct(self) -> None:
        self.assertEqual(NAESS_2017_RADII_M, (0.079, 0.080, 0.085, 0.090))
        self.assertEqual(naess_2017_conductivities(20), (0.33, 1.65, 0.0165, 0.33))
        self.assertEqual(naess_2017_conductivities(40), (0.33, 1.65, 0.00825, 0.33))
        self.assertEqual(naess_2017_conductivities(80), (0.33, 1.65, 0.004125, 0.33))
        self.assertNotEqual(PROMPT_PROPOSAL_RADII_M, NAESS_2017_RADII_M)
        self.assertNotEqual(PROMPT_PROPOSAL_SIGMAS_SM, NAESS_2017_SIGMAS_SM_BY_K[80])
        with self.assertRaises(OracleInputError):
            naess_2017_conductivities(30)
        with self.assertRaises(OracleInputError):
            naess_2017_conductivities(True)

    def test_paper_basis_is_7_by_7_and_matches_rescaled_transfer(self) -> None:
        for skull_factor in (20, 40, 80):
            sigmas = naess_2017_conductivities(skull_factor)
            for degree in (1, 2, 4, 8, 16):
                normalized = solve_four_shell_mode(degree, NAESS_2017_RADII_M, sigmas)
                for source_radius in (0.020, 0.050, NAESS_2017_SOURCE_RADIUS_M):
                    with self.subTest(K=skull_factor, degree=degree, rz=source_radius):
                        paper = solve_naess_basis_mode(
                            degree, source_radius, NAESS_2017_RADII_M, sigmas
                        )
                        self.assertEqual(paper.matrix_shape, (7, 7))
                        self.assertEqual(paper.unknown_order, ("A1", "A2", "B2", "A3", "B3", "A4", "B4"))
                        self.assertLess(abs(paper.surface_transfer_ratio - normalized.surface_transfer_ratio), 2e-12)
                        self.assertLess(paper.transfer_consistency_scaled, 2e-12)
                        self.assertLess(paper.residuals.max_potential_continuity_scaled, 1e-12)
                        self.assertLess(paper.residuals.max_current_continuity_scaled, 1e-12)
                        self.assertLess(paper.residuals.outer_current_scaled, 1e-12)
                        self.assertTrue(math.isfinite(paper.row_scaled_condition_inf))
                        self.assertGreaterEqual(paper.row_scaled_condition_inf, 1.0)

    def test_paper_source_depth_scaling_and_normalization(self) -> None:
        shallow, deep = 0.020, NAESS_2017_SOURCE_RADIUS_M
        sigmas = naess_2017_conductivities(80)
        for degree in (1, 2, 4, 8, 16):
            low = solve_naess_basis_mode(degree, shallow, NAESS_2017_RADII_M, sigmas)
            high = solve_naess_basis_mode(degree, deep, NAESS_2017_RADII_M, sigmas)
            observed = (high.layered_surface_value / deep**2) / (low.layered_surface_value / shallow**2)
            expected = (deep / shallow) ** (degree - 1)
            with self.subTest(degree=degree):
                self.assertLess(abs(observed - expected) / expected, 2e-12)

    def test_naess_homogeneous_radial_reference_matches_equation_19(self) -> None:
        radius = NAESS_2017_RADII_M[3]
        source_radius = NAESS_2017_SOURCE_RADIUS_M
        moment_size = 1.0e-7
        angles = (0.0, math.pi / 6, math.pi / 3, math.pi / 2, math.pi)
        sensors = tuple((radius * math.sin(theta), 0.0, radius * math.cos(theta)) for theta in angles)
        source = (0.0, 0.0, source_radius)
        moment = (0.0, 0.0, moment_size)
        sigma = 0.33
        actual = homogeneous_neumann_dipole_reference(source, moment, sensors, radius, sigma)
        t = source_radius / radius
        expected = []
        for theta in angles:
            cosine = math.cos(theta)
            discriminant = 1.0 + t * t - 2.0 * t * cosine
            bracket = 2.0 * (cosine - t) / discriminant**1.5
            bracket += (1.0 / math.sqrt(discriminant) - 1.0) / t
            expected.append(moment_size * bracket / (4.0 * math.pi * sigma * radius**2))
        comparison = compare_surface_potentials(expected, actual,
                                                scale_v=moment_size / (4.0 * math.pi * sigma * radius**2))
        self.assertLess(comparison.max_scaled_error, 2e-12)

    def test_tangential_associated_legendre_sign_and_symmetry_axis(self) -> None:
        radius = NAESS_2017_RADII_M[3]
        source_radius = NAESS_2017_SOURCE_RADIUS_M
        sigmas = naess_2017_conductivities(80)
        moment_size = 1.0e-7
        sensors = []
        angles = ((0.0, 0.0), (math.pi / 6, 0.3), (math.pi / 2, math.pi / 3),
                  (math.pi, 1.2), (math.pi / 3, -math.pi / 2))
        for theta, phi in angles:
            sensors.append((radius * math.sin(theta) * math.cos(phi),
                            radius * math.sin(theta) * math.sin(phi),
                            radius * math.cos(theta)))
        source = (0.0, 0.0, source_radius)
        moment = (0.0, moment_size, 0.0)
        projection = project_dipole_oracle(source, moment, sensors, NAESS_2017_RADII_M,
                                          sigmas, max_degree=512)
        expected = []
        for theta, phi in angles:
            mu = math.cos(theta)
            pairs = [(1.0, 0.0), (mu, 1.0)]
            p0, d0 = 1.0, 0.0
            p1, d1 = mu, 1.0
            for degree in range(1, 512):
                p2 = ((2 * degree + 1) * mu * p1 - degree * p0) / (degree + 1)
                d2 = ((2 * degree + 1) * (p1 + mu * d1) - degree * d0) / (degree + 1)
                pairs.append((p2, d2))
                p0, p1, d0, d1 = p1, p2, d1, d2
            tangential_sum = 0.0
            for degree in range(1, 513):
                mode = solve_naess_basis_mode(degree, source_radius, NAESS_2017_RADII_M, sigmas)
                associated_p1 = -math.sin(theta) * pairs[degree][1]
                tangential_sum += mode.layered_surface_value * (-math.sin(phi) * associated_p1)
            expected.append(moment_size * tangential_sum /
                            (4.0 * math.pi * sigmas[0] * source_radius**2))
        scale = moment_size / (4.0 * math.pi * sigmas[0] * radius**2)
        comparison = compare_surface_potentials(expected, projection.surface_potentials_v, scale_v=scale)
        self.assertLess(comparison.max_scaled_error, 2e-12)
        self.assertLess(abs(projection.surface_potentials_v[0]), 1e-18)
        self.assertLess(abs(projection.surface_potentials_v[3]), 1e-18)

    def test_projector_harmonic_convergence_and_public_comparator(self) -> None:
        radius = NAESS_2017_RADII_M[3]
        source = (0.0, 0.0, NAESS_2017_SOURCE_RADIUS_M)
        moment = (0.0, 0.0, 1.0e-7)
        sensor = ((0.0, 0.0, radius),)
        equal_sigmas = (0.33, 0.33, 0.33, 0.33)
        reference = homogeneous_neumann_dipole_reference(source, moment, sensor, radius, equal_sigmas[0])
        scale = 1.0e-7 / (4.0 * math.pi * equal_sigmas[0] * radius**2)
        errors = []
        for limit in (8, 16, 32, 64, 128, 256, 512):
            projection = project_dipole_oracle(source, moment, sensor, NAESS_2017_RADII_M,
                                               equal_sigmas, max_degree=limit)
            comparison = compare_surface_potentials(reference, projection.surface_potentials_v,
                                                    scale_v=scale)
            errors.append(comparison.max_scaled_error)
        self.assertTrue(all(left > right for left, right in zip(errors[:5], errors[1:6])))
        self.assertLess(errors[-2], 5e-12)
        self.assertLess(errors[-1], 5e-12)
        self.assertLessEqual(errors[-1], 4.0 * errors[-2])
        identical = compare_surface_potentials((1.0, 2.0), (1.0, 2.0), scale_v=2.0)
        self.assertEqual(identical.sample_count, 2)
        self.assertEqual(identical.max_scaled_error, 0.0)
        with self.assertRaises(OracleInputError):
            compare_surface_potentials((1.0,), (1.0, 2.0), scale_v=1.0)
        with self.assertRaises(OracleInputError):
            compare_surface_potentials((1.0,), (float("nan"),), scale_v=1.0)
        with self.assertRaises(OracleInputError):
            compare_surface_potentials((1.0,), (0.0,), scale_v=1e-320)
        large_finite = compare_surface_potentials((1e308, 0.0), (0.0, 0.0), scale_v=1e308)
        self.assertTrue(math.isfinite(large_finite.rms_absolute_error_v))
        self.assertEqual(large_finite.max_scaled_error, 1.0)

    def test_input_contract_rejects_invalid_degree_geometry_and_conductivity(self) -> None:
        for invalid_degree in (0, -1, 1.5, True):
            with self.subTest(degree=invalid_degree), self.assertRaises(OracleInputError):
                solve_four_shell_mode(invalid_degree)  # type: ignore[arg-type]
        for invalid_radii in (
            (0.078, 0.080, 0.086),
            (0.078, 0.080, 0.080, 0.095),
            (0.078, 0.086, 0.080, 0.095),
            (0.078, 0.080, float("nan"), 0.095),
            (78.0, 80.0, 86.0, 95.0),
            (1e-200, 2e-200, 3e-200, 4e-200),
        ):
            with self.subTest(radii=invalid_radii), self.assertRaises(OracleInputError):
                solve_four_shell_mode(2, invalid_radii, DEFAULT_SIGMAS_SM)
        for invalid_sigmas in (
            (0.33, 1.79, 0.0042),
            (0.33, 0.0, 0.0042, 0.33),
            (0.33, float("inf"), 0.0042, 0.33),
        ):
            with self.subTest(sigmas=invalid_sigmas), self.assertRaises(OracleInputError):
                solve_four_shell_mode(2, DEFAULT_RADII_M, invalid_sigmas)

    def test_input_contract_rejects_source_sensor_and_nonfinite_values(self) -> None:
        radii = DEFAULT_RADII_M
        good_sensors = ((0.0, 0.0, radii[3]), (radii[3], 0.0, 0.0),
                        (0.0, radii[3], 0.0), (0.0, 0.0, -radii[3]))
        with self.assertRaises(OracleInputError):
            project_dipole_oracle((0.0, 0.0, radii[0]), (1e-9, 0.0, 0.0), good_sensors)
        with self.assertRaises(OracleInputError):
            project_dipole_oracle((0.0, 0.0, float("nan")), (1e-9, 0.0, 0.0), good_sensors)
        with self.assertRaises(OracleInputError):
            project_dipole_oracle((0.0, 0.0, 0.02), (float("inf"), 0.0, 0.0), good_sensors)
        with self.assertRaises(OracleInputError):
            project_dipole_oracle((0.0, 0.0, 0.02), (1e-9, 0.0, 0.0), ((0.0, 0.0, 95.0),))
        with self.assertRaises(OracleInputError):
            project_dipole_oracle((0.0, 0.0, 0.02), (1e-9, 0.0, 0.0), ((0.0, 0.0, 0.095),))
        with self.assertRaises(OracleInputError):
            project_dipole_oracle((0.0, 0.0, 0.02), (1e-9, 0.0, 0.0), good_sensors, max_degree=0)

    def test_audit_report_is_deterministic_finite_json_and_explicitly_non_candidate(self) -> None:
        first = run_default_audit()
        second = run_default_audit()
        self.assertEqual(first, second)
        encoded = json.dumps(first, sort_keys=True, allow_nan=False)
        self.assertIn("HOLD / SYNTHETIC_ONLY", encoded)
        self.assertIn('"candidate_implementation_tested": false', encoded)
        self.assertEqual(first["paper_system"]["matrix_shape"], [7, 7])  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
