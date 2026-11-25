# Scientific-Release Conformance Suite

Owner: `tests/release_readiness/scientific_conformance/**`,
`scripts/validate_scientific_release_conformance.py`.

## What this is

An **additive** end-to-end fixture suite testing whether the integrated
research-cycle system actually refuses invalid scientific claims and
incomplete evidence — not a new gate, not a new implementation. It
consumes two already-merged, canonical modules as read-only dependencies
and never modifies or duplicates either:

- `tools/research_claim_gate/gate.py` — `evaluate_claim()`, the
  production claim gate.
- `tools/simulation_artifacts/extractor.py` — `extract_run()`, the
  production simulation-artifact extractor.

This suite's only job is to throw adversarial, synthetic, local fixtures
at those two real functions and assert they behave the way a release
process needs them to: reject bad science, never invent a PASS, never
silently zero-fill a missing value.

## How these fixtures were derived

Every fixture's expected outcome was verified against the real
`evaluate_claim()`/`extract_run()` *before* being committed here — see
`conftest.py`'s `ADVERSARIAL_CASES` table, which pairs each fixture with
the exact decision and reason code the real gate produces for it. This
suite does not guess at the gate's behavior; every assertion was checked
against actual code, not documentation, so if `gate.py` or `extractor.py`
change their logic, these tests will fail loudly rather than silently
pass on the old assumption.

## The four-way outcome taxonomy

The claim gate has eight `DECISION_STATES`
(`CLAIM_ADMISSIBLE, CLAIM_REQUIRES_REVIEW, CLAIM_DOWNGRADED,
CLAIM_REJECTED, CLAIM_INCOMPLETE, CLAIM_SYNTHETIC_ONLY,
CLAIM_PROVENANCE_INVALID, CLAIM_NOT_COMPARABLE`). This task's four
required outcomes (`BLOCKED`, `INCOMPLETE`, `DOWNGRADED`,
`REVIEW_REQUIRED`) are a generalization over those eight
(`conftest.py::DECISION_BUCKET`):

| Gate decision | Bucket |
|---|---|
| `CLAIM_REJECTED`, `CLAIM_SYNTHETIC_ONLY`, `CLAIM_PROVENANCE_INVALID`, `CLAIM_NOT_COMPARABLE` | `BLOCKED` |
| `CLAIM_INCOMPLETE` | `INCOMPLETE` |
| `CLAIM_DOWNGRADED` | `DOWNGRADED` |
| `CLAIM_REQUIRES_REVIEW` | `REVIEW_REQUIRED` |
| `CLAIM_ADMISSIBLE` | *(not a bucket — the one outcome no adversarial fixture may reach)* |

`tools/simulation_artifacts/extractor.py`'s own status vocabulary
(`COMPLETE, INCOMPLETE, PARTIAL, FAILED, CONFLICTING, BLOCKED`) is
checked directly for the one scenario the claim gate has no reason code
for (partial/timed-out simulation): every adversarial run fixture must
land in `{INCOMPLETE, PARTIAL, FAILED, CONFLICTING, BLOCKED}`, never
`COMPLETE`.

## Scenario → fixture → expected outcome

| Required scenario | Fixture | Decision | Reason code |
|---|---|---|---|
| Synthetic output presented as empirical | `synthetic_output_as_empirical` | `CLAIM_SYNTHETIC_ONLY` | `SYNTHETIC_NOT_EMPIRICAL` |
| Proxy dependence presented as causality | `proxy_dependence_as_causality` | `CLAIM_DOWNGRADED` | `PROXY_NOT_CAUSAL` |
| Fabricated provenance | `fabricated_provenance` | `CLAIM_PROVENANCE_INVALID` | `INVALID_PROVENANCE` |
| Missing checksum | `missing_checksum` | `CLAIM_PROVENANCE_INVALID` | `INCOMPLETE_PROVENANCE` |
| Invalid condition labels | `invalid_condition_labels` | `CLAIM_REJECTED` | `UNVERIFIED_LABELS` |
| Train/test subject overlap | `train_test_subject_overlap` | `CLAIM_REJECTED` | `SUBJECT_SESSION_OVERLAP` |
| Temporal leakage | `temporal_leakage` | `CLAIM_REJECTED` | `FUTURE_PAST_LEAKAGE` |
| Future-sample features | `future_sample_features` | `CLAIM_REJECTED` | `FUTURE_PAST_LEAKAGE` |
| Missing multiplicity metadata | `missing_multiplicity_metadata` | `CLAIM_REQUIRES_REVIEW` | `MISSING_MULTIPLICITY_CORRECTION` |
| Missing null model | `missing_null_model` | `CLAIM_REQUIRES_REVIEW` | `MISSING_NULL_CONTROLS` |
| Partial or timed-out simulation | `fixtures/simulation_runs/{partial_run,failed_run}` | `PARTIAL` / `FAILED` (extractor status) | — |
| Full-dataset download request | `full_dataset_download_request` | `CLAIM_REJECTED` | `NETWORK_ACCESS_NOT_APPROVED` |
| Network-policy violation | `network_policy_violation` | `CLAIM_REJECTED` | `NETWORK_ACCESS_NOT_APPROVED` |
| Dry-run placeholder metrics | `dry_run_placeholder_metrics` | `CLAIM_DOWNGRADED` | `FORMAL_METHOD_NOT_VALIDATED` |
| Topology/physiology namespace confusion | `topology_namespace_confusion`, `physiology_namespace_confusion` | `CLAIM_REJECTED` | `GRAPH_BETA1_NOT_SPATIAL_CHARGE`, `PARASYMPATHETIC_NOT_EQUANIMITY` |

