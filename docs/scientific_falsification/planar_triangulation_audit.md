# Planar Triangulation and Embedding Validity Audit (Batch 2 / Antigravity Agent A)

**Status:** HOLD / SYNTHETIC_ONLY<br/>
**Branch:** `batch2/antigravity-a-planar-triangulation`<br/>
**Base Commit:** `f6951115bcbf83b75bf20481085a5dad9c25c7e6` (`origin/main`)<br/>
**Candidate PR #416 Commit:** `04d5af7321ff002bb88d75353e59aec73eabbf56` (`batch2/cursor-a-planar-triangulation`)<br/>
**Scope:** Independent adversarial test surface for planar sensor triangulation and embedding validity (`tests/experimental/test_planar_triangulation.py` and `tests/experimental/planar_mesh_test_helpers.py`).

---

## 1. Executive Summary & Project Posture

- **Project Posture:** `HOLD / SYNTHETIC_ONLY`. The tests in this suite establish geometric and topological properties of 2D sensor-coordinate planar meshes. They do not establish cortical topology, functional localization, or scientific/consciousness claims.
- **Gemini Revision 8 Status:** Treated strictly as unverified research input, not mathematical ground truth.
- **Candidate PR #416 Integration:**
  - Audited and executed directly against PR #416's candidate production module (`neurotopology_sim/experimental/geometry/planar_triangulation.py` at commit `04d5af7321ff002bb88d75353e59aec73eabbf56`).
  - No mocks, stubs, or local replacement validators were used for candidate tests.
  - Candidate implements exact-sign predicates on IEEE-754 binary floats via `Fraction.from_float`, separating `input_validation`, `abstract_chain`, `planar_hull_triangulation`, and `delaunay_empty_circle` diagnostic layers.
  - Candidate v3/v4 (`e4a44f6`, `04d5af7`) introduces the `FailureKind` enum (`MALFORMED_INPUT`, `INVALID_PLANAR_EMBEDDING`, `DELAUNAY_POLICY_FAILURE`, `NONE`), top-level `failure_kind` attribute on `PlanarTriangulationResult`, structured vertex-on-open-edge / T-junction detection (`edge_touch`), and unified out-of-range index diagnostics matching adversarial parity.

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

**Crucial Finding:** This identity holds identically even for geometrically invalid meshes where faces overlap, edges cross, and boundaries mismatch. Satisfying $\partial_1 \partial_2 = 0$ is purely combinatorial and provides **zero guarantee** of geometric planar embedding validity in $\mathbb{R}^2$. Both Counterexample A and Counterexample B satisfy $D_1 @ D_0 == 0$ with `status="holds"`, but are correctly rejected by the candidate's planar layer for geometric defects.

### 2.2 Delaunay Incircle Condition vs. Planar Triangulation
- A planar triangulation of a point set $P$ is a collection of triangles whose union equals the convex hull $\text{CH}(P)$, whose vertices are $P$, and whose relative interiors are pairwise disjoint.
- Delaunay triangulation imposes an additional empty-circumcircle criterion.
- As proven by `test_delaunay_condition_independence` (`non_delaunay_valid_fixture`), a 100% valid planar triangulation can violate the Delaunay circumcircle test. Delaunay is an optimization criterion, not a basic planar embedding axiom.

---

## 3. Adversarial Fixtures & Exact Rational Verification

### 3.1 Counterexample A: 5-Vertex Square with Interior Vertex $(2, 1)$
- **Coordinates:** $V_0=(0,0), V_1=(4,0), V_2=(4,4), V_3=(0,4), V_4=(2,1)$.
- **Triangles:** $(0,1,2), (0,1,4), (1,2,4), (0,4,3)$.
- **Exact Rational Arithmetic:**
  - Triangle CCW areas:
    - $\text{Area}(0,1,2) = 8$
    - $\text{Area}(0,1,4) = 2$
    - $\text{Area}(1,2,4) = 4$
    - $\text{Area}(0,4,3) = 4$
  - All 4 triangles are strictly CCW with positive areas: `[Fraction(8), Fraction(2), Fraction(4), Fraction(4)]`.
  - Hull area of $[0,4] \times [0,4]$ square is 16.
  - Rational area sum: $8 + 2 + 4 + 4 = 18$.
  - **Analysis of Prompt Specification:** The prompt states "Verify positive areas and total area 16, then assert rejection for the actual geometric/mesh defect." The square convex hull area is indeed 16, but programmatically evaluating the declared triangles with exact rational arithmetic reveals an area sum of 18. This disparity occurs because triangles $(0,1,4)$ (area 2) and $(1,2,4)$ (area 4) are strictly contained inside triangle $(0,1,2)$ (area 8), creating internal double-coverage. This precisely illustrates why hand-written area claims must be verified with exact rational arithmetic.
  - Exact pairwise overlaps against triangle $(0,1,2)$:
    - $\text{Area}((0,1,4) \cap (0,1,2)) = 2$ (fully interior)
    - $\text{Area}((1,2,4) \cap (0,1,2)) = 4$ (fully interior)
    - $\text{Area}((0,4,3) \cap (0,1,2)) = \frac{4}{5}$ (crosses hypotenuse $y=x$)
  - Exact crossing intersection: segment $(2,1) \to (0,4)$ crosses diagonal $(0,0) \to (4,4)$ at exact rational coordinates $(\frac{8}{5}, \frac{8}{5})$ ($t = \frac{1}{5}, u = \frac{2}{5}$).
  - Simplicial boundary identity $D_1 @ D_0 == 0$ holds identically.
