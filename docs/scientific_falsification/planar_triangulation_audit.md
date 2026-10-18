# Planar Triangulation and Embedding Validity Audit (Batch 2 / Antigravity Agent A)

**Status:** HOLD / SYNTHETIC_ONLY
**Branch:** `batch2/antigravity-a-planar-triangulation`
**Base Commit:** `19c3203573082f8bc41f7da226b52dc20a49fdb0` (`origin/main`)
**Candidate PR #416 Commit:** `0eec157b9f20ba088ebf31ddbabf05b7c5ee0fcf` (`batch2/cursor-a-planar-triangulation`)
**Scope:** Independent adversarial test surface for planar sensor triangulation and embedding validity (`tests/experimental/test_planar_triangulation.py` and `tests/experimental/planar_mesh_test_helpers.py`).

---

## 1. Executive Summary & Project Posture

- **Project Posture:** HOLD / SYNTHETIC_ONLY. The tests in this suite establish geometric and topological properties of 2D sensor-coordinate planar meshes. They do not establish cortical topology, functional localization, or scientific/consciousness claims.
- **Gemini Revision 8 Status:** Treated strictly as unverified research input, not mathematical ground truth.
- **Candidate PR #416 Integration:**
  - Audited and executed directly against PR #416's candidate production module (`neurotopology_sim/experimental/geometry/planar_triangulation.py`).
  - No mocks or local replacement validators were used for candidate tests.
  - Candidate implements exact-sign predicates on IEEE-754 binary floats via `Fraction.from_float`, separating `abstract_chain`, `planar_hull_triangulation`, and `delaunay_empty_circle` diagnostic layers.

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
**Crucial Finding:** This identity holds identically even for geometrically invalid meshes where faces overlap, edges cross, and boundaries mismatch. Satisfying $\partial_1 \partial_2 = 0$ is purely combinatorial and provides **zero guarantee** of geometric planar embedding validity in $\mathbb{R}^2$. Both Counterexample B and the Mandatory Counterexample satisfy $D_1 @ D_0 == 0$ with `status="holds"`, but are correctly rejected by the candidate's planar layer.

### 2.2 Delaunay Incircle Condition vs. Planar Triangulation
- A planar triangulation of a point set $P$ is a collection of triangles whose union equals the convex hull $\text{CH}(P)$, whose vertices are $P$, and whose relative interiors are pairwise disjoint.
- Delaunay triangulation imposes an additional empty-circumcircle criterion.
- As proven by `test_delaunay_condition_independence` (`non_delaunay_valid_fixture`), a 100% valid planar triangulation can violate the Delaunay circumcircle test. Delaunay is an optimization criterion, not a basic planar embedding axiom.

---

## 3. Adversarial Fixtures & Counterexamples

### 3.1 Mandatory Full-Validator Counterexample
- **Coordinates:** $V_0=(0,0), V_1=(4,0), V_2=(4,4), V_3=(0,4), V_4=(3,1)$.
- **Triangles:** $(0,1,3), (0,1,4), (1,2,4), (2,0,4)$.
- **Exact Arithmetic:**
  - Triangle CCW areas: $8, 2, 2, 4 \implies \text{Sum} = 16 = \text{Area of square hull}$.
  - Counts: 5 vertices, 4 faces, 8 unique edges.
  - All edge incidences are in $\{1, 2\}$, and incidence-1 vertices are exactly $\{0, 1, 2, 3\}$.
- **Geometric Embedding Failures (Detected by Validator):**
  - Non-incident edges $(1, 3)$ and $(2, 0)$ cross at $(2, 2)$.
  - Triangle interiors overlap (e.g. $(0,1,4)$ is completely inside $(0,1,3)$ with overlap area $2$; $(2,0,4)$ overlaps $(0,1,3)$ with overlap area $2$).
  - Boundary edges $\{(1,3), (3,0), (1,2), (2,0)\}$ do not equal the convex hull cycle $\{(0,1), (1,2), (2,3), (3,0)\}$.
- **Candidate Validator Verdict:** REJECTED (`ok=False`, `status="rejected"`). `abstract_chain` holds ($D_1 @ D_0 == 0$), while `planar_hull_triangulation` fails.

