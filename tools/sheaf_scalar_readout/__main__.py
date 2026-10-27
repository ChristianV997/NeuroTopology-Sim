"""Run the sheaf→scalar readout benchmark and print a JSON dossier fragment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from .hodge import closedness_needs_degree_two_map, readout_breaks_hodge_demo
from .sheaf import (
    LinearReadout,
    exactness_preserved,
    is_endpoint_compatible,
    random_vertex_cochain,
    reverse_edge_orientation,
    sheaf_coboundary,
    scalarize_edge_cochain,
)
from .triangle_example import (
    build_canonical_triangle,
    compatible_readout_all_identity_sheaf,
    first_coordinate_readout,
    run_canonical_triangle,
)


def kernel_tests() -> dict:
    sheaf = build_canonical_triangle()
    # Zero readout: everything maps to 0 — compatible with Λ₀=0, preserves exactness trivially
    zero = LinearReadout({e.name: np.zeros(2) for e in sheaf.edges})
    ok0, v0, _ = is_endpoint_compatible(sheaf, zero)
    z = {"1": np.array([1.0, 1.0]), "2": np.zeros(2), "3": np.zeros(2)}
    exact0, sc0, c0 = exactness_preserved(sheaf, zero, z)

    # Nonzero incompatible (first coord)
    nonzero = first_coordinate_readout(sheaf)
    ok1, _, diag1 = is_endpoint_compatible(sheaf, nonzero)
    exact1, sc1, c1 = exactness_preserved(sheaf, nonzero, z)

    # Nonzero compatible on identity sheaf
    sheaf_I, lam_I = compatible_readout_all_identity_sheaf()
    ok2, _, _ = is_endpoint_compatible(sheaf_I, lam_I)
    exact2, sc2, c2 = exactness_preserved(sheaf_I, lam_I, z)
    return {
        "zero_readout": {
            "compatible": ok0,
            "scalar_exact": exact0,
            "cycle_sum": c0,
            "scalar_edges": sc0,
        },
        "nonzero_incompatible": {
            "compatible": ok1,
            "diag": diag1,
            "scalar_exact": exact1,
            "cycle_sum": c1,
            "scalar_edges": sc1,
        },
        "nonzero_compatible_identity_sheaf": {
            "compatible": ok2,
            "scalar_exact": exact2,
            "cycle_sum": c2,
            "scalar_edges": sc2,
        },
    }


def orientation_reversal_check() -> dict:
    sheaf = build_canonical_triangle()
    z = {"1": np.array([1.0, 1.0]), "2": np.zeros(2), "3": np.zeros(2)}
    omega = sheaf_coboundary(sheaf, z)
    sheaf_r = reverse_edge_orientation(sheaf, "e12")
    omega_r = sheaf_coboundary(sheaf_r, z)
    return {
        "omega_e12": omega["e12"].tolist(),
        "omega_rev_e12": omega_r["e12"].tolist(),
        "negation_holds": bool(np.allclose(omega_r["e12"], -omega["e12"])),
        "other_edges_unchanged": bool(
            np.allclose(omega_r["e23"], omega["e23"])
            and np.allclose(omega_r["e31"], omega["e31"])
        ),
    }


def random_cochain_survey(n: int = 40, seed: int = 7) -> dict:
    sheaf = build_canonical_triangle()
    bad = first_coordinate_readout(sheaf)
    sheaf_I, good = compatible_readout_all_identity_sheaf()
    rng = np.random.default_rng(seed)
    incompat_nonzero_cycles = 0
    compat_nonzero_cycles = 0
    for _ in range(n):
        z = random_vertex_cochain(sheaf, rng)
        _, _, c_bad = exactness_preserved(sheaf, bad, z)
        if abs(c_bad) > 1e-8:
            incompat_nonzero_cycles += 1
        z2 = random_vertex_cochain(sheaf_I, rng)
        _, _, c_good = exactness_preserved(sheaf_I, good, z2)
        if abs(c_good) > 1e-8:
            compat_nonzero_cycles += 1
    return {
        "n": n,
        "seed": seed,
        "incompatible_nonzero_cycle_count": incompat_nonzero_cycles,
        "compatible_nonzero_cycle_count": compat_nonzero_cycles,
        "note": (
            "Compatible readout: cycle sums must vanish (exactness preserved). "
            "Incompatible: often nonzero — not a probabilistic claim about neural data."
        ),
    }


def physical_bridge_gap() -> dict:
    return {
        "what_exists_mathematically": (
            "Endpoint-compatible Λ gives a cochain map on the 1-skeleton so scalar "
            "cycle sums of exact sheaf cochains vanish; incompatible Λ need not."
        ),
        "what_scalar_CTMC_needs": (
            "A continuous-time Markov chain on graph vertices typically uses scalar "
            "edge affinities / log-rate ratios whose cycle sums encode nonequilibrium "
            "drive (EMF). That is a scalar graph object."
        ),
        "missing_bridge": (
            "Still missing: (1) a readout with explicit units of work (or free-energy) "
            "per sheaf-stalk mismatch; (2) an independently justified map from that "
            "scalar affinity to CTMC transition rates or electromotive force — not "
            "postulated by the algebra alone."
        ),
        "kept_distinct": [
            "mathematical exactness of sheaf/scalar cochains",
            "scalar CTMC cycle affinity as a modeling choice",
            "physical energy/EMF coupling requiring units and independent justification",
        ],
        "non_claim": "This example does not model actual neural dynamics.",
    }


def main() -> int:
    payload = {
        "agent": "Cursor D",
        "benchmark": "sheaf_to_scalar_readout",
        "canonical_triangle": run_canonical_triangle(),
        "kernels": kernel_tests(),
        "orientation_reversal": orientation_reversal_check(),
        "random_cochain_survey": random_cochain_survey(),
        "hodge": readout_breaks_hodge_demo(),
        "closedness_vs_exactness": closedness_needs_degree_two_map(),
        "physical_bridge_gap": physical_bridge_gap(),
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    digest = hashlib.sha256(blob).hexdigest()
    out = {"results_sha256": digest, "payload": payload}
    text = json.dumps(out, indent=2, default=str)
    print(text)
    scratch = Path("/tmp/sheaf-scalar-readout-scratch")
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "results.json").write_text(text)
    (scratch / "RESULTS_HASH.txt").write_text(digest + "\n")
    art = Path("/opt/cursor/artifacts/sheaf-scalar-readout")
    try:
        art.mkdir(parents=True, exist_ok=True)
        (art / "results.json").write_text(text)
        (art / "RESULTS_HASH.txt").write_text(digest + "\n")
    except OSError:
        pass  # artifact FS may be flaky; scratch copy is authoritative
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
