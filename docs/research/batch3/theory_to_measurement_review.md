# Theory-to-Measurement Review (Batch 3, Grok Chat Agent A)

**Audit date:** 2026-10-16  
**Base commit:** `3f3fe8593303184cb88eef056c1322f3d4e57a16` (origin/main)  
**Scope:** Independent source-grounded review of theoretical-to-operational bridges implied by repository materials (PITNN, open-quantum / Fröhlich / EP layers, higher-order topological descriptors, graph beta-1, entropy production) in the context of prior Batch 1/2 audits and the higher-order literature audit.  
**Not a line-by-line equation audit** (that narrower task was assigned elsewhere).  
**Retrieval:** Public peer-reviewed sources and official repository claim-language contracts. Preprints labeled as such. Gemini-generated assertions or test output are not treated as primary evidence.

## Distinctions enforced

| Category | Meaning | Does not license |
|----------|---------|------------------|
| Formal mathematical identity | Proven equality under stated axioms | Empirical measurement of a biological construct |
| Computational analogy / borrowed operator | Operator transferred from another domain | Identity with the biological mechanism |
| Operational measurement claim | Feature is computable from sensors | Feature measures the proposed construct |
| Empirical claim | Observation under stated controls | Causal or mechanistic interpretation |
| Phenomenological / mechanistic interpretation | Narrative linking math to biology | Confirmation without independent identification |

“A feature is computable” ≠ “the feature measures the proposed biological construct.”

## Source-to-claim table (summary)

| Claim ID | Category | Strongest primary source | Direct support? | Key assumption | Counterevidence / uncertainty | Alternative | Falsifiable test |
|----------|----------|---------------------------|-----------------|----------------|-------------------------------|-------------|------------------|
| TTM-001 | Computational analogy | Giusti et al. 2016 (J Comput Neurosci) simplicial complexes for higher-order neural structure | Nearby only (graph → simplicial encoding) | Sensor data embed higher-order relations | Volume conduction, inverse non-uniqueness, reference choice | Pairwise + noise or linear mixing | Pre-registered pairwise nulls on independent EEG cohort; source-space vs sensor-space discrepancy |
| TTM-002 | Operational measurement | Repository claim_language.md + prior PITNN K>100 gate failure (20/20 on ds005620) | No (gate failed) | K>100 from empirical marginal likelihood | Synthetic/proxy never PASS; no independent replication | Classifier accuracy without topological invariant | Independent cohort, full provenance, multiplicity-controlled formal K>100 with pairwise baselines |
| TTM-003 | Phenomenological interpretation | Open-quantum Fröhlich / EP simulation literature (theoretical) | No empirical identification from EEG/fMRI | Quantum coherence or EP maps to macroscopic EEG | No validated biological quantum inputs; decoherence timescales | Classical nonlinear oscillator or filtered noise | Biophysical constraint matching (temperature, coupling) + null classical models that reproduce the same EEG descriptors |
| TTM-004 | Formal mathematical identity (graph) | Algebraic topology textbooks / Betti number definitions | Yes for graph cycle rank | Graph constructed from thresholded connectivity | Threshold dependence, nonstationarity, phase uncertainty at amplitude zeros | Alternative filtrations or random geometric graphs | Sensitivity analysis across thresholds and montages; comparison to spatial winding number (distinct per claim_language) |
| TTM-005 | Empirical claim (higher-order) | Higher-order literature audit (arXiv:2609.03987 preprint, Neuron 2026 breathing paper, etc.) | Source identity only; supported_for_repository=false | Triadic or spectral features add information | Preprint status; construct confounds (discernment ≠ nonjudgment) | Pairwise baselines + demand characteristics | Preregistered independent replication with pairwise and null models |

Full matrix in `reports/batch3/grok_chat_a/claim_matrix.json`.

## Detailed claims

### TTM-001 — Simplicial / higher-order operators license measurement of neural higher-order structure

