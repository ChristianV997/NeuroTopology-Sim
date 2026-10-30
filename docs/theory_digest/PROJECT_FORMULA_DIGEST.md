# NeuroTopology-Sim — Project Formula & Theory Digest

**Inventory date:** 2026-10-30  
**Scope:** Project-*own* theory / framework / formula artifacts on consciousness-adjacent research, contemplative mapping, physics-of-consciousness bridges, neurotopology, and TOE literature scaffolding. External papers are cited only when the project itself audits or digests them.  
**Sources:** `/opt/cursor/artifacts/*` research dossiers + `/workspace/core/topology.py` + `/workspace/outputs/toe_research/` + `/workspace/tools/toe_research/` + root `REPORT_*topology*.md` + claim-language guardrails.

**Claim ceiling for this digest:** descriptive inventory of equations and project-encoded ceilings. No ontology promotion, no proof of consciousness/TOE/suffering/rebirth.

---

## Core NeuroTopology metric stack (equations)

### Phase wrapping

From `core/topology.py::wrap_phase`:

\[
\mathrm{wrap}(x) = (x+\pi)\bmod(2\pi)-\pi \in (-\pi,\pi]
\]

### Plaquette / local winding charge

For a 2D phase field \(\theta_{i,j}\), clockwise plaquette loop
\((i,j)\to(i+1,j)\to(i+1,j+1)\to(i,j+1)\):

\[
\begin{aligned}
a &= \mathrm{wrap}(\theta_{i+1,j}-\theta_{i,j}) \\
b &= \mathrm{wrap}(\theta_{i+1,j+1}-\theta_{i+1,j}) \\
c &= \mathrm{wrap}(\theta_{i,j+1}-\theta_{i+1,j+1}) \\
d &= \mathrm{wrap}(\theta_{i,j}-\theta_{i,j+1}) \\
q_{i,j} &= \frac{a+b+c+d}{2\pi}
\end{aligned}
\]

**Sign convention (project-explicit):** this loop is the **negative** of the standard mathematical counter-clockwise winding. Analytic ground-truth defects of charge \(+k\) yield \(Q=-k\) here (`plaquette_charge` docstring; validated in `tests/test_topology_analytic_ground_truth.py`).

### Signed net charge \(Q\) / \(Q_z\)

Slice:

\[
Q = \mathrm{nint}\!\Big(\sum_{i,j} q_{i,j}\Big)
\]

3D field \(\psi\) (complex), slices along axis \(a\):

\[
\theta = \arg(\psi),\quad
Q_z[s] = \mathrm{nint}\!\Big(\sum_{i,j} q_{s,i,j}\Big),\quad
Q_{\mathrm{abs}}[s] = \sum_{i,j}|q_{s,i,j}|
\]

(`compute_Qz`). Registry shorthand (EQ-001 / topology digest):

\[
Q = \frac{1}{2\pi}\sum_p \mathrm{wrap}(\Delta\phi_p)
\]

### Absolute charge \(Q_{\mathrm{abs}}\) / \(Q_{\mathrm{abs}}\)

\[
Q_{\mathrm{abs}} = \sum_{i,j}|q_{i,j}|
\qquad\text{(EQ-002: }Q_{\mathrm{abs}}=\tfrac{1}{2\pi}\sum_p|\mathrm{wrap}(\Delta\phi_p)|)
\]

### Excess dressing \(f_{\mathrm{dress}}\) / `fdress`

From `compute_f_dress(Qz, Qabs, eps=1e-9)` and EQ-003:

\[
f_{\mathrm{dress}}
=
\frac{\langle Q_{\mathrm{abs}}\rangle - \lvert\langle Q_z\rangle\rvert}
{\lvert\langle Q_z\rangle\rvert + \varepsilon}
\]

Near 0 when local ± windings cancel into a coherent net charge; rises when unsigned local winding dominates the signed net.

### Nematic (director) defect charge

For head–tail symmetric director \(\theta\) (mod \(\pi\)):

\[
\psi = \mathrm{wrap}(2\theta),\quad
Q_{\mathrm{nem}} = -\frac{Q(\psi)}{2}
\]

Sign-corrected to the standard CCW convention (opposite of raw `plaquette_charge`).

### EEG / montage signed defect map (empirical reports)

`validation/montage_topology.py::signed_defect_map` on triangulation:

\[
Q \approx \mathrm{round}\!\Big(\sum_t w_t\Big),\qquad
Q_{\mathrm{abs}} = \sum_t |w_t|
\]

