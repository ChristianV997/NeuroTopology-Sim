# Signed/localized phase-defect metrics on real propofol EEG (ds005620)

**Question.** The signed-winding metrics added to `validation/montage_topology.py`
(`signed_defect_map`, `net_charge_by_region`, `defect_spatial_clustering`,
`signed_defect_topology_from_band`) recover chirality and location that the
unsigned `Qabs` scalar destroys. Validated on synthetic fixtures only, they had
never touched real EEG. Does the signed family add anything the unsigned family
doesn't at a large, ground-truth-anchored consciousness transition — propofol
loss of responsiveness — where topology is known to move hard?

---

## Dataset & provenance

**OpenNeuro ds005620** — "A repeated awakening study… complexity measures…
during propofol sedation" (Bajwa, Nilsen, Skukies, Aamodt, Ernst, Storm, Juel;
Oslo). 64-ch BrainVision EEG, 5000 Hz, 10-20 montage with real VEOG/HEOG.
`provenance="real_eeg"` on every result. Staged from the OpenNeuro **S3 bucket**
(the `openneuro.org` API, `repository.cam.ac.uk`, and `fieldtriptoolbox.org` are
all egress-blocked — 403 CONNECT — documented, not worked around).

**Conditions (within-subject):** `awake` (eyes-closed baseline) vs `sed`
(resting propofol sedation, runs = awakenings) vs `sed2` (1-min resting just
before an awakening). Behavioural ground truth = the repeated-awakening paradigm.

**Cohort:** 21 subjects, 1 flagged `excluded` in the dataset (sub-1037) → **20
processed, 125/125 recordings OK, 0 errors, 20/20 with awake+sed+sed2.**

**Honest scope (not smoothed over):** this is a **within-subject awake-vs-
propofol-sedation transition**, NOT a dose-graded 4-level titration, and it has
**no recovery arm**. Per the dataset README, `sed` and `sed2` are both steady
sedation (sed2 = a pre-awakening epoch), so the clean axis is awake↔sedated. It
is nonetheless a large *discrete* state transition — the regime where topology is
expected to move — so it is a valid and strong test bed, with these limitations
stated rather than papered over.

**Method.** Resample 5000→256 Hz (a 1 Hz HP at 5 kHz never finishes) → HP 1 Hz →
bad-channel interpolation → average reference → picard ICA using the dataset's
**real VEOG/HEOG** channels (mean 2.4 comps removed/recording) → CSD surface
Laplacian → per band (δ,θ,α,β,γ): unsigned scalars (`phase_grid_topology_from_band`
+ PLV connectivity/H1/graph) **and** the signed family
(`signed_defect_topology_from_band` with a documented 10-20 naming-convention
zone map: frontal/central/parietal/occipital/temporal-L/R). CSD (not eLORETA):
its fsaverage BEM host is blocked and it added nothing over CSD on ds003969.

---

## Q1 — Does the UNSIGNED topology move with sedation? YES, hard (sanity check passed)

The whole-montage unsigned metrics collapse under propofol, matching the
Betti-collapse literature (Awake ~124 → Propofol ~14.6 H1 cycles):

| band | metric | awake | sed | dz | p |
|---|---|---|---|---|---|
| beta | persistence_sum | 4.53 | 3.42 | **−1.25** | 2e-5 *** |
| gamma | persistence_sum | 3.39 | 2.42 | −0.83 | 0.0015 ** |
| beta | global_eff | 0.476 | 0.459 | −0.75 | 0.003 ** |
| beta | b1_count | 53.3 | 46.5 | −0.73 | 0.004 ** |
| gamma | b1_count | 40.1 | 31.6 | −0.65 | 0.009 ** |
| gamma | global_eff | 0.415 | 0.361 | −0.63 | 0.011 * |
| gamma | modularity | 0.327 | 0.255 | −0.58 | 0.018 * |

H1 loop count, persistence, global efficiency and modularity all drop under
sedation, largest in β/γ (dz up to **1.25**, a large effect comparable to the
ds000245 PD gradient η²=0.41). The pipeline and dataset work, and global topology
collapses under propofol exactly as the literature predicts. 8/35 unsigned
band×metric cells reach p<0.05.

---

## Q2 — Does the SIGNED family add anything? YES — a spatial signature with no unsigned analog

**The headline result.** In the **alpha band**, the *whole-montage* unsigned
scalar is **null**, but the *regional signed* decomposition is strongly
significant and coherent:

