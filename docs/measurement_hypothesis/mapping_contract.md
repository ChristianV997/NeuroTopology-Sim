# Measurement/hypothesis mapping contract

Status: validator and offline tests. No feature is computed, no evidence state is assigned,
and no gate decision is changed.

Code: `shared/measurement_hypothesis/`. Tests: `tests/measurement_hypothesis/`.
Run: `python -m shared.measurement_hypothesis MAPPING.json [--as-of YYYY-MM-DD]`.

## What a mapping is

A mapping links one operational feature, meaning code that exists, to one interpretation,
meaning a hypothesis about what the feature might indicate. The record keeps the two sides
apart. The operational side is derived from code. The interpretation side is a proposal with
sources, assumptions, alternatives, confounds, and falsifiers.

The operator is imported only as a signal-processing generator. A mapping never treats a
mathematical operator as a physical object. EEG electrodes are not claimed to be literal
quantum-gauge objects.

## Namespaces

| Namespace | Fields | Rule |
|---|---|---|
| Operational | `operational`, `measurement`, `operator` | Identifiers are derived from code. No interpretation term may appear here. |
| Interpretation | `interpretation`, `sources` | Theory terms such as TTFCD or UTTL are allowed here, but only with a source reference. |

`feature_id` must equal `<symbol>.<output_key>`. A mapping cannot give an existing feature a
new name. `display_name`, `alias`, `feature_name`, and similar keys are rejected.

## What the validator checks

1. **Implementation resolves.** The module must be a file inside the repository (symlinks
   followed). The symbol must be a module-level function. Its output key and metric-kind literal
   must appear in that function. Preprocessing steps must resolve in the same module. Resolution
   is by AST only. Nothing is imported or executed.
2. **Checksum binds the mapping to current code.** `sha256` must match the file bytes. If the file
   changes, the mapping fails with `IMPLEMENTATION_DRIFT` until a reviewer re-reads it.
3. **Measurement is complete.** Units must be in `shared.feature_contracts.validators.VALID_UNITS`.
   Data type and preprocessing are required. A feature family, if given, must be a registered
   `FeatureFamily`. If none is given, the mapping must say why.
4. **Operator is a generator.** The role must be `signal_processing_generator`, and
   `literal_physical_identity` must be `false`.
5. **Interpretation is a proposal.** The claim class must be `hypothesis` or `speculation`. At least one
   each of assumption, alternative, confound, and falsifier is required. Each falsifier needs an id,
   a test, and a discriminating outcome. At least one source is required.
6. **Language stays a proposal.** Equivalence phrasing ("is identical to", "is literally") and
   causal or mechanistic phrasing ("causes", "mechanism", "underlies") match with no negation
   exemption: a preceding "not" does not clear them. Phrasing that presents a proposal as
   established ("confirms", "demonstrates", "proves") is rejected unless it is negated within
   a short window ("not yet validated"). The shared claim-language rules and the Level-O ontology
   firewall are also applied.
7. **Sources are exact.** Each source needs a title, an https URL, an exact version, a
   publication date, an access date no later than the validation date, and a verification level
   (`publisher_page`, `repository_page`, or `search_index_metadata`).
8. **The gate decides.** The proposal is passed read-only to `tools.research_claim_gate.gate.evaluate_claim`.
   The decision is recorded in the report. A decision other than `CLAIM_ADMISSIBLE` or
   `CLAIM_REQUIRES_REVIEW` blocks the mapping. Eligibility must stay false.
9. **Evidence fields are refused.** Any key such as `evidence_state`, `evidence_class`,
   `scientific_pass`, `formal_bayes_factor`, `gate_decision`, or `promotion`, at any depth, is
   rejected. The mapping cannot carry or request evidence.

Every report carries `evidence_ready: false`. `VALID_HYPOTHESIS_MAPPING` means the mapping is
well formed and its references resolve. It does not mean the interpretation is supported.

## Reused contracts

| Need | Reused from |
|---|---|
| Units and feature families | `shared.feature_contracts` (`VALID_UNITS`, `FeatureFamily`) |
| Claim decision and eligibility | `tools.research_claim_gate.gate.evaluate_claim` (read-only) |
| Claim-language rules | `shared.research_claims.language_rules.scan_text` |
| Forbidden ontology phrases | `sciencer_d.ontology.firewall.scan_text` |

The only new vocabularies are the mapping schema, the equivalence, causal, and support phrase
lists, and the interpretation-namespace term list. None of them assigns an evidence state.

## Fixtures

| Fixture | Expected result |
|---|---|
| `valid_hypothetical_mapping.json` | `VALID_HYPOTHESIS_MAPPING`; gate `CLAIM_ADMISSIBLE`; eligibility false |
| `missing_provenance.json` | `REJECTED`: `SOURCE_FIELD_MISSING` (accessed), `SOURCE_URI_NOT_HTTPS` |
| `theory_term_leak.json` | `REJECTED`: `THEORY_TERM_IN_OPERATIONAL_IDENTIFIER` on `feature_id`, plus `FEATURE_ID_NOT_DERIVED` |
| `empirical_support_implied.json` | `REJECTED`: `CLAIM_CLASS_NOT_PERMITTED`, `CAUSAL_OR_MECHANISM_LANGUAGE`, `EMPIRICAL_SUPPORT_IMPLIED`, and gate `CLAIM_REJECTED` |

## Sources used in the example

Each reference was confirmed from search-index metadata in this session. Publisher pages could
not be fetched from the build environment, so the DOIs were not resolved directly. Each entry
records its verification level.

| Source id | Reference | Used for |
|---|---|---|
| `barbarossa2020tsp` | Barbarossa and Sardellitti, "Topological signal processing over simplicial complexes," IEEE Trans. Signal Process. 68 (2020) 2992-3007, doi:10.1109/TSP.2020.2981920 | Operator as a signal-processing generator |
| `jiang2011hodge` | Jiang, Lim, Yao, and Ye, "Statistical ranking and combinatorial Hodge theory," Math. Program. Ser. B 127 (2011) 203-244, doi:10.1007/s10107-010-0419-x | Gradient, curl, and harmonic decomposition on graphs |
| `nolte2004` | Nolte et al., "Identifying true brain interaction from EEG data using the imaginary part of coherency," Clin. Neurophysiol. 115 (2004) 2292-2307, doi:10.1016/j.clinph.2004.04.029 | Volume-conduction alternative |
| `stam2007` | Stam, Nolte, and Daffertshofer, "Phase lag index," Hum. Brain Mapp. 28 (2007) 1178-1193, doi:10.1002/hbm.20346 | Common-source confound and falsifier F3 |

## What the mapping does not establish

- It does not establish that EEG electrodes are literal gauge or quantum objects.
- It does not establish that `phase_grad` measures phase circulation or any spatial topology.
  Channel-index order is not geometry, and the example's own assumption records that.
- It does not establish a causal or mechanistic relation, empirical support, or a scientific pass.
- It does not compute a formal Bayes factor, and it assigns no evidence state.
- It does not validate TTFCD or UTTL. Neither term is defined in this repository.
- It does not establish that the Hodge-decomposition features (coexact, harmonic) exist. Neither
  appears in the codebase. A mapping that names them is rejected with `SYMBOL_UNRESOLVED`.
- Keyword rules are a conservative screen, not a semantic review.
