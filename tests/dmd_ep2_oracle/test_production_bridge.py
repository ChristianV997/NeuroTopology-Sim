"""Production-import bridge for the DMD/EP2 oracle (HOLD / SYNTHETIC_ONLY).

Two run modes
-------------
* **oracle-only** (default discover of ``test_oracle.py``): never imports production.
* **production-import** (this module): requires
  ``neurotopology_sim.experimental.dynamics.dmd_crouzeix``.

Environment
-----------
``DMD_EP2_REQUIRE_PRODUCTION=1``
    Fail closed if the production leaf cannot be imported (no silent skip).
Unset (default)
    Skip with an explicit ``ORACLE_ONLY`` reason when the leaf is absent
    (historical #400 base without the merged leaf). When the leaf *is*
    present, tests run and must not skip.
"""
from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from types import CodeType, FunctionType, ModuleType, SimpleNamespace
from unittest.mock import patch


def _load_oracle_helpers():
    """Load sibling ``test_oracle`` by file path (package- and discover-safe).

    Avoids ``from test_oracle import …`` which raises ``ModuleNotFoundError``
    when this module is loaded as ``tests.dmd_ep2_oracle.test_production_bridge``
    and would otherwise be mistaken for a missing production leaf.
    """
    path = Path(__file__).resolve().parent / "test_oracle.py"
    spec = importlib.util.spec_from_file_location(
        "dmd_ep2_oracle_test_oracle_helpers", path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load oracle helpers from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_oracle = _load_oracle_helpers()
model = _oracle.model
signed_nyquist_alias = _oracle.signed_nyquist_alias


def _load_production():
    from neurotopology_sim.experimental.dynamics import dmd_crouzeix as dmd

    return dmd


def _expected_production_source():
    return (
        Path(__file__).resolve().parents[2]
        / "neurotopology_sim"
        / "experimental"
        / "dynamics"
        / "dmd_crouzeix.py"
    )


def _assert_checkout_production_source(dmd):
    checkout_root = Path(__file__).resolve().parents[2]
    expected = _expected_production_source().resolve()
    expected_name = "neurotopology_sim.experimental.dynamics.dmd_crouzeix"
    raw_path = getattr(dmd, "__file__", None)
    if not raw_path:
        raise AssertionError("production module has no source file path")
    actual = Path(raw_path).resolve()
    try:
        actual.relative_to(checkout_root)
    except ValueError as exc:
        raise AssertionError(
            f"production source is outside this checkout: {actual}"
        ) from exc
    if actual != expected:
        raise AssertionError(
            "production source is not this checkout's dmd_crouzeix.py: "
            f"expected {expected}, got {actual}"
        )
    if getattr(dmd, "__name__", None) != expected_name:
        raise AssertionError(
            f"unexpected production module name: {getattr(dmd, '__name__', None)!r}"
        )

    spec = getattr(dmd, "__spec__", None)
    spec_origin = getattr(spec, "origin", None)
    if not spec_origin or Path(spec_origin).resolve() != expected:
        raise AssertionError(
            "production module import spec does not identify this checkout's source"
        )
    loader = getattr(dmd, "__loader__", None)
    if loader is None or loader is not getattr(spec, "loader", None):
        raise AssertionError("production module was not loaded by its declared source loader")

    # Import metadata and co_filename can both be forged by an in-process
    # stub. Compare the exercised function code against definitions compiled
    # directly from the exact source file. This is a test-time identity check,
    # not a security boundary against arbitrary Python code execution.
    source_code = compile(expected.read_text(encoding="utf-8"), str(expected), "exec")
    source_functions = {
        item.co_name: item
        for item in source_code.co_consts
        if isinstance(item, CodeType)
    }

    for symbol in (
        "ep2_hamiltonian",
        "diagnose_ep2",
        "discrete_eigenvalue_from_frequency_hz",
        "alias_ambiguity_report",
    ):
        function = getattr(dmd, symbol, None)
        code = getattr(function, "__code__", None)
        if (
            function is None
            or getattr(function, "__module__", None) != expected_name
            # Genuine code rebound to another globals dict would run against forged names.
            or getattr(function, "__globals__", None) is not dmd.__dict__
            or code is None
            or Path(code.co_filename).resolve() != expected
            or source_functions.get(symbol) != code
        ):
            raise AssertionError(
                f"production function {symbol!r} does not match this checkout's source"
            )
    return actual


def _load_production_for_suite(require, loader=None, source_path=None):
    """Skip only when the leaf file is absent; never disguise import faults."""
    source_path = Path(source_path or _expected_production_source())
    if not source_path.is_file():
        message = f"production leaf is absent at {source_path}"
        if require:
            raise AssertionError(message)
        raise unittest.SkipTest(
            f"ORACLE_ONLY: {message}; re-run with DMD_EP2_REQUIRE_PRODUCTION=1 "
            "against a tree that contains the merged dmd_crouzeix leaf"
        )

    try:
        dmd = (loader or _load_production)()
    except Exception as exc:
        raise AssertionError(
            "production leaf exists, but importing it failed; this is not "
            f"ORACLE_ONLY (check dependencies/runtime): {type(exc).__name__}: {exc}"
        ) from exc
    _assert_checkout_production_source(dmd)
    return dmd


class ProductionImportBridgeTests(unittest.TestCase):
    """Cross-check oracle fixtures against the real production leaf."""

    @classmethod
    def setUpClass(cls):
        require = os.environ.get("DMD_EP2_REQUIRE_PRODUCTION", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        cls.dmd = _load_production_for_suite(require)

    def test_ep2_hamiltonian_matches_oracle_and_nilpotency(self):
        import numpy as np

        h_oracle = model(0.0, 1.2, 0.0, 1.2)
        h_prod = self.dmd.ep2_hamiltonian(omega=0.0, delta=1.2, gamma=0.0, g=1.2)
        self.assertTrue(np.allclose(np.asarray(h_oracle), h_prod, atol=1e-12))
        rep = self.dmd.diagnose_ep2(h_prod)
        self.assertEqual(rep.algebraic_multiplicity, 2)
        self.assertEqual(rep.geometric_multiplicity, 1)
        self.assertGreater(float(rep.nilpotent_norm), 1e-8)
        self.assertLess(float(rep.nilpotent_square_norm), 1e-10)
        self.assertIn("HOLD", str(self.dmd.PROJECT_STATUS))

    def test_nyquist_alias_matches_production_report(self):
        import numpy as np

        # Exact signed equivalence (oracle) — do not relax to almost-equal.
        self.assertEqual(signed_nyquist_alias(240.0, 250.0), -10.0)
        self.assertEqual(
            signed_nyquist_alias(240.0, 250.0),
            signed_nyquist_alias(-10.0, 250.0),
        )
        dt = 1.0 / 250.0
        l240 = self.dmd.discrete_eigenvalue_from_frequency_hz(240.0, dt)
        lm10 = self.dmd.discrete_eigenvalue_from_frequency_hz(-10.0, dt)
        self.assertTrue(np.allclose(l240, lm10, atol=1e-12))
        rep = self.dmd.alias_ambiguity_report(f_hz=240.0, fs_hz=250.0)
        self.assertTrue(rep.phases_match)
        self.assertEqual(float(rep.f_alias_hz), -10.0)

    def test_bridge_loaded_real_production_module(self):
        """Hard-import proof: resolved module path is the production leaf file."""
        path = _assert_checkout_production_source(self.dmd)
        self.assertEqual(path, _expected_production_source().resolve())
        self.assertEqual(path.name, "dmd_crouzeix.py")

    def test_production_finite_and_shape_validation(self):
        """Bridge surfaces production fail-closed contracts (synthetic only)."""
        Err = self.dmd.DMDValidationError
        with self.assertRaises(Err):
            self.dmd.ep2_hamiltonian(float("nan"), 1.2, 0.0, 1.2)
        with self.assertRaises(Err):
            self.dmd.ep2_hamiltonian(0.0, float("inf"), 0.0, 1.2)
        import numpy as np

        with self.assertRaises(Err):
            self.dmd.diagnose_ep2(np.ones((3, 3), dtype=np.complex128))
        bad = np.array([[np.nan + 0j, 0j], [0j, 1 + 0j]], dtype=np.complex128)
        with self.assertRaises(Err):
            self.dmd.diagnose_ep2(bad)


class ProductionBridgePolicyTests(unittest.TestCase):
    """The optional oracle-only mode must not hide bridge import defects."""

    def test_missing_dependency_is_not_reported_as_missing_production_leaf(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "neurotopology_sim"
            / "experimental"
            / "dynamics"
            / "dmd_crouzeix.py"
        )
        self.assertTrue(source.is_file(), "the checkout contains the production leaf")
        missing_numpy = ModuleNotFoundError("No module named 'numpy'", name="numpy")
        with patch.dict(os.environ, {"DMD_EP2_REQUIRE_PRODUCTION": ""}):
            with patch(__name__ + "._load_production", side_effect=missing_numpy):
                try:
                    ProductionImportBridgeTests.setUpClass()
                except unittest.SkipTest as exc:
                    self.fail(
                        "a present production leaf with a missing dependency was "
                        f"misclassified as ORACLE_ONLY: {exc}"
                    )
                except AssertionError as exc:
                    self.assertIn("production leaf", str(exc).lower())
                else:
                    self.fail("production import failure must not be accepted")

    def test_rejects_same_suffix_module_from_another_checkout(self):
        repo_root = Path(__file__).resolve().parents[2]
        copied_path = (
            repo_root
            / "unrelated-checkout"
            / "neurotopology_sim"
            / "experimental"
            / "dynamics"
            / "dmd_crouzeix.py"
        )
        copied_module = SimpleNamespace(
            __file__=str(copied_path),
            __name__="neurotopology_sim.experimental.dynamics.dmd_crouzeix",
        )
        had_previous = hasattr(ProductionImportBridgeTests, "dmd")
        previous = getattr(ProductionImportBridgeTests, "dmd", None)
        try:
            with patch.dict(os.environ, {"DMD_EP2_REQUIRE_PRODUCTION": "1"}):
                with patch(__name__ + "._load_production", return_value=copied_module):
                    try:
                        ProductionImportBridgeTests.setUpClass()
                    except AssertionError as exc:
                        self.assertIn("checkout", str(exc).lower())
                    else:
                        self.fail(
                            "a module from another checkout passed the suffix-only "
                            "production path check"
                        )
        finally:
            if had_previous:
                ProductionImportBridgeTests.dmd = previous
            elif hasattr(ProductionImportBridgeTests, "dmd"):
                del ProductionImportBridgeTests.dmd

    def test_rejects_stub_claiming_exact_production_source_path(self):
        """A module-name/path-shaped stub is not the imported production leaf."""
        expected = _expected_production_source().resolve()
        stub = SimpleNamespace(
            __file__=str(expected),
            __name__="neurotopology_sim.experimental.dynamics.dmd_crouzeix",
        )
        with self.assertRaisesRegex(AssertionError, "production module|production function"):
            _load_production_for_suite(
                True,
                loader=lambda: stub,
                source_path=expected,
            )

    def test_rejects_stub_with_forged_import_and_function_metadata(self):
        """Metadata alone cannot make unrelated function bodies the production leaf."""
        expected = _expected_production_source().resolve()
        name = "neurotopology_sim.experimental.dynamics.dmd_crouzeix"
        stub = ModuleType(name)
        stub.__file__ = str(expected)
        stub.__spec__ = importlib.util.spec_from_file_location(name, expected)
        stub.__loader__ = stub.__spec__.loader
        spoofed_functions = compile(
            "\n".join(
                f"def {symbol}(*args, **kwargs): return 'spoofed'"
                for symbol in (
                    "ep2_hamiltonian",
                    "diagnose_ep2",
                    "discrete_eigenvalue_from_frequency_hz",
                    "alias_ambiguity_report",
                )
            ),
            str(expected),
            "exec",
        )
        exec(spoofed_functions, stub.__dict__)
        with self.assertRaisesRegex(AssertionError, "production function"):
            _load_production_for_suite(True, loader=lambda: stub, source_path=expected)

    def test_oracle_only_skip_is_limited_to_an_absent_leaf(self):
        missing_source = _expected_production_source().with_name(
            "missing_dmd_crouzeix.py"
        )

        def unexpected_load():
            self.fail("loader must not run when the source file is absent")

        with self.assertRaisesRegex(unittest.SkipTest, "ORACLE_ONLY: production leaf is absent"):
            _load_production_for_suite(
                False, loader=unexpected_load, source_path=missing_source
            )
        with self.assertRaisesRegex(AssertionError, "production leaf is absent"):
            _load_production_for_suite(
                True, loader=unexpected_load, source_path=missing_source
            )

    def test_rejects_stub_with_missing_required_symbol(self):
        """A module missing one of the required symbols must be rejected.

        The genuine module object is used, with only alias_ambiguity_report unset. Copying
        genuine functions into a separate stub module is a forgery, and the globals check
        rejects it before the missing symbol is reached.
        """
        expected = _expected_production_source().resolve()
        real_dmd = _load_production()
        with patch.object(real_dmd, "alias_ambiguity_report", None):
            with self.assertRaisesRegex(AssertionError, "production function 'alias_ambiguity_report'"):
                _load_production_for_suite(True, loader=lambda: real_dmd, source_path=expected)

    def test_rejects_stub_with_loader_mismatch(self):
        """A module whose loader doesn't match its spec loader must be rejected."""
        expected = _expected_production_source().resolve()
        name = "neurotopology_sim.experimental.dynamics.dmd_crouzeix"
        stub = ModuleType(name)
        stub.__file__ = str(expected)
        stub.__spec__ = importlib.util.spec_from_file_location(name, expected)
        stub.__loader__ = object()  # Mismatched loader
        with self.assertRaisesRegex(AssertionError, "not loaded by its declared source loader"):
            _load_production_for_suite(True, loader=lambda: stub, source_path=expected)

    def test_rejects_stub_with_none_file_attribute(self):
        """A module without __file__ must fail closed."""
        expected = _expected_production_source().resolve()
        stub = SimpleNamespace(__name__="neurotopology_sim.experimental.dynamics.dmd_crouzeix")
        with self.assertRaisesRegex(AssertionError, "has no source file path"):
            _load_production_for_suite(True, loader=lambda: stub, source_path=expected)

    def test_rejects_stub_with_spec_origin_mismatch(self):
        """A module whose spec origin differs from expected must fail closed."""
        expected = _expected_production_source().resolve()
        name = "neurotopology_sim.experimental.dynamics.dmd_crouzeix"
        stub = ModuleType(name)
        stub.__file__ = str(expected)
        stub.__spec__ = SimpleNamespace(origin=str(expected.parent / "other.py"), loader=object())
        stub.__loader__ = stub.__spec__.loader
        with self.assertRaisesRegex(AssertionError, "import spec does not identify this checkout's source"):
            _load_production_for_suite(True, loader=lambda: stub, source_path=expected)



    def test_rejects_genuine_code_rebound_to_forged_globals(self):
        """Genuine code objects bound to a different globals dict are not the leaf's functions."""
        expected = _expected_production_source().resolve()
        name = "neurotopology_sim.experimental.dynamics.dmd_crouzeix"
        real = _load_production()
        stub = ModuleType(name)
        stub.__file__ = str(expected)
        stub.__spec__ = importlib.util.spec_from_file_location(name, expected)
        stub.__loader__ = stub.__spec__.loader
        forged_globals = dict(real.__dict__)
        forged_globals["__name__"] = name
        for symbol in (
            "ep2_hamiltonian",
            "diagnose_ep2",
            "discrete_eigenvalue_from_frequency_hz",
            "alias_ambiguity_report",
        ):
            genuine = getattr(real, symbol)
            rebound = FunctionType(
                genuine.__code__, forged_globals, symbol, genuine.__defaults__, genuine.__closure__
            )
            rebound.__kwdefaults__ = genuine.__kwdefaults__
            setattr(stub, symbol, rebound)
        with self.assertRaisesRegex(AssertionError, "production function"):
            _load_production_for_suite(True, loader=lambda: stub, source_path=expected)

    def test_production_required_flag_is_case_insensitive(self):
        """'True' and 'Yes' are required-mode spellings: an absent leaf must fail, not skip."""
        missing = _expected_production_source().with_name("missing_dmd_crouzeix.py")
        for value in ("True", "Yes", "yes", "TRUE"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"DMD_EP2_REQUIRE_PRODUCTION": value}):
                    with patch(__name__ + "._expected_production_source", return_value=missing):
                        try:
                            ProductionImportBridgeTests.setUpClass()
                        except unittest.SkipTest:
                            self.fail(f"required-mode value {value!r} produced an ORACLE_ONLY skip")
                        except AssertionError:
                            pass
                        else:
                            self.fail(f"required-mode value {value!r} accepted an absent leaf")


if __name__ == "__main__":
    unittest.main()