- **Statement:** Algebraic-topological operators (simplicial complexes, persistent homology, higher-order spectra) applied to EEG/fMRI functional connectivity measure biologically meaningful higher-order interactions beyond pairwise dependence.
- **Category:** Computational analogy / borrowed operator.
- **Strongest source:** Giusti, Ghrist, Bassett (2016) “Two’s company, three (or more) is a simplex,” *J Comput Neurosci* 41:1–14. DOI: 10.1007/s10827-016-0608-6. Primary mathematical result on encoding non-dyadic relations.
- **Direct support?** Only for the mathematical encoding step. Does not establish that EEG sensor measurements recover the underlying simplicial structure of neural interactions.
- **Assumptions:** Connectivity matrix faithfully represents interactions; embedding dimension and filtration recover relevant topology; sensors sample the relevant manifold.
- **Counterevidence / uncertainty:** Volume conduction mixes sources; reference choice and montage geometry alter pairwise measures; inverse problem non-uniqueness; phase uncertainty near amplitude zeros; nonstationarity; limited sensor coverage.
- **Alternatives:** Linear mixing of pairwise sources; thresholding artifacts; spectral leakage from filtering.
- **Falsifiable prediction:** On independent, preregistered EEG data, higher-order descriptors must significantly outperform pairwise + matched nulls (phase-randomized, spatial-surrogate) after controlling for volume conduction (source-space vs sensor-space) and reference. Failure on both spaces disconfirms the operational claim.
- **Evidence limit:** Literature audit already set supported_for_repository=false.

### TTM-002 — PITNN / K>100 gate as evidence of topological neural network mechanism

- **Statement:** Phase-invariant topological neural network (PITNN) features that pass a formal Bayes-factor gate K>100 identify a topological mechanism in EEG.
- **Category:** Operational measurement claim (computable) vs empirical claim (gate failed).
- **Strongest source:** Repository scientific falsification contract and prior execution result: PITNN K>100 gate failed 20/20 on ds005620. Claim language explicitly separates proxy K from formal Bayes factor.
- **Direct support?** No. Gate failure is the available result.
- **Assumptions:** Marginal likelihood correctly specified; multiplicity controlled; provenance complete.
- **Counterevidence:** Explicit failure; synthetic/proxy never allowed as PASS.
- **Alternatives:** Overfitting to noise structure; incomplete null models; dataset-specific artifacts.
- **Falsifiable test:** Independent dataset, locked analysis pipeline, formal K>100 with pairwise spectral and graph baselines, full provenance, and sensitivity to filtering/montage. Current result is disconfirming for the operational claim on that dataset.

### TTM-003 — Open-quantum / Fröhlich condensation / exceptional-point layers map to EEG

- **Statement:** Open quantum system simulations of Fröhlich condensation, Diósi-Penrose effects, or exceptional points produce descriptors that measure biological quantum or critical phenomena in macroscopic EEG.
- **Category:** Phenomenological / mechanistic interpretation.
- **Strongest source:** Theoretical physics literature on Fröhlich condensates and exceptional points (e.g., classical reviews of coherent excitations; modern EP literature in non-Hermitian systems). No peer-reviewed primary source demonstrates identification from standard EEG/fMRI.
- **Direct support?** No. Prior review: “PITNN/open-quantum/EP layers are speculative and not empirically identifiable from available EEG/fMRI.”
- **Assumptions:** Quantum coherence timescales survive to macroscopic sensors; gravitational or EP effects are detectable above thermal noise.
- **Counterevidence / uncertainty:** Decoherence rates at biological temperatures; lack of validated quantum inputs for the simulation; classical nonlinear models can produce similar spectral and topological descriptors.
- **Alternatives:** Classical limit-cycle oscillators, filtered 1/f noise, or thresholded connectivity graphs.
- **Falsifiable prediction:** Biophysical parameter constraints (temperature, coupling strength, timescale) must be matched by the simulation, and a classical null model of equal complexity must fail to reproduce the same EEG topological statistics under the same sensor forward model. Current simulations do not meet this bar.
- **Evidence limit:** Historical repository prose; not a current empirical claim.

