import cmath
import math
import subprocess
import sys
import unittest
from fractions import Fraction
from pathlib import Path


def model(omega, delta, gamma, g):
    return ((complex(omega + delta, -gamma), complex(0, -g)),
            (complex(0, -g), complex(omega - delta, -gamma)))


def discriminant(delta, g):
    # Eigenvalues are omega-i*gamma +/- sqrt(delta**2-g**2).
    return delta * delta - g * g


def pairs(trajectories):
    return [(x[i], x[i + 1]) for x in trajectories for i in range(len(x) - 1)]


def log_diag(z):
    _require_finite_scalar(z, name='eigenvalue')
    if z == 0:
        raise ValueError('singular matrix has no logarithm')
    return cmath.log(z)


def _require_finite_scalar(z, name='value'):
    if isinstance(z, complex):
        if not (math.isfinite(z.real) and math.isfinite(z.imag)):
            raise ValueError(f'{name} must be finite')
        return
    if isinstance(z, (int, float)):
        try:
            finite = math.isfinite(float(z))
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f'{name} must be finite') from exc
        if not finite:
            raise ValueError(f'{name} must be finite')
        return
    # numpy scalars / other numeric
    try:
        c = complex(z)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f'{name} must be numeric') from exc
    if not (math.isfinite(c.real) and math.isfinite(c.imag)):
        raise ValueError(f'{name} must be finite')


def _require_finite_nonnegative_real(value, name):
    try:
        numeric = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f'{name} must be a finite nonnegative real number') from exc
    if not math.isfinite(numeric) or numeric < 0.0:
        raise ValueError(f'{name} must be a finite nonnegative real number')
    return numeric


def _require_finite_2x2(a, name='matrix'):
    """Fail closed on non-2×2 shape or non-finite entries (oracle contract)."""
    try:
        rows = len(a)
        cols = [len(row) for row in a]
    except TypeError as exc:
        raise ValueError(f'{name} must be a 2x2 sequence') from exc
    if rows != 2 or cols != [2, 2]:
        raise ValueError(f'{name} must be shape (2, 2); got rows={rows} cols={cols}')
    for i in range(2):
        for j in range(2):
            _require_finite_scalar(a[i][j], name=f'{name}[{i},{j}]')


def branch_diagnostic(eigenvalues, margin=1e-6):
    # Distance in phase to +/-pi; warning only, not an aliasing test.
    # Exact-zero / empty spectra are degenerate for a branch-cut proximity
    # check: fail closed rather than crashing on min() of an empty iterable.
    margin = _require_finite_nonnegative_real(margin, 'margin')
    nonzero = []
    for z in eigenvalues:
        _require_finite_scalar(z, name='eigenvalue')
        if z != 0:
            nonzero.append(z)
    if not nonzero:
        raise ValueError(
            'branch_diagnostic requires at least one nonzero finite eigenvalue; '
            'exact-zero or empty spectra are degenerate'
        )
    d = min(abs(math.pi - abs(cmath.phase(z))) for z in nonzero)
    return {'near_cut': d <= margin, 'phase_margin': d}


def signed_nyquist_alias(frequency, sampling_rate):
    """Return the signed representative in [-Fs/2, Fs/2).

    Fail closed on non-finite frequency/rate or non-positive sampling rate
    (avoids silent NaN and ZeroDivisionError from ``% 0``).
    """
    try:
        f = float(frequency)
        fs = float(sampling_rate)
    except (TypeError, ValueError) as exc:
        raise ValueError('frequency and sampling_rate must be real floats') from exc
    if not math.isfinite(f):
        raise ValueError(f'frequency must be finite; got {frequency!r}')
    if not math.isfinite(fs) or fs <= 0.0:
        raise ValueError(f'sampling_rate must be a positive finite float; got {sampling_rate!r}')
    return ((f + fs / 2) % fs) - fs / 2


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


def mat_mul(a, b):
    return tuple(
        tuple(a[i][0] * b[0][j] + a[i][1] * b[1][j] for j in range(2))
        for i in range(2)
    )