- **Candidate Validator Verdict:** REJECTED (`ok=False`, `status="rejected"`, `failure_kind="invalid_planar_embedding"`).
  - Flags overlapping triangle pairs: $(0,1,4)$ and $(1,2,4)$ inside $(0,1,2)$.
  - Flags nonincident edge crossings: edge $(0,2)$ crosses $(1,4)$ at $(2,1)$, and edge $(4,3)$ crosses $(0,2)$ at $(8/5, 8/5)$.
  - Flags boundary edge mismatch: hull edges $(0,1)$ and $(1,2)$ have incidence 2 instead of 1, and hull edge $(2,3)$ is unreferenced.

### 3.2 Counterexample B: 5-Vertex Square with Interior Vertex $(3, 1)$
- **Coordinates:** $V_0=(0,0), V_1=(4,0), V_2=(4,4), V_3=(0,4), V_4=(3,1)$.
- **Triangles:** $(0,1,3), (0,1,4), (1,2,4), (2,0,4)$.
- **Exact Arithmetic:**
  - Triangle CCW areas: $8, 2, 2, 4 \implies \text{Sum} = 16 = \text{Area of square hull}$.
  - Counts: 5 vertices, 4 faces, 8 unique edges.
  - All edge incidences are in $\{1, 2\}$, and incidence-1 vertices are exactly $\{0, 1, 2, 3\}$.
  - Simplicial boundary identity $D_1 @ D_0 == 0$ holds identically.
- **Exact Pairwise Overlaps & Uncovered Area:**
  - $\text{Area}((0,1,4) \cap (0,1,3)) = 2$ (triangle $(0,1,4)$ fully inside $(0,1,3)$).
  - $\text{Area}((2,0,4) \cap (0,1,3)) = 2$ (overlap region inside $(0,1,3)$).
  - All other 4 triangle pairs have zero mutual interior overlap.
  - Total overlap area: $2 + 2 = 4$.
  - Total union area covered: $\sum \text{areas} - \text{overlap} = 16 - 4 = 12$.
  - Uncovered area: $\text{Area}(\text{Hull}) - \text{Union} = 16 - 12 = 4$.
- **Geometric Embedding Failures:**
  - Non-incident edges $(1, 3)$ and $(2, 0)$ cross at $(2, 2)$ ($t=1/2, u=1/2$).
  - Triangle interiors overlap (overlap area $4$).
  - Boundary edges $\{(1,3), (3,0), (1,2), (2,0)\}$ do not match the convex hull cycle.
- **Candidate Validator Verdict:** REJECTED (`ok=False`, `status="rejected"`, `failure_kind="invalid_planar_embedding"`).

### 3.3 Exact Segment Intersection Derivation
For line-segment parametric forms:
$$P(t) = S + t(E - S) \quad \text{and} \quad Q(u) = C_1 + u(C_2 - C_1)$$
The exact parameter $t$ is:
$$t = \frac{\text{orient2d}(C_1, C_2, S)}{\text{orient2d}(C_1, C_2, S) - \text{orient2d}(C_1, C_2, E)}$$
Verified on canonical crossing segment $S=(0, -1) \to E=(0, 1)$ against clip line $C_1=(0, 0) \to C_2=(1, 0)$:
- $\text{orient2d}(C_1, C_2, S) = -1$
- $\text{orient2d}(C_1, C_2, E) = +1$
- $t = \frac{-1}{-1 - 1} = \frac{1}{2}$
- $P(1/2) = (0, 0)$ with $u = 0$.

