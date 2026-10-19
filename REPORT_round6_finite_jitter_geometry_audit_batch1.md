# Independent Audit of Round 6 Finite-Jitter Triangulation Claims — Batch 1

**Disposition:** HOLD / SYNTHETIC_ONLY

**Audit date:** 2026-10-17

**Branch:** `batch1/hermes-b-mesh-geometry-audit`

**Worktree:** `C:/Users/HP/OneDrive/Documentos/GitHub/.repo-dev-worktrees/mesh-geometry-audit-batch1-20261016`

**Verified base (original):** `origin/main` at `3f3fe8593303184cb88eef056c1322f3d4e57a16`.
**Live main (rebased):** `origin/main` at `bc91af19a22783d2721fc881842573f7e08a8925`.
**Submission note:** The independent reviewer was unavailable through the configured provider route; the user authorized proceeding without that review. Exact final head SHA and PR URL are in the submission handoff.

### Production-import addendum (Cursor Agent C / Batch 2)

Live main now includes
`neurotopology_sim/experimental/geometry/planar_triangulation.py`.
Owned comparison tests:
`tests/test_finite_jitter_production_import.py` hard-import that module,
assert a production mesh passes this independent auditor, and assert the
overlapping-face adversarial mesh fails the auditor.

**Round 6 discovery gap → Codex Agent A (do not edit workflows here):**
`.github/workflows/round6_experimental_tests.py` has **no** component for
`tools/audit_finite_jitter_triangulation.py` /
`tests/test_finite_jitter_triangulation_audit.py` /
`tests/test_finite_jitter_production_import.py`. Proposed mapping name:
`finite_jitter_triangulation_audit` with those three paths as
implementation/tests. Without it, hosted Round 6 never collects these suites.

## Executive finding

The claimed `16` points, `20` faces, `35` edges, and `10` extreme hull vertices are mutually consistent for a triangulation with ten boundary vertices. The counts follow from the planar triangulation formulas `F = 2n - 2 - h` and `E = 3n - 3 - h`; they are necessary consistency checks, not proof of a planar embedding.

The stated checks—edge incidence, positive unperturbed face areas, and equality of summed face area with a shoelace area computed from triangle-inferred boundary vertices—do **not** establish a planar triangulation. The adversarial square in the focused tests has all four vertices covered, two positive and consistently oriented triangles, valid one/two edge incidences, the expected `F=2` and `E=5`, and an exact area-sum identity. Yet the two triangles overlap, their diagonals cross, and their one-face edges do not match the independently computed hull. Angularly sorting the inferred boundary vertices still gives the square’s exact shoelace area. Direct independent hull correspondence and intersection checks are therefore material, not redundant.

No executable Round 6 finite-jitter candidate was found in the inspected proposal branch. The results below are tests of an independent geometric specification and synthetic meshes only; they are **not** candidate-code results, a Delaunay certification, or scientific validation. CGAL’s documentation defines a triangulation as a planar subdivision of the convex hull; the empty-circle condition is an additional Delaunay property, which this auditor deliberately does not test.[1][2]

## Discovery and scope

- Live `origin/main` was `3f3fe8593303184cb88eef056c1322f3d4e57a16` at preflight and again when the candidate branch was checked.
- The inspected proposal branch was `batch3/grok-chat-a-round6-claim-audit`, head `c483aa3ea6fdca3f736c901f8867dc40cf6fe292`. Its matching tree path was `docs/research/batch3/grok_chat_a_round6_claim_audit.md`; no executable finite-jitter triangulator or Round 6 geometry implementation was found in that branch tree. The document itself is not evidence that a candidate implementation was tested.[4][5]
- Existing production `validation/montage_topology.py:156-166` calls `scipy.spatial.Delaunay` and returns its simplices. That path was not changed or used as the audit oracle.
- Only the new auditor, its focused tests, and this Batch 1 report are in scope. No package was installed. No dataset, participant data, or third-party triangulation source was downloaded, opened, or executed.

## Independent audit method

`tools/audit_finite_jitter_triangulation.py` is a standard-library-only command-line auditor for supplied coordinates and indexed triangles. It does not create or perturb meshes.

