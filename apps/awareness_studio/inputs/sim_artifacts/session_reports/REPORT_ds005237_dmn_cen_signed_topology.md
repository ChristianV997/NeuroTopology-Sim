# ds005237 (Transdiagnostic Connectome Project) — does the signed/localized topology instrument add anything in a *psychiatric* domain?

Every prior real-data test of the signed/localized phase-topology metrics was on
a large discrete state transition where topology moves hard (propofol sedation —
the metric won decisively, gated twice; Parkinson's — large unsigned effect). This
task asks the harder question: does the instrument add anything over the standard
amplitude-correlation DMN–CEN connectivity that the psychopathology literature
uses? **Answer up front: barely, and not robustly. This is closer to a null than
to the ds005620 win, and it supports the interpretation that the instrument's power
is specific to large discrete state transitions, not general to psychiatric trait
differences.**

---

## 1. Cohort, atlas, phenotype

- **OpenNeuro ds005237**, denoised+GSR **parcellated timeseries provided by the
  dataset** (`fMRI_timeseries_clean_denoised_GSR_parcellated/`) — sidesteps the
  no-retained-timeseries gap that blocked ds000245. `provenance="real_fmri"`.
- **240/241 processed OK, 1 missing file, 0 errors.** With covariates:
  **149 Patient / 91 GenPop** (healthy comparison). (The 5 non-redistributable
  participants are already absent from the release.)
- **Atlas: Schaefer-2018 400-parcel 17-network** (cortical parcels 0–399) + 34
  subcortical/cerebellar (434 total; parcels 434≠rest-TR 488≠Stroop-TR 510
  confirmed parcel count). The atlas is **not shipped with the dataset** and the
  README doesn't name it (preprint egress-blocked), so it was **inferred and then
  empirically validated**: with the standard Schaefer 17-network partition,
  within-DMN FC = 0.138 and within-CEN FC = 0.145 vs global-mean 0.014 (~10×),
  confirming parcels 0–399 follow standard Schaefer order — a non-circular check
  (the published partition predicts which parcels co-fluctuate; the data confirm
  it). **DMN = DefaultA/B/C (79 parcels), CEN = ContA/B/C frontoparietal (61
  parcels)**, both auditable from the published atlas, not hand-picked.
- **Rumination measure: Ruminative Response Scale (`rrs01.tsv`)**, total = sum of
  22 items, matched by NDAR `subjectkey` (224/240 subjects have RRS). TR = 0.8 s.

## 2. fMRI-phase methodological choice (Step 2, stated plainly)

BOLD has no fast oscillatory phase. Primary analysis = **Hilbert analytic phase of
BOLD band-passed to 0.01–0.1 Hz** (established phase-coupling technique — Glerean
2012; Cabral LEiDA 2017), a **single** band (EEG's δ/θ/α/β/γ boundaries are
physiological to EEG and were **not** transferred to hemodynamics). Parcels
projected **top-down (axial x-y of MNI centroids) + Delaunay**, exactly analogous
to the EEG sensor-montage treatment. **Limitation, explicit:** the axial projection
collapses the dorsal-ventral (z) axis, so the winding is over an axial 2D
projection, not the folded cortical manifold — a pragmatic analog, not a true
cortical-surface phase field. This is the first time this project's signed-winding
approach has run outside EEG's native fast-oscillation regime; the whole result
should be read with that caveat.

## 3. Head-to-head — standard vs signed (the central question)

### Categorical (Patient vs GenPop)

| metric | kind | Patient | GenPop | d | p |
|---|---|---|---|---|---|
| DMN–CEN correlation | **STANDARD** | 0.0947 | 0.0982 | −0.07 | 0.62 |
| within-DMN corr | STANDARD | 0.146 | 0.158 | −0.19 | 0.15 |
| within-CEN corr | STANDARD | 0.152 | 0.155 | −0.06 | 0.66 |
| **DMN \|charge\|** | **SIGNED** | 11.96 | 11.48 | **+0.28** | **0.033** |
| **defect clusters** | **SIGNED** | 7.28 | 7.14 | **+0.27** | **0.044** |
| CEN \|charge\| | SIGNED | 7.31 | 7.18 | +0.13 | 0.34 |
| DMN/CEN net charge, chirality | SIGNED | — | — | \|d\|≤0.10 | ns |

**The standard amplitude-correlation DMN–CEN metric is fully null** (no group
difference — the hyperconnectivity signature does not replicate as a categorical
effect here). **The signed metric shows a nominal Patient>GenPop effect on DMN
phase-defect charge and defect-cluster count** (d≈0.28) that the standard metric
does not — the ds005620-style "signed sees what standard doesn't" direction.

### Dimensional (RRS rumination, n=224)

**Every metric is null** — standard *and* signed (all |r| < 0.11, p > 0.10). Neither
approach tracks rumination severity dimensionally. The dataset's core
transdiagnostic-dimensional hypothesis is not supported by either instrument here.

## 4. Does the signed group effect hold up? — gate, permutation, confounds

- **Group-label permutation** (5000 shuffles, distinct from the phase-randomization
  gate): DMN \|charge\| p = 0.047, clusters p = 0.043; standard DMN–CEN p = 0.64.
  So the *raw* signed group contrast is nominally real vs a relabeling null, and
  the standard one is null.
- **Confound control is where it breaks.** Regressing each metric on group + age +
  site + motion(FD): DMN \|charge\| group effect **p = 0.098**, clusters
  **p = 0.067** — both drop to non-significant. The culprit is **age**: DMN \|charge\|
  correlates with age (r = +0.12, p = 0.057) and cluster count with age (r = +0.13,
  p = 0.05), and the 18–70 sample is much wider than prior datasets. Site: CEN
  \|charge\| shows a site effect (p = 0.03) but DMN \|charge\|/clusters do not. FD:
  used denoised+GSR data; headline metrics not FD-driven.
- **Multiple comparisons:** 10 metrics tested; the two nominal signed hits (p =
  0.033, 0.044) do **not** survive Bonferroni (×10) and are borderline under FDR.
- **Phase-randomization gate (metric validity):** the identical signed regional
  |charge| metric passed decisively on ds005620 (z ≈ −13, 80/80) and ds003969
  (z ≈ −10), establishing it measures genuine spatial phase structure, not a
  spectral artifact. A BOLD-specific gate on this data (3 subjects, 200 FT
  surrogates each; a full-cohort gate is expensive on 400 parcels) gives
  **z = −7.1, −3.5, −4.3 (mean −5.0), passes 3/3** — real DMN |charge| sits below
  the phase-randomized null, confirming the BOLD signed metric also measures
  genuine spatial phase structure. So the metric is valid; the group difference is
  simply small and age-confounded, not artifactual.
- **Medication:** the released phenotype has no clean psychotropic-medication field
  (`demos.tsv` is malformed; only substance-use questionnaires exist) — so
  medication **could not be controlled** and is a stated caveat, not a resolved
  confound.

## 5. Verdict — undecorated

**In this psychiatric/transdiagnostic domain the signed/localized instrument did
NOT add robust information over standard connectivity.** It produced a *nominal*
group difference (DMN phase-defect charge and clustering, d≈0.28) where the
standard amplitude-correlation DMN–CEN metric was fully null — but that signed
effect **does not survive age+site+motion control (p≈0.07–0.10), does not survive
multiple-comparison correction, and has no dimensional counterpart** (neither metric
tracks RRS rumination). This is a real and useful negative result: unlike propofol
(decisive win, gated twice) and Parkinson's (large unsigned effect), a psychiatric
*trait* contrast does not move the signed phase-topology enough to beat standard FC
robustly — **consistent with the instrument's power being specific to large,
discrete state transitions (anesthesia, pathology) rather than general to
psychiatric trait/state differences.** The standard DMN–CEN hyperconnectivity
signature also failed to replicate categorically or dimensionally in this dataset
with this parcellation — so the honest reading is that *neither* instrument found a
robust DMN–CEN psychopathology marker here, and the signed one's small edge is
age-confounded.

## 6. Limitations specific to this first-outside-EEG application

Axial 2D projection (collapses z); single resting band (no principled BOLD
sub-banding); BOLD Hilbert phase is a debated construct; medication uncontrolled;
Stroop directed-cognition contrast not run (time); the signed group edge is
age-confounded and correction-fragile. The durable, reusable deliverable is
`dual_engine/bold_phase_topology.py` (tested) — the honest scientific deliverable
is the negative verdict above.
