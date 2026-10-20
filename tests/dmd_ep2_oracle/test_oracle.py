import cmath
import math
import unittest


def model(omega, delta, gamma, g):
    return ((complex(omega + delta, -gamma), complex(0, -g)),
            (complex(0, -g), complex(omega - delta, -gamma)))


def discriminant(delta, g):
    # Eigenvalues are omega-i*gamma +/- sqrt(delta**2-g**2).
    return delta * delta - g * g


def pairs(trajectories):
    return [(x[i], x[i + 1]) for x in trajectories for i in range(len(x) - 1)]


def log_diag(z):
    if z == 0:
        raise ValueError('singular matrix has no logarithm')
    return cmath.log(z)


def branch_diagnostic(eigenvalues, margin=1e-6):
    # Distance in phase to +/-pi; warning only, not an aliasing test.
    d = min(abs(math.pi - abs(cmath.phase(z))) for z in eigenvalues if z != 0)
    return {'near_cut': d <= margin, 'phase_margin': d}


def signed_nyquist_alias(frequency, sampling_rate):
    """Return the signed representative in [-Fs/2, Fs/2)."""
    return ((frequency + sampling_rate / 2) % sampling_rate) - sampling_rate / 2


def mat_identity():
    return ((1 + 0j, 0j), (0j, 1 + 0j))


def mat_add(a, b):
    return tuple(tuple(a[i][j] + b[i][j] for j in range(2)) for i in range(2))


def mat_scale(c, a):
    return tuple(tuple(c * a[i][j] for j in range(2)) for i in range(2))


def mat_sub(a, b):
    return mat_add(a, mat_scale(-1, b))


def mat_norm(a):
    return math.sqrt(sum(abs(a[i][j]) ** 2 for i in range(2) for j in range(2)))


def matrix_function_2x2(a, function, derivative, tol=1e-12):
    """Analytic 2x2 oracle, using interpolation or the repeated-root limit."""
    center = (a[0][0] + a[1][1]) / 2
    half_diff = (a[0][0] - a[1][1]) / 2
    radius = cmath.sqrt(half_diff * half_diff + a[0][1] * a[1][0])
    if abs(radius) <= tol:
        n = mat_sub(a, mat_scale(center, mat_identity()))
        if mat_norm(n) <= tol:
            return mat_scale(function(center), mat_identity())
        # A defective repeated-root 2x2 matrix has N**2 == 0.
        return mat_add(mat_scale(function(center), mat_identity()),
                       mat_scale(derivative(center), n))
    l1, l2 = center + radius, center - radius
    slope = (function(l1) - function(l2)) / (l1 - l2)
    return mat_add(mat_scale(function(l2), mat_identity()),
                   mat_scale(slope, mat_sub(a, mat_scale(l2, mat_identity()))))


def mat_exp(a):
    return matrix_function_2x2(a, cmath.exp, cmath.exp)


def principal_matrix_log(a):
    # The oracle is valid only when the spectrum avoids zero and the cut.
    return matrix_function_2x2(a, cmath.log, lambda z: 1 / z)


def max_entry_error(a, b):
    return max(abs(a[i][j] - b[i][j]) for i in range(2) for j in range(2))


