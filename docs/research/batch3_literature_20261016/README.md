# Batch 3 Literature and Public-Source Registry

- **Review date:** 2026-10-21
- **PR head reviewed:** `69fb8af983a168ffd7934b9c03f95e5236007362`
- **Live `main` at review:** `4e91c6f080647280940ded4f90f4ee9278960c4b`
- **Scope:** Official upstream GitHub release/tag pages and top-level license artifacts for the listed software only.
- **Data boundary:** No datasets or participant data were accessed, and no listed upstream candidate software was executed in this review.

## Separation of Claims

- **Verified release facts:** Each exact version is tied to its official upstream release/tag page; each license label is tied to the linked top-level license text at that tag.
- **Not assessed:** Authors, CVE/security status, maintenance/support, dependency inventory, data-access behavior, and legal compatibility. `not assessed` is not a negative finding.
- **Compatibility recommendations:** `classification`, `adapter_boundary`, and `recommendation_notes` are project recommendations, not upstream facts, validated integrations, or endorsements.
- **Scientific findings:** This registry review makes none. A software release or license record is not empirical or scientific evidence.

## Software Systems

See `configs/research/batch3_source_registry.yaml` for the full structured registry.

### INTEGRATE (compatibility recommendations)
- MNE-Python, MNE-BIDS, MNE-Connectivity — candidates for separate adapter and fixture review; integration is not verified.

### EMULATE (compatibility recommendations)
- PyBIDS, PyNWB, GUDHI, Ripser.py — possible limited emulation or optional capability probes; no parity or dependency assessment was performed.

### REFERENCE_ONLY (compatibility recommendations)
- BIDS Validator, DANDI CLI, Nilearn, DataLad, OpenLineage, neurolib, LangGraph.

### REJECT (compatibility recommendations; legal review required)
- The Virtual Brain — upstream tag license is GPL-3.0-or-later; reject is a local recommendation, not a legal opinion.
- REA — out of scope for scientific-method integration in this registry.

## Scientific Literature Topics

The topics below are catalog labels only. Each has status `not assessed`; `REFERENCE_ONLY` is a recommendation, not a finding. This registry does not evaluate papers, identifiers, empirical support, or repository applicability.

- Higher-order and triadic functional connectivity
- Bispectrum and trispectrum methods
- Respiratory/autonomic modulation
- Contemplative discernment, nonattachment, and decentering
- Prospective state-transition forecasting
- Null-model and causal-identification limits

## License and Risk Summary

- The SPDX-style label is transcribed from the linked upstream root license at the reviewed tag. It does not cover every dependency or grant project-wide reuse clearance.
- Security, known vulnerabilities/CVEs, maintenance/support, dependencies, and data-access behavior are **not assessed**; no “low risk,” “active,” or “no known CVE” conclusion is made.
- `REJECT` for The Virtual Brain is a compatibility recommendation pending legal review, not legal advice or a finding about license compatibility.
- Any future integration requires a separate engineering, security, provenance, and legal review. No upstream candidate source was copied or executed for this registry.

## Next Actions

- Keep version and license assertions linked to release-tagged upstream artifacts; update them only after reviewing a new artifact.
- Keep compatibility labels and adapter boundaries clearly marked as recommendations.
- Do not promote these software records or topic labels to scientific evidence or validated integrations.
