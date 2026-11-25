# Higher-order literature audit

Read-only classification of sources proposed for the Awareness Studio
research loop. This audit does not establish that repository theories
are true.

Owned files:

- `docs/research/higher_order_literature_audit.md`
- `configs/research/higher_order_claims.yaml`
- `tests/research/test_higher_order_claims.py`

The evidence registry from PR #276 is not modified.
`obsidian/15_DS005620_Post_Execution_Controls/Execution_Artifact_Audit.md`
and `outputs/command_center/mock_payloads/guardrails_status.json` are
not modified.

Audit base: `origin/main` `287093b7223cc35e1c4f588904da70e22a68b0ab`.

## Distinctions enforced

| Must not conflate | With |
| --- | --- |
| Statistical dependence | Causation |
| Predictive gain | Mechanism |
| Parasympathetic activation | Detachment |
| Discernment | Nonjudgment |
| Decentering | Nonattachment |
| Theory | Evidence |
| Preprint | Peer-reviewed replication |

## Sources

### 1. Triadic functional connectivity — confirmed preprint

- Source identity: arXiv:2609.03987 (DOI `10.48550/arXiv.2609.03987`).
- Authors: Qiang Li, Masoud Seraji, Yu-Ping Wang, Godfrey D Pearlson, Vince D Calhoun.
- Title: High-Order Triadic Functional Connectivity in the Brain and Beyond.
- Source type: preprint (`q-bio.NC`, submitted 3 Sep 2026).
- Peer-review status: not peer reviewed.
- Claim text: entropy-based triadic dependence can add information beyond pairwise functional connectivity and separate rest from task in the reported analyses.
- Source location: arXiv abstract page for 2609.03987.
- Evidence tier: preprint empirical methods.
- Causal status: statistical dependence only.
- Alternative interpretations: pairwise-plus-noise; classification accuracy is predictive gain, not a mechanism.
- Limitations: preprint; combinatorial triplet explosion; no synaptic, charge, or quantum identification.
- Replication requirement: independent cohort, pairwise baselines, preregistered triplet nulls.
- Repository hypothesis link: `H-AUDIT-TRIADIC-DEPENDENCE`.
- Repository support: not granted.

### 2. Higher-order spectral modulation — confirmed preprint

- Source identity: arXiv:2609.03172 (DOI `10.48550/arXiv.2609.03172`).
- Authors: Christopher K. Kovach, Sukhbinder Kumar.
- Title: Modulation Analysis with Higher-Order Spectra.
- Source type: preprint (`eess.SP`, submitted 2 Sep 2026).
- Peer-review status: not peer reviewed.
- Prior preprint identity (not a substitute journal version): TechRxiv `10.36227/techrxiv.21401703.v1`, earlier title "A Slice of Trispectrum for Patterns of Modulation".
- Claim text: a two-dimensional trispectrum subdomain (modulogram) identifies modulated oscillations; illustrated with blind detection of beta bursts in rodent and human LFP.
- Source location: arXiv abstract page for 2609.03172.
- Evidence tier: preprint empirical methods.
- Causal status: descriptive method, not mechanism.
- Alternative interpretations: spectral descriptor of modulation is not a synaptic or topological-charge mechanism; LFP beta-burst detection is not a meditation contrast.
- Limitations: preprint methods paper; not a peer-reviewed replication of this arXiv version at audit time.
- Replication requirement: independent LFP or EEG cohort with pairwise spectral baselines and preregistered modulogram nulls.
- Repository hypothesis link: `H-AUDIT-SPECTRAL-MODULOGRAM`.
- Repository support: not granted.

Identity note: this identifier resolves. It is not disputed. What is rejected is any upgrade from "preprint methods paper" to "established neural mechanism" or "peer-reviewed replication".

### 3. Slow breathing and inter-organ dynamics — confirmed peer-reviewed article

- Source identity: DOI `10.1016/j.neuron.2026.04.044`.
- Authors: Huang, Schmidt, Rebollo, Molter, Pu, Keweloh, Lam, Mohr, Bellucci, Röttger, Park.
- Title: Slow breathing impacts inter-organ dynamics modulating brain function and risk behavior.
- Source type: peer-reviewed empirical article (*Neuron*, 2026).
- Peer-review status: peer reviewed.
- Linked preprint: bioRxiv `10.64898/2026.01.09.698695`.
- Claim text: instructed prolonged exhalation increased risky choices by raising reward sensitivity and cardiac parasympathetic activity, with correlated vmPFC and precuneus reward responses.
- Source location: *Neuron* article S0896-6273(26)00339-9.
- Evidence tier: peer-reviewed empirical.
- Causal status: intervention-associated; not detachment; not nonattachment.
- Alternative interpretations: demand characteristics of instructed breathing; press language exceeds the task; parasympathetic activation is not psychological detachment.
- Limitations: risky-choice task; not meditation versus propofol EEG; not beta_1-loop or biological-quantum evidence.
- Replication requirement: preregistered breathing intervention with an active control and an independent sample.
- Repository hypothesis link: `H-AUDIT-BREATH-PARASYMPATHETIC`.
- Repository support: not granted.

