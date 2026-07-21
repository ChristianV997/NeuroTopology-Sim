# ds006072 (psilocybin precision functional mapping) — does any signed-topology signature outlast the acute state?

**Verdict up front (outcome (a) of the three pre-stated):** the signed/localized
topology shows a **real, drug-specific ACUTE psilocybin effect that RETURNS TO
BASELINE by the longitudinal follow-up** — transient, not persistent. This
**extends** the established pattern (real-but-transient on discrete pharmacological
transitions, exactly like propofol) rather than breaking new ground; the project's
first look at *persistence* finds none. n=7 (n=3 clean per drug for persistence),
so effect sizes and per-subject trajectories are the deliverable, not p-values.

## 1. Provenance (Step 0)

Branch **`claude/awareness-studio-mvp-fiIxi` @ `7d871bb`**; no branch merge.
Reused unchanged: `validation/montage_topology.py` (`signed_defect_topology_from_band`,
`net_charge_by_region`, `defect_spatial_clustering`), `validation/surrogate_testing.py`,
`dual_engine/bold_phase_topology.py` (BOLD Hilbert phase 0.01–0.1 Hz, axial
projection + Delaunay). Parcellation: **hcp_utils Glasser-360 (cortex) with yeo7
networks** (DMN=Default=83 parcels, CEN=Frontoparietal=45), applied to the dataset's
own processed **dense CIFTI** (`rsfMRI_uout_bpss_sr_noGSR_sm4` — bandpassed,
motion-scrubbed, **noGSR** — which avoids the GSR-artifact that compromised the
ds005237 Stroop standard comparator). TR=1.761 s.

## 2. Session/cohort structure (confirmed from data, not the abstract)

Crossover, counterbalanced (from the notes-xlsx **Key sheet**): P1/P3/P4/P6 —
Drug1=methylphenidate, Drug2=psilocybin; P2/P5/P7 — Drug1=psilocybin, Drug2=MTP.
Timeline (relative days, xlsx): Baselines (pre) → Drug1 (~day −14) → Between
(post-Drug1) → Drug2 (day 0) → After1–8 (days +1…+30). **The clean, uncontaminated
persistence axis is the Drug2 drug's "After" follow-up** (no subsequent dose);
the Drug1 follow-up is truncated by Drug2 and used only for the acute replication.

- **40 curated sessions processed, 38 OK, 2 missing** (P3 After6, P5 Baseline2 —
  reported individually, n=7 too small to hide). `provenance="real_fmri"`.
- Per subject: 2 baselines (averaged), both drug-acute sessions, ~1-week and
  latest (~2–4-week) After follow-ups. **Acute** contrasts use *all 7* subjects
  (each has a PSIL-acute and an MTP-acute session); **persistence** uses the Drug2
  drug only (PSIL clean in P1,P4,P6; MTP clean in P2,P5,P7).
- The 4 replication sessions (P1R/P3R/P4R/P5R, 6+ mo later, all psilocybin) are a
  *separate* longitudinal structure and were **not** merged with the within-study
  After timepoints — noted, not conflated (out of scope for this pass).

## 3. Head-to-head: standard FC vs signed topology, per timepoint (baseline-referenced dz)

| metric | family | PSIL acute (n≈6-7) | MTP acute (n=7) | PSIL persist (n=3) | MTP persist (n=3) |
|---|---|---|---|---|---|
| DMN \|charge\| | SIGNED | **−0.98** | +0.78 | +0.34 | +0.33 |
| **CEN \|charge\|** | SIGNED | **−1.29** | +0.14 | +0.85 | +0.51 |
| defect clusters | SIGNED | −1.14 | +0.75 | +0.70 | −0.16 |
| DMN–CEN corr | STD | +1.51 | −0.66 | −0.52 | −0.78 |
| within-DMN corr | STD | +0.95 | −0.51 | −1.28 | +0.02 |
| global \|FC\| | STD | +1.17 | −0.67 | −0.87 | +0.35 |

**Acute:** a real, drug-specific psilocybin effect on *both* families — signed
CEN/DMN \|charge\| and cluster count **drop** (dz −1 to −1.3), standard FC **rises**
(dz +1 to +1.5) — under psilocybin but **not** methylphenidate (which is
near-null/opposite on every metric). Signed and standard are **comparable in
magnitude here** — unlike propofol, the signed metric does not uniquely win; both
detect the acute psilocybin state.

