# ds005237 Stroop — does the signed topology detect CEN state-engagement, replicating the ds003969 beta finding?

This tests the prior ds005237 report's own conclusion (the signed instrument's
power looks specific to large discrete *state* transitions, not slow *trait*
variation at rest) on the dataset's within-subject **Stroop incongruent>congruent
state contrast** — a well-powered, trial-level driver of the same fronto-parietal
cognitive-control engagement whose reduction was this project's clearest surviving
EEG finding (ds003969 beta decrease during meditation vs directed thinking). This
is a cross-modality (BOLD, not EEG), cross-paradigm (Stroop, not meditation)
replication attempt of that finding.

**Verdict up front (outcome (c) of the task's three): the signed/localized
instrument detects NO incongruent>congruent CEN signature here — not
parametrically, not by permutation, not against behaviour. The ds003969 beta-band
cognitive-control signature does not cross-replicate to fMRI BOLD phase-topology on
this task.** Reused unchanged: Schaefer-400 17-network atlas + DMN/CEN parcel lists
(ContA/B/C=61, DefaultA/B/C=79), BOLD Hilbert phase 0.01–0.1 Hz, axial projection,
`signed_defect_topology_from_band`, `surrogate_testing`.

---

## 1. Cohort & windowing

- **221/241 usable.** 15 subjects lack Stroop runs (dataset design — README notes
  Stroop n≈226/224); **5 excluded** for malformed events.tsv (missing `onset`
  column) — reported, not reconstructed. `provenance="real_fmri"`. Patient=134,
  GenPop=87.
- **Windowing (primary, trial-locked):** Hilbert phase computed on the **whole run**
  (0.01–0.1 Hz) to avoid short-epoch filter artifacts; signed topology then computed
  on the phase **restricted to each condition's HRF-window TRs** ([onset+3, onset+9]s,
  capturing the BOLD peak+tail), with TRs claimed by both conditions (jittered-ISI
  overlap) excluded and **high-motion TRs (FD>0.5 mm) excluded per trial** (the
  event-related-specific motion control). Typical yield ≈ 244 congruent / 88
  incongruent TRs per run. **AP + PA runs averaged** (per-condition estimates).
- **Standard comparator (secondary, whole-run GLM):** canonical-HRF first-level GLM,
  incongruent>congruent activation beta per parcel, averaged over CEN/DMN — the
  dataset paper's activation logic. **These two are methodologically distinct and
  are not conflated:** trial-locked-signed ≠ whole-run-GLM.

## 2. Head-to-head — standard GLM vs trial-locked signed (CEN, with DMN alongside)

*A-priori prediction (frontoparietal-control-network literature): CEN should move
on this contrast; DMN should be comparatively unresponsive or move oppositely.*

| metric | kind | value (inc−con or activation) | dz | p |
|---|---|---|---|---|
| **CEN GLM inc>con** | STANDARD | **−1.00** | −0.44 | 4e-10 |
| DMN GLM inc>con | STANDARD | −0.50 | −0.22 | 0.001 |
| **CEN \|charge\|** inc−con | SIGNED | −0.011 | −0.02 | 0.78 |
| DMN \|charge\| inc−con | SIGNED | +0.086 | +0.09 | 0.17 |
| CEN net charge inc−con | SIGNED | +0.027 | +0.08 | 0.24 |
| CEN chirality inc−con | SIGNED | +0.0002 | +0.02 | 0.81 |
| defect clusters inc−con | SIGNED | −0.026 | −0.08 | 0.24 |

- **The trial-locked signed metric is fully null** for CEN and DMN on every
  quantity (|dz| ≤ 0.09, all p > 0.17). Within-subject condition-label permutation
  (5000 shuffles) confirms it: CEN \|charge\| perm-p = 0.77, DMN 0.17, clusters 0.24.