### 4. Discernment / nonjudgment — confirmed requested DOI, plus nearby scale paper

- Requested source identity: DOI `10.1007/s12671-026-02976-7` — confirmed.
- Authors: Yu, Chio, Sik, Mak, Chen, Peng, Cheng.
- Title: Discerning Mindfulness or Nonjudging Mindfulness? Investigating the Relative Temporal Association of Discerning and Nonjudging Quality with Nonattachment and Mental Health.
- Source type: peer-reviewed longitudinal survey / psychometric article (*Mindfulness*, 2026).
- Peer-review status: peer reviewed.
- Claim text: over eight months, nonattachment mediated a path from baseline discernment to later life satisfaction; nonjudgment did not show the same temporal associations.
- Source location: *Mindfulness* DOI `10.1007/s12671-026-02976-7`.
- Evidence tier: peer-reviewed psychometric longitudinal.
- Causal status: construct association, not a neural mechanism.
- Nearby confirmed comparison DOI: `10.1007/s12671-026-02770-5`, Sik, Yu, Chan, Ho, Mak, *Being Mindful with Discernment* (MDS scale validation). This nearby paper is a related construct instrument, not a correction of the requested DOI.
- Distinctions required by both papers: discernment is not nonjudgment; decentering is not nonattachment.
- Alternative interpretations: self-report method variance; non-meditator sample; no EEG or fMRI.
- Limitations: psychometric / survey evidence only.
- Replication requirement: keep the four constructs coded separately in any meditation-condition contract.
- Repository hypothesis link: `H-AUDIT-DISCERNMENT-NE-NONJUDGMENT`.
- Repository support: not granted.

### 5. Buddhist training ecology — confirmed theory paper

- Source identity: DOI `10.3389/fpsyg.2026.1938434` — confirmed.
- Authors: Yukun Mei, Jiyu Li, Sarawadee Phuchomsri.
- Title: From Buddhist meditation to psychological well-being: an ethical-cultural training ecology model.
- Source type: theory paper (*Frontiers in Psychology*, Hypothesis and Theory, published 3 Sep 2026).
- Peer-review status: peer reviewed as a theory article, not as an empirical report.
- Claim text: meditation is a coordinated ethical-cultural practice ecology; hypothesized mechanisms (attention, emotion regulation, self-decentering, nonattachment, compassion) acquire function through ecological configuration; authority reorganization is an explanatory principle; self-transcendence is a possible outcome.
- Source location: Frontiers Psychology article 10.3389/fpsyg.2026.1938434.
- Evidence tier: theory / hypothesis framework.
- Causal status: theoretical model, not evidence.
- Alternative interpretations: the model can be read as a taxonomy of practice conditions rather than a causal account of neural states.
- Limitations: three hypothetical illustrations and five untested propositions; no EEG, fMRI, or topology result.
- Replication requirement: convert the five propositions into preregistered empirical tests.
- Repository hypothesis link: `H-AUDIT-TRAINING-ECOLOGY-THEORY`.
- Repository support: not granted.

Identity note: this identifier resolves. It is not disputed. What is rejected is treating a Hypothesis and Theory article as empirical support for repository claims.

### Audit-control disputed DOI

- Identifier `10.1007/s12671-026-00000-0` is reserved as an unresolved control.
- Identity status: disputed.
- It must not enter the evidence store.
- Hypothesis link: `H-AUDIT-CONTROL-UNRESOLVED-DOI`.

## Claim board

Supported as source-identity facts only:

- arXiv:2609.03987 exists as a preprint on triadic functional connectivity.
- arXiv:2609.03172 exists as a preprint on higher-order spectra / modulograms.
- DOI `10.1016/j.neuron.2026.04.044` exists as a *Neuron* article on slow breathing and risky choice.
- DOI `10.1007/s12671-026-02976-7` exists as a *Mindfulness* longitudinal construct paper.
- Nearby DOI `10.1007/s12671-026-02770-5` exists as the MDS scale paper.
- DOI `10.3389/fpsyg.2026.1938434` exists as a Frontiers Hypothesis and Theory article.

Rejected or downgraded:

- Triadic FC as PITNN / topological / causal proof.
- Modulogram / trispectrum as a causal awareness or charge mechanism.
- Treating either arXiv paper as a peer-reviewed replication.
- Slow breathing as detachment or nonattachment.
- Equating discernment with nonjudgment, or decentering with nonattachment.
- Treating the training-ecology model as empirical evidence.
- Using the control DOI `10.1007/s12671-026-00000-0` as a source.

## Hypotheses proposed (not results)

- `H-AUDIT-TRIADIC-DEPENDENCE`
- `H-AUDIT-SPECTRAL-MODULOGRAM`
- `H-AUDIT-BREATH-PARASYMPATHETIC`
- `H-AUDIT-DISCERNMENT-NE-NONJUDGMENT`
- `H-AUDIT-TRAINING-ECOLOGY-THEORY`
- `H-AUDIT-CONTROL-UNRESOLVED-DOI`

A literature audit does not establish that the repository's theories are true.
