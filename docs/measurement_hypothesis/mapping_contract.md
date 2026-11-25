# Measurement/hypothesis mapping contract (schema v2)

Status: validator and offline tests. No feature is computed, no evidence state is assigned,
no gate decision is changed, and no empirical analysis is run.

Code: `shared/measurement_hypothesis/`. Tests: `tests/measurement_hypothesis/`.
Run: `python -m shared.measurement_hypothesis MAPPING.json [--as-of YYYY-MM-DD]`.
Claim classification of the Round 6 claims and adjacent audits: `claim_levels_audit.md`.

## The five levels

A mapping keeps five levels apart. Each has its own block, and no block may stand in for another.

| Level | Block | What the validator requires |
|---|---|---|
| 1. Formal or borrowed identity | `operator` | `identity_status` is `borrowed_formal_identity`, `implementation_only`, or `none`. A borrowed identity states its `identity_conditions`. The operator is a signal-processing generator and never a physical object. |
| 2. Implemented numerical descriptor | `operational` | A closed `category`, and the implementation resolves to code. The checksum is computed over source bytes with CRLF line endings normalized to LF, so it is stable across Windows and POSIX checkouts while still detecting source-content changes. |
| 3. Sensor-space measurement | `measurement` | Units, data type, preprocessing, and `observables` in sensor space. |
| 4. Empirical claim | `empirical_claim` | Statement, required data, analysis design, and controls. `status` is `NOT_RUN` and `data_access` is `NOT_AUTHORIZED`. |
| 5. Interpretation | `interpretation` | A `hypothesis` or `speculation` proposal with assumptions, alternatives, confounds, falsifiers, and sources. |

`construct_validity` sits beside the levels. Its `status` may only be `NOT_ESTABLISHED`. Its
`intended_construct` and `basis` are required.

## Computability is not construct validity

The report carries both, and they are independent:

- `computable`: the implementation resolves, its checksum matches, the output key and metric-kind
  literal are produced, and the preprocessing steps resolve.
- `construct_validity_status`: always `NOT_ESTABLISHED`.
- `measures_intended_construct`: always `false`.

A descriptor can be computable and still rejected, for example when its construct validity is
overstated. The report then shows `computable: true`, `contract_status: REJECTED`, and
`measures_intended_construct: false`.

## Operational categories

Closed vocabulary: `sensor_space_winding`, `graph_topological_statistic`, `origin_shift_identity`,
`synthetic_detector`, `sensor_space_phase_gradient`, `other_declared`. A missing or unknown
category fails closed, and a descriptor with no computable category is never reported as computable.

## Target constructs are never equated with a descriptor

For every category, a proposal, assumption, or observable may not equate the descriptor with:
cortical wave or propagation, source localization, consciousness, or biological validation.
An explicit negation ("is not a cortical wave") is allowed. An affirmative equation is rejected
with `EQUIVALENCE_TO_TARGET_CONSTRUCT`. The same check applies to the definition, operator name,
alternative explanations, confounds, falsifier `test` and `discriminates`, construct-validity
`basis`, and `required_data`. `intended_construct` is exempt, because it names the target.

Matching folds compatibility forms (NFKC), case, invisible format characters, and hyphen or
underscore separators, and maps Cyrillic look-alikes to Latin letters. A negation exempts a match
only when one whole-word negation sits directly before it. A double negation does not.

