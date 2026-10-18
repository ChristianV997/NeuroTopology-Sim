# Planar Triangulation and Embedding Validity Audit (Batch 2 / Antigravity Agent A)

**Status:** HOLD / SYNTHETIC_ONLY<br/>
**Branch:** `batch2/antigravity-a-planar-triangulation`<br/>
**Base Commit:** `19c3203573082f8bc41f7da226b52dc20a49fdb0` (`origin/main`)<br/>
**Candidate PR #416 Commit:** `88b21ccd22576939f88865cc4cf20f788cbbf1b4` (`batch2/cursor-a-planar-triangulation`)<br/>
**Scope:** Independent adversarial test surface for planar sensor triangulation and embedding validity (`tests/experimental/test_planar_triangulation.py` and `tests/experimental/planar_mesh_test_helpers.py`).

---

## 1. Executive Summary & Project Posture

- **Project Posture:** `HOLD / SYNTHETIC_ONLY`. The tests in this suite establish geometric and topological properties of 2D sensor-coordinate planar meshes. They do not establish cortical topology, functional localization, or scientific/consciousness claims.
- **Gemini Revision 8 Status:** Treated strictly as unverified research input, not mathematical ground truth.
- **Candidate PR #416 Integration:**
  - Audited and executed directly against PR #416's candidate production module (`neurotopology_sim/experimental/geometry/planar_triangulation.py` at commit `88b21ccd22576939f88865cc4cf20f788cbbf1b4`).
  - No mocks, stubs, or local replacement validators were used for candidate tests.
  - Candidate implements exact-sign predicates on IEEE-754 binary floats via `Fraction.from_float`, separating `input_validation`, `abstract_chain`, `planar_hull_triangulation`, and `delaunay_empty_circle` diagnostic layers.

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
  - Simplicial boundary identity $D_1 @ D_0 == 0$ holds identically.
- **Candidate Validator Verdict:** REJECTED (`ok=False`, `status="rejected"`).
  - Flags overlapping triangle pairs: $(0,1,4)$ and $(1,2,4)$ inside $(0,1,2)$.
  - Flags nonincident edge crossings: edge $(0,2)$ crosses $(1,4)$ at $(2,1)$.
  - Flags boundary edge mismatch: hull edges $(0,1)$ and $(1,2)$ have incidence 2 instead of 1, and hull edge $(2,3)$ is unreferenced.

### 3.2 Counterexample B: 5-Vertex Square with Interior Vertex $(3, 1)$
- **Coordinates:** $V_0=(0,0), V_1=(4,0), V_2=(4,4), V_3=(0,4), V_4=(3,1)$.
- **Triangles:** $(0,1,3), (0,1,4), (1,2,4), (2,0,4)$.
- **Exact Arithmetic:**
  - Triangle CCW areas: $8, 2, 2, 4 \implies \text{Sum} = 16 = \text{Area of square hull}$.
  - Counts: 5 vertices, 4 faces, 8 unique edges.
  - All edge incidences are in $\{1, 2\}$, and incidence-1 vertices are exactly $\{0, 1, 2, 3\}$.
  - Simplicial boundary identity $D_1 @ D_0 == 0$ holds identically.
- **Geometric Embedding Failures:**
  - Non-incident edges $(1, 3)$ and $(2, 0)$ cross at $(2, 2)$.
  - Triangle interiors overlap (e.g. $(0,1,4)$ inside $(0,1,3)$ with overlap area $2$).
  - Boundary edges $\{(1,3), (3,0), (1,2), (2,0)\}$ do not match the convex hull cycle.
- **Candidate Validator Verdict:** REJECTED (`ok=False`, `status="rejected"`).

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

## 4. Input & Simplex Index Validation Hardening (PR #416 v2)

In commit `88b21ccd22576939f88865cc4cf20f788cbbf1b4`, Cursor Agent A hardened simplex index parsing and coordinate validation:
- **Simplex Index Rejection Before Array Indexing:**
  - Float indices (e.g. `(0.9, 1.0, 2.0)`): rejected (`floating-point simplex index is not allowed`).
  - Boolean indices (e.g. `(True, 1, 2)`): rejected (`boolean is not a valid simplex index`).
  - Repeated vertices (e.g. `(0, 0, 1)`): rejected (`repeated vertices are not allowed`).
  - Negative indices (e.g. `(-1, 0, 1)`): rejected (`negative simplex index`).
  - Out-of-range indices (e.g. `(0, 1, 99)`): rejected (`out of range for n_points`).
  - All malformed indices return a structured rejection in `validate_planar_mesh` without unhandled `IndexError` exception crashes or negative index wraparound.
- **NumPy Coordinate Array Acceptance:**
  - 2D NumPy arrays of shape `(n, 2)` are accepted and validated directly.
  - Malformed shapes (`(3, 3)` or 1D arrays) return structured rejections.
- **Non-Finite Coordinates:**
  - Coordinates with `NaN`, `+Inf`, or `-Inf` return structured rejections.
- **Cocircular Policy Separation (Delaunay Enabled vs. Disabled):**
  - `triangulate_2d` with `require_delaunay=False, degeneracy_policy="reject"`: accepts cocircular point sets as valid planar triangulations.
  - `triangulate_2d` with `require_delaunay=True, degeneracy_policy="reject"`: rejects represented cocircularity.
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
  - `pytest tests/experimental/test_planar_triangulation.py -v`: 34 passed in 3.30s.
  - Combined suite (`tests/neurotopology_sim/experimental/geometry/` + `tests/experimental/`): 57 passed in 3.78s.
- **Git Hygiene:** `git diff --check` clean (0 warnings, 0 whitespace errors).
- **Merge Disposition:** Candidate PR #416 successfully passes all 34 adversarial tests and all 23 candidate tests. PR #421 is merge-ready for review. In accordance with project instructions and branch protection policies, PR #421 remains open and is NOT merged into `origin/main`.