### TTM-004 — Graph beta-1 as spatial topological charge

- **Statement:** Graph cycle rank (beta-1) computed on functional connectivity equals or measures spatial winding number / topological charge.
- **Category:** Formal mathematical identity for the graph quantity; does not transfer to spatial charge.
- **Strongest source:** Repository claim_language.md (explicit distinction: graph_beta1, spatial_winding_q, scalar_chirality remain distinct). Standard algebraic topology definitions.
- **Direct support?** Yes for the graph definition; no for the identification with spatial charge.
- **Assumptions:** Graph construction preserves spatial topology.
- **Counterevidence:** Different constructions (threshold, lag, source vs sensor) yield different beta-1; spatial winding requires a continuous field or embedding not recovered by graph cycle rank.
- **Alternatives:** Cycle rank as a connectivity complexity measure only.
- **Falsifiable test:** Compute both quantities on the same data under controlled embeddings; systematic divergence under montage or inverse changes disconfirms identity.
- **Evidence limit:** Explicitly prohibited as promoted language.

### TTM-005 — Higher-order literature as support for repository theories

- **Statement:** Preprints on triadic FC, higher-order spectra, and related construct papers support PITNN, topological charge, or quantum-layer claims.
- **Category:** Empirical claim (source identity) / phenomenological interpretation (upgrade).
- **Strongest source:** Higher-order literature audit (docs/research/higher_order_literature_audit.md) on origin/main. All five requested identifiers confirmed as sources; all supported_for_repository=false.
- **Direct support?** Source existence only.
- **Assumptions:** Methodological similarity implies theoretical support.
- **Counterevidence:** Preprint status; construct confounds (discernment ≠ nonjudgment; breathing ≠ detachment); no EEG topology or quantum identification.
- **Alternatives:** Independent methodological contributions that do not license the repository’s mechanistic claims.
- **Falsifiable test:** Independent replication that simultaneously satisfies the repository’s falsification contract (K>100, provenance, nulls). Current audit disconfirms the upgrade.
- **Evidence limit:** Explicit downgrade in the literature audit.

## Alternative explanations (cross-cutting)

1. Volume conduction and source mixing produce apparent higher-order dependence from pairwise sources.
2. Reference electrode and montage geometry systematically alter phase and connectivity estimates.
3. Filtering and Hilbert phase extraction introduce uncertainty near amplitude zeros and nonstationarity.
4. Inverse-problem non-uniqueness allows multiple source configurations consistent with the same sensor data.
5. Graph or persistent-homology features capture complexity or noise structure rather than a specific biological construct.
6. Quantum or EP simulations are computational analogies whose macroscopic predictions are indistinguishable from classical nonlinear models under current sensor constraints.

## What remains unknown

- Whether any higher-order descriptor survives rigorous pairwise + spatial-surrogate nulls in source space on independent data.
- Whether formal K>100 can be obtained under the full falsification contract on any real dataset.
- Whether classical models of equal complexity can reproduce the topological statistics attributed to quantum or EP layers.
- The precise contribution of volume conduction versus genuine higher-order interactions under realistic forward models.
- Independent replication status of the cited preprints.

## Explicit non-promotion

This review does not introduce VALIDATED status. No claim is promoted. Successful completion of the audit artifact does not establish that any scientific hypothesis is true. A literature or theory-to-measurement review is not scientific evidence for the repository’s theories.

**Retrieval date for all sources:** 2026-10-16.  
**Source types:** Peer-reviewed articles, repository claim contracts, prior audit documents. Preprints labeled.  
**Evidence limits:** No participant data downloaded; no third-party code executed; no network during validation.