The empirical statement may name a target only as a question (ending in `?`), to test under the
declared controls. A non-question statement that names a target is rejected. Every statement is
scanned for equivalence and ontology-firewall wording. A non-question statement is also scanned for
causal and support wording, so a statement that reports a result (for example "was validated across
40 recordings") is rejected with `EMPIRICAL_SUPPORT_IMPLIED`, because the analysis is `NOT_RUN`.

## What the validator checks

1. **Structure.** Closed schema `v2`. Unknown fields rejected. Evidence and promotion fields are
   rejected at any depth. Non-finite numbers are rejected.
2. **Implementation.** A repository-relative module, resolved by AST without import or execution.
   The symbol must be module-level. Its output key and metric-kind literal must appear in it. A
   checksum mismatch is `IMPLEMENTATION_DRIFT`. CRLF is normalized to LF before hashing to avoid
   checkout line-ending differences changing the checksum.
3. **Operational identity.** `feature_id` must equal `<symbol>.<output_key>`. Interpretation terms
   such as TTFCD, UTTL, consciousness, and gauge may not appear in operational fields.
4. **Measurement.** Registered units, a data type, preprocessing steps that resolve in the same
   module, and at least one observable.
5. **Operator.** Role `signal_processing_generator`, `literal_physical_identity: false`, and an
   identity status with conditions when borrowed.
6. **Interpretation.** Class `hypothesis` or `speculation`. Non-empty assumptions, alternatives,
   confounds, and falsifiers. Each falsifier has an id, a test, and a discriminating outcome. At
   least one resolvable source. Equivalence, causal, and support wording rejected, support wording
   excepted only when negated. The shared claim rules and ontology firewall apply.
7. **Empirical claim.** Required fields present, controls non-empty, `status` exactly `NOT_RUN`,
   `data_access` exactly `NOT_AUTHORIZED`. Overstated statuses such as `PASS`, `VALIDATED`, or
   `SUPPORTED` are a distinct code.
8. **Construct validity.** `status` exactly `NOT_ESTABLISHED`. Overstated statuses such as
   `VALIDATED` or `PASS` are a distinct code.
9. **Sources.** An https URL, an exact version, a publication date, an access date no later than
   the validation date, and a declared verification level. Verification is provenance metadata:
   the offline validator checks its vocabulary but does not fetch or independently verify sources.
10. **Gate reference.** The proposal is passed read-only to `tools.research_claim_gate.gate.evaluate_claim`.
    A decision other than `CLAIM_ADMISSIBLE` or `CLAIM_REQUIRES_REVIEW` blocks the mapping. Scientific
    eligibility must remain false.

## Reused contracts

| Need | Reused from |
|---|---|
| Units and feature families | `shared.feature_contracts` (`VALID_UNITS`, `FeatureFamily`) |
| Claim decision and eligibility | `tools.research_claim_gate.gate.evaluate_claim` (read-only) |
| Claim-language rules | `shared.research_claims.language_rules.scan_text` |
| Forbidden ontology phrases | `sciencer_d.ontology.firewall.scan_text` |
| Statistical reporting | Not reimplemented. The merged `analysis/binomial_planning` package (PR #405) is the only operating-characteristic utility, and this contract does not duplicate it. |

## Fixtures

| Fixture | Expected result |
|---|---|
| `valid_hypothetical_mapping.json` | `VALID_HYPOTHESIS_MAPPING`; computable; gate `CLAIM_ADMISSIBLE`; eligibility false; construct validity not established |
| `missing_provenance.json` | `REJECTED`: `SOURCE_FIELD_MISSING` (accessed), `SOURCE_URI_NOT_HTTPS` |
| `theory_term_leak.json` | `REJECTED`: `THEORY_TERM_IN_OPERATIONAL_IDENTIFIER` and `FEATURE_ID_NOT_DERIVED`; not computable |
| `empirical_support_implied.json` | `REJECTED`: `CLAIM_CLASS_NOT_PERMITTED`, `CAUSAL_OR_MECHANISM_LANGUAGE`, `EMPIRICAL_SUPPORT_IMPLIED`, gate `CLAIM_REJECTED` |
| `origin_shift_cortical_wave_equivalence.json` | `REJECTED`: `EQUIVALENCE_TO_TARGET_CONSTRUCT`. Derived from Round 6 claim R6-007 (PR #412). |

## Sources used in the example

The bibliography records below were checked against publisher metadata on 2026-10-21. The IEEE,
Springer, and Wiley pages exposed the title, DOI, and cited volume/page metadata. The ScienceDirect
listing exposed the Nolte title and DOI, but its full page returned HTTP 403 in this review; the
volume/page and month in that record therefore remain unverified and its fixture label remains
`search_index_metadata`. The verified fields are bibliographic metadata only—not the scientific
claims, applicability, or construct validity. The validator itself remains offline and does not
repeat these checks: its `verification` field is a declared provenance label, not an automated
publisher lookup.

| Source id | Reference | Used for |
|---|---|---|
| `barbarossa2020tsp` | Barbarossa and Sardellitti, IEEE Trans. Signal Process. 68 (2020) 2992–3007, [doi:10.1109/TSP.2020.2981920](https://ieeexplore.ieee.org/document/9044758/) — publisher metadata checked | Operator as a signal-processing generator |
| `jiang2011hodge` | Jiang, Lim, Yao, and Ye, Math. Program. Ser. B 127 (2011) 203–244, [doi:10.1007/s10107-010-0419-x](https://link.springer.com/article/10.1007/s10107-010-0419-x) — publisher metadata checked | Gradient, curl, and harmonic decomposition on graphs |
| `nolte2004` | Nolte et al., *Identifying true brain interaction from EEG data using the imaginary part of coherency*, [doi:10.1016/j.clinph.2004.04.029](https://www.sciencedirect.com/science/article/pii/S1388245704001993) — title/DOI observed in publisher listing; remaining citation metadata unverified | Volume-conduction alternative |
| `stam2007` | Stam, Nolte, and Daffertshofer, Hum. Brain Mapp. 28 (2007) 1178–1193, [doi:10.1002/hbm.20346](https://onlinelibrary.wiley.com/doi/10.1002/hbm.20346) — publisher metadata checked; online publication date recorded | Common-source confound and falsifier F3 |

## What the mapping does not establish

- It does not establish that EEG electrodes are literal gauge or quantum objects.
- It does not establish that any descriptor measures cortical wave propagation, anatomical source
  activity, consciousness, or biological validity.
- It does not establish that `phase_grad` measures phase circulation or any spatial topology. Channel-index order is not geometry.
- It does not establish a causal or mechanistic relation, empirical support, or a scientific pass.
- It does not compute a formal Bayes factor, and it assigns no evidence state.
- It does not validate TTFCD or UTTL. Neither term is defined in this repository.
- It does not establish that the Hodge-decomposition features (coexact, harmonic) exist. Neither appears in the codebase.
- Keyword rules are a conservative screen, not a semantic review.
