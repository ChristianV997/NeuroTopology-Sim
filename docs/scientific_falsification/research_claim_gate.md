# Deterministic research-claim gate

`tools/research_claim_gate` is an offline, non-LLM contract for deciding how
a claim may be reported. It checks declared metadata and a small set of
non-negotiable semantic guardrails. It does not calculate statistics, inspect
raw data, contact a service, or rewrite a claim.

## Claim classes

The closed vocabulary is:

`engineering_fact`, `benchmark_result`, `synthetic_demonstration`,
`descriptive_empirical`, `proxy_inference`, `formal_statistical_evidence`,
`hypothesis`, `speculation`, and `unsupported_claim`.

## Decision states

| State | Meaning |
| --- | --- |
| `CLAIM_ADMISSIBLE` | The record is internally admissible for reporting under its declared class. This is not scientific confirmation. |
| `CLAIM_REQUIRES_REVIEW` | Required metadata or controls are incomplete, including unknown test count, multiplicity, null controls, uncertainty, or effect size. |
| `CLAIM_DOWNGRADED` | The wording or declared method overreaches; the recommended class is returned without changing the claim. |
| `CLAIM_REJECTED` | A hard safety rule, unsupported class, leakage, unverified label, or unapproved network request was detected. |
| `CLAIM_INCOMPLETE` | The input cannot be safely represented, for example malformed JSON or missing required identity/text. |
| `CLAIM_SYNTHETIC_ONLY` | The result may describe a synthetic demonstration but cannot support an empirical or biological claim. |
| `CLAIM_PROVENANCE_INVALID` | Evidence-bearing metadata lacks complete, valid provenance. |
| `CLAIM_NOT_COMPARABLE` | An input explicitly declares that its feature families or estimands are incompatible; current hard topology/causal mismatches are rejected with reason codes. |

The gate never emits a scientific `PASS`, a formal Bayes factor, or a causal
conclusion by inference. `scientific_pass` and `scientific_eligibility` are
always `false`. An admissible record means only that the declared reporting
class and metadata pass this contract; independent review is still required.

## Provenance and evidence

Evidence-bearing claims require source identity, checksum, acquisition source,
and dataset/version metadata. Labels must be explicitly verified. Synthetic
fixtures are useful engineering demonstrations but cannot be promoted to
empirical, biological, or mental-state evidence. A proxy metric remains a
proxy: RSS/AIC/AICc/BIC ratios cannot be called formal Bayesian evidence,
causal influence, or a mechanism.

Placeholder identities such as `none`, `unknown_source`, `derived_from_ledger`,
and `TBD`, and bare verdict-like tokens such as `pass`, `fail`, `ok`, `true`,
and `null`, are rejected as invalid provenance in any required field. A verdict
word is never a source identity, acquisition record, or dataset version. A syntactically complete checksum
is not independently verified by this offline gate and therefore cannot create
a scientific-evidence status.

Unknown `n_tests` is never interpreted as one test. More than one test requires
an explicit multiplicity-correction status. Missing null controls, uncertainty,
or effect size produces review rather than an implied clean result.

Train/test subject or session overlap and future-to-past leakage are hard
rejections for predictive or forecasting claims. Triadic dependence is not
causal influence. Graph beta-1 is not spatial winding or spatial charge.
Parasympathetic activation is not automatically equanimity or nonattachment,
and a clean audit is not scientific confirmation.

## CLI and no-network policy

One JSON record:

```text
python scripts/validate_research_claim.py --input claim.json --output result.json
```

JSONL batch:

```text
python scripts/validate_research_claim.py --input claims.jsonl --jsonl --output results.json
```

The CLI performs no network access. A caller that explicitly requests network
access without an approved policy receives `NETWORK_ACCESS_NOT_APPROVED` and a
rejected result; even an approved policy does not cause this validator to make
a network call.

All output uses strict JSON (`allow_nan=False`) and represents unavailable
formal Bayes-factor values as JSON `null`. Evaluation is deterministic for a
fixed input and preserves input order in JSONL batches.

## Scientific limitation

This is a reporting admissibility gate, not a truth detector or biological
validation procedure. It cannot establish causation, mechanism, consciousness,
equanimity, nonattachment, or any final theory. Independent statistical and
domain review remains required.