def mat_inv_2x2(a, tol=1e-14):
    """Invert a nonsingular 2×2 matrix; reject ill-conditioned det analytically."""
    det = a[0][0] * a[1][1] - a[0][1] * a[1][0]
    if abs(det) <= tol:
        raise ValueError(f"singular / ill-conditioned 2x2 inverse; |det|={abs(det)}")
    inv_det = 1.0 / det
    return (
        (a[1][1] * inv_det, -a[0][1] * inv_det),
        (-a[1][0] * inv_det, a[0][0] * inv_det),
    )


def mat_similarity(p, b):
    """Return A = P B P^{-1} (synthetic similarity transform)."""
    return mat_mul(p, mat_mul(b, mat_inv_2x2(p)))


def frobenius_cond_diag_dominant(a):
    """Crude 2×2 spectral condition proxy: |λ_max|/|λ_min| for diagonalizable diag case.

    Used only to justify residual tolerances on synthetic nonnormal fixtures;
    not a production κ estimator and not an empirical claim.
    """
    center = (a[0][0] + a[1][1]) / 2
    half_diff = (a[0][0] - a[1][1]) / 2
    radius = cmath.sqrt(half_diff * half_diff + a[0][1] * a[1][0])
    l1, l2 = center + radius, center - radius
    if l1 == 0 or l2 == 0:
        raise ValueError("zero eigenvalue: matrix log undefined")
    return abs(l1) / abs(l2) if abs(l1) >= abs(l2) else abs(l2) / abs(l1)


def assert_full_nilpotency(n, tol=1e-12):
    """Require the full matrix condition N**2 == 0 (not a single-entry proxy)."""
    tol = _require_finite_nonnegative_real(tol, 'tol')
    _require_finite_2x2(n, name='nilpotent part')
    n2 = mat_mul(n, n)
    _require_finite_2x2(n2, name='nilpotent part squared')
    residual = mat_norm(n2)
    if not math.isfinite(residual):
        raise ValueError('nilpotency residual norm must be finite')
    if residual > tol:
        raise ValueError(
            "repeated-eigenvalue branch requires full nilpotency N**2 == 0; "
            f"||N**2||={residual}"
        )
    return n2


def _matrix_center_radius(a):
    """Return finite center/radius values for a validated 2×2 matrix."""
    _require_finite_2x2(a, name='matrix')
    scale = max(
        max(abs(value.real), abs(value.imag))
        for row in a
        for value in row
    )
    if scale == 0.0:
        return 0j, 0j

    scaled = tuple(tuple(value / scale for value in row) for row in a)
    scaled_center = (scaled[0][0] + scaled[1][1]) / 2
    half_diff = (scaled[0][0] - scaled[1][1]) / 2
    radicand = half_diff * half_diff + scaled[0][1] * scaled[1][0]
    _require_finite_scalar(scaled_center, name='scaled matrix eigenvalue center')
    _require_finite_scalar(radicand, name='scaled matrix eigenvalue radicand')
    try:
        scaled_radius = cmath.sqrt(radicand)
    except (OverflowError, ValueError) as exc:
        raise ValueError('matrix eigenvalue radius is invalid') from exc
    center = scaled_center * scale
    radius = scaled_radius * scale
    _require_finite_scalar(center, name='matrix eigenvalue center')
    _require_finite_scalar(radius, name='matrix eigenvalue radius')
    return center, radius