- **The standard GLM shows a strong but NEGATIVE CEN inc>con contrast** (dz = −0.44),
  the *opposite* of the expected cognitive-control activation. **This is almost
  certainly a preprocessing artifact, and it is the key methodological caveat of
  this task:** the only timeseries the dataset provides are `clean_denoised_GSR` —
  aggressively denoised **with global signal regression, for connectivity**, not for
  task activation. GSR is well known to distort/invert task-activation contrasts. So
  the standard comparator on this data is **compromised**, and one cannot claim
  "signed misses what standard finds" — rather, *neither* approach cleanly recovers
  the expected positive CEN activation from this GSR'd connectivity-preprocessed
  data. A clean activation test would need the non-GSR raw BOLD + a task-appropriate
  pipeline (out of scope; flagged).

## 3. Surrogate gate & permutation

- **No signed headline effect exists to gate** — every signed inc−con contrast is
  null. The within-subject condition-label **permutation** (the decision-relevant
  "is the contrast real" test) confirms null (above). The signed |charge| metric's
  *validity* (that it measures genuine spatial phase structure, not artifact) was
  already established on this exact dataset in the prior ds005237 run
  (phase-randomization gate z ≈ −5, passes 3/3) — so the null is a true absence of a
  condition effect, not an insensitive/broken metric.

## 4. Behavioral (dimensional individual-differences test)

The signed CEN inc−con contrast does **not** track each subject's own Stroop RT
effect (r = −0.04, p = 0.57; DMN r = +0.05, p = 0.51; clusters r = −0.02, p = 0.77),
n = 221. The classic behavioral Stroop cost is present in the data (mean RT
inc−con ≈ +0.22 s), so the null is not for lack of a real behavioral effect — the
neural signed signature simply doesn't scale with it.

## 5. Diagnostic group on the task-state axis (secondary, exploratory)

On the inc−con contrast, Patient vs GenPop: CEN \|charge\| d = +0.24, **p = 0.083**
(a non-significant trend, Patients slightly higher), CEN GLM d = +0.07 (p = 0.61),
clusters d = −0.01 (p = 0.95). Nothing significant. (Marked secondary — the primary
question is state-vs-state, not group.)

## 6. Confounds

Standard CEN GLM activation: not age- (r = +0.09, p = 0.19) or site- (p = 0.32)
confounded. Signed metrics are null so covariate control is moot. Event-related
motion handled by per-trial FD>0.5 mm TR exclusion (a task-specific control absent
in the resting run). Medication uncontrolled (not cleanly in the phenotype, as in
the prior run).

## 7. Verdict — undecorated

**Outcome (c): the signed/localized phase-topology instrument does NOT detect a
CEN-specific incongruent>congruent state-engagement signature on the Stroop task,
in this modality and dataset.** It is null parametrically (|dz| ≤ 0.09), by
within-subject permutation (p ≥ 0.17), and against individual behavioral Stroop
effect (p ≥ 0.57), with only a non-significant group trend. **The ds003969 EEG
beta-band cognitive-control finding does not cross-replicate to fMRI BOLD
phase-topology here.** Combined with the resting-state null in the prior ds005237
run, this is consistent — now across two ds005237 designs (trait-rest and
state-task) — with the interpretation that the signed instrument's demonstrated
sensitivity is **specific to large, discrete physiological state transitions
(propofol sedation — decisive, twice-gated; and, by unsigned metrics, PD pathology)
rather than to psychiatric trait variation or to task-level cognitive-control state
shifts.** Honest bound on the claim: the standard activation comparator is itself
compromised on this GSR'd connectivity data, so this is a null for the *signed
phase-topology* approach specifically — not proof that no CEN engagement exists in
these data, only that this instrument, applied to the provided timeseries, does not
capture it.

## 8. Limitations specific to this application

Provided timeseries are GSR+connectivity-denoised (distorts the standard activation
comparator; would ideally re-derive from raw BOLD); BOLD Hilbert-phase and axial 2D
projection carried over from the prior run's stated caveats; trial-locking selects
HRF-window TRs from a whole-run phase (a reasonable but non-standard adaptation);
medication uncontrolled. Durable tested deliverable: `dual_engine/bold_task_epoching.py`.