where \(w_t\) is per-triangle signed winding (`triangle_winding_batch`). Spatial extras: region net/abs charge, chirality, defect clustering / persistence proxy. Channel-mean unsigned summaries in many `REPORT_*` use `q_net`, `q_abs`, `f_dress`, `defect_density`.

### Cubical persistent homology (additive, not replacement)

On a real field \(f\) (e.g. \(|\psi|\) or charge density), GUDHI/cripser cubical persistence yields diagrams \(\{(b_k,d_k)\}\) in \(H_0,H_1,(H_2)\).

Betti curve:

\[
\beta(t) = \#\{(b,d): b\le t < d\}
\]

Persistence landscape layer \(k\) (Bubenik): \(k\)-th largest tent \(\max(0,\min(t-b,d-t))\).

Bottleneck distance \(d_B(D_1,D_2)\) via GUDHI — topological analogue of state-change distance (cf. PCI for complexity).

### Sheaf consistency residual (TOE registry / constitutive audits)

EQ-004 / topology digest:

\[
E_{\mathrm{sheaf}}(x)=\sum_{v,e}\big\|\rho_{v\leftarrow e}(x_e)-x_v\big\|^2
\qquad
L_{\mathrm{sheaf}}=\delta^\top\delta
\]

Constitutive audits (`CONSTITUTIVE_BRIDGE_AUDIT.md`, `NETWORK_TO_AFFINITY_DISSIPATION.md`) define residual

\[
r = B_0^{\mathcal F}z-\omega
\]

as **geometric consistency error only** — not force, heat, ATP, or suffering unless identified with thermodynamic affinity (below).

### Hypothesis-pipeline scalar stack

`pipelines/hypothesis.py`: synthetic intensity \(I\), then \(Q_z\), \(Q_{\mathrm{abs}}\), \(f_{\mathrm{dress}}\). Typical PASS gate:

\[
I_{\mathrm{mean}}\ge I_{\mathrm{mean,min}}
\;\wedge\;
Q_{\mathrm{abs}}\le Q_{\mathrm{abs,max}}
\]

(optional \(I_{\mathrm{std}}\)). These are **engineering thresholds**, not consciousness criteria.

---

## Thermodynamics / CTMC / affinity stack

Primary artifacts:  
`/opt/cursor/artifacts/ctmc-cycle-affinity/docs/{FORMULAS,INTERPRETATION}.md`,  
`/opt/cursor/artifacts/network-affinity-dissipation/docs/NETWORK_TO_AFFINITY_DISSIPATION.md`,  
`/opt/cursor/artifacts/constitutive-bridge/CONSTITUTIVE_BRIDGE_AUDIT.md`.

### Graph / cellular bookkeeping

\[
\beta_G = |E|-|V|+1
\]

With one 2-cell filling the unique cycle: \(\beta_1(\text{complex})=0\) while \(\beta_G=1\). CTMC rates live on the **1-skeleton**; attaching a 2-cell changes homology bookkeeping without changing \(p^\star,J,\dot\sigma\).

### Incidence, cycles, stationarity

Project \(B_0\) layout (node×edge):

\[
(B_0)_{i,e}=
\begin{cases}
-1 & i=\mathrm{src}(e)\\
+1 & i=\mathrm{dst}(e)\\
0 & \text{otherwise}
\end{cases}
\qquad
B_0 C=0,\quad B_0 J=0
\]

### Affinities, currents, entropy production rate (EPR)

\[
\alpha_e=\ln\frac{w_{uv}}{w_{vu}},\quad
J_e=p_u w_{uv}-p_v w_{vu},\quad
\dot\sigma=\sum_e J_e\ln\frac{p_u w_{uv}}{p_v w_{vu}}
\]

Detailed balance \(\Leftrightarrow\) \(C^\top\alpha=0\) (all cycle affinities vanish).

Edge affinity (stochastic thermo form used in network digest):

\[
A_e=\ln\frac{w_{ij}p_i}{w_{ji}p_j},\qquad
\frac{\dot S_{\mathrm i}}{k_B}=\sum_e J_e A_e\ge 0
\]

Cycle affinity:

\[
A_\gamma=\sum_{e\in\gamma}\ln\frac{w_e}{w_{-e}}
\]

(at NESS decomposes EPR over fundamental cycles — Schnakenberg).

### Near-equilibrium linear response

