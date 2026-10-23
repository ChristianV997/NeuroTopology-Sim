# Round 6 Claim Audit (Batch 3, Grok Chat Agent A)

**Audit date:** 2026-10-16 (source notes re-verified 2026-10-23)<br>
**PR base at review:** `3f3fe8593303184cb88eef056c1322f3d4e57a16`<br>
**`main` at 2026-10-23 re-verification:** `2c8a80bf9874b9f14205d4bb4e466754fb4589cb` (the earlier note named `a65611adcf4490a0d2378cbecb92dd883f4c5f0a`, which was `main` at the first review and is no longer current)<br>
**Prior artifact:** `docs/research/batch3/theory_to_measurement_review.md` on open PR #393 (`batch3/grok-chat-a-theory-to-measurement`, HEAD `5634a707` at first review; `7b9be88e7a2e84a279b7c7204cd284680fbca7ff` on 2026-10-23, and the file is still not on `main`). This document does not overwrite that history.<br>
**Project status:** HOLD / SYNTHETIC_ONLY. Round 6 proposals are not established.  
**Retrieval dates:** 2026-10-21 (first pass); 2026-10-23 (re-verification). On 2026-10-23 publisher, DOI, arXiv, PMC and MNE-docs hosts were not directly reachable from the verifying environment, so those checks used the primary pages' text as returned by search, plus the pinned MNE 1.13.2 source for the MNE statements. Items that could not be confirmed against the primary page are marked *unconfirmed*.

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
| Four-shell concentric-sphere EEG forward model | Næss et al. 2017, “Corrected Four-Sphere Head Model for EEG Signals,” *Front Hum Neurosci* 11:490 | DOI: 10.3389/fnhum.2017.00490; published 2017-10-18 | Yes for corrected analytical formulas of a four-layered concentric sphere (brain/CSF/skull/scalp) and FEM consistency checks; not a realistic head, not empirical EEG validation, and parameter values must be declared. The paper reports that the earlier published formulas were wrong and that the corrected ones agree with FEM simulations; it uses the conductivities and radii of Nunez & Srinivasan (2006) in its examples | 2026-10-21; re-checked 2026-10-23 |
| Homogeneous-sphere surface potential / boundary | Næss et al. 2017, “Corrected Four-Sphere Head Model for EEG Signals,” limiting-case section (comparison to Nunez & Srinivasan 2006 Eq. 6.7; “§3.2” is the preprint numbering) | [PMC5651266](https://pmc.ncbi.nlm.nih.gov/articles/PMC5651266/); the “Limiting case” section with the Eq. 6.7 comparison is confirmed in the bioRxiv preprint (10.1101/124875). Its section number in the published Frontiers version is *unconfirmed* | Yes for the model’s stated homogeneous-limit comparison; the specific ratio “(2l+1)/l” is not established by this citation and requires a separate term-by-term derivation with explicit normalization | 2026-10-16; re-checked 2026-10-23 (search text only) |
| MNE CSD / Perrin surface Laplacian | Perrin et al. 1987, *IEEE Trans Biomed Eng* BME-34(4):283–288; Perrin et al. 1989 (spherical splines); MNE-Python 1.13.2 `compute_current_source_density` | Perrin 1987 DOI 10.1109/TBME.1987.326089 (title: “Scalp current density mapping: value and estimation from potential data”; end page reported as 283–287 or 283–288 in different reference lists, *unconfirmed*). The spherical-spline paper itself is Perrin et al. 1989, *Electroencephalogr Clin Neurophysiol* 72(2):184–187. The pinned MNE 1.13.2 `compute_current_source_density` docstring cites the bibliography keys PerrinEtAl1987, PerrinEtAl1989, Cohen2014 and KayserTenke2015 (confirmed in the 1.13.2 source; the bibliography entries were not retrieved) | Yes for the spherical-spline surface-Laplacian method as implemented in MNE; not identity or parity with this repository’s implementation or with cortical charge. MNE's output is a numerical spherical-spline surface Laplacian of scalp potentials; agreement with it on a synthetic fixture would be a numerical comparison, not implementation parity, EEG measurement, or biological inference | 2026-10-21; re-checked 2026-10-23 |
| Crouzeix C=2 | Crouzeix & Palencia 2017, *SIAM J Matrix Anal Appl* 38:649–655 (DOI 10.1137/17M1116672); Ransford & Schwenninger 2018, *SIAM J Matrix Anal Appl* 39:342–345 (DOI 10.1137/17M1143757) | Peer-reviewed bound: \(1+\sqrt{2}\) (Crouzeix & Palencia 2017, vol. 38 no. 2, DOI confirmed). Ransford & Schwenninger 2018 (vol. 39 no. 1, pp. 342–345; DOI *unconfirmed* in re-check) give a short proof of the key lemma and show \(1+\sqrt{2}\) is sharp *within that lemma*, not as a bound on the conjecture. \(C=2\) is the conjectured constant. **Newer preprint, not peer-reviewed in my retrieval:** Lorist & Schwenninger, “A solution to Crouzeix’s conjecture,” arXiv:2608.03841 (submitted 2026-08-04, v2 2026-08-17), claims a proof of \(C=2\); other 2026 preprints cite it. Its argument and refereeing status were *not* verified here, so this audit treats \(C=2\) as “claimed in an unrefereed preprint, not established by the peer-reviewed literature retrieved” and does not call it an open conjecture without qualification | No. Whether or not \(C=2\) holds, it is a statement about matrices and the numerical range; it does not establish EP2 recovery, EEG measurement, or biological interpretation | 2026-10-21; re-checked 2026-10-23 |

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
| R6-008 | Crouzeix C=2 licenses EP2 or charge recovery | Speculative interpretation | Crouzeix–Palencia 2017 proves \(1+\sqrt{2}\); a 2026 arXiv preprint (2608.03841) claims \(C=2\) but is unrefereed and unverified here | A refereed proof of \(C=2\) *and* an independent biophysical mapping; the mapping does not exist regardless of the pure-math status | Unverified |

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
- Status of the claimed proof of Crouzeix C=2 (arXiv:2608.03841): unrefereed in this retrieval, argument not checked.
- Biological relevance of Crouzeix C=2, which is unestablished independent of that status.

## Explicit non-promotion

This audit does not introduce VALIDATED status. No claim is promoted. Round 6 proposals remain proposals. The project status HOLD / SYNTHETIC_ONLY is preserved. A claim audit is not scientific evidence.

**Changed paths:** `docs/research/batch3/grok_chat_a_round6_claim_audit.md`  
**Sources:** Næss et al. 2017 (DOI 10.3389/fnhum.2017.00490), Perrin et al. 1987 (DOI 10.1109/TBME.1987.326089), MNE-Python 1.13.2 CSD documentation, Crouzeix & Palencia 2017 (DOI 10.1137/17M1116672), Ransford & Schwenninger 2018 (DOI 10.1137/17M1143757, unconfirmed), Lorist & Schwenninger 2026 preprint (arXiv:2608.03841, unrefereed), Perrin et al. 1989, prior theory-to-measurement review, claim_language.md.<br>
**Evidence limits:** Public sources only; no dataset downloads; no package installs; no third-party code executed. The 2026-10-23 re-verification could not open the primary hosts directly and did not read the Lorist–Schwenninger argument; it is a source-note check, not a mathematical review.
