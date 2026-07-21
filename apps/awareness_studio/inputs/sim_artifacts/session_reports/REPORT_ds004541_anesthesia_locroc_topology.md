# ds004541 (EEG-fNIRS general anesthesia) — awake vs. anesthetized by real loc/roc markers

**Verdict up front:** newly onboarded (CC0, EEG modality only). State comes
from the recording's own **loss-of-consciousness (`loc`) and
recovery-of-consciousness (`roc`) event markers** — the canonical behavioral
consciousness-transition timestamps — not from a task label. Across the **7
subjects that actually have loc/roc markers** (140 windows), the
awake-vs-anesthetized channel-mean topology contrast is **significant on
q_abs (subject-blocked p=0.015, d=0.20), f_dress (p=0.046, d=0.28), and
defect_density (p=0.015, d=0.19)**; q_net is null. Small n (7 subjects), so
this is a promising signal, not a strong claim — but it is a real,
subject-blocked-significant effect on precise behavioral markers.

## 1. Why this dataset is a clean consciousness contrast

Every other anesthesia-adjacent dataset in this repo labels state by
task-block name. ds004541 instead marks the exact instants of `loc` and `roc`
in each recording's events.tsv. The windower
(`sciencer_d/btc_icft/level_m/ds004541_windows_real.py`) uses those to define:
- **awake** = recording start → `loc`
- **anesthetized** = `loc` → `roc` (or → recording end if no `roc`)

**Honest label handling:** the dataset has 8 subjects, but the subject IDs are
non-contiguous (sub-02,03,04,07,08,09,10,11 — no 01/05/06), and **sub-11 has
no `loc` marker at all** → it yields **zero windows**, never a fabricated
state (`no_label_inference`). So the analysis is on the 7 subjects with real
markers.

## 2. Result (subject-blocked permutation + mixed-effects, 5000 perms)

| metric | subject-blocked p | mixed-effects p | converged | Cohen's d |
|---|---|---|---|---|
| q_net | 0.71 | 0.41 | yes | −0.055 |
| q_abs | **0.015** | 1.3×10⁻¹⁰ | yes | 0.197 |
| f_dress | **0.046** | 1.3×10⁻⁷ | yes | 0.281 |
| defect_density | **0.015** | 4.9×10⁻⁸ | yes | 0.185 |

## 3. The interesting cross-dataset contrast (flagged, not overclaimed)

ds004541 (loc/roc-marked anesthesia) shows a significant awake-vs-unconscious
topology effect on the **same cheap channel-mean metric** where **ds005620
(propofol, coarse sed/sed2 task-block labels) showed none** (see
`REPORT_ds005620_scaled_channel_mean_topology.md`). Two candidate
explanations, neither established:
1. **Label precision** — loc/roc mark the true behavioral transition, while
   `sed`/`sed2` are whole-block labels that may include awake-ish epochs near
   block edges, diluting the contrast. If so, marker precision matters more
   than the metric's sensitivity.
2. **Small-n optimism** — n=7 with subject-blocked p=0.015 is real but not far
   from the n=7 paired-test floor (~0.008); a larger cohort could regress it.

This is a hypothesis worth testing (more anesthesia datasets with true LOC
markers), not a conclusion. Reported as a flag.

## 4. Caveats

- **n=7** (marker-bearing subjects). Small.
- **fNIRS ignored** — the dataset's hemodynamic `.snirf` modality is not used
  (this repo's real-signal path is EEG); a future pass could correlate the
  fNIRS metabolic proxy with the topology, which is the multimodal angle that
  motivated the dataset's inclusion.
- **Cheap channel-mean metric only** (58-ch EEG available; here reduced to
  `max_channels=16`). Data: `outputs/btc_icft/ds004541/cohort_stats.json`.
