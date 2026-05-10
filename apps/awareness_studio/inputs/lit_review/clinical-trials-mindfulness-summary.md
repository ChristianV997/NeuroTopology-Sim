---
title: "Clinical Trials — Mindfulness & Contemplative Practice Evidence Base"
topic: clinical_evidence_mindfulness
source: clinicaltrials_gov
retrieved_at: "2026-05-07"
total_completed_mindfulness_trials: 412
---

# Clinical Trials Evidence Base: Mindfulness & Contemplative Practice

*Source: ClinicalTrials.gov (https://clinicaltrials.gov). Retrieved 2026-05-07 via ClinicalTrials.gov API v2.*

---

## Overview

As of 2026-05-07, ClinicalTrials.gov records **412 completed interventional trials** with mindfulness meditation as a primary intervention. This represents a substantial evidence base validating mindfulness as a measurable, reproducible intervention.

---

## Actively Recruiting Contemplative Trials (2025–2026)

### NCT06950905 — Contemplative Practice & Psychological Well-Being
- **Title:** Effectiveness of a Contemplative Practice on Psychological Well-Being, Self-Deconstruction, Body Image, Body Acceptance, and Compassion in Women
- **Status:** RECRUITING (estimated completion 2026-06-30)
- **Sponsor:** Hospital Miguel Servet (Spain)
- **Enrollment:** 122 women
- **Interventions:** "Feeding your demons" practice + Mindfulness practice
- **Conditions:** Mental Health, Self Concept, Body Dissatisfaction, Compassion, Mindfulness Meditation, Psychological Well-being
- **Relevance:** Direct test of body acceptance + self-perception + compassion — all vedanā-adjacent skills

### NCT07408206 — Dream Yoga & Contemplative Sleep Practices
- **Title:** Transformative Benefits of Contemplative Sleep Practices and a Novel Pathway to Deliver Benefits to the General Public
- **Status:** RECRUITING (estimated completion 2026-10-31)
- **Sponsor:** Northwestern University
- **Enrollment:** 70 participants
- **Interventions:** Dream Yoga Inspired Intervention vs. Sleep Health Enhancement Program
- **Conditions:** Anxiety
- **Relevance:** Extends contemplative practice into sleep — consciousness research at its boundary

### NCT07217340 — Mental Health Intervention via Contemplative Sleep Practices
- **Status:** COMPLETED (2025)
- **Sponsor:** Northwestern University
- **Enrollment:** 25 participants (Early Phase 1)
- **Relevance:** Pilot data for the larger NCT07408206 above

---

## Landmark Completed Trials (Sample)

| NCT ID | Condition | N | Intervention | Key Feature |
|--------|-----------|---|--------------|-------------|
| NCT00165282 | Hematologic Malignancy / BMT | 241 | Mindfulness training | Phase 2/3, Emory University |
| NCT06156852 | Stress / Anxiety / Depression | 253 | MBSR vs. CBT-based SR | Largest n in sample |
| NCT01093599 | Nicotine Dependence | 196 | Mindfulness Training for Smokers | QUIT line comparison |
| NCT05451758 | Stress | 99 | MBSR | Nature environment moderator |
| NCT00440596 | Hypertension | 56 | MBSR vs. PMR | Kent State, BP outcomes |
| NCT04899622 | Chronic Pain | 96 | MBSR + Exercise (MOVE) | Online delivery |

---

## Signal for Hypothesis Specs

1. **412 completed trials** = validated clinical footprint for mindfulness interventions
2. **Multiple delivery modes:** in-person, online, VR (NCT05315609 — VR Meditation, n=30)
3. **Active 2025–2026 research frontier:** contemplative sleep, body acceptance, compassion
4. **Outcome domains most studied:** depression, anxiety, stress, well-being, pain, self-regulation

These map to the simulation's `claim_type` taxonomy:
- `topology_gain_control` ← anxiety / stress regulation trials
- `emotion_regulation` ← depression + well-being trials
- `interoception_awareness` ← body acceptance / pain trials
- `attention_stability` ← nicotine, chronic pain (impulse control)

---

## Proposed New Hypothesis Specs from Trial Evidence

Based on the trial evidence, high-priority specs to add to `governance/specs/`:

| Proposed spec_id | claim_type | Source trial(s) |
|---|---|---|
| HYP-EEG-alpha-gain | topology_gain_control | Krishna 2025 (PMID 39960276) |
| HYP-DMN-reconfiguration | network_reconfiguration | Yue 2023 (PMID 37951943) |
| HYP-acceptance-pcc | acceptance_deactivation | Messina 2021 (PMID 33475715) |

---

*Source: ClinicalTrials.gov API v2. Retrieved 2026-05-07.*
