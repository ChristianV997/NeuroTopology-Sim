---
title: "Meditation & EEG Neural Oscillations — Research Literature"
topic: eeg_oscillations_meditation
claim_type: topology_gain_control
layer: biophysical
source: pubmed
retrieved_at: "2026-05-07"
pmids: ["39960276", "40933789"]
---

# Meditation EEG: Alpha/Theta Oscillations as Gain-Control Markers

*Based on articles retrieved from PubMed. DOI links provided for all citations.*

---

## Key Hypothesis Link

Neural oscillatory bands map directly to the simulation variables:
- **Alpha power** (8–13 Hz) ↔ inhibitory gain-control ↔ Qabs (topology charge magnitude)
- **Theta power** (4–8 Hz) ↔ focused attention engagement ↔ I_mean (field intensity)
- **Frontal alpha asymmetry** ↔ approach/withdrawal motivation ↔ vortex chirality (Qz sign)

---

## Article 1 — Krishna et al. (2025): Frontal Alpha & Impulsivity in Heartfulness Meditators

**Citation (PubMed PMID 39960276):**
Krishna D, Krishna P, Singh D. "Neural Correlates of Impulsivity and Frontal Electroencephalogram Oscillations in Heartfulness Meditators: A Cross-Sectional Study."
*Altern Ther Health Med* 31(4):42–47. (No DOI recorded in PubMed for this article.)

**Key findings:**
- 65 participants (Heartfulness meditators 1245 ± 355 hrs vs. naïve controls)
- **Higher right frontal alpha power** (p<0.05) in meditators
- **Lower frontal beta power** (p<0.05) in meditators
- Impulsiveness **negatively correlated** with frontal alpha power
- Impulsiveness **positively correlated** with frontal beta power
- Total impulsive behavior significantly lower in meditators

**Relevance to model:**
- Frontal alpha = inhibitory gain-control: higher alpha → more regulated reactivity → supports vedanā gain-control
- Beta = high-frequency reactivity: lower beta = less reactive, aligns with Qabs reduction
- The alpha/beta ratio is a candidate biophysical metric for the simulation's f_dress (dressed frequency)

**Keywords:** EEG, alpha power, beta power, impulsivity, meditation, frontal lobe, Heartfulness

---

## Article 2 — Brahmi et al. (2025): Neural Oscillations in Novice Meditators (ānāpānasati)

**Citation (PubMed PMID 40933789):**
Brahmi M, Sharma A, Jain H, Kumar J. "Electrophysiological and Behavioural Markers of Novice State Mindfulness in Relation to Trait Mindfulness, Values, Personality Traits and Academic Dispositions."
*Ann Neurosci*. [DOI: 10.1177/09727531251369287](https://doi.org/10.1177/09727531251369287)

**Key findings:**
- 97 university students, EEG during ānāpānasati (breath awareness) meditation
- 5-band spectral analysis: delta, theta, alpha, beta, gamma in prefrontal, occipital, DMN regions
- **Acting with Awareness** trait → **enhanced theta power** during meditation (focused attention)
- Discontinuity of Mind → elevated posterior alpha + prefrontal beta (fragmented mentation)
- **Posterior alpha** correlates with mind-wandering (less focused = more alpha)
- Prefrontal alpha reflects alertness/inhibitory tone (paradox of meditation: alert but calm)
- Stimulation-value individuals: lower prefrontal alpha (heightened alertness → less inhibitory control)

**Relevance to model:**
- Theta enhancement = vortex coherence (Qz maintains stable topology) under focused attention
- Posterior alpha elevation during mind-wandering → DMN activation → elevated Qabs
- The ānāpānasati technique maps precisely to vedanā practice: continuous sensory monitoring without reactivity
- "Trait-to-state continuity" supports the simulation's `seed` parameter as encoding prior state

**Note on EEG band-simulation mapping:**

| EEG band | Simulation variable | Interpretation |
|---|---|---|
| Theta (4–8 Hz) | I_mean | Field intensity under focused attention |
| Frontal alpha (8–13 Hz) | Qabs (inverse) | Inhibitory control = topology stability |
| Beta (13–30 Hz) | I_std | Reactivity / noise amplitude |
| Delta (1–4 Hz) | elapsed_s | Integration timescale |

**Keywords:** EEG, neural oscillations, theta, alpha, mindfulness, ānāpānasati, prefrontal, DMN

---

## Hypothesis Spec Implication

These findings suggest a new testable spec:

**HYP-EEG-001:** In the simulation, lower I_std (less field reactivity) and stable Qz
(consistent topology) should co-occur, mirroring the alpha-gain-control mechanism
observed in experienced meditators.

Proposed thresholds (from Krishna 2025 effect sizes):
- `I_std_max: 0.15` (low reactivity)
- `Qabs_max: 2.0` (stable topology, not large charge excursions)

---

*Source: PubMed (https://pubmed.ncbi.nlm.nih.gov). Retrieved 2026-05-07.*
