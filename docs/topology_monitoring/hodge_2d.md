# Weighted 2D Discrete Hodge-Helmholtz Decomposition

Status: **HOLD / SYNTHETIC_ONLY**
Module: `neurotopology_sim.experimental.topology.hodge_2d`
Tests: `tests.neurotopology_sim.experimental.topology.test_hodge_2d`

---

## 1. Scope & Guardrails

This document specifies the production implementation of the weighted discrete
Hodge-Helmholtz decomposition on oriented 2-dimensional cell/simplicial complexes.

### Guardrails and Non-Claims
- **No clinical claims**: This module computes an algebraic and numerical decomposition
  on oriented 2-complexes; it does NOT constitute clinical evidence or diagnostics.
- **No biological ontology promotion**: Decomposed components (exact, coexact, harmonic)
  are mathematical cochains on a graph/mesh and must NOT be equated with neural
  propagation, macroscopic consciousness fields, or cortical flow.
- **No proof claims**: Gemini Revision 8 and related theoretical proposals are
  treated as unverified working hypotheses. The code implements only discrete exterior
  calculus / algebraic topology identities.
- **HOLD / SYNTHETIC_ONLY posture**: Operates exclusively on synthetic complexes and
  analytic verification fixtures.

---

## 2. Mathematical Formulation

### 2.1 Cochain Complex and Coboundary Operators
Let $C_0, C_1, C_2$ denote the chain spaces of vertices $V$, oriented edges $E$, and
oriented faces $F$. The coboundary operators are:
- $d_0: C^0 \to C^1$ (shape $|E| \times |V|$): maps 0-cochains (vertex potentials)
  to 1-cochains (oriented edge differences).
- $d_1: C^1 \to C^2$ (shape $|F| \times |E|$): maps 1-cochains (edge circulations)
  to 2-cochains (oriented face fluxes).

The fundamental exactness identity is:
$$d_1 @ d_0 = 0$$
The implementation verifies $\|d_1 @ d_0\|_\infty \le \text{atol}$ before any solve
and fails closed with `CochainComplexError` if violated.

### 2.2 1-Cochain Metric $W_1$ & Disclosure
The inner product on edge 1-cochains is induced by a symmetric positive-definite
matrix $W_1$ (shape $|E| \times |E|$) or positive diagonal weights $w_e > 0$:
$$\langle u, v \rangle_{W_1} = u^T W_1 v, \quad \|u\|_{W_1}^2 = u^T W_1 u$$

> **METRIC TYPE DISCLOSURE:**
> Ad hoc diagonal edge weights or arbitrary SPD matrices represent a weighted
> $L_2$ cochain metric (`MetricType.DIAGONAL_L2` or `MetricType.GENERAL_SPD`).
> They must **never** be labeled the "canonical DEC Hodge star" $*_1$. In Discrete
> Exterior Calculus (DEC), the canonical Hodge star $*_1$ requires a well-centered
> primal-dual complex (such as a Delaunay-Voronoi mesh) where diagonal entries
> equal the geometric ratio of dual edge length to primal edge length ($|e^*| / |e|$).

Supported classifications (`MetricType`):
- `DIAGONAL_L2`: Ad hoc positive diagonal weights.
- `GENERAL_SPD`: Full symmetric positive-definite metric matrix.
- `BARYCENTRIC_LUMPED`: Lumped dual-to-primal metric ratio from barycentric dual.
- `CIRCUMCENTRIC_DEC`: True circumcentric DEC Hodge star ($*_1 = |e^*|/|e|$),
  strictly requiring well-centered Delaunay dual geometry.

### 2.3 Hodge-Helmholtz Decomposition
Any 1-cochain $\omega \in \mathbb{R}^{|E|}$ admits an orthogonal decomposition:
$$\omega = \omega_{\text{exact}} + \omega_{\text{coexact}} + \omega_{\text{harm}}$$

1. **Exact Component** ($\omega_{\text{exact}} = d_0 \alpha$):
   The potential $\alpha \in \mathbb{R}^{|V|}$ satisfies the weighted 0-Laplacian normal equation:
   $$(d_0^T W_1 d_0) \alpha = d_0^T W_1 \omega$$
2. **Coexact Component** ($\omega_{\text{coexact}} = W_1^{-1} d_1^T \gamma$):
   The face potential $\gamma \in \mathbb{R}^{|F|}$ satisfies:
   $$(d_1 W_1^{-1} d_1^T) \gamma = d_1 \omega$$
   Stream function $\beta = W_2^{-1} \gamma$ (if face metric $W_2$ is provided; otherwise $\beta = \gamma$).
3. **Harmonic Component** ($\omega_{\text{harm}} = \omega - \omega_{\text{exact}} - \omega_{\text{coexact}}$):
   Satisfies closedness ($d_1 \omega_{\text{harm}} = 0$) and coclosedness ($d_0^T W_1 \omega_{\text{harm}} = 0$).

---

## 3. Algebraic Orthogonality and Energy Closure

### 3.1 Mutual Orthogonality
Because $d_1 @ d_0 = 0$ identically:
$$\langle \omega_{\text{exact}}, \omega_{\text{coexact}} \rangle_{W_1} = (d_0 \alpha)^T W_1 (W_1^{-1} d_1^T \gamma) = \alpha^T (d_1 d_0)^T \gamma = 0$$
This orthogonality is **algebraically exact** and holds regardless of the choice of
metric $W_1$ or boundary conditions.

Similarly, from the normal equations:
$$\langle \omega_{\text{exact}}, \omega_{\text{harm}} \rangle_{W_1} = \alpha^T (d_0^T W_1 \omega_{\text{harm}}) = 0$$
$$\langle \omega_{\text{coexact}}, \omega_{\text{harm}} \rangle_{W_1} = \gamma^T (d_1 \omega_{\text{harm}}) = 0$$

