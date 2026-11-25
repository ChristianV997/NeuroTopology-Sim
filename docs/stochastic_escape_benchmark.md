# Stochastic Escape Normal-Form Benchmark (`sim.stochastic_escape_benchmark`)

## 1. Purpose and Epistemic Scope

This module implements a self-contained **numerical synthetic benchmark** comparing:
1. A finite-domain **Backward Kolmogorov Crank–Nicolson survival-PDE oracle**, and
2. A **right-censored Euler–Maruyama Monte Carlo simulator** with independent per-trial `SeedSequence` streams

on a one-dimensional saddle-node normal-form stochastic differential equation (SDE).

**Scope & Guardrails (`SYNTHETIC_NUMERICAL_BENCHMARK`):**
- Connect local instability and finite-horizon escape through an explicit dynamical equation rather than treating local Hessian curvature alone as an escape rate.
- Does **not** infer or establish a biological, neural, SU(2), or contemplative escape law.
- Asymptotic Kramers rates are **only** reported when the barrier-to-noise ratio $\Delta V / D \ge 6.0$ (`asymptotic_valid=True`), and even then apply only to unbounded/infinite-horizon escape across the saddle rather than directly replacing finite-domain $[q_{\min}, q_{\max}]$, finite-horizon $[0, T]$ survival.

## 2. Model Equations, Boundary Conditions, and Units

All quantities use declared **dimensionless normal-form units** ($[q]=1, [t]=1, [r]=1, [D]=1$):

$$dq_t = (r - q_t^2)\,dt + \sqrt{2 D}\,dW_t, \qquad r > 0,\ D > 0.$$

Associated potential:

$$V(q) = -r q + \frac{1}{3} q^3,$$

with stable equilibrium $q_+ = +\sqrt{r}$, unstable saddle $q_- = -\sqrt{r}$, and barrier height $\Delta V = \frac{4}{3} r^{3/2}$.

### Compatible Finite-Horizon Estimands

On a finite spatial domain $[q_{\min}, q_{\max}]$ ($q_{\min} < -\sqrt{r} < q_0 \le q_+ < q_{\max}$) and finite horizon $[0, T]$ with exit time $\tau = \inf\{t \ge 0 : q_t \le q_{\min}\}$:
- **Survival probability:** $S(q_0, T) = \mathbb{P}_{q_0}(\tau > T)$.
- **Restricted Mean Survival Time (RMST):** $\operatorname{RMST}(T) = \int_0^T S(q_0, t)\,dt = \mathbb{E}_{q_0}[\min(\tau, T)]$.

### Survival-PDE Oracle

The Crank–Nicolson oracle solves:

$$\frac{\partial S}{\partial t} = (r - q^2)\frac{\partial S}{\partial q} + D \frac{\partial^2 S}{\partial q^2}, \qquad S(q, 0) = 1\ (q > q_{\min}),$$

with absorbing lower boundary $S(q_{\min}, t) = 0$ and reflecting upper boundary $\partial_q S(q_{\max}, t) = 0$.

### Provenance Integration

Metrics are packaged via the canonical repository contract `runs.run_record.RunRecordV1` (`build_escape_run_record`).
