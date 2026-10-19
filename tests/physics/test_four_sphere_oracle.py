"""Independent boundary-value oracle for the four-sphere EEG candidate.

Status: HOLD / SYNTHETIC_ONLY. This file imports the candidate implementation
under test; its expected coefficients and potentials are computed independently.

Equation source: Næss, S. et al. (2017), “Corrected Four-Sphere Head Model for
EEG Signals,” Frontiers in Human Neuroscience 11:490, doi:10.3389/fnhum.2017.00490.
The article is available under CC BY 4.0; see the publisher's copyright terms at
https://www.frontiersin.org/legal/copyright-statement. The shell basis and
boundary equations below are independently assembled from the paper's stated
Poisson/Laplace solutions and continuity conditions. No paper code or figures
are copied.

Homogeneous comparison: Brody, D. A., Terry, F. H., and Ideker, R. E. (1973),
“Eccentric Dipole in a Spherical Medium: Generalized Expression for Surface
Potentials,” IEEE Transactions on Biomedical Engineering 20(2), 141–143,
doi:10.1109/TBME.1973.324177. The closed form below is independently derived
from the Legendre generating function; its radial term is Næss et al. Eq. 19.

Convention: source axis is +z; outward radial dipole moment is positive;
P_l uses the ordinary Legendre recurrence and P_l^1(mu) =
-sqrt(1-mu**2) * dP_l/dmu (Condon–Shortley). A +y tangential dipole therefore
projects as -sin(phi) P_l^1. Radii are metres, conductivity S/m, dipole moment
A·m, and output volts. This file does not use GPL-3.0 Neuroinflab/fourspheremodel
or LFPy code or fixtures.
"""
from __future__ import annotations

import math
import unittest
from functools import lru_cache

import numpy as np

from physics.eeg_forward import (
    FourSphereGeometry,
    FourSphereInputError,
    FourSphereQualityError,
    forward_potentials,
    transfer_ratios,
)


# Næss et al. Table 1: radii 7.9/8.0/8.5/9.0 cm; CSF is 5*sigma_brain,
# skull is sigma_brain/K, and scalp equals brain. Figures 1–2 place the source
# at z=7.8 cm, 1 mm inside the 7.9 cm brain boundary.
NAESS_RADII_M = (0.079, 0.080, 0.085, 0.090)
NAESS_SKULL_FACTORS = (20, 40, 80)
NAESS_CONDUCTIVITIES_S_M = {
    factor: (0.33, 1.65, 0.33 / factor, 0.33)
    for factor in NAESS_SKULL_FACTORS
}
HOMOGENEOUS_CONDUCTIVITIES_S_M = (0.33, 0.33, 0.33, 0.33)
PAPER_SOURCE_DEPTH_M = 0.078
DIPOLE_MOMENT_A_M = 1.0e-7

_A_INDEX = (0, 1, 3, 5)
_B_INDEX = (None, 2, 4, 6)