### 3.2 Total Energy Closure
The energy partitions without cross-terms:
$$\|\omega\|_{W_1}^2 = \|\omega_{\text{exact}}\|_{W_1}^2 + \|\omega_{\text{coexact}}\|_{W_1}^2 + \|\omega_{\text{harm}}\|_{W_1}^2$$
Relative energy error:
$$\text{RelEnergyErr} = \frac{|\|\omega\|_{W_1}^2 - (E_{\text{exact}} + E_{\text{coexact}} + E_{\text{harm}})|}{\|\omega\|_{W_1}^2 + \varepsilon} < 10^{-10}$$

---

## 4. Boundary Conditions and Topological Cases

### 4.1 Boundary Conditions (`BoundaryCondition`)
- `NATURAL` (aliases: `ABSOLUTE`, `FREE`):
  Standard unconstrained decomposition. Potential $\alpha$ satisfies natural
  Neumann boundary conditions on the graph.
- `DIRICHLET_POTENTIAL`:
  Potential $\alpha$ is constrained to zero on boundary vertices $\partial V$.
  Boundary vertices are detected automatically from $(d_0, d_1)$ (edges incident to
  exactly 1 face) or supplied by the caller.

### 4.2 Zero-Interior-Node Complexes
For complexes such as a single triangle or an open fan where every vertex touches
the boundary, the count of interior vertices is zero ($|V \setminus \partial V| = 0$).
When `DIRICHLET_POTENTIAL` is requested on such complexes:
- The system detects `zero_interior_nodes == True`.
- Constrains $\alpha \equiv 0$ on all boundary vertices.
- Yields $\omega_{\text{exact}} \equiv 0$.
- Records `dirichlet_all_boundary: True` in `diagnostics`.
- Avoids empty-matrix solver crashes.

### 4.3 Complexes with Dependent Face Rows (Closed 2-Manifolds)
For closed surfaces (e.g. sphere, torus) or closed 2-cycles:
$$\sum_{f} d_{1, f} = \mathbf{0}$$
The matrix $M = d_1 W_1^{-1} d_1^T$ has $\operatorname{rank}(M) < |F|$ and is singular.
The solver uses rank-revealing minimum-norm pseudoinverse solutions (`np.linalg.lstsq`
with SVD fallback), ensuring stability without division by zero. Diagnostics record:
`dependent_face_rows: True` and the effective rank.

### 4.4 Non-Trivial 1st Homology ($b_1 > 0$)
On complexes with non-contractible 1-cycles (e.g. annulus, circle with hole):
A circulating 1-cochain that is divergence-free ($d_0^T W_1 \omega = 0$) and
curl-free ($d_1 \omega = 0$) cannot be represented as a gradient ($d_0 \alpha$).
The decomposition isolates this circulation purely into $\omega_{\text{harm}}$:
$$E_{\text{harm}} = \|\omega\|_{W_1}^2, \quad E_{\text{exact}} = 0, \quad E_{\text{coexact}} = 0$$

---

## 5. Gauge Invariance

Because the kernel of $d_0$ contains constant potentials on connected components,
$\alpha$ is determined up to an additive constant per component.

Supported policies (`GaugePolicy`):
- `MINIMUM_NORM`: Solves for the minimum Euclidean norm potential $\alpha$.
- `PINNED_VERTEX`: Pins reference vertex $\alpha[0] = 0$.
- `ZERO_MEAN`: Shifts $\alpha$ such that $\sum_v \alpha_v = 0$.

**Gauge Invariance Invariant:**
For all gauge policies, the physical exact 1-cochain is strictly invariant:
$$\omega_{\text{exact}} = d_0 (\alpha + c \mathbf{1}) = d_0 \alpha$$
Verified across all test suites to machine precision ($\Delta < 10^{-12}$).

---

## 6. Numerical Conditioning & Fail-Closed Diagnostics

The effective condition number $\kappa_{\text{eff}}(A) = \sigma_{\max} / \sigma_{\min, > 0}$
is computed for $L_0$ and $M$ over their non-gauge positive spectrum.

Conditioning criteria:
- Non-positive or non-finite weights $\to$ raises `MetricError`.
- Non-symmetric or non-SPD 2D metric $\to$ raises `MetricError`.
- If $\kappa_{\text{eff}} > \text{cond\_reject}$ (default $10^{12}$) or weight ratio
  $\max(w_e)/\min(w_e) > \sqrt{\text{cond\_reject}}$:
  - If `fail_on_ill_conditioned=True` $\to$ raises `IllConditionedMetricError`.
  - If `fail_on_ill_conditioned=False` $\to$ sets `diagnostics["accepted"] = False`
    and `verdict = "REJECTED_ILL_CONDITIONED"`.

---

## 7. Python API Quickstart

```python
import numpy as np
from neurotopology_sim.experimental.topology.hodge_2d import (
    hodge_decompose,
    BoundaryCondition,
    GaugePolicy,
    MetricType,
)

# 1-cochain on edges, coboundary matrices d0, d1, and edge weights
result = hodge_decompose(
    edge_cochain=omega,
    d0=d0,
    d1=d1,
    edge_metric=weights_e,
    boundary_condition=BoundaryCondition.NATURAL,
    gauge=GaugePolicy.MINIMUM_NORM,
)

print("Exact component:", result.exact)
print("Coexact component:", result.coexact)
print("Harmonic component:", result.harmonic)
print("Total energy:", result.energy_total)
print("Reconstruction residual:", result.reconstruction_residual_norm)
print("Orthogonality <exact, coexact>:", result.orthogonality_exact_coexact)
print("Accepted:", result.accepted)
```
