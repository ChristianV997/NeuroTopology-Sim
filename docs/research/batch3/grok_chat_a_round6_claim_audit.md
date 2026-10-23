# Round 6 Claim Audit (Batch 3, Grok Chat Agent A)

**Audit date:** 2026-10-16 (primary-source audit refreshed 2026-10-23 UTC)<br>
**PR #412 starting head:** `d42a085dd6eb48ff3b36854cd6c987b4f7308ed7` (five commits; one changed document)<br>
**PR base branch:** `main`; live `main` at source-audit refresh: `b51bb9b4bdf63c19894bb407eadcd70f528f7dda`<br>
**Prior artifact:** `docs/research/batch3/theory_to_measurement_review.md` on open PR #393 (`batch3/grok-chat-a-theory-to-measurement`, live head `3758e2ab7f7f33fb5825aedc3dfc0351bdffe8c2`, as checked 2026-10-23). This claim audit does not overwrite that review or duplicate its claim matrix.<br>
**Project status:** HOLD / SYNTHETIC_ONLY. Round 6 proposals are not established.  
**Source audit:** On 2026-10-23 UTC, the SIAM publisher records, the full Frontiers article, the current arXiv v2 record and PDF, and the pinned MNE-Python 1.13.2 source and bibliography were directly inspected. The 2026 arXiv paper's claim is source-verified; its proof was not independently validated, and peer-reviewed publication/acceptance was not verified. A separate 2026 preprint by Jin claims its own proof; the Townsend–Greenbaum account of checking it is an author-reported assessment (see the Crouzeix row), and neither proof was evaluated here. No dataset or third-party code was accessed or executed.

## Distinctions enforced (updated for Round 6)

| Category | Meaning | Evidence required to advance | Does not license |
|----------|---------|------------------------------|------------------|
| Formal mathematical identity | Equality under stated axioms and boundary conditions | Peer-reviewed derivation or textbook proof with explicit normalization | Measurement of a cortical wave |
| Numerical implementation claim | Code reproduces a known formula within tolerance on synthetic data | Deterministic fixture, version-pinned reference, finite-JSON report | Biological identification |
| Borrowed physical model | Established volume-conductor formula transferred to EEG | Primary source + parameter values + limiting-case checks | Empirical detector performance |
| Operational measurement claim | Feature is computable from sensors | Documented pipeline + surrogate/null controls | Feature measures the proposed construct |
| Empirical claim | Observation on real data under locked controls | Independent cohort, provenance, multiplicity, pairwise baselines | Mechanistic interpretation |
| Speculative interpretation | Narrative linking math/model to biology | Independent identification beyond volume conduction and classical alternatives | Any promotion |

“A feature is computable” ≠ “the feature measures the proposed biological construct.” Code, synthetic results, and preprints are not evidence that a neuroscience construct has been measured.

## Source verification

