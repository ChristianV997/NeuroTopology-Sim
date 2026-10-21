# Theory-to-Measurement Review (Batch 3, Grok Chat A)

**Audit date:** 2026-10-21
**Current-main reference:** `4e91c6f080647280940ded4f90f4ee9278960c4b`
**PR content reviewed before correction:** `5634a707db09457330b413f739b2dd8eebf89647`
**Scope:** Claim-language and citation-scope review for the five propositions in the Batch 3 matrix. The categories identify the kind of bridge under review, not whether the proposition is true.
**Method:** Checked the cited public source pages and current repository claim-language contract. This was a bounded source check, not a systematic literature review or a line-by-line model audit.

## Reading the matrix

Each `review_question` is a proposition being evaluated, not an asserted result. `direct_support_for_proposition` asks whether that particular source supports the proposition as written; it is not a rating of source quality. Every source record states its support scope and limitations. Repository policies and prior audits are labeled as repository sources, not primary scientific evidence.

A computational representation, an operational measurement, empirical evidence, a formal identity, and a biological/mechanistic interpretation are separate levels. Support at one level does not automatically transfer to another.

## Claim-by-claim source assessment

| ID | Proposition class | Sources checked | Direct support for proposition? | Review finding |
|---|---|---|---|---|
| TTM-001 | Computational analogy / borrowed operator | Giusti et al. (2016), a peer-reviewed methodological review | Yes, narrowly: it describes simplicial complexes as higher-order representations and reviews neural-data applications | Supports a computational representation, not the biological validity of a resulting EEG/fMRI measure. |
| TTM-002 | Operational measurement | Current repository evidence/claim-language contract | No | A formal model-comparison threshold is not, by itself, validation of a measurement construct or identification of a biological mechanism. No primary empirical source establishing the PITNN-to-mechanism mapping is cited here. |
| TTM-003 | Biological/mechanistic interpretation | Fröhlich (1968), Diósi (1984), and Penrose (1996) theoretical papers | No | These sources concern theoretical proposals; they do not establish that the corresponding processes are measured in macroscopic EEG/fMRI. No primary source for an exceptional-point-to-EEG biological mapping was identified in this bounded review. |
| TTM-004 | Formal mathematical identity | Current repository claim-language contract | No | The contract explicitly keeps graph cycle rank, spatial winding/topological charge, and scalar chirality distinct. The identity is not supported. |
| TTM-005 | Empirical evidence | Li et al. (arXiv:2609.03987) and Kovach & Kumar (arXiv:2609.03172), version 1 pages | No | The preprints report their own triadic-connectivity and higher-order-spectral methods; the inspected source pages do not test the repository-specific PITNN, spatial-charge, or quantum-mechanism propositions. This is a citation-scope finding, not a disconfirmation of those hypotheses. |

## Detailed assessment

### TTM-001 — Computational representation is not measurement validation

**Question under review:** Can simplicial-complex methods represent groupwise relationships beyond pairwise edges in neural-data analyses?

