# Evidence promotion gate

`tools/evidence_promotion_gate` is an offline, non-LLM **reporting/promotion
gate**. It decides whether a local artifact may be shown as engineering,
synthetic, proxy, literature-hypothesis, or descriptive-review material. It
does **not** confirm science, compute statistics, contact a network, or
promote any record to empirical evidence.

Scientific status on this repository remains `INCONCLUSIVE`. Synthetic output
remains `NOT_SUPPORTED`.

This package **calls** `tools.research_claim_gate.gate.evaluate_claim`. It
does not rewrite claim-gate behavior.

## Why this exists

RunRecords, RAG Markdown from `export_sim_artifacts`, command-center
payloads, Airtable-shaped cards, and research-cycle snapshots can display a
pipeline `verdict` or an `evidence_class` without a promotion check. A
synthetic or proxy record that appears as `PASS` / `EMPIRICAL` is the
highest-risk leak between the sim engine and Awareness Studio.

This gate is a sidecar consumer. It reads those artifacts and writes a
promotion decision file. It does not modify production writers.

## Decisions

Closed vocabulary:

| Decision | Meaning |
| --- | --- |
| `HOLD_SYNTHETIC_ONLY` | Synthetic, fixture, null, surrogate, or `performance_only`. Not empirical. |
| `HOLD_PROXY_ONLY` | Proxy K / RSS / AIC / AICc / BIC. `formal_bayes_factor` stays `null` unless a formal method was declared; even then this is not confirmation. |
| `HOLD_LITERATURE_HYPOTHESIS` | Literature `hypothesis` or `review_required`. Never `EMPIRICAL`. |
| `HOLD_INCOMPLETE_PROVENANCE` | Missing or incomplete provenance. Not treated as clean. |
| `HOLD_INCONCLUSIVE` | Unknown `n_tests`, unknown multiplicity, missing null controls, or otherwise uninterpretable. Unknown test count is never one test. |
| `BLOCK_PROMOTION` | Fail-closed block. Used when a downstream payload would display `verdict: PASS` or `evidence_class: EMPIRICAL`, or when a record declares `EMPIRICAL`. |
| `ADMISSIBLE_FOR_DESCRIPTIVE_REVIEW` | May be *reviewed* as descriptive. Not empirical confirmation. `scientific_pass` remains false. |
| `ADMISSIBLE_FOR_ENGINEERING_REPORT` | Engineering or benchmark reporting only. |

`scientific_pass` is always `false`. This gate never emits a scientific
`PASS`. `K == 100` is not a PASS. Missing metrics are JSON `null`. JSON never
contains NaN or Infinity.

### Dataset metadata readiness for descriptive data review

An attempted `descriptive_empirical` review is held as
`HOLD_INCONCLUSIVE` unless the input explicitly declares all of:

- `license_status: "compatible"`;
- `cohort_status: "consistent"`;
- `cohort_discrepancy: false`.

The fields may be top-level or grouped under `dataset_metadata` (including an
adapter `fields` object). Conflicting, unknown, incompatible, missing, or
malformed declarations block descriptive review eligibility. If multiple
artifacts declare these values, contradictory
declarations also block review. The gate does not infer a license from a URL,
identify a cohort from a dataset name, or verify the truth of these declarations;
it only requires explicit, internally consistent metadata. An explicit
`EMPIRICAL` declaration remains `BLOCK_PROMOTION` regardless of these fields.

This requirement is limited to empirical/descriptive evidence-bearing claims.
Engineering-only metadata reports remain non-empirical and are not rejected
solely because dataset license or cohort metadata is absent or unresolved.
The serialized `scientific_eligibility` flag for this route means only
eligibility for the gate's limited descriptive review. It is not legal
permission, cohort validation, scientific confirmation, or biological
evidence; `scientific_pass` remains `false`.

## Allowed evidence classes

The gate records `declared_evidence_class` separately from
`allowed_evidence_class`. Allowed values never include `EMPIRICAL`.

`engineering_fact`, `benchmark_result`, `synthetic_demonstration`,
`descriptive_empirical` (review only), `proxy_inference`, `hypothesis`,
`speculation`, `unsupported_claim`.

## CLI

Validate a fixture directory (each subdirectory is one case):

```text
python scripts/validate_evidence_promotion.py \
  --input tests/evidence_promotion_gate/fixtures \
  --output /tmp/epg-out.json
```

Generate the fixture-only report, command-center payload, and RAG pack:

```text
python scripts/generate_evidence_promotion_report.py \
  --input tests/evidence_promotion_gate/fixtures \
  --output outputs/evidence_promotion_gate
```

Local Makefile cycle:

```text
make -C tools/evidence_promotion_gate cycle
```

No network access is performed. A caller that requests network access on an
input record is fail-closed (`NETWORK_ACCESS_NOT_APPROVED`); the gate still
does not make a call.

## Inputs

Local files only:

- `RunRecord.json`
- optional claim-gate JSON (`NeuroTopology.ResearchClaimGate.v1`)
- optional claim JSON for `evaluate_claim`
- optional exported Markdown (YAML frontmatter)
- optional command-center JSON
- optional Airtable-shaped card
- optional research-cycle snapshot
- optional literature record

## Outputs

Strict JSON (`allow_nan=False`):

- `promotion_decision`
- `reason_codes`
- `declared_evidence_class` vs `allowed_evidence_class`
- `synthetic_demo`
- `scientific_pass: false`
- `formal_bayes_factor` (`null` unless a fixture declares a formal method; still not confirmation)
- `input_fingerprints` (SHA-256 of local files)

Repeat evaluation of the same fixture is deterministic.

## Scientific limitation

Admissible engineering or descriptive-review status is not biological
validation, not a formal Bayes confirmation, and not an ontology, clinical,
TOE, or consciousness claim. Independent statistical and domain review
remains required.