1. **Independent hull:** computes a strict convex hull using a monotone-chain orientation algorithm, then separately recovers all supplied input points lying on each hull segment. Candidate-inferred boundary vertices are not used to compute this hull.
2. **Exact predicates on represented inputs:** integer, `Fraction`, and JSON-decimal coordinates are exact rationals. Python floats are interpreted as their exact binary floating-point values. Orientation, segment, area, and hull predicates use rational arithmetic without a geometric epsilon. Robust orientation decisions matter because rounded floating-point predicates can change sign-based geometric classifications.[3]
3. **Coverage and topology:** validates triangle indices and uniqueness, requires every input point to occur in a face, checks nonzero areas and consistent winding, counts edge incidences, and tests face connectedness through shared edges.
4. **Embedding and boundary:** checks non-shared segment crossings (including collinear overlaps and T-junctions), pairwise triangle intersections, and equality between observed one-face edges and the independently computed hull chain, including collinear hull-edge points.
5. **Consistency checks:** compares face/edge counts with the Euler-derived formulas and compares the exact sum of absolute face areas with the independent convex-hull area.

Under the stated assumptions—finite unique 2D points, nondegenerate convex hull, correct triangle indexing, and exact predicates on the supplied values—the combined checks reject gaps, overlaps, crossings, missing input vertices, nonmanifold incidences, disconnected face sets, and incorrect boundaries. Together they are a geometric consistency certificate for a straight-line triangulation of the supplied point set’s convex hull. They do not establish the jitter algorithm’s behavior, a Delaunay empty-circle property, or any scientific claim.[1][2]

## Why area equality and angular sorting are insufficient

The square counterexample uses points `[(0,0), (1,0), (1,1), (0,1)]` and faces `[(0,1,2), (0,1,3)]`:

- `4` points, `2` faces, `5` unique edges, and `4` hull vertices match the triangulated-disk Euler counts.
- Both face orientations are positive; all input points are covered; every edge has incidence one or two; summed face area equals convex-hull area exactly.
- The inferred one-face edge endpoints include all four square vertices. Sorting those vertices by angle around their centroid and applying the shoelace formula also gives the square’s exact area.
- Despite those results, there is one non-shared edge crossing and one intersecting triangle pair. The one-face edges differ from the independently computed hull chain.

Summed absolute area can conceal overlap balanced by missing area; a shoelace identity over boundary vertices inferred from the same mesh is not an independent boundary test. Angular sorting orders a supplied vertex set; it does not establish that the set is the convex hull, that boundary edges correspond to hull segments, or that faces do not overlap.

## Adversarial outcomes

| Case | Result |
|---|---|
| Requested-style 16-point fixture (6 inner, 10 outer; trigonometric float coordinates) | `16` points, `20` faces, `35` edges, `10` extreme hull and boundary vertices; all auditor checks satisfied. |
| Exact-cocircular 16-point fixture | Added a second synthetic fixture using rational parametrizations: six points satisfy `x²+y²=4/25`, ten satisfy `x²+y²=1` exactly. A valid annulus-zipper mesh has `20` faces, `35` edges, and `10` extreme hull vertices; all auditor checks satisfied. The nonuniform rational angular spacing preserves exact cocircularity without claiming exact equal-angle spacing. |
| Overlapping square counterexample | Area identity, coverage, positive areas, consistent orientation, edge incidence, and Euler counts are true; one crossing and one intersecting face pair are found; independent boundary correspondence is false; overall geometry result is rejected. |
| Near-cocircular quadrilateral, `δ=10⁻¹²` | Both non-overlapping diagonal choices pass geometric checks. This is not a Delaunay/tie-breaking test. |
| Near-collinear positive-area triangle, height `10⁻³⁰` | Accepted with exact nonzero area; no absolute area tolerance is used. |
| Input point on a hull edge | Four extreme hull vertices and five hull-boundary vertices are distinguished; the boundary chain must include the collinear input point. |
| Reordered 16-point input | The permuted mesh preserves counts, exact area equality, and geometric consistency after index remapping. |
| Uniform scaling by `10⁻¹⁰⁰` and `10¹⁰⁰`; translation by `(2³⁰, -2³⁰)` | The supplied transformed meshes preserve the `20`/`35` counts and geometric checks. |
| Finite jitter after large translation | For span `1`, jitter `10⁻¹⁰` is rounded away when added to coordinates at magnitude `2³⁰`; the ULP there is `2.384185791015625×10⁻⁷`. The resulting binary float coordinates are unchanged. Thus relative jitter magnitude alone does not guarantee a distinct perturbed coordinate after translation. |
| Degenerate/adversarial topology | Collinear hull, duplicate coordinates, non-finite coordinate, out-of-range index, uncovered point, disconnected faces, mixed winding, and a three-face edge incidence are rejected by their corresponding checks. |

The first fixture uses ordinary trigonometric floats and therefore represents near-cocircular binary coordinates, not exact real-number circles. The second fixture supplies exact rational circles. The auditor certifies the meshes supplied to it; neither fixture executes candidate code.

