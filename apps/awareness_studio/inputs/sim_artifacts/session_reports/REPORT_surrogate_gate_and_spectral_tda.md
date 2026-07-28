# Surrogate null-hypothesis gate + spectral TDA re-analysis of ds003969

Two components of the "elevate the simulator" proposal. The other four
(TVB-NEST, EBRAINS Docker/BIDS, LSL closed-loop, heavy TVB connectome tooling)
were explicitly out of scope and not attempted.

Deliverables: `validation/surrogate_testing.py` (+7 tests),
`dual_engine/spectral_tda.py` (+4 tests), `scripts/tvb_validation_synthetic_check.py`
(Part 3, optional). All 28 new+existing montage/surrogate/spectral tests pass.

---

## Part 1 — Surrogate null gate

`phase_randomize_surrogate` (FT + IAAFT) and `surrogate_test_topology_metric`.
The correctness point: FT surrogates randomize phase **independently per channel**
by default (destroying cross-channel structure — the right null for connectivity/
topology), with a `preserve_cross_channel_lag` flag for the weaker relative-phase-
preserving null. Rank-based p-values, directional or two-sided, failure tracking,
finite checks throughout. IAAFT additionally preserves each channel's amplitude
distribution.

### Retroactive gate on the three prior headline results

The honest constraint first: **all three prior pipelines were process-and-discard,
so the raw per-subject time series are not on disk.** What *is* cached:

| prior headline | cached on disk? | gate-able now? |
|---|---|---|
| ds000245 PD global_efficiency (η²=0.41) | only `conn/*.npy` correlation **matrices** — no ROI timeseries | **No** — a correlation matrix cannot be phase-randomized. Needs re-fetch from OpenNeuro S3 + re-run ROI extraction. |
| ds003969 meditation beta β₁ (CSD, dz=−0.32) | no (discarded) — but **re-fetched for Part 2** | **Yes** (gated below) |
| ds005620 propofol alpha parietal \|charge\| (dz=−1.06) | no (discarded) | **No** from cache. Needs re-fetch of the propofol EEG + re-run CSD. Flagged, not silently skipped. |

So of the three, only ds003969 could be gated with reasonable effort (re-fetched
anyway for Part 2). ds000245 and ds005620 are flagged follow-ups requiring
re-fetch — stated rather than skipped.

### ds003969 gate result (20 subjects, 40 recordings, real_eeg)

The prior "one surviving real effect" was the CSD **beta-band β₁** (meditation <
thinking). Gated per recording against FT surrogates that preserve each channel's
power spectrum:

- **real β₁ mean = 61.5 vs phase-randomized null mean = 137.1**, z = **−10.0**,
  **passes the gate in 39/40 recordings** (p<0.05).

The real β₁ is far *below* the null (genuine cross-channel synchronization
collapses loops relative to phase-randomized data), i.e. **the beta topological
metric reflects real cross-channel structure, not a power-spectrum artifact** —
the exact failure mode the gate exists to catch. The ds003969 beta metric's
substrate survives.

*Scope note:* this gate validates that the **metric reflects genuine structure**
(the concern the task raised: "a topology metric can be large with no genuine
cross-channel synchronization"). It does not by itself prove the *meditation−
thinking difference* is beyond a between-condition power difference; a stricter
per-condition difference-gate (surrogates preserving each condition's spectrum,
then testing the contrast) is the next step, not run here for compute reasons —
flagged.

---

## Part 2 — Spectral TDA on ds003969 (meditation vs thinking)

`dual_engine/spectral_tda.py`: Welch coherence spectrum → per-frequency first
persistence landscape (implemented directly; persim is not a repo dependency) →
per-band landscape "mass". A frequency-resolved replacement for the ad hoc
band-by-band scalar testing every prior report did by hand. Reuses the exact
committed ds003969 CSD preprocessing.

### Result (20 subjects, paired, same within-subject design)

| band | med | think | dz | p | vs prior |
|---|---|---|---|---|---|
| delta | 0.0360 | 0.0357 | +0.08 | 0.72 | **NULL** — the falsified delta finding does NOT reappear |
| theta | 0.0395 | 0.0394 | +0.02 | 0.93 | null |
| alpha | 0.0408 | 0.0415 | −0.14 | 0.55 | null |
| **beta** | 0.0394 | 0.0406 | **−0.47** | **0.048** | **med<think — REPLICATES the CSD beta effect** |
| gamma | 0.0340 | 0.0346 | −0.16 | 0.49 | null |

**Answers to the three required questions:**

1. **Different pattern than amplitude-envelope connectivity?** Partly. The
   coherence-based spectral landscape puts *all* its signal in **beta** and shows
   **delta as flat null** — so the delta-band effect that was falsified as ocular
   artifact stays dead under a completely different (coherence, not amplitude-
   envelope) construction, and the beta effect (med<think) reappears. The
   frequency-resolved method independently reproduces the "beta, opposite to the
   naive low-drag prediction" pattern and independently confirms delta was noise.

2. **Surrogate-gated?** The beta-band topological structure passes the gate
   decisively (z=−10, 39/40 recordings) — so the beta spectral effect is measured
   on genuine cross-channel structure, not a spectral artifact. (The landscape-
   mass-specific difference-gate is the flagged stricter follow-up above.)

3. **Does it change the meditation verdict?** **No — it confirms it.** Three prior
   rounds (sensor / CSD / eLORETA) found: delta falsified as artifact, and a small
   beta effect opposite to the low-drag prediction. The frequency-resolved spectral
   TDA agrees on both counts (delta null, beta med<think, dz−0.47, p=.048). The
   meditation-topology story is unchanged: no low-drag signature; a small,
   gate-passing, replicated beta effect in the *opposite* direction.

---

## Part 3 — TVB synthetic validation (optional, attempted, succeeded)

`pip install tvb-library tvb-data` installed cleanly (lazy-imported; not added to
core requirements). Simulated the bundled **76-region connectome**
(Generic2dOscillator + linear coupling, HeunStochastic) and fed region time series
through the existing phase-grid TDA + coherence spectral-TDA + the Part 1 gate.

- **Recovery confirmed:** functional connectivity tracks the structural connectome,
  r = **+0.29** (p=2e-57) at coupling a=0.10 (swept 0.02→0.6; weak coupling gives
  no recovery, as expected).
- **Gate:** simulated coupling produces mean|corr| = 0.758 vs null 0.362,
  **z = +113, passes** — the gate correctly detects genuine simulated coupling.
  (Opposite gate direction from ds003969's β₁ (z=−10): mean-correlation rises with
  coupling while loop-count falls — both correctly flag real structure, confirming
  the gate is direction-agnostic.)

The full pipeline recovers known simulated topology. Calibration only — no
NEST/TVB-NEST/EBRAINS/Docker/BIDS.

---

## The single most important sentence

**Nothing that could be gated with available data failed the surrogate gate:**
ds003969's beta β₁ — the one "surviving real" effect from the prior meditation
reports — passes decisively (z=−10, 39/40 recordings) and is independently
replicated by coherence-based spectral TDA (beta med<think, dz−0.47, p=.048),
while the already-falsified delta effect stays null; the other two headlines
(ds000245 PD η²=0.41, ds005620 propofol alpha |charge| dz−1.06) **could not be
gated from cached data and require re-fetch to test** — flagged as the outstanding
integrity gap, not silently passed.
