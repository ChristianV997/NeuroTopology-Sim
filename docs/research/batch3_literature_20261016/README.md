# Batch 3 Literature and Public-Source Mining Package

**Access date:** 2026-10-16  
**Base commit:** 3f3fe85 (origin/main)  
**Scope:** Highest-value scientific methods and open-source systems for NeuroTopology-Sim and Awareness Studio.  
**Constraint:** No datasets downloaded. No third-party software executed. Literature review is not empirical evidence.

## Separation of Claims

- **Sourced facts:** Public GitHub/PyPI metadata, license texts, and version tags retrieved 2026-10-16.
- **Interpretation:** Relevance judgments relative to existing provenance, capability-registry, and falsification layers.
- **Hypotheses:** Testable statements that would need future empirical work (none currently supported).
- **Recommendations:** Classification (INTEGRATE / EMULATE / REFERENCE_ONLY / REJECT) with explicit adapter boundaries.

## Software Systems

See `configs/research/batch3_source_registry.yaml` for the full structured registry.

### Highest-value INTEGRATE candidates
- **MNE-Python** (BSD-3-Clause): Core I/O. Adapter already partially anticipated in provenance readers.
- **MNE-BIDS** (BSD-3-Clause): BIDS bridge.
- **MNE-Connectivity** (BSD-3-Clause): Spectral connectivity methods relevant to higher-order descriptors under audit.

### EMULATE (do not vendor heavy or copyleft code)
- PyBIDS, PyNWB, GUDHI, Ripser.py — implement minimal pure-Python or optional-probe equivalents.

### REFERENCE_ONLY
- BIDS Validator, DANDI CLI, Nilearn, DataLad, OpenLineage, neurolib, LangGraph.

### REJECT
- The Virtual Brain (GPL-3.0 copyleft).
- REA (out of scientific scope; REA_UNAVAILABLE for this batch).

## Scientific Literature Topics

All topics remain **REFERENCE_ONLY**. Prior higher-order literature audit (docs/research/higher_order_literature_audit.md) already classified five requested identifiers; none received `supported_for_repository: true`.

Testable hypotheses (not conclusions):
1. Higher-order (triadic) connectivity descriptors computed via MNE-Connectivity spectral methods on ds005620-style EEG will fail the K>100 null-calibration gate under phase-randomized surrogates.
2. Bispectrum/trispectrum features, after residualizing respiratory and autonomic regressors, will not uniquely identify contemplative state transitions beyond linear spectral power.
3. Any prospective state-transition forecast trained on synthetic neural-mass trajectories (neurolib/TVB style) will be rejected by the evidence_claim_allowed gate.

## License and Risk Summary

- Prefer BSD-3-Clause / MIT / Apache-2.0.
- Reject GPL-3.0 linking without legal review.
- All integrations must pass capability_snapshot, no-network socket patching, finite-JSON, and null-calibration.
- Do not copy code without license and provenance review.

## Next Actions

- Implement INTEGRATE adapters only after explicit capability-registry PR and offline fixture tests.
- Keep all scientific claims downgraded until empirical readiness audit reports READY_FOR_FORMAL_EVIDENCE_REVIEW.