def _exact_determinant_quotient(a, root):
    """Recover det(A)/root exactly from the input floats when scaling underflows."""
    def parts(value):
        value = complex(value)
        return Fraction.from_float(value.real), Fraction.from_float(value.imag)

    def multiply(left, right):
        return (
            left[0] * right[0] - left[1] * right[1],
            left[0] * right[1] + left[1] * right[0],
        )

    def subtract(left, right):
        return left[0] - right[0], left[1] - right[1]

    determinant = subtract(
        multiply(parts(a[0][0]), parts(a[1][1])),
        multiply(parts(a[0][1]), parts(a[1][0])),
    )
    if determinant == (0, 0):
        return 0j

    root_real, root_imag = parts(root)
    denominator = root_real * root_real + root_imag * root_imag
    if denominator == 0:
        raise ValueError('cannot recover an eigenvalue from a zero dominant root')
    quotient = (
        (determinant[0] * root_real + determinant[1] * root_imag) / denominator,
        (determinant[1] * root_real - determinant[0] * root_imag) / denominator,
    )
    try:
        result = complex(float(quotient[0]), float(quotient[1]))
    except (OverflowError, ValueError) as exc:
        raise ValueError('recovered matrix eigenvalue is not representable') from exc
    _require_finite_scalar(result, name='recovered matrix eigenvalue')
    if result == 0j and quotient != (0, 0):
        raise ValueError('recovered matrix eigenvalue underflows floating-point range')
    return result


def _matrix_eigenvalues_2x2(a, center, radius):
    """Compute both roots, recovering a cancellation-prone root from a scaled det."""
    first, second = center + radius, center - radius
    _require_finite_scalar(first, name='first matrix eigenvalue')
    _require_finite_scalar(second, name='second matrix eigenvalue')
    scale = abs(center) + abs(radius)
    cancellation_limit = math.sqrt(math.ulp(1.0)) * scale
    if scale > 0.0 and min(abs(first), abs(second)) <= cancellation_limit:
        matrix_scale = max(
            max(abs(value.real), abs(value.imag))
            for row in a
            for value in row
        )
        scaled = tuple(tuple(value / matrix_scale for value in row) for row in a)
        determinant_left = scaled[0][0] * scaled[1][1]
        determinant_right = scaled[0][1] * scaled[1][0]
        determinant_scaled = determinant_left - determinant_right
        _require_finite_scalar(determinant_scaled, name='scaled matrix determinant')
        determinant_roundoff = (
            4.0
            * math.ulp(1.0)
            * (abs(determinant_left) + abs(determinant_right))
        )
        exact_recovery = abs(determinant_scaled) <= determinant_roundoff
        if abs(first) < abs(second) and second != 0:
            large_scaled = second / matrix_scale
            if exact_recovery:
                first = _exact_determinant_quotient(a, second)
            else:
                first = (determinant_scaled / large_scaled) * matrix_scale
                if first == 0j:
                    first = _exact_determinant_quotient(a, second)
        elif abs(second) < abs(first) and first != 0:
            large_scaled = first / matrix_scale
            if exact_recovery:
                second = _exact_determinant_quotient(a, first)
            else:
                second = (determinant_scaled / large_scaled) * matrix_scale
                if second == 0j:
                    second = _exact_determinant_quotient(a, first)
    _require_finite_scalar(first, name='first matrix eigenvalue')
    _require_finite_scalar(second, name='second matrix eigenvalue')
    return first, second


def matrix_function_2x2(a, function, derivative, tol=1e-12):
    """Analytic 2x2 oracle, using interpolation or the repeated-root limit."""
    tol = _require_finite_nonnegative_real(tol, 'tol')
    center, radius = _matrix_center_radius(a)
    if abs(radius) <= tol:
        n = mat_sub(a, mat_scale(center, mat_identity()))
        _require_finite_2x2(n, name='matrix nilpotent part')
        if mat_norm(n) <= tol:
            value = function(center)
            _require_finite_scalar(value, name='matrix function value')
            result = mat_scale(value, mat_identity())
            _require_finite_2x2(result, name='matrix function result')
            return result
        # Defective Jordan case: enforce full N**2 == 0 before using N f'(λ).
        assert_full_nilpotency(n, tol=tol)
        value = function(center)
        slope = derivative(center)
        _require_finite_scalar(value, name='matrix function value')
        _require_finite_scalar(slope, name='matrix function derivative')
        result = mat_add(mat_scale(value, mat_identity()), mat_scale(slope, n))
        _require_finite_2x2(result, name='matrix function result')
        return result
    l1, l2 = _matrix_eigenvalues_2x2(a, center, radius)
    value1 = function(l1)
    value2 = function(l2)
    _require_finite_scalar(value1, name='first matrix function value')
    _require_finite_scalar(value2, name='second matrix function value')
    slope = (value1 - value2) / (l1 - l2)
    _require_finite_scalar(slope, name='matrix function slope')
    result = mat_add(
        mat_scale(value2, mat_identity()),
        mat_scale(slope, mat_sub(a, mat_scale(l2, mat_identity()))),
    )
    _require_finite_2x2(result, name='matrix function result')
    return result