Plus three bonus fixtures beyond the required 15, strengthening coverage
of the gate's other hard-reject rules: `triadic_dependence_as_causal`
(`TRIADIC_NOT_CAUSAL`), `unsupported_claim_class`
(`UNSUPPORTED_CLAIM_CLASS`), `unknown_claim_class`
(`UNKNOWN_CLAIM_CLASS`).

And one **control** fixture, `accepted_baseline`: a well-formed claim
with complete provenance, verified labels, a declared null control,
uncertainty, and effect size. It must be admitted
(`CLAIM_ADMISSIBLE`) — proving this suite tests *discrimination*, not
blanket rejection. A conformance suite that rejects everything, good
science included, would be worthless.

### A known gap in the gate's own vocabulary

"Temporal leakage" and "future-sample features" are listed as two
separate required scenarios, but the current `gate.py` has exactly one
reason code for both (`FUTURE_PAST_LEAKAGE`, driven by a single
`future_to_past_leakage` boolean field). This suite tests both as
distinct fixtures anyway (different fixture text, same underlying
mechanism) and documents the gap here rather than inventing a second
reason code the real gate doesn't have — see `KNOWN_LIMITATIONS` in the
handoff for this PR.

## Requirement-by-requirement mapping

3. **Invalid states become BLOCKED/INCOMPLETE/DOWNGRADED/REVIEW_REQUIRED** — `test_claim_gate_conformance.py::test_adversarial_fixture_is_never_admissible`, one case per fixture, asserting both the exact decision and its bucket.
4. **No fixture can produce scientific PASS or a formal Bayes factor** — `test_invariants.py::test_no_fixture_ever_produces_scientific_pass_or_a_formal_bayes_factor` (parametrized over every fixture) plus `test_injecting_a_fake_pass_or_bayes_factor_into_the_input_has_no_effect` (an injection-resistance test: adding `scientific_pass: true` / `formal_bayes_factor: 999.0` / `decision: "CLAIM_ADMISSIBLE"` to the raw input has zero effect, since `evaluate_claim` never reads those field names from its input).
5. **Missing values remain null, never silently zero-filled** — `test_unknown_number_of_tests_stays_null_not_defaulted_to_one` (holds the gate to its own documented reason message: "number of tests is unknown and was not treated as one test"), `test_malformed_input_leaves_identity_fields_null_not_zero_or_empty_string`, `test_missing_provenance_fields_stay_null_in_the_serialized_provenance_record`.
6. **Release-evidence decisions remain engineering review decisions, not scientific confirmation** — `test_decision_is_never_reported_as_a_scientific_confirmation` (parametrized over every fixture, checking the literal serialized output, not just the Python object).
7. **Deterministic, finite, local-only, synthetic** — `test_fixtures_are_deterministic_across_repeated_evaluation`, `test_serialized_gate_output_is_finite_json`, `test_fixtures_are_locally_loadable_and_are_pure_json_with_no_network_markers`, `test_no_network.py` (static import scan + confirms `network_access_performed` is always `False`, even for the two fixtures that *request* network access).
8. **Machine-readable report with `evidence_class=scientific_release_conformance`** — `scripts/validate_scientific_release_conformance.py::build_report`, tested by `test_report_script.py`.

## The report

```bash
python -m scripts.validate_scientific_release_conformance --output-dir artifacts/scientific_release_conformance
```

Writes `scientific_release_conformance_report.json`:
`schema_version`, `evidence_class: "scientific_release_conformance"`,
`generated_at`, `conformant` (bool — the overall pass/fail), `invariants`
(seven named booleans, one per check above), `claim_gate_cases` (every
fixture's decision/bucket/reason_codes/scientific_pass/
formal_bayes_factor/network_access_performed), `simulation_artifact_cases`
(every run fixture's status/evidence_class/synthetic flag), `summary`
counts, a `note` explicitly stating the report is not itself a scientific
finding, and `report_sha256` (computed last, excluding itself).
Deterministic given the same `--now`; exit code `0` when `conformant`,
`1` otherwise.

## This suite does not certify scientific truth

It certifies that the **engineering gate** correctly declines to promote
weak, incomplete, or adversarially-mislabeled input to a stronger claim
than the evidence supports. `conformant: true` means the gate behaved
correctly on this fixture battery — it says nothing about whether any
real result NeuroTopology-Sim produces is true.