class OracleTests(unittest.TestCase):
    def test_splitting_sweep_and_ep(self):
        self.assertAlmostEqual(2 * math.sqrt(discriminant(1.2, .4)), 2.2627416997969525)
        self.assertAlmostEqual(2 * math.sqrt(discriminant(1.2, 1.0)), 1.32664991614216)
        self.assertEqual(discriminant(1.2, 1.2), 0)
        # At EP, shifted H is nonzero nilpotent: rank one, algebraic mult. two.
        h = model(0, 1.2, 0, 1.2)
        n = ((h[0][0], h[0][1]), (h[1][0], h[1][1]))
        # Full N^2 == 0 (not a single-entry proxy that can pass for non-nilpotent matrices).
        n2 = (
            (n[0][0] * n[0][0] + n[0][1] * n[1][0],
             n[0][0] * n[0][1] + n[0][1] * n[1][1]),
            (n[1][0] * n[0][0] + n[1][1] * n[1][0],
             n[1][0] * n[0][1] + n[1][1] * n[1][1]),
        )
        for i in range(2):
            for j in range(2):
                self.assertAlmostEqual(n2[i][j], 0j)
        self.assertNotEqual(mat_norm(n), 0)
        self.assertNotEqual(n[0][1], 0)
        # Analytic nullspace has dimension one: one nonzero row, determinant zero.
        self.assertAlmostEqual(n[0][0]*n[1][1] - n[0][1]*n[1][0], 0j)

    def test_single_entry_n2_proxy_is_insufficient(self):
        """Regression: n00^2 + n01*n10 == 0 does not imply N^2 == 0 in general."""
        # Trace nonzero ⇒ N²[0,1] = n01*(n00+n11) ≠ 0 while the [0,0] proxy vanishes.
        n = ((1 + 0j, 1 + 0j), (-1 + 0j, 1 + 0j))
        proxy = n[0][0] ** 2 + n[0][1] * n[1][0]
        self.assertAlmostEqual(proxy, 0j)
        n2 = (
            (n[0][0] * n[0][0] + n[0][1] * n[1][0],
             n[0][0] * n[0][1] + n[0][1] * n[1][1]),
            (n[1][0] * n[0][0] + n[1][1] * n[1][0],
             n[1][0] * n[0][1] + n[1][1] * n[1][1]),
        )
        self.assertGreater(mat_norm(n2), 1e-9)

    def test_pairs_do_not_cross_seams(self):
        a, b = [1, 2, 3], [100, 101]
        self.assertEqual(pairs([a, b]), [(1, 2), (2, 3), (100, 101)])
        self.assertNotIn((3, 100), pairs([a, b]))
        naive = list(zip(a + b, (a + b)[1:]))
        self.assertIn((3, 100), naive)

    def test_scalar_log_and_branch_are_distinct(self):
        z = 2 + 0j
        self.assertAlmostEqual(abs(cmath.exp(log_diag(z)) - z), 0)
        self.assertFalse(branch_diagnostic([z])['near_cut'])
        cut = cmath.rect(1, math.pi - 1e-9)
        self.assertTrue(branch_diagnostic([cut])['near_cut'])
        # Principal log maps negative-real eigenvalues to phase +pi; proximity
        # warns of branch sensitivity, not an unobserved physical frequency.
        self.assertAlmostEqual(log_diag(-1+0j).imag, math.pi)

    def test_signed_nyquist_alias_convention(self):
        # With Fs=250 Hz, signed principal representatives put 240 Hz at
        # -10 Hz and the Nyquist endpoint 250 Hz at 0 Hz.  This demonstrates
        # aliasing; it does not show that sampling can recover the source.
        self.assertAlmostEqual(signed_nyquist_alias(240.0, 250.0), -10.0)
        self.assertAlmostEqual(signed_nyquist_alias(250.0, 250.0), 0.0)
        self.assertAlmostEqual(signed_nyquist_alias(-240.0, 250.0), 10.0)

    def test_singular_log_rejected(self):
        with self.assertRaises(ValueError):
            log_diag(0j)

    def test_matrix_log_oracle_diagonalizable_defective_and_nonnormal(self):
        cases = [
            ((2 + 0j, 0j), (0j, 3 + 0j)),
            ((2 + 0j, 1 + 0j), (0j, 2 + 0j)),  # defective, nonzero nilpotent part
            ((2 + 0j, 100 + 0j), (0j, 3 + 0j)),  # strongly nonnormal
        ]
        for matrix in cases:
            log_a = principal_matrix_log(matrix)
            self.assertLess(max_entry_error(mat_exp(log_a), matrix), 1e-10)
            # The residual is a reconstruction check, not generator recovery.

    def test_matrix_log_oracle_rejects_singular_and_flags_cut(self):
        singular = ((0j, 0j), (0j, 2 + 0j))
        with self.assertRaises(ValueError):
            principal_matrix_log(singular)
        near_cut = ((cmath.rect(1, math.pi - 1e-9), 0j),
                    (0j, 2 + 0j))
        self.assertTrue(branch_diagnostic([near_cut[0][0], near_cut[1][1]])['near_cut'])

    def test_matrix_log_round_trip_does_not_identify_branch(self):
        # exp(log(z)) is also compatible with logs differing by 2*pi*i*k.
        z = 2 + 0j
        principal = cmath.log(z)
        alternate = principal + 2j * math.pi
        self.assertAlmostEqual(abs(cmath.exp(principal) - z), 0)
        self.assertAlmostEqual(abs(cmath.exp(alternate) - z), 0)


if __name__ == '__main__':
    unittest.main()
