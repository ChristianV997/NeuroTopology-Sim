# Quantum-memory versus classical-memory benchmark

**Status: `SYNTHETIC_MODEL_ONLY`.** This is a bounded write–wait–read task for comparing receiver-accessible memory channels. It is not a biological model and gives no evidence of biological quantum advantage, consciousness, or Orch OR.

## Task and matching contract

The evaluator prepares one of four equally weighted qubit states, `Z0`, `Z1`, `X+`, or `X-`. The state is stored for the same declared wait time $T$. Only after that wait does the receiver learn the measurement basis $b\in\{Z,X\}$ and return one bit. The receiver API receives neither the preparation label nor the random seed, hidden trajectory, joint bath state, or future outcome. Scores are calculated from the Born probability of the corresponding projective readout for each of the four preparations; the quantum score is the expected score, not a sampled quantum readout record. There is no postselection.

The quantum output register is one qubit (Hilbert dimension 2). The classical write stores one binary outcome; its noisy OU readout is a scalar derived from that stored bit and independent process noise. The two systems therefore have the same nominal two-symbol write alphabet and the same delayed basis information, but they are not a full hardware-resource match. The quantum model also contains an unobserved thermal pseudomode during storage. Its internal dimension, energy, reset cost, control precision, and coupling resources are not equated to the classical device. The classical one-bit ceiling below bounds binary classical write/read strategies for this input task; the OU process is one explicit aging model beneath that ceiling. Do not interpret beating this baseline as a general quantum advantage or as evidence for a biological mechanism.

For a binary classical measurement of the input qubit, write its effects as $E_\pm=(\alpha I\pm\mathbf m\cdot\boldsymbol\sigma)/2$, where positivity implies $\lVert\mathbf m\rVert\le1$. After the basis is announced, the receiver can choose which result maps to which bit. Averaging the two bit states in each basis gives

$$
P_{\rm cl}=\frac12+\frac{|m_x|+|m_z|}{4}
\le\frac12+\frac{\sqrt2}{4}\simeq0.853553.
$$

The bound follows from $|m_x|+|m_z|\le\sqrt2\lVert\mathbf m\rVert$. A projective measurement attains it at the Breidbart axis $\mathbf n=(\hat x+\hat z)/\sqrt2$. A classical system that receives the preparation label, stores more than one bit, or obtains side information is outside this bound and must be reported as a different comparator.

The explicit classical memory is

$$
dx=-\frac{x}{\tau_c}dt+\sqrt{2D}\,dW_t,
\qquad
x(T)=e^{-T/\tau_c}x(0)+\sigma_\infty\sqrt{1-e^{-2T/\tau_c}}\,\xi,
$$

where $x(0)=\pm A$, $\xi\sim\mathcal N(0,1)$, and $\sigma_\infty=\sqrt{D\tau_c}$. The implementation uses dimensionless $x$ with default $A=1$; hence $D$ has units of inverse seconds and $\sigma_\infty$ is dimensionless. The receiver's optimal sign decision has retention factor

$$
\chi(T)=2\Phi\!\left(\frac{A e^{-T/\tau_c}}
 {\sigma_\infty\sqrt{1-e^{-2T/\tau_c}}}\right)-1,
\qquad
P_{\rm OU}(T)=\frac12+\chi(T)\frac{\sqrt2}{4}.
$$

At $T=0$, the zero-noise limit gives $\chi=1$ and reaches the one-bit bound. The exact OU expectation and a seeded Monte Carlo estimate are both reported. Monte Carlo estimates can fluctuate above a theoretical ceiling by sampling error; use the exact expectation for the comparator and the sampled standard error only to describe Monte Carlo precision. For scientific use, fit OU/HMM parameters only on declared training waits, freeze them, and report held-out waits separately.

## Open quantum pseudomode

The stored register is a qubit coupled longitudinally to one damped bosonic pseudomode. The Hamiltonian is given in angular-frequency units:

$$
H/\hbar=\omega_m a^\dagger a+
\frac{g}{2}\sigma_z(a+a^\dagger)+\epsilon(a+a^\dagger).
$$

The initial joint state is the prepared qubit tensor a thermal pseudomode state, independent of the preparation label. The density operator obeys

