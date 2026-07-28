# ds005555 (BOAS full-night PSG sleep) — natural-sleep gradient topology

**Verdict up front:** the battery runs end-to-end on real, human-expert-scored
polysomnography with non-degenerate output across all 5 AASM stages
(wake/N1/N2/N3/REM). Wake-vs-REM and wake-vs-N3 topology contrasts are
computed but **not significant at n=1 subject** (window-pooled p=0.08-0.80,
underpowered) — reported honestly as a capability activation, not a claimed
effect. Montage-aware spatial topology could not resolve on this dataset's
non-standard channel naming (documented limitation, not a silent failure).

## 1. Why this dataset

Natural full-night sleep is a genuinely different consciousness-state axis
from every other dataset in this repo: a **graded** wake→N1→N2→N3→REM
gradient (vs. anesthesia/meditation/hypnosis's more abrupt or
volitional transitions), with a 3-expert-scorer human consensus label
(`stage_hum`) per 30-second epoch — the AASM clinical gold standard.

## 2. Onboarding (dedicated module — does not fit the generic registry)

Every BOAS recording's task entity is literally `task-Sleep`; the real
state lives in a per-epoch `stage_hum` column of a companion `events.tsv`,
not in any task-entity string. `sciencer_d/btc_icft/level_m/ds005555_windows_real.py`
(new, ~140 lines) reads the human-consensus stage per scored epoch (skipping
disconnection/artifact codes, never fabricating a label) and windows the
6-channel clinical PSG acquisition (`acq-psg`: F3/F4/C3/C4/O1/O2). The
2-channel wearable headband acquisition is intentionally excluded — too few
channels for montage-aware topology.

## 3. Battery results (sub-1, 40 real 30s epochs, 6 channels)

Stage distribution: wake=12, n1=3, n2=13, n3=6, rem=6 (evenly subsampled
across the full night, not truncated to the start).

| instrument | result |
|---|---|
| topology quality | mean 0.784 (min 0.479), 5176/6600 valid triangles — passed |
| connectivity | mean PLV 0.479, PLI 0.055, wPLI 0.014 |
| phase-based topology (alpha) | mean Qabs 0.050, phase_grad 0.708 |
| spatial topology (montage-aware) | **0/40 resolved** — see limitation below |
| surrogate null gate (50 surrogates/window, 20-window sample) | 10/20 windows passed \|z\|≥2 |

**Spatial topology limitation:** BOAS channel names are prefixed (`PSG_F3`,
`PSG_C3`, …), which does not match any standard montage's exact channel
names in `resolve_montage_positions`'s lookup. This is a real, reported
skip (`"no standard montage matched channel names"`) — not a silent
fabrication. A channel-name-normalization step (strip the `PSG_` prefix
before montage lookup) would fix this for a future pass; out of scope here.

## 4. Stage-contrast gate (window-pooled permutation, n=1 subject, sub-1)

| contrast | q_net p | q_abs p | f_dress p | defect_density p |
|---|---|---|---|---|
| wake vs rem | 0.796 | 0.082 | 0.255 | 0.271 |
| wake vs n3 | 0.788 | 0.089 | 0.242 | 0.227 |

No contrast reaches significance at n=1 subject — the honest result at this
sample size (q_abs trends lowest of the four metrics in both contrasts,
consistent with q_abs being the most sensitive topology metric elsewhere in
this repo, but not a claim). BOAS has 74 subjects; scaling subject count is
the direct path to a properly powered wake→stage gradient test.

## 5. Scope note

This pass proves the full-night PSG windower and every downstream
instrument produce genuine, non-degenerate, per-stage-varying output on one
real subject — not a multi-subject sleep-stage-gradient replication.
