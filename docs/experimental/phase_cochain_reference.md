# Simplicial Phase Cochain and Weighted Hodge Decomposition Reference

This document provides the mathematical specifications, discrete differential geometry foundations, sign conventions, and operational constraints for the experimental simplicial phase cochains and weighted Hodge decomposition reference implementation (`experimental/phase_cochain_reference`).

---

## 1. Operational Scope & Guardrails

> [!IMPORTANT]
> This module is an independent, synthetic experimental reference implementation intended for algebraic topology and discrete exterior calculus validation. It contains no clinical, neurological, or consciousness claims. All calculations operate on discrete simplicial complexes and synthetic phase fields. Status: **HOLD / SYNTHETIC_ONLY**.
>
> **Relation to merged production (#413 / #423):** Production owns
> `neurotopology_sim.experimental.topology.winding` (floor-branch phase winding)
> and `hodge_2d` (weighted Hodge). This package remains useful for
> `SimplicialComplex` builders, dipole/annulus fixtures, and a complex-centric
> reference API. It is **not** a second production engine. Principal-branch
> wrapping here is defined via `wrap_to_pi` (equivalent to
> `n = floor((raw+π)/2π)`), matching production `#413` at half-turn ties.

---

## 2. Simplicial Complex & Discrete Coboundaries

### 2.1 Simplicial Complex Definition
Let $K = (V, E, T)$ be a finite 2-dimensional simplicial complex where:
- $V = \{0, 1, \dots, N-1\}$ is the set of 0-simplices (vertices) with optional spatial embedding coordinates $\mathbf{r}_v \in \mathbb{R}^D$.
- $E \subset V \times V$ is the set of 1-simplices (oriented edges), canonically ordered such that each edge $e = (u, v)$ satisfies $u < v$.
- $T \subset V \times V \times V$ is the set of 2-simplices (oriented triangles), canonically ordered such that each triangle $t = (i, j, k)$ satisfies $i < j < k$.

**Simplicial Closure Requirement**:
For every triangle $t = (i, j, k) \in T$, all three boundary edges must exist in the complex:
$$(i, j) \in E, \quad (j, k) \in E, \quad (i, k) \in E$$
Violations are strictly rejected by the validator with `ValueError`.

### 2.2 Coboundary Operators $d_0$ and $d_1$
The discrete coboundary operators map cochain spaces $d_k: C^k(K) \to C^{k+1}(K)$.

#### 0-Coboundary $d_0 \in \mathbb{R}^{|E| \times |V|}$
For oriented edge $e = (u, v)$ with $u < v$ and 0-cochain $\theta \in C^0(K)$:
$$(d_0 \theta)_e = \theta_v - \theta_u$$
$$[d_0]_{e, v} = +1.0, \quad [d_0]_{e, u} = -1.0, \quad [d_0]_{e, w} = 0.0 \; (\forall w \notin \{u, v\})$$

#### 1-Coboundary $d_1 \in \mathbb{R}^{|T| \times |E|}$
The oriented boundary cycle of a 2-simplex $t = [i, j, k]$ ($i < j < k$) is:
$$\partial_2 t = [j, k] - [i, k] + [i, j]$$
The coboundary operator dual to $\partial_2$ acts on a 1-cochain $\omega \in C^1(K)$ as:
$$(d_1 \omega)_t = \omega_{(j, k)} - \omega_{(i, k)} + \omega_{(i, j)}$$
$$[d_1]_{t, (j, k)} = +1.0, \quad [d_1]_{t, (i, k)} = -1.0, \quad [d_1]_{t, (i, j)} = +1.0$$

### 2.3 Fundamental Topological Exactness: $d_1 d_0 = 0$
For any 0-cochain $\theta$ and any triangle $t = (i, j, k)$:
$$\begin{aligned}
(d_1 (d_0 \theta))_t &= (d_0 \theta)_{(j, k)} - (d_0 \theta)_{(i, k)} + (d_0 \theta)_{(i, j)} \\
&= (\theta_k - \theta_j) - (\theta_k - \theta_i) + (\theta_j - \theta_i) \\
&= \theta_k - \theta_j - \theta_k + \theta_i + \theta_j - \theta_i \\
&= 0
\end{aligned}$$
Thus, $d_1 @ d_0 = 0$ holds identically over both $\mathbb{Z}$ and $\mathbb{R}$.

---

## 3. Phase Cochains & Topological Charge Invariants

### 3.1 Phase Wrapping Function
Angles are mapped to the principal branch $[-\pi, \pi)$ via:
$$\operatorname{wrap}(\phi) = ((\phi + \pi) \pmod{2\pi}) - \pi$$

### 3.2 Wrapped 1-Cochains
Given vertex phases $\theta \in \mathbb{R}^{|V|}$:
1. Unwrapped difference along edges:
   $$\Delta \theta = d_0 \theta \in \mathbb{R}^{|E|}$$
2. Wrapped 1-cochain via principal-value map:
   $$\omega_e = \operatorname{wrap}(\Delta \theta_e) \in [-\pi, \pi)$$
3. Integer branch jumps recovered from the identity $\omega = \Delta\theta - 2\pi n$:
   $$n_e = \operatorname{rint}\left(\frac{\Delta \theta_e - \omega_e}{2\pi}\right) \in \mathbb{Z}$$
This is equivalent to $n_e = \lfloor(\Delta\theta_e+\pi)/(2\pi)\rfloor$ (production `#413`).
Do **not** use bare `round(Δθ/2π)`: NumPy banker's rounding at half-turns leaves $\omega=+\pi\notin[-\pi,\pi)$.

### 3.3 Exact Integer Topological Charge
The circulation around triangle $t$ is $(d_1 \omega)_t$. Substituting $\omega$:
$$d_1 \omega = d_1 (d_0 \theta - 2\pi n) = (d_1 d_0) \theta - 2\pi d_1 n$$
Because $d_1 d_0 = 0$ identically:
$$d_1 \omega = -2\pi d_1 n$$
Dividing by $2\pi$ yields the topological charge vector:
$$q = \frac{1}{2\pi} d_1 \omega = - d_1 n \in \mathbb{Z}^{|T|}$$
Because $n \in \mathbb{Z}^{|E|}$ and $d_1 \in \{-1, 0, 1\}^{|T| \times |E|}$, $q$ is strictly integer-valued.

### 3.4 Orientation Covariance
For an arbitrary triangle ordering $\tau = (\tau_0, \tau_1, \tau_2)$:
- Let $\pi$ be the permutation ordering $\tau$ into canonical order $(i, j, k)$ with $i < j < k$.
- The winding circulation satisfies:
  $$\operatorname{winding}(\tau) = \operatorname{sgn}(\pi) \cdot \operatorname{winding}(i, j, k)$$
- Even (cyclic) permutations preserve winding:
  $$\operatorname{winding}(0, 1, 2) = \operatorname{winding}(1, 2, 0) = \operatorname{winding}(2, 0, 1)$$
- Odd (reversal) permutations invert winding:
  $$\operatorname{winding}(0, 2, 1) = -\operatorname{winding}(0, 1, 2)$$

### 3.5 Confidence Weighting
When face confidence or quality weights $w_t \in (0, 1]$ are provided:
- Weighted scores: $s_t = w_t q_t$.
- **Invariance Rule**: The raw topological integer charge $q_t \in \mathbb{Z}$ is never altered or rounded.

---

## 4. Spatial Moments & Centroids

When vertex embedding coordinates $\mathbf{r}_v \in \mathbb{R}^D$ are available, triangle barycenters are:
$$\mathbf{r}_t = \frac{1}{3} (\mathbf{r}_i + \mathbf{r}_j + \mathbf{r}_k)$$

### 4.1 Charge Quantities
- Net charge: $Q_{\text{net}} = \sum_{t} q_t \in \mathbb{Z}$
- Total absolute charge: $Q_{\text{abs}} = \sum_{t} |q_t| \in \mathbb{Z}_{\ge 0}$

### 4.2 Magnitude Centroid
$$\mathbf{r}_{|\sigma|} = \begin{cases} \frac{\sum_t |q_t| \mathbf{r}_t}{Q_{\text{abs}}} & \text{if } Q_{\text{abs}} > 0 \\ \text{None} & \text{if } Q_{\text{abs}} = 0 \end{cases}$$

### 4.3 Signed First Moment & Origin Shift Identity
The signed first moment is:
$$\mathbf{m} = \sum_{t} q_t \mathbf{r}_t$$
Under an arbitrary spatial shift $\mathbf{r}'_v = \mathbf{r}_v + \mathbf{v}$:
$$\mathbf{m}' = \sum_{t} q_t (\mathbf{r}_t + \mathbf{v}) = \sum_t q_t \mathbf{r}_t + \mathbf{v} \sum_t q_t = \mathbf{m} + Q_{\text{net}} \mathbf{v}$$
When $Q_{\text{net}} = 0$ (neutral dipole), $\mathbf{m}$ is strictly invariant to choice of coordinate origin.

### 4.4 Positive-to-Negative Charge Separation
Let $T_+ = \{t \mid q_t > 0\}$ and $T_- = \{t \mid q_t < 0\}$.
If $|T_+| > 0$ and $|T_-| > 0$:
$$\mathbf{r}_+ = \frac{\sum_{t \in T_+} q_t \mathbf{r}_t}{\sum_{t \in T_+} q_t}, \quad \mathbf{r}_- = \frac{\sum_{t \in T_-} |q_t| \mathbf{r}_t}{\sum_{t \in T_-} |q_t|}$$
$$d_{+-} = \|\mathbf{r}_+ - \mathbf{r}_-\|_2$$
> [!CAUTION]
> If $|T_+| == 0$ or $|T_-| == 0$ (monopolar or zero configuration), $d_{+-}$ returns `None`. It is never imputed as `0.0`, which would falsely represent co-located opposite charges.

---

## 5. Weighted Hodge-Helmholtz Decomposition

### 5.1 Weighted Metrics & Inner Products
Let positive diagonal metric matrices be:
- $W_0 = \operatorname{diag}(w_v)$ on 0-cochains ($w_v > 0$)
- $W_1 = \operatorname{diag}(w_e)$ on 1-cochains ($w_e > 0$)
- $W_2 = \operatorname{diag}(w_t)$ on 2-cochains ($w_t > 0$)

The weighted inner product on 1-cochains is:
$$\langle u, v \rangle_{W_1} = u^T W_1 v, \quad \|u\|_{W_1}^2 = u^T W_1 u$$

### 5.2 Codifferential Operators
The adjoint operators $\delta_1: C^1 \to C^0$ and $\delta_2: C^2 \to C^1$ satisfy:
$$\langle \delta_1 \omega, \theta \rangle_{W_0} = \langle \omega, d_0 \theta \rangle_{W_1} \implies \delta_1 = W_0^{-1} d_0^T W_1$$
$$\langle \delta_2 \phi, \omega \rangle_{W_1} = \langle \phi, d_1 \omega \rangle_{W_2} \implies \delta_2 = W_1^{-1} d_1^T W_2$$

### 5.3 1-Form Decomposition
Every 1-cochain $\omega \in C^1(K)$ admits a unique orthogonal decomposition:
$$\omega = \omega_{\text{exact}} + \omega_{\text{coexact}} + \omega_{\text{harmonic}} = d_0 \alpha + \delta_2 \beta + h$$
where:
1. **Exact (curl-free / gradient)**:
   $$\omega_{\text{exact}} = d_0 \alpha, \quad \text{where } (d_0^T W_1 d_0) \alpha = d_0^T W_1 \omega$$
2. **Coexact (div-free / solenoidal)**:
   $$\omega_{\text{coexact}} = W_1^{-1} d_1^T \gamma, \quad \text{where } (d_1 W_1^{-1} d_1^T) \gamma = d_1 \omega \quad \text{and } \beta = W_2^{-1} \gamma$$
3. **Harmonic ($h \in \ker(\delta_1) \cap \ker(d_1)$)**:
   $$h = \omega - \omega_{\text{exact}} - \omega_{\text{coexact}}$$

### 5.4 Proof of Orthogonality
$$\langle \omega_{\text{exact}}, \omega_{\text{coexact}} \rangle_{W_1} = (d_0 \alpha)^T W_1 (W_1^{-1} d_1^T \gamma) = \alpha^T d_0^T d_1^T \gamma = \alpha^T (d_1 d_0)^T \gamma = 0$$
This holds identically because $d_1 d_0 = 0$.
Furthermore:
$$\langle \omega_{\text{exact}}, h \rangle_{W_1} = \alpha^T d_0^T W_1 h = \alpha^T W_0 (\delta_1 h) = 0$$
$$\langle \omega_{\text{coexact}}, h \rangle_{W_1} = \gamma^T d_1 h = 0$$
Thus, the three components are mutually orthogonal under $\langle \cdot, \cdot \rangle_{W_1}$.

### 5.5 Energy Conservation
$$\|\omega\|_{W_1}^2 = \|\omega_{\text{exact}}\|_{W_1}^2 + \|\omega_{\text{coexact}}\|_{W_1}^2 + \|h\|_{W_1}^2$$

---

## 6. Hand-Verifiable Complex Fixtures

The reference module provides 4 canonical test fixtures:
1. `single_triangle`: 3 vertices, 3 edges, 1 triangle. Simply connected ($b_1 = 0$).
2. `vortex_quad`: 5 vertices (4 boundary, 1 center), 8 edges, 4 triangles. Contractible disk ($b_1 = 0$).
3. `dipole_complex`: 6 vertices, 6 edges, 2 separated triangles forming a neutral dipole ($Q_{\text{net}} = 0, Q_{\text{abs}} = 2$).
4. `annulus_complex`: 6 vertices (3 inner, 3 outer), 12 edges, 6 triangles forming a non-contractible band with Euler characteristic $\chi = 6 - 12 + 6 = 0$ and 1st Betti number $b_1 = 1$, supporting non-trivial harmonic 1-forms.