$$
\dot\rho=-i[H/\hbar,\rho]+
\kappa(\bar n+1)\mathcal D[a]\rho+
\kappa\bar n\mathcal D[a^\dagger]\rho+
\gamma_\phi\mathcal D[\sigma_z/\sqrt2]\rho+
\gamma_1\mathcal D[\sigma_-]\rho,
$$

where $\mathcal D[L]\rho=L\rho L^\dagger-\{L^\dagger L,\rho\}/2$ and

$$
\bar n=\left[\exp\!\left(\frac{\hbar\omega_m}{k_BT}\right)-1\right]^{-1}.
$$

$T$ is temperature in kelvin; $\omega_m,g,\epsilon$ are in radians per second; $\kappa,\gamma_\phi,\gamma_1$ are in inverse seconds. The optional $\gamma_1$ term is amplitude damping from $|0\rangle$ to $|1\rangle$ in the declared $\sigma_z$ basis. No qubit energy splitting is modeled, so no thermodynamic temperature or detailed-balance interpretation is assigned to this term. The mode is truncated to a finite Fock basis. The code uses NumPy fixed-step RK4, with a hard step-count and Fock-cutoff cap. It checks trace, Hermiticity, and minimum eigenvalue and raises if tolerances fail; it does not clip or renormalize an invalid state. The receiver gets only $\mathrm{Tr}_m\rho(T)$ and then performs the announced $Z$ or $X$ projective readout. It never receives the pseudomode or bath.

For ideal pure dephasing with transverse contraction $\lambda(T)$ and preserved $Z$ populations, the task score is

$$
P_Q(T)=\frac{3+\lambda(T)}{4}.
$$

It exceeds the one-classical-bit ceiling only when $\lambda>\sqrt2-1\simeq0.4142$. The full pseudomode model can add population loss and correlations, so its unconditional score is computed directly rather than inferred from this shortcut. This threshold is task-specific, not a general quantum-memory theorem.

## Controls and interpretation

- **Zero coupling:** set $g=0$. A driven/damped pseudomode must not alter the isolated qubit score.
- **Zero wait:** checks the write/read channel and classical one-bit ceiling.
- **No side information:** receiver interfaces contain only the reduced qubit state or classical scalar and the delayed basis; evaluator-side labels and seed are not arguments.
- **No postselection:** every one of the four input preparations contributes to the expected score.
- **Density checks:** trace, Hermiticity, positivity tolerance, and valid readout probabilities are checked; nonphysical states are rejected, not repaired.
- **Thermal and driven Fock convergence:** compare increasing cutoffs, verify nonzero population at $n\ge4$, monitor edge population, and compare scores. Occupied high levels matter; a cutoff check with an unpopulated mode is not evidence of convergence.
- **Resource limits:** integration steps are capped at 20,000, Fock cutoff at 32, and the estimate $N_{\rm steps}(2N_{\rm Fock})^3$ at 25 million matrix-work units. These conservative caps bound this small reference implementation, not all possible research-scale simulations or a guaranteed wall-clock time.
- **Classical fit discipline:** the default OU parameters are explicit and not fitted to the quantum score. Any fitted OU/HMM must be calibrated only on training waits and frozen before held-out waits.

An advantage over the one-bit bound would show only that this simulated qubit channel retains task-relevant information beyond a binary classical write strategy under the declared assumptions. It does not show that an open quantum system in biology has this coupling, that its resources are matched in energy or volume, or that it supports a phenomenological theory. A stronger follow-up should compare learned finite-state classical hidden-memory models under an explicit total internal-state/resource budget, alongside the analytic one-bit bound.

## Reproduction

From the repository root, with NumPy available:

```powershell
python scripts/benchmark_quantum_classical_memory.py --wait-s 2e-13 --fock-cutoff 10 --trials 1000 --seed 20261124
python -m unittest tests.test_quantum_memory_benchmark -v
```

The script writes finite JSON to stdout with schema `quantum-memory-benchmark-v1`. The Monte Carlo seed belongs to the evaluator, never to the receiver; the density-matrix calculation itself is deterministic. Keep exact configurations, Python/NumPy versions, command, and output hash with any archived result. No empirical or biological interpretation is authorized by this artifact.
