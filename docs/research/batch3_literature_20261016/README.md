# Batch 3 Literature and Public-Source Registry

- **Review date:** 2026-10-23 (UTC date of the primary-source fetch)
- **PR head reviewed:** `573d1480c14a6f9b0694e501797d4a7455cb7656` (merge of the registry correction with live `main`; the commit that records this SHA cannot name itself)
- **Live `main` at review:** `d78f54128b6fd60c30665c9e9cff307056dbdd82`
- **Scope:** Official upstream GitHub release/tag pages, tagged top-level license files, and PyPI JSON for the pinned versions. The GUDHI row also cites the upstream licensing page and leaves per-module licensing unresolved.
- **Data boundary:** No datasets or participant data were accessed, and no listed upstream candidate software was executed in this review.
- **Not validation:** This registry is not legal validation and not scientific validation.

## Separation of Claims

- **Verified release facts:** Each exact version is tied to its official upstream release/tag page; `release_date` is the UTC calendar date of that page's publication timestamp. Each license descriptor is tied to the linked top-level license text at that tag.
- **Not assessed:** Authors, CVE/security status, maintenance/support, dependency inventory, data-access behavior, and legal compatibility. `not assessed` is not a negative finding.
- **Compatibility recommendations:** `classification`, `adapter_boundary`, and `recommendation_notes` are project recommendations, not upstream facts, validated integrations, or endorsements.
- **Scientific findings:** This registry review makes none. A software release or license record is not empirical or scientific evidence.

## Software Systems

See `configs/research/batch3_source_registry.yaml` for the full structured registry.

### INTEGRATE (compatibility recommendations)
- MNE-Python, MNE-BIDS, MNE-Connectivity — candidates for separate adapter and fixture review; integration is not verified.

### EMULATE (compatibility recommendations)
- PyBIDS, PyNWB, GUDHI, Ripser.py — possible limited emulation or optional capability probes; no parity assessment was performed.
- GUDHI top-level `LICENSE` at `tags/gudhi-release-3.13.0` is MIT. Upstream https://gudhi.inria.fr/licensing/ states modules depending on CGAL/Miniball/PyKeOps are under GPLv3 or LGPL and that a GPL dependency is effectively GPL-3.0 for users of those modules. Per-module licensing requires project legal review and is unresolved. That is not a legal-compatibility conclusion.

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

- License descriptors are bounded transcriptions of the linked upstream root license at the reviewed tag; they do not inventory every dependency or determine legal compatibility. PyNWB's tagged license contains three BSD-style conditions plus an additional custom Enhancement clause, recorded explicitly rather than reduced to plain BSD-3-Clause.
- GUDHI: top-level LICENSE is MIT. Upstream https://gudhi.inria.fr/licensing/ states modules depending on CGAL/Miniball/PyKeOps are under GPLv3 or LGPL and that a GPL dependency is effectively GPL-3.0 for users of those modules. Per-module licensing requires project legal review; unresolved.
- Pins kept, and not described as latest: DANDI CLI `0.75.0`, REA `rea-agents-6.5.0`, and LangGraph `1.2.15`. Newer tags exist as of the access date; not reviewed. neurolib `v0.7.0` is the GitHub tag; PyPI latest is 0.6.2.
- Security, known vulnerabilities/CVEs, maintenance/support, dependencies, and data-access behavior are **not assessed**; no “low risk,” “active,” or “no known CVE” conclusion is made.
- `REJECT` for The Virtual Brain is a compatibility recommendation pending legal review, not legal advice or a finding about license compatibility.
- Any future integration requires a separate engineering, security, provenance, and legal review. No upstream candidate source was copied or executed for this registry.

## Next Actions

- Keep version and license assertions linked to release-tagged upstream artifacts; update them only after reviewing a new artifact.
- Keep compatibility labels and adapter boundaries clearly marked as recommendations.
- Do not promote these software records or topic labels to scientific evidence or validated integrations.