Giusti, Ghrist, and Bassett describe simplicial complexes as a generalization of graph representations and review applications to neural data ([2016 article](https://doi.org/10.1007/s10827-016-0608-6)). This is a methods review, not an independent empirical validation of a biological construct. It supports the narrow computational-representation proposition only.

Whether a particular EEG/fMRI-derived feature measures biologically meaningful higher-order neural interaction is a separate operational question. This review did not estimate source mixing, reference, montage, threshold, filtering, or nonstationarity effects. Those are potential controls for future tests, not effects demonstrated by this artifact.

### TTM-002 — A statistical gate does not identify a mechanism

**Question under review:** Would a formal Bayes factor greater than 100 for a PITNN feature establish that the feature measures a biological topological mechanism in EEG?

The current [repository claim-language contract](https://github.com/ChristianV997/NeuroTopology-Sim/blob/4e91c6f080647280940ded4f90f4ee9278960c4b/docs/scientific_falsification/claim_language.md) defines the project’s evidence boundary and explicitly distinguishes proxy quantities from formal Bayes factors. That internal contract is not an empirical source for construct or mechanism validity.

The earlier draft asserted that a PITNN gate failed “20/20” on ds005620. I could not locate a linked run record in the reviewed PR, documentation, or report tree that establishes the exact run, configuration, and count. The number is removed from the matrix and is not relied on as evidence. No participant files or dataset contents were inspected.

### TTM-003 — Theoretical proposals do not establish a biological EEG mapping

**Question under review:** Do simulations using Fröhlich-like coherence, Diósi–Penrose state-reduction proposals, or exceptional-point dynamics establish biological quantum or critical processes measured in macroscopic EEG/fMRI?

The original Fröhlich article proposes long-range coherence in biological systems ([Fröhlich, 1968](https://doi.org/10.1002/qua.560020505)). Diósi’s article proposes gravitationally related quantum localization ([Diósi, 1984](https://doi.org/10.1016/0375-9601(84)90397-9)); Penrose develops a theoretical argument concerning gravity and quantum state reduction ([Penrose, 1996](https://doi.org/10.1007/BF02105068)). These are theory papers, not demonstrations that the proposed processes occur in the brain or are identifiable from EEG/fMRI. The source set checked here contains no primary empirical source for the exceptional-point-to-EEG mapping either. That bounded finding must not be read as proof that no such source exists.

A classical model remains an alternative to test, not a result of this review. No simulation comparison, biophysical parameter validation, or empirical identifiability analysis was run here.

### TTM-004 — Graph cycle rank is not spatial winding or charge

**Question under review:** Is the cycle rank (β₁) of a constructed functional-connectivity graph mathematically identical to spatial winding number or topological charge?

The current repository [claim-language contract](https://github.com/ChristianV997/NeuroTopology-Sim/blob/4e91c6f080647280940ded4f90f4ee9278960c4b/docs/scientific_falsification/claim_language.md) explicitly keeps `graph_beta1`, `spatial_winding_q`, and `scalar_chirality` distinct and prohibits calling graph beta-1 spatial charge. The contract is a project rule, not evidence that either quantity measures a biological construct. The submitted proposition has no direct support in the cited source and must not be promoted.

### TTM-005 — Methodological overlap is not evidence for repository-specific mechanisms

**Question under review:** Do the cited triadic-connectivity and higher-order-spectral papers provide empirical evidence for this repository’s PITNN, spatial-charge, or quantum-layer mechanisms?

Li et al.’s arXiv v1 page reports a triadic functional-connectivity method and analyses distinguishing resting-state from task activity ([arXiv:2609.03987](https://arxiv.org/abs/2609.03987)). Kovach and Kumar’s arXiv v1 page describes higher-order spectral/modulogram methods and illustrates them with beta-burst detection in rodent and human local-field-potential recordings ([arXiv:2609.03172](https://arxiv.org/abs/2609.03172)). These source pages describe their own methods and reported analyses; they do not test the repository-specific PITNN, graph-charge, or open-quantum propositions. The arXiv pages were checked at version 1; publication or independent replication status beyond those pages was not verified for this audit.

The source-scope mismatch means these citations do not support the proposed upgrade. It does not disconfirm the underlying hypotheses.

## Open questions and limits

- Whether any higher-order descriptor measures a stable construct after matched pairwise and spatial-surrogate controls remains untested here.
- No independent cohort, participant data, or dataset artifacts were accessed.
- No model, solver, or third-party code was executed for this source review.
- Citation presence, source identity, and a completed audit do not establish scientific validity, causation, biological mechanism, or replication.
- All falsifiable tests in the matrix are proposed future tests, not results from this audit.

## Explicit non-promotion

This artifact does not emit or assign scientific `VALIDATED` status and does not establish any scientific claim. It records a bounded review of source scope and claim wording only. The project remains **HOLD / SYNTHETIC_ONLY**.

**Retrieval date:** 2026-10-21.
**Evidence boundary:** Public source pages and repository documentation only; no participant data, dataset contents, or third-party code.