| Claim element | Primary source | Version / DOI / commit | Direct support for Round 6 use? | Retrieval |
|---------------|----------------|------------------------|----------------------------------|-----------|
| Four-shell concentric-sphere EEG forward model | Næss et al. 2017, [“Corrected Four-Sphere Head Model for EEG Signals”](https://www.frontiersin.org/journals/human-neuroscience/articles/10.3389/fnhum.2017.00490/full), peer-reviewed article in *Front Hum Neurosci* 11:490 | DOI: 10.3389/fnhum.2017.00490; received 2017-05-18, accepted 2017-09-26, published 2017-10-18 | The published article derives corrected analytical formulas for four concentric compartments (brain/CSF/skull/scalp), checks interface conditions, and reports agreement with FEM in the tested configurations. It says the examples use radii and conductivities from Nunez & Srinivasan (2006). This is a model result, not validation on empirical EEG or a claim that the sphere is a realistic head model; parameters must be declared | Full publisher article inspected 2026-10-23 |
| Homogeneous-sphere limit | Næss et al. 2017, [published article, §3.2 “Limiting case”](https://www.frontiersin.org/journals/human-neuroscience/articles/10.3389/fnhum.2017.00490/full), comparing its result with Nunez & Srinivasan (2006), Eq. 6.7 | DOI: 10.3389/fnhum.2017.00490 | The published Frontiers article itself labels this section §3.2. It states that equal conductivity in all four shells yields agreement between its simplified four-sphere result and the homogeneous single-sphere surface potential for a radial dipole. This is a model limiting-case check reported by that paper, not empirical validation or independent verification of the cited textbook equation. The specific ratio “(2l+1)/l” is not asserted by this comparison and remains unverified pending a separate derivation with explicit normalization | Full publisher article, including §3.2, inspected 2026-10-23 |
| MNE CSD / Perrin surface Laplacian | Perrin et al. 1987 and 1989; MNE-Python 1.13.2 [`compute_current_source_density` source](https://raw.githubusercontent.com/mne-tools/mne-python/v1.13.2/mne/preprocessing/_csd.py) and [pinned bibliography](https://raw.githubusercontent.com/mne-tools/mne-python/v1.13.2/doc/references.bib) | Perrin 1987, *IEEE Trans Biomed Eng* BME-34(4):283–288, DOI 10.1109/TBME.1987.326089 ([PubMed record](https://pubmed.ncbi.nlm.nih.gov/3504202/)); Perrin et al. 1989, *Electroencephalogr Clin Neurophysiol* 72(2):184–187, DOI 10.1016/0013-4694(89)90180-6 ([publisher record](https://www.sciencedirect.com/science/article/abs/pii/0013469489901806)) | The pinned MNE docstring calls the transform a spherical-spline surface Laplacian and cites keys PerrinEtAl1987, PerrinEtAl1989, Cohen2014 and KayserTenke2015; the pinned bibliography resolves those entries. The 1987 end page is 288, not unconfirmed. This documents MNE's references and method only—not identity or parity with this repository, empirical EEG evidence, or biological interpretation. A synthetic comparison would be numerical comparison, not implementation parity | Pinned MNE 1.13.2 source and bibliography inspected 2026-10-23 |
| Crouzeix's conjecture (constant 2) | Crouzeix & Palencia 2017, [SIAM article](https://epubs.siam.org/doi/10.1137/17M1116672); Ransford & Schwenninger 2018, [SIAM article](https://epubs.siam.org/doi/10.1137/17M1143757); Lorist & Schwenninger 2026, [arXiv:2608.03841v2](https://arxiv.org/abs/2608.03841v2); Jin 2026, preprint "The Numerical Range Is a 2-Spectral Set" (Preprints.org 202607.1919; [author repository](https://github.com/jinshanmu/CrouzeixConjecture)); Townsend & Greenbaum 2026, SIAM News essay ["The Neurosurgery Resident Who Proved Crouzeix's Conjecture"](https://alextownsend.net/essays/SIAMNews_CrouzeixConjecture.pdf) | **Crouzeix–Palencia 2017** (peer-reviewed): *SIAM J Matrix Anal Appl* 38(2):649–655, DOI 10.1137/17M1116672, proves the \(1+\sqrt{2}\) spectral-set bound for the numerical range; the conjecture's constant 2 was then unproven. **Ransford–Schwenninger 2018** (peer-reviewed): *SIAM J Matrix Anal Appl* 39(1):342–345, DOI 10.1137/17M1143757; its abstract shows \(1+\sqrt{2}\) is sharp only within the functional-analysis lemma it isolates from the Crouzeix–Palencia argument, so it says nothing about the full conjecture. **Lorist–Schwenninger 2026** (arXiv preprint, not peer-reviewed): the record lists v1 (2026-08-04) and v2 (2026-08-17); the full v2 PDF claims a proof of \(C=2\) using a perturbation lemma for 2-dilations, discloses AI assistance, and states that a separate proof appeared independently. **Jin 2026** (separate preprint, posted late July 2026 and revised; sources give 2026-07-24 and 2026-07-27 for the first posting; not peer-reviewed): claims a proof of \(C=2\) and reports AI assistance. The author's repository states that formal peer review is pending and that audits found no specific error; that is the author's own statement. **Townsend–Greenbaum 2026** (SIAM News essay, dated 2026-08-15): reported to say that they and Crouzeix reviewed Jin's argument and believe it is correct. This is an author-reported expert assessment in a magazine essay. It is not peer-reviewed publication of the proof, and Crouzeix's own check is known here only through their account. This audit did not validate either proof and does not call the conjecture settled or open | No. The conjecture concerns operators/matrices and numerical range; neither the peer-reviewed bounds nor either preprint claim establishes EP2 recovery, EEG measurement, or biological interpretation | SIAM records, full arXiv v2 record and PDF inspected 2026-10-23. Jin, Townsend–Greenbaum, and the Lorist–Schwenninger independence statement were located by web search on 2026-10-23 UTC (search descriptions plus the Jin repository page); the Townsend–Greenbaum PDF and Jin's preprint text were not opened in that refresh |

No participant data or third-party code was executed. Parameter values for any four-shell model must be taken from the cited source or declared as synthetic; they are not automatically biological.

## Round 6 claim matrix (concise)

| Claim ID | Statement (proposed) | Category | Primary source / note | Evidence required to advance | Status |
|----------|----------------------|----------|-----------------------|------------------------------|--------|
| R6-001 | 2D phase-winding / cochain engine computes a topological descriptor from sensor phase | Numerical implementation claim | Prior TTM-004 (graph β₁ ≠ spatial charge) | Deterministic fixture vs known cochain/Hodge reference; sensitivity to phase zeros and filtering | Unverified |
| R6-002 | Four-shell concentric-sphere model is a valid EEG forward model | Borrowed physical model | Næss et al. 2017 DOI 10.3389/fnhum.2017.00490 | Limiting-case match to homogeneous sphere; declared radii/conductivities; not realistic head geometry | Model only |
| R6-003 | Homogeneous-shell boundary enhancement ratio is (2l+1)/l | Formal mathematical identity (conditional) | Series expansion of sphere potential; normalization must be checked against Nunez/Næss | Explicit term-by-term derivation under the stated boundary conditions | Requires verification |
| R6-004 | MNE CSD parity holds for the implementation | Numerical implementation claim | Perrin et al. 1987; MNE source | Version-pinned numerical agreement on synthetic sphere within tolerance | Unverified |
| R6-005 | DMD recovers an exact EP2 on synthetic data | Numerical implementation claim (synthetic) | Prior TTM-003; claim_language.md rule 5 | Synthetic fixture only; classical null of equal complexity must fail | Synthetic only |
| R6-006 | Surrogate tests and BIDS inventory/preregistration checks are performed | Operational / engineering | Repository contracts | Locked pipeline, finite-JSON reports, no empirical promotion | Engineering |
| R6-007 | “Origin-invariant” charge-separation terminology identifies a cortical propagating wave | Speculative interpretation | None primary | Source-space vs sensor-space discrepancy under volume conduction, reference, montage, inverse non-uniqueness | Unverified |
| R6-008 | Crouzeix's conjecture (constant 2) licenses EP2 or charge recovery | Speculative interpretation | Crouzeix–Palencia 2017 proves the \(1+\sqrt{2}\) bound; two separate 2026 preprints (Jin; Lorist & Schwenninger arXiv v2, 2608.03841) each claim a proof of \(C=2\); Townsend–Greenbaum report checking Jin's (author-reported) | Even a correct mathematical proof would not establish EP2 recovery or a biophysical mapping; neither follows from these operator-theory sources | Unverified |

## Sensor-space phase winding / derived charge moment vs cortical propagating wave

Sensor-space phase winding or a derived charge moment does **not** identify a cortical propagating wave under the following confounds (explicitly carried forward from the prior theory-to-measurement review):

- **Volume conduction:** Linear mixing of sources can produce apparent phase structure on the scalp.
- **Reference / montage:** Average or linked-ear references and electrode geometry alter phase estimates.
- **Spatial sampling:** Limited sensors cannot resolve fine spatial gradients required for true winding.
- **Filtering and phase uncertainty:** Hilbert or wavelet phase is undefined or unstable near amplitude zeros; bandpass choices introduce group delay.
- **Inverse non-uniqueness:** Multiple source configurations (including non-propagating) are consistent with the same sensor data.
- **Source orientation:** Radial vs tangential dipoles produce different surface patterns under spherical models.
- **Classical explanations:** Thresholded connectivity, filtered noise, or simple traveling-wave surrogates can generate similar descriptors.

A feature that is computable on sensors remains an operational measurement claim until it survives source-space reconstruction, pairwise + spatial-surrogate nulls, and montage/reference sensitivity on independent empirical data.

## Validation distinctions

1. **Shell boundary-condition validation:** Matching potential and normal current at layer interfaces in the analytical four-shell solution (Næss et al. 2017). This is a mathematical check of the model.
2. **Complete dipole-to-sensor forward projection:** Numerical agreement of the full series solution (or FEM/BEM) with a reference implementation for a dipole inside the innermost sphere, including the outer boundary condition with air. This is still a model validation, not empirical.
3. **Empirical detector performance:** Classification or recovery of a proposed biological construct (propagating wave, topological charge, EP) on real EEG under locked controls, pairwise baselines, and full provenance. Round 6 does not establish this. Project remains HOLD / SYNTHETIC_ONLY.

## Reconciliation with prior review

- Prior TTM-001, TTM-002, TTM-003, TTM-004, TTM-005 remain unchanged. Round 6 does not upgrade any of them.
- Graph β₁, spatial winding, and scalar chirality remain distinct (claim_language.md).
- Open-quantum / EP layers remain speculative.
- Higher-order literature downgrades are preserved.
- No VALIDATED or scientific PASS is introduced.

## Smallest next falsification experiment

On a single, locked synthetic four-shell sphere (declared radii and conductivities from Næss et al. 2017 or an explicit fixture):

1. Compute the analytical surface potential for a known radial and tangential dipole.
2. Compare the implementation’s output to the analytical series (including the claimed (2l+1)/l term) within a pre-registered tolerance.
3. Apply the phase-winding / cochain operator to the synthetic sensor data and to a phase-randomized surrogate of the same power spectrum.
4. Report the difference as a finite JSON; do not interpret as biological.

Any claim that the operator identifies a cortical propagating wave must remain unverified until an independent empirical dataset survives source-space + pairwise/spatial-surrogate nulls under the repository’s falsification contract.

## What remains unverified

- Exact normalization of the homogeneous-shell ratio (2l+1)/l against the primary series expansion.
- Numerical parity of the four-shell implementation and MNE CSD on a shared fixture.
- DMD recovery of an exact EP2 beyond synthetic data.
- Any mapping from sensor-space phase winding or “origin-invariant” charge to a cortical propagating wave.
- Mathematical correctness and peer-reviewed publication/acceptance status of each separate proof claim: arXiv:2608.03841v2 (Lorist–Schwenninger) and Jin's preprint. This audit did not independently validate either proof.
- The Townsend–Greenbaum (with Crouzeix) assessment of Jin's proof is an author-reported check, not peer review and not an independent verification by this audit.
- Biological relevance of Crouzeix's conjecture, which is unestablished independent of those statuses.

## Explicit non-promotion

This audit does not introduce VALIDATED status. No claim is promoted. Round 6 proposals remain proposals. The project status HOLD / SYNTHETIC_ONLY is preserved. A claim audit is not scientific evidence.

**Changed paths:** `docs/research/batch3/grok_chat_a_round6_claim_audit.md`  
**Sources:** Direct publisher links and pinned source links are in the source table; prior theory-to-measurement review and repository claim-language policy provide context only, not independent scientific evidence.<br>
**Evidence limits:** Public primary sources only; no datasets downloaded, packages installed, or third-party code executed. The Crouzeix sources establish that two 2026 preprints each claim a proof of the constant 2 and that Townsend and Greenbaum report checking one of them; this audit does not adjudicate either proof's correctness or peer-review status. A claim audit is not scientific evidence.
