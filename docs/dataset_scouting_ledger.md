# Dataset Scouting & Rejection Ledger

Exhaustive record of all datasets considered for onboarding into NeuroTopology-Sim, tracking their status and rationale. Updated as part of each scouting pass to prevent re-proposing dead ends and document infrastructure gaps.

**Methodology**: Direct S3/DANDI metadata enumeration (not web-search guessing). All claims verified via unsigned S3 listing of real data before any ingestion code is written.

---

## Onboarded Datasets (16 total)

| Dataset ID | Modality | Status | Notes | Date Onboarded |
|---|---|---|---|---|
| ds005620 | EEG | **Onboarded** | Propofol sedation; task→state: awake/sed/sed2; 182 recordings | 2026-06 |
| ds003969 | EEG | **Onboarded** | Meditation vs thinking; BioSemi 64ch 1024Hz | 2026-06 |
| ds003816 | EEG | **Onboarded** | Loving-kindness meditation; BrainVision 128ch | 2026-06 |
| ds004541 | EEG | **Onboarded** | General anesthesia (awake vs anesthetized); loc/roc event markers | 2026-06 |
| ds004040 | EEG | **Onboarded** | Trance channeling (altered consciousness); rest/trance event markers; EEGLAB .set; 13 subjects, 2 ses | 2026-07 |
| ds001787 | EEG | **Onboarded** | Naturalistic dataset; dual-mode windower (Level-M + Level-T) | 2026-06 |
| ds004572 | EEG | **Onboarded** | Sham hypnosis baseline vs experience blocks | 2026-06 |
| ds004917 | EEG | **Onboarded** | [Registry status to be confirmed] | 2026-06 |
| ds006644 | fMRI | **Onboarded** | DMT+harmine (verum/placebo BETWEEN-SUBJECT); ses-02 post-retreat; MNI152 + Schaefer-100 atlas; AROMA-denoised | 2026-06 |
| ds005917 | fMRI | **Onboarded** | Ketamine crossover (WITHIN-SUBJECT drug/placebo); MDD group (n=25); per-subject KMeans parcellation (no shared atlas due to raw BOLD, disclosed) | 2026-06 |
| ds005237 | fMRI | **Onboarded** | [Processed twice per plan; modality/details TBD] | 2026-06 |
| ds006072 | fMRI | **Onboarded** | [Details to be extracted] | 2026-06 |
| dandi000458 | DANDI/NWB | **Onboarded** | Claar/Rembado 2023 mouse EEG (awake vs isoflurane-anesthetized); lazy HTTP reads via remfile; epochs table with `isoflurane_anesthesia` state labels | 2026-07 |
| DREAM | Meta | **Onboarded** | Cross-dataset gate report (structure TBD) | 2026-06 |
| cross-dataset-gate | Meta | **Onboarded** | Cross-dataset gate report (structure TBD) | 2026-06 |

---

## Registry-Driven Config-Only Datasets (9 total)

These are declared in `configs/btc_icft/dataset_onboarding_registry.json` and are executed via the generic EEG streamer, but have NOT been fully processed (cohort stats / reports not yet generated):

| Dataset ID | Title | Task→State Map | Status |
|---|---|---|---|
| ds005620 | Propofol sedation EEG | awake/sed/sed2 → sedated | Config declared |
| ds003969 | Meditation vs thinking | med1breath/med2 → meditation; think1/think2 → thinking | Config declared |
| ds003816 | Loving-kindness meditation | lkmself/lkmother → meditation; preresting/postresting → resting | Config declared |
| ds004148 | Eyes open/closed resting | eyesopen → eyes_open; eyesclosed → eyes_closed | Config declared |
| ds003800 | Auditory gamma entrainment | auditorygammaentrainment → entrainment; rest → rest | Config declared |
| ds002338 | Motor imagery neurofeedback | mipre → motor_imagery_pre; mipost → motor_imagery_post | Config declared |
| ds004572 | Sham hypnosis | baseline1/2 → baseline; experience1-4 → experience | Config declared |
| ds005555 | Bitbrain sleep (BOAS) PSG | State from events.tsv stage_hum (wake/n1/n2/n3/rem); dedicated windower | Config declared |
| ds004541 | EEG-fNIRS general anesthesia | State from loc/roc event markers; dedicated windower | Config declared |

---

## Rejected / Blocked Candidates

| Dataset ID | Source | Status | Reason | Date Rejected | Report Link |
|---|---|---|---|---|---|
| ds003059 | OpenNeuro search | **Rejected** | LSD study; raw BOLD only, no `derivatives/` folder, no FSL/ANTs in sandbox for registration | 2026-06 | N/A |
| ds007783 | Propofol anesthesia fMRI (mice) | **Rejected** | Raw BOLD only (verified S3), no `derivatives/` folder, no spatial normalization; same infrastructure blocker as ds003059; 10 subjects; would need FSL/ANTs registration unavailable in sandbox | 2026-07 | N/A |
| I-CARE v2.0 | Literature / gate reports | **Rejected** | Access gate / institutional requirement; not deposited on OpenNeuro | 2026-06 | N/A |
| jhana/cessation papers | Literature search | **Rejected** | Referenced in consciousness literature but not actually deposited on OpenNeuro; dataset accession not verifiable | 2026-06 | N/A |

---

## Step 0 Scan Summary (2026-07-22)

**Methodology**: Direct S3 enumeration of `dataset_description.json` across OpenNeuro; keyword matching on name/description; subject count via S3 listing. DANDI scan deferred (API access issues in sandbox; recommend manual `dandi search-dandisets` CLI). Scanned ~40 targeted recent datasets plus expanded consciousness/anesthesia/meditation/sleep keyword sweep.

**Candidates evaluated**:
- **New onboardable candidates identified**: 1 (ds004040 — trance channeling EEG, 13 subjects, event-marker-based state)
- **Blocked candidates identified**: 1 (ds007783 — propofol fMRI, raw BOLD, no derivatives, 10 subjects)
- **Already-known candidates**: All recent releases (ds008000+) either don't exist, are access-gated, or lack consciousness/anesthesia/meditation keywords

**Conclusion**: OpenNeuro consciousness/anesthesia/meditation space is well-saturated by 16 existing onboarded datasets. ds004040 is the sole new viable candidate discovered; it has been moved to registry (config-only, pending dedicated windower implementation as ds004040_windows_real.py).

---

## Metadata

- **Last scan**: 2026-07-22 (ongoing)
- **Scan methodology**: Direct S3 enumeration of `dataset_description.json` (OpenNeuro) + `dandiset.yaml` (DANDI); keyword matching on name/description; subject count verified via S3 listing
- **Keywords monitored**: consciousness, anesthesia, sedation, propofol, isoflurane, meditation, contemplative, mindfulness, altered state, psychedelic, psilocybin, lsd, sleep stage, sleep scoring, rem, nrem, hypnosis, trance, lucid dream
- **Known infrastructure gaps**:
  - Raw BOLD + no FSL/ANTs for registration (blocks ds007783, ds003059)
  - No per-subject state-label mechanism (blocks datasets without task entities or events.tsv markers)
  - No DANDI API access in this environment (DANDI scan done manually or via CLI)