## Scale invariance and downstream floors

The new auditor itself has no absolute area or edge-length floor: its predicates are exact on the represented inputs. The Round 6 implementation was absent, so any candidate-specific downstream face-area or edge-length thresholds remain **unknown and unverified**.

In the inspected current-main geometry path, `validation/montage_topology.py:8,251,309` uses `EPS = 1e-12` in a dimensionless metric denominator; it is not a triangle-area or edge-length rejection floor. Its `_median_nn_distance` helper uses the same epsilon as a fallback for fewer than two points or zero nearest-neighbor distance (`:559-579`). `topo_monitor/tda_adapters/fallback.py:78-100` uses `dist_mat > 1e-12` only to choose a default maximum threshold; the later edge loop includes distances up to that maximum. `max_edge_length` is an upper filtration cutoff, not a minimum edge-length floor. No Round 6 face-area floor or minimum-edge rejection was found in the inspected current-main paths.

A fixed absolute threshold would break scale invariance: face area changes by `λ²` under uniform coordinate scaling, while edge length changes by `|λ|`. Any downstream `A_min` or `L_min` must therefore be shown to scale with the coordinates, or the claimed invariance must be restricted to a stated coordinate range. This cannot be resolved without the absent candidate/downstream code. Finite floating-point jitter is also not fully translation invariant: translation changes the local ULP, and a perturbation smaller than that ULP may disappear. Robust predicates can classify the coordinates that remain, but cannot restore a perturbation already rounded away.[3]

## Reproduction and limitations

From the repository root, use an input JSON object with `points: [[x,y], ...]` and `triangles: [[i,j,k], ...]`:

```bash
python tools/audit_finite_jitter_triangulation.py --input mesh.json
```

The CLI emits a finite JSON report and keeps `decision` at `HOLD / SYNTHETIC_ONLY`. Exit codes: `0` means all implemented geometric consistency checks are satisfied; `1` means the mesh/input failed a geometric check; `2` means the JSON file could not be read or parsed. Exit `0` is not a scientific validation or a Delaunay claim.

Focused tests are in `tests/test_finite_jitter_triangulation_audit.py`. The exact command used is:

```bash
PYTHONDONTWRITEBYTECODE=1 python -c 'import runpy,sys; sys.path.insert(0, "."); runpy.run_path("tests/test_finite_jitter_triangulation_audit.py", run_name="__main__")'
```

Result: `Ran 14 tests in 3.147s; OK` (software checks only). `python -m pytest --version` reports `No module named pytest`; `make check` could not start because `make` is not installed/on PATH. No package installation was attempted. Direct `unittest discover -s tests` also resolves `tools` to `tests/tools/__init__.py`, which shadows the repository-root `tools` package; the command above puts the repository root first and executes the focused module. The full repository pytest/Makefile checks are therefore unverified.

Limitations: pairwise edge and face intersection checks are quadratic; this is intended for small audit fixtures, not production meshing. The auditor does not check Delaunay empty circumcircles, finite-jitter determinism, exact equal-angle construction, or downstream absolute thresholds absent from the candidate. Exact arithmetic certifies represented coordinates, not intended pre-rounding coordinates.

## Files in scope

- `tools/audit_finite_jitter_triangulation.py` — independent standard-library geometric auditor and CLI.
- `tests/test_finite_jitter_triangulation_audit.py` — deterministic synthetic fixture and adversarial tests.
- `REPORT_round6_finite_jitter_geometry_audit_batch1.md` — this report.

*All sources below were accessed on 2026-10-17.*

## Sources

[1] https://doc.cgal.org/latest/Triangulation_2/classCGAL_1_1Triangulation__2.html — CGAL::Triangulation_2 Reference
[2] https://doc.cgal.org/latest/Triangulation_2/classCGAL_1_1Delaunay__triangulation__2.html — CGAL::Delaunay_triangulation_2 Reference
[3] https://people.eecs.berkeley.edu/~jrs/papers/robustr.pdf — Shewchuk: Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates
[4] https://github.com/ChristianV997/NeuroTopology-Sim/blob/c483aa3ea6fdca3f736c901f8867dc40cf6fe292/docs/research/batch3/grok_chat_a_round6_claim_audit.md — NeuroTopology-Sim Batch 3 Round 6 claim-audit document at pinned commit
[5] https://github.com/ChristianV997/NeuroTopology-Sim/tree/c483aa3ea6fdca3f736c901f8867dc40cf6fe292 — NeuroTopology-Sim repository tree at inspected Batch 3 proposal commit
