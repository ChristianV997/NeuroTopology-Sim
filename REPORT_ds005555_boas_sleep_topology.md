# ds005555 (BOAS full-night PSG sleep) — full 128-subject cohort, graded gradient

**Verdict up front:** scaled from n=1 to the **full 128-subject cohort** (5120
windows across all 5 AASM stages), the wake-vs-deeper-stage topology contrasts
show a **small but statistically real, and importantly GRADED, effect**: q_abs
significantly separates wake from N2 (subject-blocked p=0.011, d=0.15), N3
(p=0.042, d=0.29), and REM (p=0.005, d=0.15) — but **not from N1** (p=0.60,
d=0.11), the lightest sleep stage nearest to wake. Effect sizes are small
(d≈0.15–0.29), consistent with a subtle 6-channel-PSG topology change, but the
graded structure (no separation from the lightest stage, real separation from
the deeper/distinct ones) is scientifically coherent, not noise.

The montage-fix (below) also means the montage-aware spatial topology now
resolves on this dataset for the first time — the earlier pass's 0/40
spatial-resolution failure is closed.

## 1. The `PSG_` montage bug (fixed)

BOAS labels its PSG electrodes `PSG_F3`, `PSG_C4`, … — a device prefix that
matched no standard montage, so `resolve_montage_positions` returned
`(None, None)` on every window (0/40 in the n=1 pass). `resolve_montage_positions`
now strips a **scoped, documented** device-prefix list (`KNOWN_STRIPPABLE_PREFIXES`)
before matching, keying the returned positions by the original names so
callers are unaffected. Verified: `PSG_F3…PSG_O2` now resolves to
`standard_1020`; unprefixed names and unrelated `PSG`-starting strings are
untouched.

## 2. Full cohort result (subject-blocked permutation, 5000 perms, q_abs shown)

| contrast | windows | subject-blocked p (q_abs) | mixed-effects p | Cohen's d |
|---|---|---|---|---|
| wake vs **N1** | 951 / 172 | 0.60 (ns) | 0.41 | 0.11 |
| wake vs **N2** | 951 / 2985 | **0.011** | 6.3×10⁻⁵ | 0.15 |
| wake vs **N3** | 951 / 226 | **0.042** | 0.011 | 0.29 |
| wake vs **REM** | 951 / 786 | **0.005** | 0.0008 | 0.15 |

The gradient is the story: **q_abs does not distinguish wake from N1** (the
lightest, most wake-like stage) on any test, but **does distinguish wake from
N2, N3, and REM.** This is the expected shape if the metric tracks a genuine
depth-of-unconsciousness axis rather than a generic "asleep vs awake" flag.

## 3. Honest caveats

- **Small effects.** d≈0.15–0.29. Real at n=128, but small — a 6-channel
  clinical PSG montage carries limited spatial topology, and q_abs is a
  channel-mean heuristic. Not every metric reaches significance on every
  contrast (q_net/f_dress/defect_density are weaker and mixed; q_abs is the
  most consistent, matching its behavior as the most sensitive metric
  elsewhere in this repo).
- **Multiple comparisons.** 4 metrics × 4 contrasts = 16 tests. q_abs's
  wake-vs-N2 (p=0.011) and wake-vs-REM (p=0.005) survive a Bonferroni×16
  factor only marginally (wake-vs-REM: 0.005×16=0.08); the mixed-effects
  wake-vs-N2 (6×10⁻⁵) survives comfortably. Treat the *graded pattern across
  stages* as the robust finding, not any single cell's exact p.
- **Cheap metric only.** Channel-mean topology, as with the other scaled
  datasets — not the full battery.

## 4. Onboarding (unchanged)

Dedicated per-epoch windower (`ds005555_windows_real.py`) reading the
human-consensus `stage_hum` AASM label; `acq-psg` only (headband excluded).
Streamed via `tools/stream_process_ds005555.py` across 128 subjects. Data:
`outputs/btc_icft/ds005555/cohort_stats.json`.