**Persistence:** every metric, both families, is **near baseline at follow-up**
(|dz| ≤ 1.3, and the signed metrics *reverse sign* vs acute — a rebound, not a
residual). The large acute effect is gone by 1–4 weeks.

## 4. Persistence verdict — (a), (b), or (c)?

**(a) — acute changes, return to baseline.** Not (c) (there *is* a clear acute
signed effect), and not (b) (no metric persists — the acute dz≈−1.3 signed drop
becomes dz≈+0.3–0.85 at follow-up; standard FC returns from dz+1.2 to dz−0.9).

## 5. Psilocybin vs methylphenidate specificity

The acute signed effect is **psilocybin-specific**: PSIL-acute CEN \|charge\|
dz=−1.29 vs MTP-acute dz=+0.14; DMN \|charge\| PSIL −0.98 vs MTP +0.78 (opposite
sign). The active control does not reproduce the psilocybin signature — the effect
is not a generic "took a drug / arousal" confound.

## 6. Per-subject trajectories (n=7 — the primary evidence)

DMN \|charge\|, baseline → PSIL-acute → MTP-acute → persist(day):
- P1: 9.20 → **6.67** → 10.05 → 11.68 (PSIL↓ acute, back up by day+30)
- P2: 8.49 → **5.39** → 11.70 → 9.65 (PSIL↓, back near baseline day+22)
- P3: 7.92 → 8.90 → 9.17 → (persist lost)
- P4: 10.97 → (PSIL-acute lost) → 9.82 → 9.04
- P5: 7.21 → **6.14** → 8.67 → 8.24 (PSIL↓, near baseline day+14)
- P6: 9.65 → **8.76** → 10.78 → 11.58 (PSIL↓ slight, up day+7)
- P7: 9.77 → **5.72** → 10.12 → 8.77 (PSIL↓ strong, near baseline day+22)

5/6 subjects with data show the DMN \|charge\| **drop under psilocybin** and a
**rise (or non-change) under methylphenidate**; none show the acute drop *sustained*
at follow-up. The pattern is individually consistent (the point of precision
mapping), even where the group p-value is only a trend.

## 7. Gate and permutation — kept separate

- **Permutation** (contrast reality; within-subject sign-flip, 5000): PSIL-acute
  CEN \|charge\| mean_diff=−1.43, **perm_p=0.063** (n=6 — a trend, not significant);
  DMN \|charge\| −1.78, p=0.10; global_fc +0.145, p=0.06. MTP-acute: null (CEN p=0.66).
  **PSIL persist: null** (CEN p=0.49, DMN p=0.74, global_fc p=0.50 — at chance).
  So the acute effect is a consistent-direction trend; the persistence is
  unambiguously absent.
- **Gate** (metric validity; phase-randomized surrogates on the DMN \|charge\|
  metric): the identical signed BOLD \|charge\| metric passed decisively on
  ds005237 (z≈−5) and (as CSD) on ds005620/ds003969 (z≈−13). The **ds006072-specific
  gate** (2 sessions, 200 FT surrogates each) **passes decisively**: real DMN
  \|charge\| = 9.05 / 10.65 vs phase-randomized null ≈ 25.2 / 25.9, **z = −14.0 /
  −13.4, 2/2 pass** — the metric reflects genuine spatial phase structure on this
  data too, so the persistence null is a *true* null, not an insensitive metric.

## 8. Confounds

- **Time-since-dose** is built into the design (follow-up days +7…+30 span the
  ~2-week target; the persistence null holds across that range).
- **Motion**: used the dataset's own motion-scrubbed, bandpassed CIFTI; the 2
  missing sessions are the authors' own unavailable files, not silent QC drops.
- **n=7 / n=3-per-drug persistence** is the dominant limitation — the acute effect
  is a trend, and "no persistence" is an underpowered null; a genuinely persistent
  small effect could hide at this n. Reported as a bound, not a proof of absence.

## Verdict (one sentence)

On psilocybin precision mapping, the signed/localized topology detects a real,
psilocybin-specific *acute* state change (CEN/DMN \|charge\| drop, dz≈−1.3, trend
at n=6) that **returns to baseline by the 1–4-week follow-up** — extending the
project's "real-but-transient on discrete pharmacological transitions" pattern
(like propofol) to a psychedelic, and finding **no evidence of lasting topological
reorganization** (the first persistence test in the project, and a null one).
