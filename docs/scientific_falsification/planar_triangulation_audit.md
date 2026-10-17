# Planar Triangulation and Embedding Validity Audit (Batch 2 / Antigravity Agent A)

**Status:** HOLD / SYNTHETIC_ONLY
**Branch:** `batch2/antigravity-a-planar-triangulation`
**Base Commit:** `19c3203573082f8bc41f7da226b52dc20a49fdb0` (`origin/main`)
**Scope:** Independent adversarial test surface for planar sensor triangulation and embedding validity (`tests/experimental/test_planar_triangulation.py` and `tests/experimental/planar_mesh_test_helpers.py`).

---

## 1. Executive Summary & Project Posture

- **Project Posture:** HOLD / SYNTHETIC_ONLY. The tests in this suite establish geometric and topological properties of 2D sensor-coordinate planar meshes. They do not establish cortical topology, functional localization, or scientific/consciousness claims.
- **Gemini Revision 8 Status:** Treated strictly as unverified research input, not mathematical ground truth.
- **Production Target Assessment:**
  - Audited legacy candidate `triangulate_xy` in `validation/montage_topology.py`.
  - Legacy `triangulate_xy` forwards raw floating-point arrays directly into `scipy.spatial.Delaunay` without input validation or geometric embedding auditing.
  - Collinear inputs and duplicate coincident points trigger unhandled `QhullError` crashes with raw C stdout dumps.
  - No production planar embedding validator exists in `origin/main` or active PRs. Dedicated production implementation remains absent/blocked.

---

## 2. Mathematical Separation: Algebraic Topology vs. Geometric Embedding

### 2.1 Simplicial Boundary Identity ($\partial_1 \partial_2 = 0$)
In algebraic topology, for any oriented abstract simplicial 2-complex:
$$\partial_2 [v_0, v_1, v_2] = [v_1, v_2] - [v_0, v_2] + [v_0, v_1]$$
$$\partial_1 [u, v] = v - u$$
The composite operator $\partial_1 \circ \partial_2 = 0$ is an algebraic identity:
$$\partial_1([v_1, v_2] - [v_0, v_2] + [v_0, v_1]) = (v_2 - v_1) - (v_2 - v_0) + (v_1 - v_0) = 0$$
In matrix form:
$$B_1 B_2 = 0 \quad (\text{or } D_1 D_0 = 0)$$
**Crucial Finding:** This identity holds identically even for geometrically invalid meshes where faces overlap, edges cross, and boundaries mismatch. Satisfying $\partial_1 \partial_2 = 0$ is purely combinatorial and provides **zero guarantee** of geometric embedding validity in $\mathbb{R}^2$.

### 2.2 Delaunay Incircle Condition vs. Planar Triangulation
- A planar triangulation of a point set $P$ is a collection of triangles whose union equals the convex hull $\text{CH}(P)$, whose vertices are $P$, and whose relative interiors are pairwise disjoint.
- Delaunay triangulation imposes an additional empty-circumcircle criterion (maximizing the minimum interior angle).
- As proven by `test_delaunay_condition_independence` (`non_delaunay_valid_fixture`), a 100% valid planar triangulation can violate the Delaunay circumcircle test. Delaunay is an optimization policy, not a basic planar embedding axiom.

---

## 3. Adversarial Fixtures & Counterexamples

### 3.1 Counterexample A: Square + Interior Vertex
- **Coordinates:** $V_0=(0,0), V_1=(1,0), V_2=(1,1), V_3=(0,1), V_4=(0.5, 0.5)$.
- **Convex Hull:** Area $= 1.0$, boundary vertices $= \{0, 1, 2, 3\}$, extreme edges $= 4$.
- **Adversarial Failure Modes:**
  1. *Partial Fixture A1:* Triangles $[0, 1, 4], [1, 2, 4], [2, 3, 4]$ (omitting $[3, 0, 4]$).
     - Sum of triangle areas: $0.25 \times 3 = 0.75 \ne 1.0$ (fails area partition).
     - Boundary incidence-1 edges: $\{(0,1), (1,2), (2,3), (0,4), (3,4)\}$ (fails boundary match with hull).
     - Uncovered region: triangle $[3, 0, 4]$.
     - Result: REJECTED.
  2. *Omitted Vertex Fixture A2:* Triangles $[0, 1, 2], [0, 2, 3]$ (ignoring interior vertex 4).
     - Area sum $= 1.0$ and boundary edges match hull, BUT vertex 4 is unreferenced.
     - Result: REJECTED (`all_input_points_covered` is False, Euler count for $V=5$ fails).
  3. *Valid Triangulation:* 4-triangle fan $(0,1,4), (1,2,4), (2,3,4), (3,0,4)$ passes all 14 geometric axioms.