def _independent_mode(
    degree: int,
    source_depth_m: float,
    radii_m: tuple[float, float, float, float],
    conductivities_s_m: tuple[float, float, float, float],
) -> tuple[float, float]:
    """Solve the paper-basis 7x7 system; return (T_l, scaled residual).

    With the singular brain-shell coefficient fixed to one, the unknowns are
    (A1, A2, B2, A3, B3, A4, B4). For shell s, the regular basis is
    (r/r_s)^l and the singular basis is (r_s/r)^(l+1); in the brain the fixed
    singular term is (r_source/r)^(l+1). The six interface rows impose
    continuity of potential and sigma*dU/dr; the seventh imposes zero scalp
    current. Coordinates are divided by r4, so the common 1/r4 derivative
    factor cancels from current-continuity equations.
    """
    if degree < 1:
        raise ValueError("degree must be >= 1")
    if not 0.0 < source_depth_m < radii_m[0]:
        raise ValueError("source must be strictly inside the brain shell")

    r4 = radii_m[3]
    rho = tuple(radius / r4 for radius in radii_m)
    source = source_depth_m / r4
    matrix = np.zeros((7, 7), dtype=float)
    rhs = np.zeros(7, dtype=float)
    row_number = 0

    def add_shell_side(
        row: np.ndarray,
        shell: int,
        x: float,
        sign: float,
        current: bool,
    ) -> float:
        if shell == 0:
            regular = (x / rho[0]) ** degree
            singular = (source / x) ** (degree + 1)
        else:
            regular = (x / rho[shell]) ** degree
            singular = (rho[shell] / x) ** (degree + 1)

        d_regular = degree * regular / x
        d_singular = -(degree + 1) * singular / x
        if current:
            regular_coefficient = conductivities_s_m[shell] * d_regular
            singular_coefficient = conductivities_s_m[shell] * d_singular
        else:
            regular_coefficient = regular
            singular_coefficient = singular

        row[_A_INDEX[shell]] += sign * regular_coefficient
        if shell == 0:
            # Move the known singular brain term from the left side to rhs.
            return -sign * singular_coefficient
        row[_B_INDEX[shell]] += sign * singular_coefficient
        return 0.0

    for interface in range(3):
        x = rho[interface]
        for current in (False, True):
            row = matrix[row_number]
            rhs[row_number] += add_shell_side(row, interface, x, +1.0, current)
            rhs[row_number] += add_shell_side(row, interface + 1, x, -1.0, current)
            row_number += 1

    # sigma4*dU4/dx = 0 at x=1; the common 1/r4 factor is immaterial.
    matrix[row_number, _A_INDEX[3]] = conductivities_s_m[3] * degree
    matrix[row_number, _B_INDEX[3]] = -conductivities_s_m[3] * (degree + 1)

    # Equilibrate each boundary row before solving; scale rhs by the same value.
    for row_id in range(7):
        row_scale = float(np.max(np.abs(matrix[row_id])))
        if row_scale == 0.0 or not math.isfinite(row_scale):
            raise ArithmeticError("singular or non-finite boundary row")
        matrix[row_id] /= row_scale
        rhs[row_id] /= row_scale

    coefficients = np.linalg.solve(matrix, rhs)
    residual_denominator = (
        float(np.max(np.sum(np.abs(matrix), axis=1)))
        * float(np.max(np.abs(coefficients)))
        + float(np.max(np.abs(rhs)))
        + np.finfo(float).tiny
    )
    scaled_residual = float(np.max(np.abs(matrix @ coefficients - rhs))) / residual_denominator
    surface_value = float(coefficients[_A_INDEX[3]] + coefficients[_B_INDEX[3]])
    source_surface_value = source ** (degree + 1)
    transfer = surface_value / source_surface_value
    if not math.isfinite(transfer) or not math.isfinite(scaled_residual):
        raise ArithmeticError("non-finite independent boundary solution")
    return transfer, scaled_residual


@lru_cache(maxsize=8192)
def _independent_transfer(
    degree: int,
    source_depth_m: float,
    radii_m: tuple[float, float, float, float],
    conductivities_s_m: tuple[float, float, float, float],
) -> tuple[float, float]:
    return _independent_mode(degree, source_depth_m, radii_m, conductivities_s_m)


def _independent_transfer_array(
    source_depth_m: float,
    radii_m: tuple[float, float, float, float],
    conductivities_s_m: tuple[float, float, float, float],
    max_degree: int,
) -> np.ndarray:
    return np.asarray(
        [
            _independent_transfer(degree, source_depth_m, radii_m, conductivities_s_m)[0]
            for degree in range(1, max_degree + 1)
        ],
        dtype=float,
    )