def mat_exp(a):
    return matrix_function_2x2(a, cmath.exp, cmath.exp)


def principal_matrix_log(a):
    # The principal matrix log is undefined for zero or negative-real spectrum.
    center, radius = _matrix_center_radius(a)
    for eigenvalue in _matrix_eigenvalues_2x2(a, center, radius):
        if eigenvalue == 0:
            raise ValueError('singular matrix has no logarithm')
        if eigenvalue.real < 0.0 and eigenvalue.imag == 0.0:
            raise ValueError(
                'principal matrix logarithm is undefined on the negative-real branch cut'
            )
    return matrix_function_2x2(a, cmath.log, lambda z: 1 / z)


def max_entry_error(a, b):
    return max(abs(a[i][j] - b[i][j]) for i in range(2) for j in range(2))


class OracleTests(unittest.TestCase):
    def test_oracle_import_firewall(self):
        """Loading this oracle must not import production or numerical engines."""
        oracle_path = Path(__file__).resolve()
        script = r"""
import importlib.abc
import importlib.util
import sys

blocked = ("neurotopology_sim", "dmd_crouzeix", "numpy", "scipy")

class ImportFirewall(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + ".") for name in blocked):
            raise AssertionError("oracle imported forbidden module: " + fullname)
        return None

sys.meta_path.insert(0, ImportFirewall())
spec = importlib.util.spec_from_file_location("isolated_dmd_ep2_oracle", sys.argv[1])
if spec is None or spec.loader is None:
    raise AssertionError("could not load oracle source")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(oracle_path)],
            cwd=str(oracle_path.parents[2]),
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"oracle import firewall failed: {result.stdout}\n{result.stderr}",
        )

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
        n2 = mat_mul(n, n)
        self.assertGreater(mat_norm(n2), 1e-9)
        with self.assertRaises(ValueError):
            assert_full_nilpotency(n)

    def test_defective_branch_requires_full_nilpotency(self):
        """Repeated-root analytic formula must refuse non-nilpotent N."""
        # Exact Jordan block: N**2 == 0 → formula accepted.
        jordan = ((2 + 0j, 1 + 0j), (0j, 2 + 0j))
        log_j = principal_matrix_log(jordan)
        self.assertLess(max_entry_error(mat_exp(log_j), jordan), 1e-10)
        # Non-nilpotent N with vanishing single-entry proxy must be rejected.
        with self.assertRaises(ValueError):
            assert_full_nilpotency(((1 + 0j, 1 + 0j), (-1 + 0j, 1 + 0j)))

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

    def test_matrix_log_rejects_exact_rank_one_matrix_after_rounding(self):
        """A rounded nonzero determinant must not admit a log for rank-one input."""
        with self.assertRaises(ValueError):
            principal_matrix_log(((1 + 0j, 3 + 0j), (15 + 0j, 45 + 0j)))

    def test_matrix_log_distinguishes_unrepresentable_root_from_singularity(self):
        """A below-subnormal positive root is unsupported, not mislabeled zero."""
        matrix = (
            (1e308 + 0j, 1.9880958645724236e-8 + 0j),
            (1.9880958645724236e-8 + 0j, 5e-324 + 0j),
        )
        with self.assertRaisesRegex(ValueError, 'underflows floating-point range'):
            principal_matrix_log(matrix)

    def test_matrix_log_subnormal_determinant_is_not_called_singular(self):
        """A nonzero exact determinant may underflow only after root recovery."""
        unit = math.ulp(0.0)
        matrix = ((100 * unit, 99 * unit), (101 * unit, 100 * unit))
        with self.assertRaisesRegex(ValueError, 'underflows floating-point range'):
            principal_matrix_log(matrix)

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

    def test_matrix_log_similarity_covariance(self):
        """f(P B P^{-1}) = P f(B) P^{-1} for the principal matrix log (diag case)."""
        b = ((2 + 0j, 0j), (0j, 3 + 0j))
        # Unimodular shear: det(P)=1, well-conditioned.
        p = ((1 + 0j, 0.5 + 0j), (0j, 1 + 0j))
        a = mat_similarity(p, b)
        log_b = principal_matrix_log(b)
        log_a = principal_matrix_log(a)
        conjugated = mat_similarity(p, log_b)
        # Exact algebraic identity for primary matrix functions on this spectrum.
        self.assertLess(max_entry_error(log_a, conjugated), 1e-10)
        # Reconstruction residual remains a check on exp∘log, not branch ID.
        self.assertLess(max_entry_error(mat_exp(log_a), a), 1e-10)

    def test_ill_conditioned_nonnormal_residual_tolerance(self):
        """Strongly nonnormal 2×2: residual tol scales with κ_proxy, not loosened ad hoc."""
        # Eigenvalues 2 and 3 (κ_proxy = 1.5); off-diagonal 1e3 drives nonnormality.
        a = ((2 + 0j, 1e3 + 0j), (0j, 3 + 0j))
        kappa = frobenius_cond_diag_dominant(a)
        self.assertAlmostEqual(kappa, 1.5)
        log_a = principal_matrix_log(a)
        residual = max_entry_error(mat_exp(log_a), a)
        # Analytic budget: unit-roundoff-scale * κ * ||A||_F (synthetic bound).
        # For this fixture ||A||_F ≈ 1e3; allow 1e-9 * κ * ||A||_F ≈ 1.5e-6.
        budget = 1e-9 * kappa * mat_norm(a)
        self.assertLess(residual, budget)
        self.assertLess(residual, 1e-6)  # absolute floor still tight; do not weaken

    def test_branch_diagnostic_rejects_exact_zero_and_empty_spectra(self):
        """Regression: exact-zero / empty spectra must fail closed (not min() crash)."""
        with self.assertRaises(ValueError):
            branch_diagnostic([0j, 0j])
        with self.assertRaises(ValueError):
            branch_diagnostic([])

    def test_matrix_rejects_bad_shape_and_nonfinite(self):
        """Shape / finite validation before any matrix-function evaluation."""
        with self.assertRaises(ValueError):
            principal_matrix_log(((1 + 0j, 0j),))  # not 2×2
        with self.assertRaises(ValueError):
            principal_matrix_log(((1 + 0j, 0j, 0j), (0j, 1 + 0j, 0j)))
        with self.assertRaises(ValueError):
            principal_matrix_log(((float('nan') + 0j, 0j), (0j, 1 + 0j)))
        with self.assertRaises(ValueError):
            principal_matrix_log(((float('inf') + 0j, 0j), (0j, 1 + 0j)))
        with self.assertRaises(ValueError):
            branch_diagnostic([float('nan') + 0j])

    def test_scalar_log_and_nilpotency_helpers_reject_nonfinite_values(self):
        """Scalar and residual helpers must not let NaN comparisons pass."""
        for value in (float('nan'), float('inf'), complex(float('nan'), 0.0)):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    log_diag(value)

        for matrix in (
            ((complex(float('nan'), 0.0), 0j), (0j, 1 + 0j)),
            # Finite inputs can still overflow/cancel to NaN while forming N².
            ((1e308 + 0j, 1e308 + 0j), (-1e308 + 0j, -1e308 + 0j)),
        ):
            with self.subTest(matrix=matrix):
                with self.assertRaises(ValueError):
                    assert_full_nilpotency(matrix)

    def test_matrix_log_rejects_cut_but_accepts_small_nonzero_eigenvalue(self):
        """Reject the principal-log cut without treating small λ>0 as zero."""
        with self.assertRaises(ValueError):
            principal_matrix_log(((-1 + 0j, 0j), (0j, 2 + 0j)))

    def test_matrix_log_accepts_small_nonzero_eigenvalue(self):
        """A representable positive eigenvalue is not singular by magnitude."""
        small_positive = 1e-13
        result = principal_matrix_log(((small_positive + 0j, 0j), (0j, 2 + 0j)))
        self.assertAlmostEqual(result[0][0].real, math.log(small_positive), places=10)
        self.assertAlmostEqual(result[1][1].real, math.log(2.0), places=14)

    def test_matrix_log_accepts_large_finite_diagonal_scale(self):
        """Finite diagonal spectra stay usable when raw discriminants overflow."""
        for magnitude in (1e154, 1e155):
            with self.subTest(magnitude=magnitude):
                result = principal_matrix_log(
                    ((magnitude + 0j, 0j), (0j, 2 * magnitude + 0j))
                )
                self.assertAlmostEqual(result[0][0].real, math.log(magnitude), places=10)
                self.assertAlmostEqual(result[1][1].real, math.log(2 * magnitude), places=10)

    def test_matrix_log_recovers_large_cancellation_prone_small_eigenvalue(self):
        """Scale determinant recovery so large finite products do not overflow."""
        small, large = 1e192, 1e200
        result = principal_matrix_log(((large + 0j, 0j), (0j, small + 0j)))
        self.assertAlmostEqual(result[0][0].real, math.log(large), places=10)
        self.assertAlmostEqual(result[1][1].real, math.log(small), places=10)

    def test_matrix_log_preserves_small_eigenvalue_below_scaled_product_range(self):
        """A representable root is recovered without underflowing det/scale²."""
        small, large = 1e-200, 1e200
        result = principal_matrix_log(((large + 0j, 0j), (0j, small + 0j)))
        self.assertAlmostEqual(result[0][0].real, math.log(large), places=10)
        self.assertAlmostEqual(result[1][1].real, math.log(small), places=10)

    def test_exponential_accepts_zero_eigenvalue(self):
        """The generic matrix-function helper must not impose log singularity."""
        result = mat_exp(((0j, 0j), (0j, 2 + 0j)))
        expected = ((1 + 0j, 0j), (0j, cmath.exp(2 + 0j)))
        self.assertLess(max_entry_error(result, expected), 1e-12)

    def test_numerical_tolerances_must_be_finite_and_nonnegative(self):
        """NaN/∞ thresholds must not turn comparisons into false acceptance."""
        near_cut = cmath.rect(1.0, math.pi - 1e-8)
        nonnilpotent = ((1 + 0j, 0j), (0j, 0j))
        diagonal = ((1 + 0j, 0j), (0j, 2 + 0j))
        for threshold in (float('nan'), float('inf'), -1.0):
            with self.subTest(threshold=threshold):
                with self.assertRaises(ValueError):
                    branch_diagnostic([near_cut], margin=threshold)
        for tolerance in (float('nan'), float('inf')):
            with self.subTest(helper='nilpotency', tolerance=tolerance):
                with self.assertRaises(ValueError):
                    assert_full_nilpotency(nonnilpotent, tol=tolerance)
            with self.subTest(helper='matrix_function', tolerance=tolerance):
                with self.assertRaises(ValueError):
                    matrix_function_2x2(diagonal, cmath.log, lambda z: 1 / z, tol=tolerance)

    def test_ep_discriminant_exact_zero_and_scaling(self):
        """At EP, discriminant is exact 0; homogeneous scaling preserves coalescence."""
        self.assertEqual(discriminant(0.0, 0.0), 0.0)
        self.assertEqual(discriminant(1.2, 1.2), 0.0)
        # Scale (delta, g) by α: disc → α² disc; EP remains EP.
        for alpha in (1e-6, 1.0, 1e3):
            self.assertEqual(discriminant(alpha * 1.2, alpha * 1.2), 0.0)
            h = model(0.0, alpha * 1.2, 0.0, alpha * 1.2)
            det = h[0][0] * h[1][1] - h[0][1] * h[1][0]
            self.assertAlmostEqual(det, 0j)
            # Full N² == 0 at every scale (synthetic algebraic identity).
            assert_full_nilpotency(h, tol=1e-9 * max(1.0, abs(alpha) ** 2))

    def test_nyquist_240_minus10_exact_equivalence(self):
        """240 Hz and −10 Hz are the same signed representative at Fs=250 Hz."""
        self.assertEqual(signed_nyquist_alias(240.0, 250.0), -10.0)
        # Do not relax: exact float identity for this dyadic-friendly pair.
        self.assertEqual(signed_nyquist_alias(240.0, 250.0), signed_nyquist_alias(-10.0, 250.0))

    def test_nyquist_rejects_nonfinite_and_nonpositive_rate(self):
        """Regression: NaN/Inf frequency and Fs<=0 must fail closed (not NaN/%0)."""
        with self.assertRaises(ValueError):
            signed_nyquist_alias(float('nan'), 250.0)
        with self.assertRaises(ValueError):
            signed_nyquist_alias(float('inf'), 250.0)
        with self.assertRaises(ValueError):
            signed_nyquist_alias(10.0, 0.0)
        with self.assertRaises(ValueError):
            signed_nyquist_alias(10.0, -250.0)
        with self.assertRaises(ValueError):
            signed_nyquist_alias(10.0, float('nan'))


    def test_matrix_log_overflow_in_off_diagonals_fails_closed(self):
        """Synthetic matrix with large entries overflowing radius fails closed."""
        matrix = ((1.7e308 + 0j, 1.7e308 + 0j), (1.7e308 + 0j, -1.7e308 + 0j))
        with self.assertRaisesRegex(ValueError, 'matrix eigenvalue radius must be finite'):
            principal_matrix_log(matrix)

    def test_matrix_log_overflow_in_eigenvalue_addition_fails_closed(self):
        """Matrix where center and radius are finite but sum overflows fails closed."""
        matrix = ((1.2e308 + 0j, 0.9e308 + 0j), (0.9e308 + 0j, 1.2e308 + 0j))
        with self.assertRaisesRegex(ValueError, 'first matrix eigenvalue must be finite'):
            principal_matrix_log(matrix)

    def test_matrix_log_overflow_in_eigenvalue_subtraction_fails_closed(self):
        """Matrix where subtraction center - radius overflows negatively fails closed."""
        matrix = ((-1.2e308 + 0j, 0.9e308 + 0j), (0.9e308 + 0j, -1.2e308 + 0j))
        with self.assertRaisesRegex(ValueError, 'second matrix eigenvalue must be finite'):
            principal_matrix_log(matrix)

    def test_matrix_log_catastrophic_cancellation_preserves_log(self):
        """Exact rational determinant recovery preserves log despite float cancellation."""
        # det = (1e100 + 1j)(1e100 - 1j) - (1e100)^2 = 1e200 + 1 - 1e200 = 1.
        matrix = ((1e100 + 1j, 1e100 + 0j), (1e100 + 0j, 1e100 - 1j))
        res = principal_matrix_log(matrix)
        for i in range(2):
            for j in range(2):
                self.assertTrue(math.isfinite(res[i][j].real))
                self.assertTrue(math.isfinite(res[i][j].imag))

    def test_matrix_log_zero_matrix_is_singular(self):
        """Zero matrix has all zero eigenvalues and is classified as singular."""
        with self.assertRaisesRegex(ValueError, 'singular matrix has no logarithm'):
            principal_matrix_log(((0j, 0j), (0j, 0j)))

    def test_exact_determinant_quotient_rejects_zero_dominant_root(self):
        """_exact_determinant_quotient fails closed if dominant root is zero."""
        matrix = ((1.0 + 0j, 0j), (0j, 1.0 + 0j))
        with self.assertRaisesRegex(ValueError, 'cannot recover an eigenvalue from a zero dominant root'):
            _exact_determinant_quotient(matrix, 0j)


if __name__ == '__main__':
    unittest.main()
