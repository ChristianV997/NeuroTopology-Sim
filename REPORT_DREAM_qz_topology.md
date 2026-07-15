# DREAM database — Experience vs No-experience sleep bifurcation: DATA UNOBTAINABLE in this environment

**Verdict up front (the one undecorated sentence):** the DREAM database and every
one of its constituent serial-awakening studies are **unreachable from this
environment** (all native hosts return HTTP 403 under the container's egress
policy, and no OpenNeuro-hosted dataset carrying awakening-level
Experience/No-experience dream-report labels exists among all 2388 OpenNeuro
accessions), so the fourth axis — content-presence bifurcation within natural
sleep — **could not be tested**, and the "signed topology moves only on large
discrete physiological/pharmacological transitions" boundary condition remains
neither extended nor broken by sleep. Per the task's own hard constraint, a
documented "couldn't get enough open data" outcome is the deliverable here, not a
fabricated substitute.

---

## 1. Branch / commit provenance (Step 0 — machinery confirmed present)

All required machinery is present and was verified on:

- **Branch `claude/awareness-studio-mvp-fiIxi` @ `7c948d1`** (the branch all recent
  signed-topology work landed on; no branch merge performed).
- `validation/montage_topology.py` — present (`signed_defect_topology_from_band`,
  `net_charge_by_region`, `defect_spatial_clustering`).
- `validation/surrogate_testing.py` — present (`surrogate_test_topology_metric`).
- `dual_engine/anesthesia_signed_winding_pipeline.py` — present, **`--save-timeseries`
  flag confirmed present** (the process-and-discard fix that would have been reused
  here for EDF+ epoch persistence).

The analysis machinery is not the blocker. The data is.

## 2. Dataset-discovery result (Step 1 — the real registry structure, no fabricated ds#####)

**DREAM is a Monash registry, not an OpenNeuro dataset** (monash.edu/dream-database,
DOI 10.26180/22133105), indexing ~20 independently-hosted sleep/dreaming studies
(≈505 participants / 2643 awakenings in its own paper), mixed access, EDF+-shaped.

### Host reachability — every DREAM-relevant host is egress-blocked

| host | purpose | result |
|---|---|---|
| `bridges.monash.edu` | the registry's figshare-backed Datasets table + Data URLs | **HTTP 403 (CONNECT tunnel failed)** |
| `figshare.com`, `ndownloader.figshare.com` | figshare-hosted study files | **HTTP 403** |
| `openneuro.org` (API) | OpenNeuro GraphQL search | **HTTP 403** (as in every prior task) |
| `s3.amazonaws.com/openneuro.org` | OpenNeuro S3 (control) | HTTP 200 (works) |

The organization egress policy that has blocked osf.io, medrxiv.org,
repository.cam.ac.uk and fieldtriptoolbox.org in prior tasks also blocks the
Monash/figshare registry and its data URLs. No workaround was attempted (policy
denials are reported, not routed around).

### OpenNeuro is the only reachable source — and none of DREAM's studies are on it

Following Step 1.2, I searched **all 2388 OpenNeuro accessions** (S3-hosted
`dataset_description.json` + `README`) for the six studies DREAM's own paper
analysed (Lacaux/Oudiette N1, Zhang & Wamsley 2019, De Gennaro ×2, Tononi/Siclari
Serial Awakenings, Sikka/REM Turku) and for sleep/dream/awakening keywords.

- **72 sleep/dream keyword hits**, but **none are a natural-sleep serial-awakening
  study with Experience/No-experience dream-report labels.** They are sleep-staging
  (BOAS ds005555; Ear-EEG ds005178/ds005185; forehead-patch ds006695), memory /
  TMR (ds005530, ds006576, ds006502), sleep-deprivation resting EEG (ds004902),
  epilepsy iEEG-during-sleep, and PET protein-synthesis studies.
- **None of DREAM's six authors' datasets are on OpenNeuro.** The one hit whose
  name suggested "Zhang" — **ds005398** — is *interictal iEEG from epilepsy
  patients during sleep* (UCLA/Detroit), **not** Zhang & Wamsley's dream-report
  study; no dream/experience labels.
- The **only reachable dataset with the serial-awakening *dreaming-report*
  paradigm is ds005620** ("A repeated awakening study… to capture dreaming during
  propofol sedation"). It fails on **two** counts for this task: (a) it is
  **propofol sedation, not natural sleep** — i.e. the pharmacological axis already
  tested and *won* on (its alpha anteriorization, gated 80/80, permutation
  p≤0.001), so it cannot serve as the independent natural-sleep axis this task
  exists to test; and (b) it **released only an `awakenings` count** in
  participants.tsv (values 0–3) — **no per-awakening Experience/No-experience
  labels** and no dream-report content (its events.tsv are bare EEG segment
  markers). There is nothing to contrast.

**Exact obtained N: 0 studies / 0 participants / 0 awakenings** with usable
Experience-vs-No-experience labels — versus DREAM's 505/2643. The shortfall is
total, and the reason is egress policy plus the absence of an OpenNeuro-hosted
equivalent, not QC exclusion.

## 3–7. Head-to-head AUC / REM-NREM / per-study / gate / permutation / confounds

**Not run — no data.** Reporting fabricated numbers here would violate the task's
"no fabricated ground truth" constraint. Had the data been obtainable, the
pre-registered plan (stated so the null-of-availability is not mistaken for a
null-of-effect) was: 30-s pre-report window on F4/C4/O2; whole-scalp signed
`region_net/abs_charge`+`chirality` in sleep-relevant bands (predicting a *global*,
not localized, signature since content-presence is not obviously region-specific);
head-to-head against DREAM's own PSD-6band + catch22 features (their published
AUC NREM≈0.586 / REM≈0.700 as reference); REM/NREM split; per-source-study effect
sizes (this being a multi-site aggregate); the surrogate gate (within-study label
shuffle) and the condition-label permutation kept as two distinct questions;
sleep-stage + source-study covariates; a ≥15-usable-awakenings-per-condition-
per-study floor. A new **EDF+ loader** (not OpenNeuro/BIDS-shaped) would have been
required — none was built, since there was no data to load.

## 8. What this means for the boundary-condition question, and what would unblock it

The prediction was explicit: if the signed instrument's power tracks *discrete
transition magnitude* rather than pharmacological cause specifically, sleep
Experience/No-experience should behave more like propofol (a win) than like
ds005237 (a null); if null here too, the boundary tightens to "gross physiological/
pharmacological state only." **This environment can adjudicate neither** — the
sleep axis is simply not testable with the data reachable here.

To unblock: (a) egress allow-listing for `bridges.monash.edu` / `figshare.com` /
`ndownloader.figshare.com` (then the registry Datasets table + open Data URLs +
an EDF+ loader), or (b) a future OpenNeuro S3 deposit of a serial-awakening
dream-report study (Siclari/Wamsley/Oudiette-style), which the 2388-accession
sweep confirms does not yet exist. Until one of those, the DREAM axis stays open —
honestly unmeasured, not falsely resolved.
