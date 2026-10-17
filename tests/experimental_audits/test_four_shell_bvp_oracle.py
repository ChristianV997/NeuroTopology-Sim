"""Offline, synthetic tests for the independent four-shell BVP oracle."""
from __future__ import annotations

import json
import math
import unittest

from tools.experimental_audits.four_shell_bvp_oracle import (
    DEFAULT_RADII_M,
    DEFAULT_SIGMAS_SM,
    OracleInputError,
    homogeneous_neumann_dipole_reference,
    homogeneous_surface_factors,
    project_dipole_oracle,
    run_default_audit,
    solve_four_shell_mode,
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
        source_radii = (0.0, 0.020, 0.050, 0.070)
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
                                                       equal_sigmas, max_degree=192)
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
            project_dipole_oracle((0.0, 0.0, 0.02), (1e-9, 0.0, 0.0), ((0.0, 0.0, 0.09),))
        with self.assertRaises(OracleInputError):
            project_dipole_oracle((0.0, 0.0, 0.02), (1e-9, 0.0, 0.0), good_sensors, max_degree=0)

    def test_audit_report_is_deterministic_finite_json_and_explicitly_non_candidate(self) -> None:
        first = run_default_audit()
        second = run_default_audit()
        self.assertEqual(first, second)
        encoded = json.dumps(first, sort_keys=True, allow_nan=False)
        self.assertIn("HOLD / SYNTHETIC_ONLY", encoded)
        self.assertIn('"candidate_implementation_tested": false', encoded)
        self.assertEqual(first["system"]["matrix_shape"], [7, 7])  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
