# Claim levels audit: Round 6 claims and geometry/model audits

Status: `HOLD / SYNTHETIC_ONLY`. This document classifies claims. It does not validate them.
Base: `origin/main` at `19c3203`. Adjacent audits are cited at the head SHAs they had when reviewed.
Nothing here was executed. No candidate model or implementation was run.

## The five levels

| Level | Name | Question it answers | Does not answer |
|---|---|---|---|
| 1 | Formal or borrowed mathematical identity | Is the equality true under stated axioms, boundary conditions, and normalization? | Whether a sensor measures anything |
| 2 | Implemented numerical descriptor | Does code reproduce the formula within tolerance on synthetic input? | Whether the descriptor measures the intended construct |
| 3 | Operational sensor-space measurement | Is the quantity computable from the recording channels as declared? | That the quantity is the intended construct |
| 4 | Empirical claim | Does the construct show the stated effect on real data under locked controls? | Anything, until the data and design exist |
| 5 | Mechanistic or phenomenological interpretation | What does the effect mean for a process or an experience? | Anything from levels 1 to 3 |

A level-2 or level-3 result never advances to level 4 or 5. Computability is reported separately
from construct validity, and construct validity is `NOT_ESTABLISHED` everywhere in this project.

## Claim classification

| Claim (source) | Level | Category | Computable at base? | Construct validity | Confounds / alternatives | Falsifiers |
|---|---|---|---|---|---|---|
| R6-002: four-shell concentric-sphere model is a valid EEG forward model (PR #412, citing Næss et al. 2017; citation metadata not independently verified in this review) | 1 borrowed; 2 not implemented | `other_declared` | **No.** No four-shell implementation exists on `main` or on any open PR branch inspected. | Not applicable: no measurement | Realistic head geometry is absent. Declared radii and conductivities are model-specific. | Limiting-case match to a homogeneous sphere; boundary-condition residuals; 7×7 vs 8×8 consistency for fixed `b1` (PR #409) |
| R6-003: homogeneous boundary ratio is (2l+1)/l (PR #412, PR #409) | 1 conditional | `other_declared` | Derived in the PR #409 oracle specification only. No implementation. | Not applicable | The ratio depends on normalization of the series terms | Term-by-term check against the primary series. Not re-verified here. |
| R6-004: MNE CSD parity holds for the implementation (PR #412) | 2 | `sensor_space_phase_gradient` or `other_declared` | Existing MNE routine. Parity was not tested here. | Not applicable | Parity is numerical agreement, not an identity with cortical charge | Version-pinned agreement on a synthetic sphere within tolerance |
| R6-001: phase-winding or cochain engine computes a topological descriptor from sensor phase (PR #412) | 2 and 3 | `sensor_space_winding` | Not verified at base | Not established | Volume conduction, reference and montage, spatial sampling, filtering and phase uncertainty, inverse non-uniqueness, source orientation | Sensitivity to phase zeros and filtering; surrogate of identical spectrum; graph β₁ is not spatial charge |
| R6-005: DMD recovers an exact EP2 on synthetic data (PR #412) | 2 on synthetic input only | `synthetic_detector` | Synthetic fixture only | Not established | Classical null of equal complexity | Classical null must fail; any biological reading is level 5 and is not admitted |
| R6-007: origin-invariant charge-separation terminology identifies a cortical propagating wave (PR #412) | 5 speculative | `origin_shift_identity` | Not applicable to the target | **Not established.** Identity claimed for a cortical wave with no source-space evidence. | Volume conduction, reference, montage, spatial sampling, filtering, inverse non-uniqueness, source orientation, and thresholded connectivity or filtered noise | Source-space versus sensor-space discrepancy; pairwise and spatial-surrogate nulls on independent empirical data. This contract rejects the equivalence (`EQUIVALENCE_TO_TARGET_CONSTRUCT`). |
| R6-008: Crouzeix C = 2 licenses EP2 recovery or charge recovery (PR #412; source citation not independently verified in this review) | 1 speculative | `other_declared` | Not applicable | Not established | The conjecture is speculative for this use. The citation and peer-review status were not independently checked here. | Peer-reviewed proof plus a biophysical mapping. Neither is established here. |
| Finite-jitter triangulation claims (PR #410) | 2 specification | `other_declared` | **No candidate found.** The auditor tests an independent geometric specification on synthetic meshes. | Not applicable | Area equality and angular sorting can hide overlaps; a Delaunay property is not tested | Exact-predicate checks: hull correspondence, crossings, pairwise intersections |
| Four-shell BVP equation oracle (PR #409) | 1 and 2 specification | `other_declared` | **No candidate found.** The oracle is derived from the assignment's basis and boundary conditions only. | Not applicable | The missing module's source, sensor, orientation, and sign mapping are unspecified | Continuity residuals; homogeneous-limit check; the 7×7 versus 8×8 discrepancy |

## What the geometry and model audits establish

- **PR #409 establishes a specification, not an implementation.** Its oracle derives the boundary
  system for a four-shell sphere and reports the 7×7 versus 8×8 discrepancy. It does not test a
  candidate model, because none exists at the base. Its disposition is `HOLD / SYNTHETIC_ONLY`.
- **PR #410 establishes a geometric consistency checker, not a Delaunay certificate.** Its
  checks are exact on the meshes supplied to it. It rejects gaps, overlaps, crossings, and incorrect
  boundaries. Its own report states that the adversarial square passes area and Euler counts while
  its faces overlap. Passing area equality is therefore not evidence of a valid triangulation.
- **PR #412 establishes a claim matrix with sources, not evidence for any claim.** Its
  distinctions are the ones this contract enforces: formal identity, numerical implementation,
  borrowed model, operational measurement, empirical claim, and speculative interpretation.

## Consequences for this contract

1. A proposal that equates a restricted descriptor with a cortical wave, source localization,
   consciousness, or biological validation is rejected for every category. The Round 6 claim R6-007
   is a regression fixture: `origin_shift_cortical_wave_equivalence.json`.
2. A computable descriptor is reported as `computable: true` and `measures_intended_construct: false`.
   Those two fields are independent, and the second is never true in this contract.
3. A level-1 identity is admissible only with stated conditions and normalization. R6-003 would be
   `borrowed_formal_identity` with an unverified normalization, so its status stays open.
4. No level-4 claim is run. Every empirical claim block reads `status: NOT_RUN` and
   `data_access: NOT_AUTHORIZED`.

## What this document does not establish

- It does not establish that any Round 6 claim is true, false, or measured.
- It does not verify the four-shell formulas against the cited primary source. The source was not re-fetched.
- It does not run any candidate model, triangulator, or forward projection.
- It does not add a statistical utility. Operating-characteristic reporting belongs to the merged
  `analysis/binomial_planning` package (PR #405). Any future synthetic ROC report should cite it, and
  this contract must not report a pass or a validation from it.