### 3.2 Exact Segment Intersection Derivation
For line-segment parametric forms:
$$P(t) = S + t(E - S) \quad \text{and} \quad Q(u) = C_1 + u(C_2 - C_1)$$
The exact parameter $t$ is:
$$t = \frac{\text{orient2d}(C_1, C_2, S)}{\text{orient2d}(C_1, C_2, S) - \text{orient2d}(C_1, C_2, E)}$$
Verified on canonical crossing segment $S=(0, -1) \to E=(0, 1)$ against clip line $C_1=(0, 0) \to C_2=(1, 0)$:
- $\text{orient2d}(C_1, C_2, S) = -1$
- $\text{orient2d}(C_1, C_2, E) = +1$
- $t = \frac{-1}{-1 - 1} = \frac{1}{2}$
- $P(1/2) = (0, 0)$ with $u = 0$.

### 3.3 Counterexample A: Square + Interior Vertex $(0.5, 0.5)$
- Partial fixture A1 (omitting $[3, 0, 4]$) is rejected: face area sum $0.75 \ne 1.0$, boundary incidence-1 edges fail to match the convex hull cycle.
- Omitted vertex fixture A2 (triangulating hull only) is rejected: interior vertex 4 is unreferenced (`uncovered input points: [4]`).
- Valid 4-triangle fan passes all checks.

### 3.4 Counterexample B: Revision 8 Overlapping Mesh
- Unit square vertices with triangles $[(0, 1, 2), (0, 1, 3)]$.
- Satisfies naive heuristics: positive areas, area sum $= 1.0$, Euler count $E=5, F=2$, edge incidences in $\{1, 2\}$, angular-sorted boundary Shoelace area $= 1.0$, and $B_1 B_2 == 0$.
- Correctly rejected by candidate validator due to diagonal crossing $(0, 2) \times (1, 3)$ at $(0.5, 0.5)$, interior overlap, and boundary mismatch.

### 3.5 Limits of Finite Jitter vs. Exact Simulation of Simplicity (SoS)
- Finite float jitter ($\pm 10^{-10}$) fails under translation:
  - At coordinates $x \ge 2^{30} \approx 1.07 \times 10^9$, $1 \text{ ULP} = 2^{30} \times 2^{-52} \approx 2.38 \times 10^{-7}$.
  - In IEEE 754 float64, $2^{30} + 10^{-10} == 2^{30}$ exactly (difference is $0.0$).
  - Jitter is completely eliminated by floating-point roundoff, proving that finite float jitter cannot substitute for exact symbolic perturbation (Simulation of Simplicity).

---

## 4. Input & Simplex Index Validation Behavior

- **Float & Boolean Simplex Indices:** Candidate validator coerces via `int(t[0])`, truncating floats (e.g. `(0.9, 1.9, 2.9) -> (0, 1, 2)`) and converting booleans (`(True, False, 2) -> (1, 0, 2)`).
- **Repeated Indices:** Rejected (`triangle 0 is degenerate in indices`).
- **Negative Indices:** Rejected (`triangle 0 has out-of-range index`).
- **Out-of-Range Indices:** Calling `validate_planar_mesh` with out-of-range indices like `(0, 1, 99)` triggers an `IndexError` in `_canonicalize_ccw`, identifying an uncaught exception boundary prior to layer diagnostics.
- **NumPy Sequence Contract:** Candidate `_parse_coords` strictly requires `isinstance(coords, (list, tuple))`. Raw NumPy arrays for `coords` return `status="rejected"` with `coords must be a sequence of 2D points` unless converted via `.tolist()`.
- **Cocircular Policy Outcomes:**
  - `check_delaunay=False`: accepted.
  - `check_delaunay=True, degeneracy_policy="reject"`: rejected (`2 exact cocircular incident(s); degeneracy_policy=reject`).
  - `check_delaunay=True, degeneracy_policy="lexicographic_tiebreak"`: accepted with deterministic tie-breaking.

---

## 5. Test Suite Verification & Merge Readiness

- **Focused Test Execution:**
  - `pytest tests/experimental/test_planar_triangulation.py -v`: 30 passed in 3.98s.
  - Combined suite (`tests/neurotopology_sim/experimental/geometry/` + `tests/experimental/`): 42 passed in 6.44s.
- **Merge Readiness:** Candidate PR #416 successfully passes all adversarial tests. PR #421 is merge-ready for peer review. In accordance with instructions, PR #421 is NOT merged into main.