\[
G_{\mathrm{eq}}=\mathrm{diag}(\varphi_e^{\mathrm{eq}}),\quad
A=C^\top\alpha,\quad
\dot\sigma\approx A^\top\bigl(C^\top G_{\mathrm{eq}}^{-1} C\bigr)^{-1}A
\]

Three-state ring reference \(w_0=\sqrt{ab}\), \(\varphi_e^{\mathrm{eq}}=w_0/3\):

\[
\dot\sigma_{\mathrm{exact}}=(a-b)\ln\frac{a}{b},\qquad
\dot\sigma_{\mathrm{approx}}=w_0\Bigl(\ln\frac{a}{b}\Bigr)^2
\]

Far-from-eq protocol (fixed \(w_0=1\), \(\kappa=a/b\)): exact \((\sqrt{\kappa}-1/\sqrt{\kappa})\ln\kappa\) vs approx \((\ln\kappa)^2\). Benchmark: relative error grows with \(\kappa\) (e.g. \(\kappa=100\) rel_err \(\approx0.535\)).

### Constitutive CRN bridge (only defensible \(\Lambda\))

\[
A_e=-\frac{1}{RT}\sum_i\nu_{ei}\,\mu_i
\qquad
\frac{k_e^+}{k_e^-}=\mathrm{e}^{A_e}\times(\text{convention})
\]

Chemical work port:

\[
\dot W_{\mathrm{chem}}=\sum_{i\in\mathrm{chemostatted}}\mu_i^{\mathrm{ext}}\,\dot n_i^{\mathrm{exchange}}
\]

**Verdict encoded in project audits:** abstract sheaf/graph residual \(\Rightarrow\) dissipation is **unsupported**. Map is **conditional** on Markov/CRN + local detailed balance + identified reservoirs. Counterexamples: residual in \(\ker\Lambda^{\mathrm{phys}}\) with \(A=0\); \(r=0\) with chemostat drive \(A_\gamma\neq0\).

### Toy ring numbers (both CTMC + network digests)

\(a=2\,\mathrm{s}^{-1}\), \(b=1\,\mathrm{s}^{-1}\): \(p^\star=(1/3)^3\), \(J_e=(a-b)/3\), \(A_e=\ln2\), \(A_\gamma=3\ln2\), \(\dot\sigma=\ln2\) nats/s.

---

## Information / ΦID / sensitivity–capture stack

### Pigozzi ΦID / “causal emergence” (external paper, project audits)

Artifacts:  
`pigozzi-phiid-audit/docs/PIGOZZI_PHIID_REPRODUCTION_AUDIT.md`,  
`pigozzi-pipeline-repro-s2/docs/PIGOZZI_PIPELINE_REPRODUCTION_REPORT.md`.

Pipeline (author methods + code, as audited):

1. ODE GRN trajectories → z-score → global signal regression → AR(1) residualization  
2. Lag-1 Gaussian MI: \(I=-\tfrac12\ln(1-\rho^2)\)  
3. MIB via Fiedler vector of MI graph → two macroscopic channels  
4. Local ΦID lattice; headline estimand:

\[
\mathrm{emergence}=\mathrm{synergy}+\mathrm{downward\ causation}
\]

**Project reproduction ceiling:**

| Claim | Status |
|-------|--------|
| 29→19 nets / 808 circuits filtering | Verified (primary) |
| Deposit 808 / 19; reconstruct emergence; 17/19 increase | Reproduced |
| Headline \(128.32\pm81.31\%\) | **Not recovered** |
| Random 145×5 controls | Deposit incomplete |
| Full ODE regen | Partial (e.g. BioModel 31) |
| ΦID ⇒ agency / consciousness / dissipation | **Unsupported interpretation** |

Sensitivity (synthetics, author codepath): lag CV \(\approx1.58\); binning multiplies continuous estimate ~4–8×; partition choice O(1) relative changes; phase-rand can inflate; independent nodes can exceed common-drive after preprocessing.

### Sensitivity–capture / \(\kappa\) reconstruction

Artifacts: `sens-capture-reconstruction/docs/{SPEC,CLAIMS_TABLE,AUDIT}.md`.

**Estimands (reconstruction [SYN]):**