### 3.4 Limits of Finite Jitter vs. Exact Simulation of Simplicity (SoS)
- Finite float jitter ($\pm 10^{-10}$) fails under translation:
  - At coordinates $x \ge 2^{30} \approx 1.07 \times 10^9$, $1 \text{ ULP} = 2^{30} \times 2^{-52} \approx 2.38 \times 10^{-7}$.
  - In IEEE 754 float64, $2^{30} + 10^{-10} == 2^{30}$ exactly (difference is $0.0$).
  - Jitter is completely eliminated by floating-point roundoff, proving that finite float jitter cannot substitute for exact symbolic perturbation (Simulation of Simplicity).

---

## 4. Input & Simplex Index Validation Hardening (PR #416 v2 & v3)

In commits `88b21ccd` and `e4a44f6e`, Cursor Agent A hardened simplex index parsing, coordinate validation, and failure classification:
- **`FailureKind` Structured Classification (v3):**
  - Rejections carry an explicit `failure_kind`: `MALFORMED_INPUT`, `INVALID_PLANAR_EMBEDDING`, or `DELAUNAY_POLICY_FAILURE`.
  - Non-failing results return `FailureKind.NONE`.
- **Simplex Index Rejection Before Array Indexing:**
  - Float indices (e.g. `(0.9, 1.0, 2.0)`): rejected (`floating-point simplex index is not allowed`, `failure_kind=malformed_input`).
  - Boolean indices (e.g. `(True, 1, 2)`): rejected (`boolean is not a valid simplex index`, `failure_kind=malformed_input`).
  - Repeated vertices (e.g. `(0, 0, 1)`): rejected (`repeated vertices are not allowed`, `failure_kind=malformed_input`).
  - Negative indices (e.g. `(-1, 0, 1)`): rejected (`negative simplex index`, `failure_kind=malformed_input`).
  - Out-of-range indices (e.g. `(0, 1, 99)`): rejected (`out-of-range index 99 for n_points`, `failure_kind=malformed_input`).
  - All malformed indices return a structured rejection in `validate_planar_mesh` without unhandled `IndexError` exception crashes or negative index wraparound.
- **T-Junction & Vertex-on-Edge Detection (v3):**
  - Vertices lying on open edges of triangles (e.g. `(1,0)` on edge `(0,0)-(2,0)`) are detected and rejected (`failure_kind=invalid_planar_embedding`).
  - T-junction configurations without matching edge subdivision are rejected.
- **NumPy Coordinate Array Acceptance:**
  - 2D NumPy arrays of shape `(n, 2)` are accepted and validated directly.
  - Malformed shapes (`(3, 3)` or 1D arrays) return structured rejections (`failure_kind=malformed_input`).
- **Non-Finite Coordinates:**
  - Coordinates with `NaN`, `+Inf`, or `-Inf` return structured rejections (`failure_kind=malformed_input`).
- **Cocircular Policy Separation (Delaunay Enabled vs. Disabled):**
  - `triangulate_2d` with `require_delaunay=False, degeneracy_policy="reject"`: accepts cocircular point sets as valid planar triangulations.
  - `triangulate_2d` with `require_delaunay=True, degeneracy_policy="reject"`: rejects represented cocircularity (`failure_kind=delaunay_policy_failure`).
  - `triangulate_2d` with `require_delaunay=True, degeneracy_policy="lexicographic_tiebreak"`: accepts via deterministic tie-breaking.

---

## 5. CI Discovery & Required Checks

- **CI Workflow Audit:**
  - `.github/workflows/required-checks.yml`: runs an explicit batch of core tests (`scripts/run_tests_isolated.py` with 9 specific files under `tests/`).
  - `.github/workflows/ci.yml`: runs explicit batches for core and optional EEG profiles.
  - **Discovery Status:** Neither workflow executes test files under `tests/experimental/` or `tests/neurotopology_sim/experimental/`.
  - **Workflow Owner:** Repository maintainers / CI owners.
  - **Action Taken:** Per instructions ("Do not modify CI workflows"), this test-only agent does not edit workflow files. CI maintainers should add `tests/experimental/test_planar_triangulation.py` and `tests/neurotopology_sim/experimental/geometry/test_planar_triangulation.py` to the core suite invocation.

---

## 6. Test Suite Verification & Merge Readiness

- **Focused Test Execution:**
  - `pytest tests/experimental/test_planar_triangulation.py -v`: 36 passed.
  - Combined suite (`tests/neurotopology_sim/experimental/geometry/` + `tests/experimental/`): 64 passed in 40.53s (36 adversarial + 28 candidate).
- **Git Hygiene:** `git diff --check` clean (0 warnings, 0 whitespace errors).
- **Merge Disposition:** Candidate PR #416 successfully passes all 36 adversarial tests and all 28 candidate tests. PR #421 is merge-ready for review. In accordance with project instructions and branch protection policies, PR #421 remains open and is NOT merged into `origin/main`.
