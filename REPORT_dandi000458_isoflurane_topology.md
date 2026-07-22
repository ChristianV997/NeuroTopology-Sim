# DANDI 000458 (mouse EEG, awake vs. isoflurane anesthesia) — first DANDI/NWB dataset, new anesthesia axis

**Verdict up front:** newly onboarded — the repo's **first DANDI/NWB dataset**
and first non-human, non-OpenNeuro EEG source. Claar/Rembado et al. 2023,
CC-BY-4.0: 30-channel EEG in head-fixed mice, recorded awake and then under
**isoflurane** anesthesia (within-subject). Across **23 subjects, 480 windows
(240 awake / 240 anesthetized)**, the channel-mean topology is **directionally
consistent — awake > anesthetized on all four metrics** (topological charge
collapses under anesthesia) — and **mixed-effects-significant on q_net (p=0.002,
d=0.25), q_abs (p=0.042) and defect_density (p=0.046), but does NOT survive the
conservative subject-blocked permutation test on any metric** (all p≥0.18).
Honest reading: a suggestive, direction-consistent effect that the strictest
pseudoreplication-resistant gate does not confirm.

## 1. Why this dataset — a genuinely new anesthesia axis

Every prior anesthesia contrast in this repo is **human**: ds004541 (EEG-fNIRS,
loc/roc markers) and ds005620 (propofol). DANDI 000458 is **mouse**, **isoflurane**
(a volatile anesthetic with a different molecular mechanism than propofol's
GABA-A potentiation), at a different recording scale (a 30-channel mouse EEG
array alongside Neuropixels). It therefore asks a question none of the prior
data can: **is the awake-vs-unconscious topology contrast specific to human
propofol, or does it generalize across species and anesthetic agent?** This is
the one genuinely actionable "micro/animal-scale anesthesia" axis that survived
triage of an external resource digest (whose other proposals — Meta TRIBE v2,
Neuralink public LFP, siibra, BDSP/I-CARE — were either fabricated, gated, or
duplicative of existing `ripser`/`gudhi` capability).

**New infrastructure (real, tested):** DANDI stores NWB (an HDF5 dialect), not
BIDS, so `mne-bids` cannot read it. `data/dandi_nwb_ingest.py` streams NWB EEG
windows **lazily over HTTP** from DANDI's public S3 (`h5py` partial reads via
`remfile`), reading only the ~1–2 MB of EEG each window needs — so even the
dataset's 27 GB raw-Neuropixels files are processed without downloading them.

## 2. State labels — from the recording's own epochs, never inferred

State comes from each NWB file's own `intervals/epochs` table
(`isoflurane_induction`, `isoflurane_anesthesia`):
- **anesthetized** = the labeled `isoflurane_anesthesia` epoch
- **awake** = recording start → `isoflurane_induction` onset (the pre-anesthesia
  baseline; its end is the real, labeled induction timestamp, not a guess)
- the **induction transition is excluded** (a grey zone, same discipline as
  ds004541 excluding the loc→roc transition).

23 unique subjects (24 NWB assets; sub-569073 has two sessions). All 24
processed with zero errors; every file yielded a clean 10-awake / 10-anesthetized
window split.

## 3. Result (subject-blocked permutation + mixed-effects, 5000 perms)

| metric | direction | window-pooled p | **subject-blocked p** | mixed-effects p | Cohen's d |
|---|---|---|---|---|---|
| q_net | awake > anesth | 0.0046 | **0.183 (ns)** | **0.0023** | 0.247 |
| q_abs | awake > anesth | 0.068 | **0.428 (ns)** | 0.042 | 0.162 |
| f_dress | awake > anesth | 0.189 | **0.570 (ns)** | 0.141 | 0.118 |
| defect_density | awake > anesth | 0.074 | **0.448 (ns)** | 0.046 | 0.159 |

State means (q_net): awake +11.0 vs anesthetized +7.1; (q_abs) +33.1 vs +24.3 —
**topological charge is consistently lower under isoflurane** across every metric.

## 4. The honest divergence — this is the pseudoreplication lesson, live

The mixed-effects model (all 480 windows, random intercept per subject) finds
q_net highly significant (p=0.002); the **subject-blocked permutation test (one
value per subject, 23 points) finds nothing** (p=0.18 for the same metric). When
these disagree, **the subject-blocked test is the more conservative, more
trustworthy claim** — it is structurally immune to the pseudoreplication that
inflated this project's own earlier ds001787 finding (the exact bug
`analysis/permutation.py` exists to prevent). So the reported verdict is the
conservative one: **direction-consistent and MixedLM-significant, but not
subject-blocked-significant.** The likely readings, not adjudicated here:
1. **Between-subject variance too high for n=23** — mouse-to-mouse EEG-array
   placement and montage variability is large; the within-subject signal
   (which MixedLM captures) is real but the subject-level aggregate is noisy.
2. **Cheap channel-mean metric only** — the same limitation as the other cheap-path
   datasets; a montage-aware or connectivity metric might sharpen it, but mouse
   EEG has no standard 10-20 montage to resolve against.

## 5. Comparison to the human anesthesia datasets — framed, not overclaimed

The **direction matches**: awake shows higher topological charge/complexity than
the unconscious state, the same qualitative direction as the anesthesia
literature's loss-of-complexity finding, and the *opposite* of the "sedated =
high fragmented charge" framing that appeared in the external digest (which this
result does not support). But this is **not** asserted to replicate ds005620 or
ds004541: different species, different anesthetic, different scale, a
between-subject design where those were within-subject-marker (ds004541) or
block-labeled (ds005620), and — critically — it does not clear the same
subject-blocked bar ds004541 did (p=0.015 there vs p=0.18 here). Reported as a
consistent-direction, conservatively-non-significant cross-species probe.

## 6. Caveats
- **Cheap channel-mean metric only** (30-ch mouse EEG reduced to `max_channels=16`).
- **Between-subject design** for the awake/anesthetized comparison at the subject
  level; MixedLM/window-pooled use within-subject structure, subject-blocked does not.
- **n=23**, mouse — adequate but the MixedLM/subject-blocked divergence suggests
  it may be underpowered at the subject level for an effect this size.
- Anesthetic depth (1–1.5% isoflurane) and time-under are not covaried here.

Data: `outputs/btc_icft/dandi000458/cohort_stats.json`.