def _legendre_and_derivative(mu: np.ndarray, max_degree: int) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate P_l and dP_l/dmu by differentiating the three-term recurrence."""
    values = np.empty((max_degree + 1, mu.size), dtype=float)
    derivatives = np.empty_like(values)
    values[0] = 1.0
    derivatives[0] = 0.0
    if max_degree == 0:
        return values, derivatives
    values[1] = mu
    derivatives[1] = 1.0
    for degree in range(1, max_degree):
        next_degree = degree + 1
        factor = 2 * degree + 1
        values[next_degree] = (
            factor * mu * values[degree] - degree * values[degree - 1]
        ) / next_degree
        derivatives[next_degree] = (
            factor * (values[degree] + mu * derivatives[degree])
            - degree * derivatives[degree - 1]
        ) / next_degree
    return values, derivatives


def _legendre_scalar_and_derivative(degree: int, mu: float) -> tuple[float, float]:
    """Evaluate one Legendre value/derivative from the three-term recurrence."""
    if degree < 0:
        raise ValueError("degree must be non-negative")
    if degree == 0:
        return 1.0, 0.0
    p_previous, p_current = 1.0, mu
    d_previous, d_current = 0.0, 1.0
    for current_degree in range(1, degree):
        next_degree = current_degree + 1
        factor = 2 * current_degree + 1
        p_next = (
            factor * mu * p_current - current_degree * p_previous
        ) / next_degree
        d_next = (
            factor * (p_current + mu * d_current)
            - current_degree * d_previous
        ) / next_degree
        p_previous, p_current = p_current, p_next
        d_previous, d_current = d_current, d_next
    return p_current, d_current


def _positive_legendre_root(degree: int, root_index: int = 0) -> float:
    """Find a positive P_degree root by recurrence, sign-bracketing, and bisection."""
    if degree < 1 or root_index < 0:
        raise ValueError("degree must be positive and root_index non-negative")
    brackets: list[tuple[float, float, float]] = []
    subdivisions = 4096
    left = 0.0
    f_left = _legendre_scalar_and_derivative(degree, left)[0]
    for step in range(1, subdivisions + 1):
        right = step / subdivisions
        f_right = _legendre_scalar_and_derivative(degree, right)[0]
        if f_left * f_right < 0.0:
            brackets.append((left, right, f_left))
        left, f_left = right, f_right
    if root_index >= len(brackets):
        raise ArithmeticError(f"could not bracket positive P_{degree} root {root_index}")

    left, right, f_left = brackets[root_index]
    for _ in range(80):
        midpoint = (left + right) / 2.0
        if midpoint == left or midpoint == right:
            break
        f_midpoint = _legendre_scalar_and_derivative(degree, midpoint)[0]
        if f_left * f_midpoint <= 0.0:
            right = midpoint
        else:
            left, f_left = midpoint, f_midpoint
    root = (left + right) / 2.0
    residual = abs(_legendre_scalar_and_derivative(degree, root)[0])
    if residual > 2.0e-14:
        raise ArithmeticError(f"P_{degree} root refinement residual {residual:.3e}")
    return root


def _independent_surface_sum(
    source_m: np.ndarray,
    moment_a_m: np.ndarray,
    sensors_m: np.ndarray,
    radii_m: tuple[float, float, float, float],
    conductivities_s_m: tuple[float, float, float, float],
    max_degree: int,
) -> np.ndarray:
    """Project an independent BVP solution onto scalp directions through L.

    Næss et al. write the source normalization as p/(4*pi*sigma1*d**2).
    At the scalp, the normalized shell coefficient contributes
    T_l*(d/r4)**(l+1). Combining that with the source prefactor gives the
    common projected prefactor T_l*(d/r4)**(l-1)/(4*pi*sigma1*r4**2);
    the radial bracket supplies l*q_r*P_l and the tangential bracket supplies
    (q_t dot e)*P_l'. This form keeps source-depth normalization explicit.
    """
    source_depth = float(np.linalg.norm(source_m))
    source_axis = (
        source_m / source_depth if source_depth > 0.0 else np.asarray((0.0, 0.0, 1.0))
    )
    directions = sensors_m / radii_m[3]
    mu = np.clip(directions @ source_axis, -1.0, 1.0)
    radial_moment = float(moment_a_m @ source_axis)
    tangent_projection = directions @ moment_a_m - radial_moment * mu
    legendre, derivative = _legendre_and_derivative(mu, max_degree)

    # T_l is independent of source depth; use an interior reference depth only
    # for the fixed singular normalization when the source is at the centre.
    basis_depth = source_depth if source_depth > 0.0 else radii_m[0] / 2.0
    transfer = _independent_transfer_array(
        basis_depth, radii_m, conductivities_s_m, max_degree
    )
    depth_ratio = source_depth / radii_m[3]
    prefactor = 1.0 / (
        4.0 * math.pi * conductivities_s_m[0] * radii_m[3] ** 2
    )
    potentials = np.zeros(sensors_m.shape[0], dtype=float)
    for degree in range(1, max_degree + 1):
        radial_power = 1.0 if degree == 1 else depth_ratio ** (degree - 1)
        potentials += (
            prefactor
            * transfer[degree - 1]
            * radial_power
            * (
                degree * radial_moment * legendre[degree]
                + tangent_projection * derivative[degree]
            )
        )
    return potentials


def _brody_homogeneous_closed_form(
    source_depth_m: float,
    moment_a_m: np.ndarray,
    sensors_m: np.ndarray,
    radius_m: float,
    conductivity_s_m: float,
) -> np.ndarray:
    """Homogeneous Neumann-sphere surface field from Legendre generating sums."""
    source = np.asarray((0.0, 0.0, source_depth_m), dtype=float)
    if source_depth_m == 0.0:
        directions = sensors_m / radius_m
        return (
            3.0 * (directions @ moment_a_m)
            / (4.0 * math.pi * conductivity_s_m * radius_m**2)
        )

    axis = source / source_depth_m
    directions = sensors_m / radius_m
    mu = np.clip(directions @ axis, -1.0, 1.0)
    radial_moment = float(moment_a_m @ axis)
    tangent_projection = directions @ moment_a_m - radial_moment * mu
    t = source_depth_m / radius_m
    d = 1.0 - 2.0 * t * mu + t * t
    inverse_root = 1.0 / np.sqrt(d)
    radial_factor = (
        2.0 * (mu - t) / (d ** 1.5)
        + (inverse_root - 1.0) / t
    )
    tangent_factor = np.zeros_like(mu)
    off_pole = np.abs(mu) < 1.0 - 1.0e-14
    tangent_factor[off_pole] = (
        2.0 / (d[off_pole] ** 1.5)
        + (
            (t - mu[off_pole]) / np.sqrt(d[off_pole]) + mu[off_pole]
        )
        / (t * (1.0 - mu[off_pole] ** 2))
    )
    return (
        radial_moment * radial_factor + tangent_projection * tangent_factor
    ) / (4.0 * math.pi * conductivity_s_m * radius_m**2)


def _sensor_grid(radius_m: float) -> np.ndarray:
    """Deterministic polar-angle/azimuth grid, including both symmetry poles."""
    points: list[tuple[float, float, float]] = []
    for theta in (0.0, math.pi / 6.0, math.pi / 3.0, math.pi / 2.0,
                  2.0 * math.pi / 3.0, 5.0 * math.pi / 6.0, math.pi):
        azimuths = (0.0,) if theta in (0.0, math.pi) else (0.0, math.pi / 4.0, math.pi / 2.0)
        for phi in azimuths:
            points.append((
                radius_m * math.sin(theta) * math.cos(phi),
                radius_m * math.sin(theta) * math.sin(phi),
                radius_m * math.cos(theta),
            ))
    return np.asarray(points, dtype=float)


def _moments() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    p = DIPOLE_MOMENT_A_M
    return (
        np.asarray((0.0, 0.0, p)),
        np.asarray((0.0, p, 0.0)),
        np.asarray((0.0, p / math.sqrt(2.0), p / math.sqrt(2.0))),
    )


def _scaled_max_error(
    actual: np.ndarray,
    expected: np.ndarray,
    moment_a_m: np.ndarray,
    conductivity_s_m: float,
    radius_m: float,
) -> float:
    physical_scale = (
        float(np.linalg.norm(moment_a_m))
        / (4.0 * math.pi * conductivity_s_m * radius_m**2)
    )
    return float(np.max(np.abs(actual - expected))) / physical_scale


class FourSphereIndependentOracleTests(unittest.TestCase):
    """Synthetic-only tests of PR #418 against independent equations."""

    def test_naess_table_one_transfer_ratios_degrees_1_through_100(self) -> None:
        for skull_factor in NAESS_SKULL_FACTORS:
            conductivities = NAESS_CONDUCTIVITIES_S_M[skull_factor]
            geometry = FourSphereGeometry(NAESS_RADII_M, conductivities)
            candidate = transfer_ratios(geometry, max_degree=100)
            expected = _independent_transfer_array(
                PAPER_SOURCE_DEPTH_M, NAESS_RADII_M, conductivities, 100
            )
            for degree in range(1, 101):
                with self.subTest(skull_factor=skull_factor, degree=degree):
                    independent_residual = _independent_transfer(
                        degree, PAPER_SOURCE_DEPTH_M, NAESS_RADII_M, conductivities
                    )[1]
                    self.assertLess(independent_residual, 5.0e-14)
                    self.assertLessEqual(
                        abs(float(candidate[degree - 1] - expected[degree - 1]))
                        / abs(float(expected[degree - 1])),
                        2.0e-10,
                    )

            # The transfer ratio must not depend on the source's radial depth.
            for source_depth in (0.020, 0.050):
                for degree in (1, 2, 7, 32, 64, 100):
                    with self.subTest(
                        skull_factor=skull_factor,
                        source_depth=source_depth,
                        degree=degree,
                    ):
                        depth_transfer, residual = _independent_transfer(
                            degree, source_depth, NAESS_RADII_M, conductivities
                        )
                        self.assertLess(residual, 5.0e-14)
                        self.assertLessEqual(
                            abs(depth_transfer - float(candidate[degree - 1]))
                            / abs(float(candidate[degree - 1])),
                            2.0e-10,
                        )

    def test_layered_projector_matches_independent_modes_for_depths_and_orientations(self) -> None:
        skull_factor = 80
        conductivities = NAESS_CONDUCTIVITIES_S_M[skull_factor]
        geometry = FourSphereGeometry(NAESS_RADII_M, conductivities)
        sensors = _sensor_grid(NAESS_RADII_M[3])
        for depth in (0.020, 0.050, PAPER_SOURCE_DEPTH_M):
            source = np.asarray((0.0, 0.0, depth))
            for moment in _moments():
                with self.subTest(depth_m=depth, moment=tuple(moment)):
                    # tail_tol=1 asks for the configured finite-L sum; it does
                    # not certify convergence. The independent reference uses
                    # precisely the same L=100, with its own shell solve.
                    result = forward_potentials(
                        geometry,
                        source,
                        moment,
                        sensors,
                        max_degree=100,
                        tail_tol=1.0,
                    )
                    expected = _independent_surface_sum(
                        source,
                        moment,
                        sensors,
                        NAESS_RADII_M,
                        conductivities,
                        100,
                    )
                    self.assertLess(
                        _scaled_max_error(
                            result.potentials_v,
                            expected,
                            moment,
                            conductivities[0],
                            NAESS_RADII_M[3],
                        ),
                        2.0e-10,
                    )

    def test_homogeneous_transfer_and_full_projector_match_brody_closed_form(self) -> None:
        geometry = FourSphereGeometry(
            NAESS_RADII_M, HOMOGENEOUS_CONDUCTIVITIES_S_M
        )
        transfer = transfer_ratios(geometry, max_degree=100)
        analytic_transfer = np.asarray(
            [(2.0 * degree + 1.0) / degree for degree in range(1, 101)]
        )
        np.testing.assert_allclose(transfer, analytic_transfer, rtol=2.0e-12, atol=0.0)

        sensors = _sensor_grid(NAESS_RADII_M[3])
        for depth in (0.020, 0.050, PAPER_SOURCE_DEPTH_M):
            source = np.asarray((0.0, 0.0, depth))
            for moment in _moments():
                with self.subTest(depth_m=depth, moment=tuple(moment)):
                    result = forward_potentials(
                        geometry,
                        source,
                        moment,
                        sensors,
                        max_degree=256,
                    )
                    expected = _brody_homogeneous_closed_form(
                        depth,
                        moment,
                        sensors,
                        NAESS_RADII_M[3],
                        HOMOGENEOUS_CONDUCTIVITIES_S_M[0],
                    )
                    self.assertLess(
                        _scaled_max_error(
                            result.potentials_v,
                            expected,
                            moment,
                            HOMOGENEOUS_CONDUCTIVITIES_S_M[0],
                            NAESS_RADII_M[3],
                        ),
                        2.0e-9,
                    )

    def test_tangential_dipole_is_zero_at_both_symmetry_poles(self) -> None:
        conductivities = NAESS_CONDUCTIVITIES_S_M[40]
        geometry = FourSphereGeometry(NAESS_RADII_M, conductivities)
        source = np.asarray((0.0, 0.0, 0.050))
        tangent = np.asarray((0.0, DIPOLE_MOMENT_A_M, 0.0))
        sensors = np.asarray(((0.0, 0.0, NAESS_RADII_M[3]),
                              (0.0, 0.0, -NAESS_RADII_M[3]),
                              (0.0, NAESS_RADII_M[3], 0.0)))
        result = forward_potentials(
            geometry, source, tangent, sensors, max_degree=100, tail_tol=1.0
        )
        scale = (
            DIPOLE_MOMENT_A_M
            / (4.0 * math.pi * conductivities[0] * NAESS_RADII_M[3] ** 2)
        )
        self.assertLessEqual(
            float(np.max(np.abs(result.potentials_v[:2]))) / scale, 1.0e-13
        )
        self.assertGreater(abs(float(result.potentials_v[2])) / scale, 1.0e-6)

    def test_radius_source_depth_units_sign_and_geometric_scaling(self) -> None:
        conductivities = NAESS_CONDUCTIVITIES_S_M[40]
        geometry = FourSphereGeometry(NAESS_RADII_M, conductivities)
        source = np.asarray((0.0, 0.0, 0.050))
        radial = np.asarray((0.0, 0.0, DIPOLE_MOMENT_A_M))
        poles = np.asarray(((0.0, 0.0, NAESS_RADII_M[3]),
                            (0.0, 0.0, -NAESS_RADII_M[3])))
        result = forward_potentials(
            geometry, source, radial, poles, max_degree=128
        )
        self.assertGreater(float(result.potentials_v[0]), 0.0)
        self.assertLess(float(result.potentials_v[1]), 0.0)

        # Coordinates are SI metres, not centimetres; source must be strictly
        # within the brain shell, and each sensor must lie on the scalp.
        with self.assertRaises(FourSphereInputError):
            FourSphereGeometry((7.9, 8.0, 8.5, 9.0), conductivities)
        with self.assertRaises(FourSphereInputError):
            forward_potentials(
                geometry,
                np.asarray((0.0, 0.0, NAESS_RADII_M[0])),
                radial,
                poles[:1],
            )
        with self.assertRaises(FourSphereInputError):
            forward_potentials(
                geometry,
                source,
                radial,
                np.asarray(((0.0, 0.0, 0.99 * NAESS_RADII_M[3]),)),
            )

        # Uniformly scaling every length by 1/2 preserves the dimensionless
        # solution and increases volts by 1/(1/2)^2; moments remain A·m.
        scale_length = 0.5
        scaled_radii = tuple(scale_length * radius for radius in NAESS_RADII_M)
        scaled_geometry = FourSphereGeometry(scaled_radii, conductivities)
        sensors = _sensor_grid(NAESS_RADII_M[3])
        base = forward_potentials(
            geometry, source, radial, sensors, max_degree=128
        ).potentials_v
        scaled = forward_potentials(
            scaled_geometry,
            scale_length * source,
            radial,
            scale_length * sensors,
            max_degree=128,
        ).potentials_v
        np.testing.assert_allclose(scaled, base / (scale_length**2), rtol=2.0e-10, atol=1.0e-15)

    def test_high_degree_homogeneous_series_converges_at_a_legendre_node(self) -> None:
        geometry = FourSphereGeometry(
            NAESS_RADII_M, HOMOGENEOUS_CONDUCTIVITIES_S_M
        )
        depth = PAPER_SOURCE_DEPTH_M
        mu = _positive_legendre_root(10)
        self.assertLess(abs(_legendre_scalar_and_derivative(10, mu)[0]), 2.0e-14)
        radius = NAESS_RADII_M[3]
        sensor = np.asarray(((radius * math.sqrt(1.0 - mu * mu), 0.0, radius * mu),))
        source = np.asarray((0.0, 0.0, depth))
        radial = np.asarray((0.0, 0.0, DIPOLE_MOMENT_A_M))
        high_degree = forward_potentials(
            geometry, source, radial, sensor, max_degree=256
        )
        expected = _brody_homogeneous_closed_form(
            depth,
            radial,
            sensor,
            radius,
            HOMOGENEOUS_CONDUCTIVITIES_S_M[0],
        )
        measured_error = _scaled_max_error(
            high_degree.potentials_v,
            expected,
            radial,
            HOMOGENEOUS_CONDUCTIVITIES_S_M[0],
            radius,
        )
        self.assertLess(measured_error, 2.0e-9)
        self.assertGreaterEqual(high_degree.diagnostics["tail_relative"], measured_error)
        self.assertEqual(high_degree.diagnostics["tail_certified"], 0.0)
        self.assertEqual(high_degree.diagnostics["tail_validated_range"], 1.0)

    def test_p10_nodal_term_is_tiny_but_omitted_tail_is_not(self) -> None:
        """A nodal last term is not evidence that the infinite tail is small.

        The candidate exposes a conditional geometric tail *estimate*, not a
        certified bound. The exception assertion checks that its public refusal
        labels that diagnostic as an estimate; the independent closed form below
        quantifies the actual omitted tail.
        """
        geometry = FourSphereGeometry(
            NAESS_RADII_M, HOMOGENEOUS_CONDUCTIVITIES_S_M
        )
        depth = PAPER_SOURCE_DEPTH_M
        degree = 10
        mu = _positive_legendre_root(degree)
        p_degree, _ = _legendre_scalar_and_derivative(degree, mu)
        self.assertLess(abs(p_degree), 2.0e-14)
        radius = NAESS_RADII_M[3]
        sensor = np.asarray(((radius * math.sqrt(1.0 - mu * mu), 0.0, radius * mu),))
        source = np.asarray((0.0, 0.0, depth))
        radial = np.asarray((0.0, 0.0, DIPOLE_MOMENT_A_M))
        exact = _brody_homogeneous_closed_form(
            depth,
            radial,
            sensor,
            radius,
            HOMOGENEOUS_CONDUCTIVITIES_S_M[0],
        )
        finite_sum = _independent_surface_sum(
            source,
            radial,
            sensor,
            NAESS_RADII_M,
            HOMOGENEOUS_CONDUCTIVITIES_S_M,
            degree,
        )
        physical_scale = (
            DIPOLE_MOMENT_A_M
            / (
                4.0
                * math.pi
                * HOMOGENEOUS_CONDUCTIVITIES_S_M[0]
                * radius**2
            )
        )
        last_term = (
            (2.0 * degree + 1.0)
            * (depth / radius) ** (degree - 1)
            * DIPOLE_MOMENT_A_M
            * p_degree
            / (4.0 * math.pi * HOMOGENEOUS_CONDUCTIVITIES_S_M[0] * radius**2)
        )
        omitted_tail = abs(float(exact[0] - finite_sum[0])) / physical_scale
        self.assertLess(abs(last_term) / physical_scale, 1.0e-12)
        self.assertGreater(omitted_tail, 0.1)

        with self.assertRaisesRegex(
            FourSphereQualityError, "truncation tail estimate"
        ):
            forward_potentials(
                geometry,
                source,
                radial,
                sensor,
                max_degree=degree,
                tail_tol=1.0e-10,
            )

        # This permissive tolerance asks the real candidate API for its explicit
        # L=10 partial sum. It does not certify the candidate's heuristic estimate.
        result = forward_potentials(
            geometry,
            source,
            radial,
            sensor,
            max_degree=degree,
            tail_tol=1.0e100,
        )
        self.assertLess(
            _scaled_max_error(
                result.potentials_v,
                finite_sum,
                radial,
                HOMOGENEOUS_CONDUCTIVITIES_S_M[0],
                radius,
            ),
            2.0e-10,
        )
        self.assertGreater(
            _scaled_max_error(result.potentials_v, exact, radial,
                              HOMOGENEOUS_CONDUCTIVITIES_S_M[0], radius),
            0.1,
        )
        actual_error = _scaled_max_error(
            result.potentials_v,
            exact,
            radial,
            HOMOGENEOUS_CONDUCTIVITIES_S_M[0],
            radius,
        )
        self.assertGreaterEqual(result.diagnostics["tail_relative"], actual_error)
        self.assertEqual(result.diagnostics["tail_certified"], 0.0)
        self.assertEqual(result.diagnostics["tail_validated_range"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