- \(d'\) from independent sensory probe hit/FA only  
- \(\mathrm{Capture}=P(\mathrm{approach}\mid\mathrm{evidence\_ready}\wedge\mathrm{probe\_threat})\) — **not** policy entropy; pre-evidence excluded  
- Direct-\(\kappa\) policy: logits = utilities + \(\kappa\times\) valence bias; default **no** affect→sensory path  
- Bayesian reference: same likelihood, \(\kappa\equiv0\)

Held-out pattern ([SYN]): Bayesian beats best \(\kappa\) in all 4 envs; positive-\(\kappa\) “helps controllable threat” **not recovered** (best \(\kappa=-1\)); capture reduction fails in `volatile_uncontrollable`. Original OB-TLA code unavailable ([AR-U]).

### Active inference (project implementations)

1. **TOE digest stubs (EQ-005, EQ-006):**

\[
F=\mathbb{E}_q[\ln q(s)-\ln p(o,s)],\quad
\varepsilon_i=o_i-\mu_i,\quad
\Pi_i\varepsilon_i
\]

\[
A=\int\!\big(c_1\|x-x^\star\|^2+c_2\|u\|^2+c_3\|\mathrm{d}\mu/\mathrm{d}t\|^2\big)\,\mathrm{d}t
\]

2. **`sim/active_inference.py`:** discretized expected free energy controller for **synthetic parameter search only** — pragmatic KL-to-preferred vs epistemic uncertainty; banned from real-EEG pipelines.

3. **Comp-psych exit cost (EQ-007):**

\[
C_{\mathrm{exit}}(x_0\to x_{\mathrm{target}})=\min_u\int\big(\|x(t)-x_{\mathrm{target}}\|^2+\lambda\|u(t)\|^2\big)\,\mathrm{d}t
\]

plus dwell time, recovery latency, \(R_{\mathrm{self}}\) recurrence — **non-diagnostic**.

### Bioelectric / basal cognition (digest stubs)

Viability set / regulation cost:

\[
V=\{x\in X:g_i(x)\le0\ \forall i\},\quad
J=\int\big(d(x(t),V)^2+\alpha\|u\|^2+\beta\,\mathrm{uncertainty}(t)\big)\,\mathrm{d}t
\]

Explicit: regulation ≠ subjective experience (F9).

---

## Unification / TOE literature bridge (project's own digests)

### Tools overview (`tools/toe_research/literature_bridge/`)

Offline P40 generator stack (no network in tests):

| Module | Role |
|--------|------|
| `generator.py` | Primitives, construct maps, guardrail flags all `False` |
| `equation_registry.py` | EQ-001…EQ-010 expressions |
| `falsifier_registry.py` | F1–F10 (rich source; see note) |
| `adversarial_consciousness_matrix.py` | GWT, IIT, RPT, Active Inference, HOT, Orch-OR, PP vs BTC-ICFT |
| `*_digest.py` | Topology, active inference, comp-psych, bioelectric, GW, cosmology |
| `rag_pack.py` | Safe docs + forbidden answer patterns |
| `validator.py` / `reporting.py` | Claim-language / report assembly |

**Note on output fidelity:** checked-in JSON under `outputs/toe_research/literature_bridge/` often has **stub fields (`"x"`)** for consciousness matrix / falsifier watchlist / some constraint matrices, while the **Python sources** hold the intended text. Prefer sources + `docs/toe_literature_bridge_constraint_falsifier_matrix.md` for semantics; treat stub JSON as scaffolding debt.

### TOE primitives (generator)

boundary, constraint, field, topology, information, symmetry, phase transition, observer/interiority, viability, allostatic cost, precision weighting, recalibration latency, local-global consistency, causal topology, cosmological field constraint, GR/Kerr reduction limit — plus BTC-ICFT constructs (\(Q\), \(Q_{\mathrm{abs}}\), `fdress`, phase field, defects, coherence, fragmentation, anesthesia wedge, M-only vs M+T residual) and ToL constructs (dukkha, taṇhā, upādāna, anattā, sati, samādhi, paññā, vimutti, exit cost, …).

### Equation candidate registry (EQ-001…010)

| ID | Expression | Project role |
|----|------------|--------------|
| EQ-001 | \(Q=(1/2\pi)\sum_p\mathrm{wrap}(\Delta\phi_p)\) | Topology telemetry |
| EQ-002 | \(Q_{\mathrm{abs}}=(1/2\pi)\sum_p|\mathrm{wrap}(\Delta\phi_p)|\) | Unsigned winding |
| EQ-003 | \(f_{\mathrm{dress}}=(Q_{\mathrm{abs}}-\|Q\|)/(\|Q\|+\varepsilon)\) | Excess dressing |
| EQ-004 | \(E_{\mathrm{sheaf}}=\sum\|\rho(x_e)-x_v\|^2\) | Sheaf consistency |
| EQ-005 | \(F=\mathbb{E}_q[\ln q(s)-\ln p(o,s)]\) | Free-energy objective |
| EQ-006 | Allostatic integral \(A=\int[\cdots]\) | Allostatic cost |
| EQ-007 | \(C_{\mathrm{exit}}\) optimal control | Exit / recalibration |
| EQ-008 | \(H^2(z)=\ldots\) | Cosmology placeholder |
| EQ-009 | \(w(z)=w_0+w_a z/(1+z)\) | Dark-energy EoS |
| EQ-010 | \(\omega_n=\omega_n^{\mathrm{Kerr}}(1+\delta_n)\), \(\tau_n=\tau_n^{\mathrm{Kerr}}(1+\gamma_n)\) | Kerr ringdown deviations |

All marked `claim_scope: research_hypothesis`, `blocked_claims: ['no proof']`.

### Cosmology / GW constraint equations (digests)

Dark-energy / Friedmann scaffolding (EQ-008/009); ringdown sum

\[
h(t)=\sum_n A_n\mathrm{e}^{-t/\tau_n}\cos(\omega_n t+\varphi_n)
\]

with area-theorem style \(A_{\mathrm{final}}\ge A_1+A_2\) listed in GW matrix. These **constrain** candidate TOE field terms; they are not evidence for consciousness claims (F7/F8).

### Unification landscape vs Intrinsic Existence

`/opt/cursor/artifacts/unification-map/UNIFICATION_LANDSCAPE_INTRINSIC_EXISTENCE.md`  
(**Intrinsic Existence line — explicitly not ICCOS**).

Three unification kinds: gauge GUT; quantum gravity/spacetime; structural amplitude relations (double copy). Ranked conceptual leads for “existence/causality” vocabulary: holography \(S_{\mathrm{EE}}=\mathrm{Area}/4G_N\); causal sets/CDT; info bounds; RG; double copy (**correspondence ≠ coupling**); string landscape; LQG; GUTs alone. **Central gap:** no bridge from unification math to lived experience / personal identity / rebirth / psi.

### Causal rebirth candidate models (conditional only)

`CAUSAL_REBIRTH_CANDIDATE_MODELS.md`:

| Model | Carrier idea | Min. new physics (strong form) |
|-------|--------------|--------------------------------|
| A Causal-pattern (anātman) | Worldly records / dispositions | None (weak) / high (strong imprint) |
| B Channel transfer | Encode \(I\) through \(\mathcal C\) under Landauer/no-cloning/no-hiding | Large (unknown channel) |
| C Field/topological \(\tau\) | Metastable defect/sector | Very large |

Shared non-sequitur: conservation of quantum info, nonzero EPR, or nonzero topological charge **does not** entail personal survival.

### Consciousness adversarial matrix (intended content)

Theories vs BTC-ICFT telemetry: GWT, IIT, RPT, Active Inference, HOT, Orch-OR, Predictive Processing. Generator text: BTC-ICFT adds “artifact-controlled phase-topology telemetry”; does **not** explain subjective experience/ontology; falsifier = no theory-distinguishing prediction under held-out controls.

---

## Contemplative / state-modulation empirical reports (index)

Root `REPORT_*topology*.md` — brief scientific claim index only (not re-analysis).

| Report | State contrast | Headline result (as written) |
|--------|----------------|------------------------------|
| `REPORT_ds005620_pitnn_cohort_topology.md` | Propofol awake vs sedated | PITNN **NOT_SUPPORTED** 20/20; some topology descriptors separate states |
| `REPORT_ds005620_scaled_channel_mean_topology.md` | Channel-mean awake vs sed | **Null** on cheap channel-mean; does not contradict montage-aware signed winding headline |
| `REPORT_ds004541_anesthesia_locroc_topology.md` | LOC/ROC markers | Small-n significant on \(q_{\mathrm{abs}}\), \(f_{\mathrm{dress}}\), defect_density |
| `REPORT_dandi000458_isoflurane_topology.md` | Mouse awake vs isoflurane | Directional / mixed-effects on \(q_{\mathrm{net}}\); \(f_{\mathrm{dress}}\) ns |
| `REPORT_ds005555_boas_sleep_topology.md` | Wake vs N2/N3/REM | Graded subtle topology gradient (6-ch PSG) |
| `REPORT_DREAM_qz_topology.md` | Dream experience bifurcation | **Data unobtainable** in environment |
| `REPORT_ds004040_trance_channeling_topology.md` | Rest vs trance | **Clean null** all metrics (\(\|d\|<0.011\)) |
| `REPORT_ds004572_hypnosis_topology.md` | Baseline vs experience | Strong subject-blocked effects; **not** isolated to hypnosis vs sham |
| `REPORT_ds004917_pcist_tms_topology.md` | TMS-EEG PCIst | Parietal inhibition ↑ PCIst (perturbational complexity) |
| `REPORT_ds005237_dmn_cen_signed_topology.md` | Psychiatric connectome | Signed topology **near-null** / not robust |
| `REPORT_ds005237_stroop_cen_state_topology.md` | Stroop CEN engagement | Does **not** cross-replicate ds003969 meditation EEG beta finding to BOLD |
| `REPORT_ds005917_ketamine_fmri_topology.md` | Ketamine vs placebo MDD | **Clean null** all TDA/graph metrics |
| `REPORT_ds006072_psilocybin_persistence_topology.md` | Acute vs follow-up | Acute drug-specific effect; **returns to baseline** (no persistence) |
| `REPORT_ds006644_dmt_meditation_fmri_topology.md` | DMT+harmine vs placebo @ meditation retreat | Marginal global-efficiency only; fails multi-comparison correction |

**Doctrine / contemplative scaffolding (non-empirical):**  
`docs/suttacentral_integration.md` — doctrine cards (`claim_type: doctrine_scaffold`); ToL mappings interpretive, not canonical proof.  
`docs/mental_flexibility_systems_medicine_bridge.md` — exit-cost / affordance / recovery model; blocks clinical & enlightenment claims.  
`docs/transition_science_foundation.md` — `TransitionRecordV1` infrastructure for state changes; explicitly not attainment claims.

**Speculative sim track:** `sim/speculative/` (Langevin lattice, non-Hermitian, pymdp) — hard-decoupled from BTC-ICFT real-EEG; requires `SPECULATIVE_BANNER`.

---

## Claim ceilings & guardrails as encoded in project

### Hard bans (`AGENTS.md`, `sciencer_d/btc_icft/report_guardrails.py`, ontology docs)

No clinical claims; no ontology promotion; no proof claims; no real-data auto-execution in P40; no live APIs/keys in tests; no label inference / target fabrication; **no Q/Qabs/fdress proof framing**; no TOE validation / final theory / consciousness solved / soul / afterlife / nibbāna proof.

Banned report phrases (canonical):

```
proves consciousness, soul proven, afterlife proven, liberation detected,
enlightenment proven, nirvana confirmed, ontology solved, ultimate reality,
q equals self, q equals soul, q_abs equals suffering, f_dress equals karma
```

RAG forbidden patterns: `TOE validated`, `final theory`, `consciousness solved`, `Q proves`, `Qabs proves`, `clinical treatment`, `diagnosis`, `soul proof`, `afterlife proof`, `ontology promotion`.

### Generator guardrail flags (all forced `False`)

`toe_validation_claims_allowed`, `final_theory_claims_allowed`, `consciousness_proof_claims_allowed`, `soul_proof_claims_allowed`, `afterlife_proof_claims_allowed`, `nibbana_proof_claims_allowed`, `q_qabs_fdress_proof_claims_allowed`, `clinical_claims_allowed`, `ontology_promotion_allowed`, fixture-as-empirical, real-data auto-exec, live APIs, etc.

### Falsifier registry F1–F10 (from `falsifier_registry.py` source)

| ID | Claim under pressure | Demotion if fail |
|----|----------------------|------------------|
| F1 | Q/Qabs/fdress residual predictive value vs M-only | Telemetry-only |
| F2 | Anesthesia LOC/ROC Q/fdress signature | Drop state-signature language |
| F3 | Winding physiological vs interpolation artifact | Quarantine interpolated winding |
| F4 | Robustness to resolution/nulls | Exploratory diagnostics only |
| F5 | Hodge/sheaf/Laplacian beat simpler metrics | Prefer simpler family |
| F6 | Mental-flexibility → longitudinal recovery | Keep conceptual |
| F7 | TOE cosmological field vs joint obs | Reject/bound field term |
| F8 | Kerr ringdown deviations | Preserve GR reduction limit |
| F9 | Bioelectric ⇒ subjective experience | Limit to regulation |
| F10 | Microtubule/biophoton mechanisms | Remove from active set |

### Artifact-level ceilings (research dossiers)

- CTMC/affinity: validates bookkeeping **only**; not neural tissue or suffering  
- Constitutive/network: residual→dissipation **unsupported** without \(\Lambda\equiv A\)  
- Unification / rebirth: conditional theory; no established carrier  
- Pigozzi: observational ΦID estimand; not agency/consciousness  
- Sens-capture: synthetic reconstruction; not human affect/craving  

### Ontology claim language (`docs/ontology_claim_language_guardrails.md`)

Safe: engineering runtime validation, marker association, topology telemetry, bridge hypothesis, mechanism candidate, falsifier. Ban metric→ontology and state-label→existential shortcuts. CI: `make ontology-language-check` (+ strict generated-output modes).

---

## Equation consolidation map (symbol → definition → where used → what it is NOT)

| Symbol | Definition | Where used | What it is NOT |
|--------|------------|------------|----------------|
| \(\mathrm{wrap}\) | Phase wrap to \((-\pi,\pi]\) | `core/topology.py`, all \(Q\) pipelines | Physical potential |
| \(q_{i,j}\) | Plaquette winding / \(2\pi\) | `plaquette_charge`, `compute_Qz` | Conscious content |
| \(Q\), \(Q_z\) | Rounded net signed charge | Topology, hypotheses, REPORT_* `q_net` | Self / soul / identity |
| \(Q_{\mathrm{abs}}\) | \(\sum\|q\|\) | Same; EQ-002 | Suffering / dukkha |
| \(f_{\mathrm{dress}}\) | Excess abs vs net | `compute_f_dress`; EQ-003 | Karma / morality |
| \(Q_{\mathrm{nem}}\) | Half-integer nematic charge | Nematic fields | Neural “director soul” |
| \(w_t\) | Triangle signed winding | Montage signed defect map | Proof of LOC |
| \(\beta(t),\lambda_k\) | Betti curve / landscape | Cubical persistence | PCI substitute for phenomenology |
| \(d_B\) | Bottleneck distance | Persistence compare | Identity continuity |
| \(E_{\mathrm{sheaf}},r\) | Sheaf consistency residual | EQ-004; constitutive audits | Force / heat / ATP |
| \(\alpha_e,A_e,A_\gamma\) | Rate / thermo affinities | CTMC + CRN digests | “Frustration” label alone |
| \(J_e\) | Probability / molar current | Same | Agency |
| \(\dot\sigma\) | EPR \(\sum J A\) | Same | Subjective suffering |
| \(\Lambda^{\mathrm{phys}}\) | Must equal \(A_e\) | Constitutive bridge | Arbitrary \(\Lambda(r)\) |
| \(A_{\mathrm{chem}}\) | Chemostat affinity | Network digest | Graph drawing residual |
| \(F,\Pi_i\varepsilon_i\) | Free energy / precision PE | Active-inf digest; sim AI controller | Proof of cognition in vivo |
| \(A\) (allostatic) | Integral cost EQ-006 | ToL / mental-flex bridge | Clinical diagnosis |
| \(C_{\mathrm{exit}}\) | Exit-cost control EQ-007 | Comp-psych digest | Therapy prescription |
| emergence | synergy + downward causation | Pigozzi audits | Macro do-intervention power |
| \(d',\mathrm{Capture},\kappa\) | Probe sensitivity / post-evidence approach / valence bias | Sens-capture recon | Human craving truth |
| \(V,J\) | Viability / regulation cost | Bioelectric digest | Phenomenal consciousness |
| \(H^2(z),w(z)\) | Cosmology stubs | EQ-008/009 | Mind cosmology |
| \(\omega_n,\tau_n,\delta_n,\gamma_n\) | Kerr QNM deviations | EQ-010; F8 | Brain–black-hole map |
| \(S_{\mathrm{EE}}\) | Ryu–Takayanagi | Unification dossier | Personal dual CFT |
| \(\tau\) (rebirth Model C) | Speculative topological carrier | Causal-rebirth dossier | Established memory field |
| \(I,\mathcal C\) (Model B) | Info channel at death | Same | Observed brain dump |
| Doctrine vars (dukkha, …) | SuttaCentral doctrine cards | `docs/suttacentral_integration.md` | Empirical EEG labels |

---

## Gaps vs SOTA external literature

1. **Constitutive gap (project-acknowledged):** Structure/sheaf residual is not automatically thermodynamic affinity; needs LDB + stoichiometry + reservoirs (Schnakenberg / Seifert / Rao–Esposito). No living-neuron EPR measurement pipeline is claimed.

2. **Consciousness theory matrix is scaffolding:** Generator emits generic comparative rows; checked-in JSON often stubbed. No preregistered multi-theory EEG/fMRI discrimination study is completed inside P40.

3. **IIT / Φ / ΦID:** Project audits Pigozzi’s Gaussian lag-1 MIB ΦID on GRNs; does **not** implement full Tononi Φ or interventional causal emergence. Metric is analysis-choice sensitive (lag/binning/partition).

4. **PCI / perturbational complexity:** Empirical PCIst report exists (`ds004917`); not unified with \(Q/f_{\mathrm{dress}}\) into a single validated consciousness index.

5. **Active inference / allostasis:** Digests list Friston-style symbols and ToL mappings; `sim/active_inference.py` is a **synthetic optimizer**, not a fitted subject-level active-inference model of EEG.

6. **Orch-OR / microtubules / biophotons:** Present only as adversarial/falsifier targets (F10), not as endorsed mechanisms; speculative package explicitly non-biological-claim.

7. **Holography / QG / GUTs:** Unification dossier correctly treats them as physics programs; no brain↔bulk or brain↔gauge coupling is derived. Double-copy correspondence ≠ physical coupling (project rule).

8. **Rebirth / Intrinsic Existence / ICCOS:** Intrinsic Existence dossiers are conditional/philosophical-physics; **ICCOS is named only as “not this line.”** No empirical carrier protocol.

9. **Contemplative SOTA:** Doctrine integration + mental-flexibility bridge are claim-governed scaffolds. Empirical contemplative/altered-state topology results are **mixed** (trance null; hypnosis baseline effect confounded; DMT/ketamine null/marginal; psilocybin acute-only). Classical jhāna/cessation OpenNeuro targets noted as missing.

10. **Equation registry incompleteness:** EQ-008 is literal `H²(z) = ...`; cosmology/GW matrices partially stubbed in JSON; construct→equation edges lack source-level citations (P40.2 called out in bridge report).

11. **M+T residual value (F1):** Core scientific bet of BTC-ICFT — topology adds predictive value beyond spectral/complexity baselines — remains a **falsifier-gated hypothesis**, not a settled result across all REPORT_* contrasts.

12. **Sens-capture / affect:** Prior OB-TLA artifacts unavailable; reconstruction cannot close the loop to published human affect/craving literature.

---

## Source index (absolute paths)

**Artifacts:**  
`/opt/cursor/artifacts/ctmc-cycle-affinity/docs/FORMULAS.md`  
`/opt/cursor/artifacts/ctmc-cycle-affinity/docs/INTERPRETATION.md`  
`/opt/cursor/artifacts/network-affinity-dissipation/docs/NETWORK_TO_AFFINITY_DISSIPATION.md`  
`/opt/cursor/artifacts/unification-map/UNIFICATION_LANDSCAPE_INTRINSIC_EXISTENCE.md`  
`/opt/cursor/artifacts/causal-rebirth-dossier/CAUSAL_REBIRTH_CANDIDATE_MODELS.md`  
`/opt/cursor/artifacts/constitutive-bridge/CONSTITUTIVE_BRIDGE_AUDIT.md`  
`/opt/cursor/artifacts/pigozzi-phiid-audit/docs/PIGOZZI_PHIID_REPRODUCTION_AUDIT.md`  
`/opt/cursor/artifacts/pigozzi-pipeline-repro-s2/docs/PIGOZZI_PIPELINE_REPRODUCTION_REPORT.md`  
`/opt/cursor/artifacts/sens-capture-reconstruction/docs/{CLAIMS_TABLE,SPEC,AUDIT}.md`

**Repo core:**  
`/workspace/core/topology.py`  
`/workspace/validation/montage_topology.py`  
`/workspace/pipelines/hypothesis.py`  
`/workspace/sim/active_inference.py`  
`/workspace/sim/speculative/`  
`/workspace/tools/toe_research/literature_bridge/`  
`/workspace/outputs/toe_research/literature_bridge/`  
`/workspace/docs/toe_literature_bridge_constraint_falsifier_matrix.md`  
`/workspace/docs/ontology_claim_language_guardrails.md`  
`/workspace/docs/suttacentral_integration.md`  
`/workspace/docs/mental_flexibility_systems_medicine_bridge.md`  
`/workspace/sciencer_d/btc_icft/report_guardrails.py`  
`/workspace/REPORT_*topology*.md`

---

*End of digest. Equations transcribed from FORMULAS.md and `core/topology.py` with project sign conventions preserved.*