### 3.2 Counterexample B: Revision 8 Overlapping Mesh
- **Coordinates:** Unit square $V_0=(0,0), V_1=(1,0), V_2=(1,1), V_3=(0,1)$.
- **Triangles:** $[(0, 1, 2), (0, 1, 3)]$.
- **Weak Heuristics That Misleadingly Pass:**
  1. *Positive Areas:* Both triangles have positive signed area $+0.5$.
  2. *Area Sum Identity:* $\sum \text{Area}(T_i) = 0.5 + 0.5 = 1.0 = \text{Area}(\text{ConvexHull})$.
  3. *Euler Counts:* $V=4, B=4 \implies E = 3(4)-7 = 5$, $F = 2(4)-6 = 2$. Exactly matches observed counts ($E=5, F=2$).
  4. *Edge Incidences:* Shared edge $(0,1)$ has incidence 2; edges $(1,2), (2,0), (1,3), (3,0)$ have incidence 1. All incidences $\in \{1, 2\}$.
  5. *Inferred Boundary Shoelace:* Boundary vertices $\{0, 1, 2, 3\}$ angularly sorted around centroid $(0.5, 0.5)$ yield polygon $(0, 1, 2, 3)$ with Shoelace area $1.0$.
  6. *Algebraic Boundary Identity:* $B_1 B_2 = 0$ holds identically.
- **Embedding Axioms That Fail (Correctly Detected by Oracle):**
  1. *Edge Crossings:* Diagonal $(0, 2)$ crosses diagonal $(1, 3)$ at $(0.5, 0.5)$ (`noncrossing_edges` is False).
  2. *Triangle Overlap:* Triangles $(0, 1, 2)$ and $(0, 1, 3)$ overlap on interior region of area $0.25$ (`nonoverlapping_triangles` is False).
  3. *Boundary Mismatch:* Incidence-1 edges are $\{(1, 2), (2, 0), (1, 3), (3, 0)\}$ instead of true hull edges $\{(0, 1), (1, 2), (2, 3), (3, 0)\}$ (`boundary_matches_independent_hull` is False).
  4. *Uncovered Region:* Triangle $[1, 2, 3]$ is empty.
  - Result: REJECTED.

### 3.3 Limits of Finite Jitter vs. Exact Simulation of Simplicity (SoS)
- Finite float jitter (e.g. adding $\pm 10^{-10}$ to IEEE 754 coordinates) fails under translation:
  - At coordinates $x \ge 2^{30} \approx 1.07 \times 10^9$, $1 \text{ ULP} = 2^{30} \times 2^{-52} \approx 2.38 \times 10^{-7}$.
  - In IEEE 754 float64, $2^{30} + 10^{-10} == 2^{30}$ exactly (difference is $0.0$).
  - Jitter is completely eliminated by floating-point roundoff, proving that finite float jitter cannot substitute for exact symbolic perturbation (Simulation of Simplicity).
- Cocircular point sets (e.g. 4 square vertices) have exact zero incircle determinant:
  - Delaunay diagonal choice is ambiguous.
  - Implementations must either reject ambiguous cocircular inputs or enforce a documented, deterministic tie-breaking policy.

---

## 4. Test Suite Summary (`tests/experimental/test_planar_triangulation.py`)

The test suite runs 30 unit and adversarial tests covering:
1. `TestInvalidInputs` (fewer than 3 points, non-finite NaN/inf, coincident duplicates, collinear points, near-degenerate collinearity).
2. `TestCocircularPolicyAndJitterLimits` (cocircular determinant zero, diagonal tie policy, ULP jitter erasure under translation).
3. `TestCounterexampleASquarePlusInteriorVertex` (exact arithmetic, valid mesh, partial fixture A1 rejection, omitted vertex A2 rejection).
4. `TestCounterexampleBRevision8OverlappingFaces` (recomputation of passing weak heuristics vs failure of geometric embedding).
5. `TestTopologicalBoundaryVsGeometricEmbedding` ($B_1 B_2 == 0$ on invalid complexes, incidence-1 edge equality with convex hull cycle).
6. `TestDelaunayConditionIndependence` (valid planar triangulation failing empty circumcircle).
7. `TestScaleAndTranslationInvariance` (invariance under extreme scale $10^{-20}$ to $10^{20}$ and translations $2^{30}$).
8. `TestCandidateProductionTriangulatorAudit` (QhullError crashes on duplicate/collinear inputs, absence of production embedding validator).

All 30 tests execute cleanly and pass via pytest.
