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


class ProductionImportBridgeTests(unittest.TestCase):
    """Cross-check oracle fixtures against the real production leaf."""

    @classmethod
    def setUpClass(cls):
        require = os.environ.get("DMD_EP2_REQUIRE_PRODUCTION", "").strip() in {
            "1",
            "true",
            "TRUE",
            "yes",
            "YES",
        }
        try:
            cls.dmd = _load_production()
        except Exception as exc:
            if require:
                raise AssertionError(
                    "production-import run requires "
                    "neurotopology_sim.experimental.dynamics.dmd_crouzeix; "
                    f"import failed: {exc}"
                ) from exc
            raise unittest.SkipTest(
                f"ORACLE_ONLY: production leaf absent ({exc}); "
                "re-run with DMD_EP2_REQUIRE_PRODUCTION=1 against a tree "
                "that contains the merged dmd_crouzeix leaf"
            ) from exc
        # Leaf present: must proceed (no silent skip).
        if cls.dmd is None:
            raise AssertionError("production leaf imported as None")
        path = getattr(cls.dmd, "__file__", "")
        if "dmd_crouzeix.py" not in str(path):
            raise AssertionError(f"unexpected production module path: {path!r}")

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
        path = Path(self.dmd.__file__).resolve()
        self.assertEqual(path.name, "dmd_crouzeix.py")
        self.assertIn("neurotopology_sim", path.parts)
        self.assertIn("experimental", path.parts)
        self.assertIn("dynamics", path.parts)
        self.assertEqual(self.dmd.__name__, "neurotopology_sim.experimental.dynamics.dmd_crouzeix")

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


if __name__ == "__main__":
    unittest.main()