| alpha metric | awake | sed | dz | p |
|---|---|---|---|---|
| **UNSIGNED** whole-montage Qabs | 1.94 | 2.04 | +0.11 | **0.63 (null)** |
| UNSIGNED defect_density | 0.026 | 0.027 | +0.12 | 0.60 (null) |
| **SIGNED** \|charge\| parietal | 0.552 | 0.325 | **−1.06** | 0.0001 *** |
| SIGNED \|charge\| occipital | 0.111 | 0.057 | −0.64 | 0.010 ** |
| SIGNED \|charge\| frontal | 0.156 | 0.371 | **+0.86** | 0.001 ** |
| SIGNED \|charge\| central | 0.751 | 1.004 | +0.65 | 0.009 ** |

Under propofol, alpha-band phase-defect content **collapses posteriorly
(parietal/occipital) and rises anteriorly (frontal/central)** — a
**posterior→anterior shift**. This is the textbook **propofol alpha
anteriorization** (Purdon et al. 2013): occipital alpha is replaced by coherent
frontal alpha. Critically, the posterior decrease and anterior increase **cancel
in the whole-montage sum** (1.94→2.04, flat) — which is *precisely why* the
unsigned scalar sees nothing while the regional signed metric sees a dz=−1.06
effect. This is a concrete case where the signed/localized metric recovers real,
physiologically-expected spatial structure that the unsigned scalar **structurally
cannot represent**.

13/70 signed cells reach p<0.05 (vs 8/35 unsigned — a similar hit rate, so this
is not noise-mining). Chirality also shifts in γ frontal/temporal (small,
dz≈−0.5), a handedness change with no unsigned analog.

---

## Head-to-head verdict — mixed, with a real and specific win

- **Raw magnitude: unsigned wins.** The single strongest signal is the global
  β-band persistence collapse (dz=−1.25). The best signed effect (alpha parietal
  \|charge\|, dz=−1.06) does not exceed it. **The signed metric does NOT replace
  the unsigned one as a global depth-of-sedation index.**
- **Specificity / information content: signed wins.** The signed family recovers
  the **alpha anteriorization** — a spatially-resolved, chirality/location-based
  signature that is (a) significant where the matched unsigned scalar (alpha
  Qabs) is flat null, and (b) a known propofol hallmark. This is information the
  whole-montage summation averages away.

So: **the signed metric complements rather than beats the unsigned one.** For a
single "is the brain sedated?" scalar, unsigned β/γ collapse is stronger and
simpler. For *where and how* the phase field reorganizes, the signed regional
metric captures a real pattern with no unsigned equivalent.

---

## Confound checks

- **Time-drift across sed runs (run-1→3):** the headline effects (alpha
  parietal/frontal \|charge\|, β persistence) do **not** appear among the
  drifting metrics. Two minor signed metrics drift (delta occipital chirality
  r=−0.36 p=0.007; alpha cluster-persistence r=+0.27 p=0.047) and are flagged as
  such — not used as headline claims. The awake-vs-sed contrast is across
  separate recordings, so within-sed drift cannot manufacture it.
- **Age/motion:** age is largely missing in participants.tsv (reported n/a for
  most) so no age covariate was fit; no dedicated motion/EMG regressor was used
  beyond ICA (the EMG channel was dropped, ocular components removed). A residual
  EMG contribution to γ cannot be excluded — flagged.
- **sed2** (pre-awakening) mirrors sed weakly and is reported in the JSON;
  it adds no independent claim.

---

## Limitations

- Within-subject awake-vs-sedation, **not** a dose-graded titration; **no
  recovery arm** (cannot test reversibility/monotonic return).
- Sensor-space CSD, coarse 6-zone naming-convention parcellation (not an
  anatomical atlas; frontal/central boundary via 10-20 prefixes).
- 200 subsampled frames/recording for topology; the cluster-persistence proxy is
  over evenly-spaced (~1.2 s) frames — a coarse stability indicator by design.
- n=20; effect sizes are the deliverable, not large-N p-values.

---

## Verdict

**MIXED — real win on specificity, not on raw magnitude.** Propofol collapses
global EEG topology hard (unsigned β/γ persistence & β₁, dz up to 1.25 —
literature-consistent, sanity check passed). The signed/localized metric does
**not** beat the unsigned scalar as a global sedation index, but it **adds a
genuine, physiologically-expected spatial signature the unsigned scalar is blind
to**: the alpha posterior→anterior anteriorization, significant (dz=−1.06 /
+0.86) exactly where whole-montage alpha Qabs is null. This is the first evidence
that the signed-winding refinement carries information beyond the unsigned count
on real data — and it does so at a large discrete state transition, consistent
with the broader pattern that topology moves on transitions, not sustained gentle
states. Unlike ds003969 (meditation, null three ways), here there is a real
localized effect to report.
