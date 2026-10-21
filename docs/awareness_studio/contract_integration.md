# Awareness Studio Research-Cycle — Contract Integration

Owner: `tools/awareness_studio_research_loop/contract_adapters.py`,
`scripts/validate_awareness_cycle_integration.py`,
`tests/awareness_studio_research_loop/test_contract_adapters.py`,
`fixtures/awareness_studio_research_loop/integration_contracts/**`.

## What this validates

Whether the Awareness Studio research-cycle orchestrator's (PR #283)
input contract actually matches what the real upstream registries
produce: the literature registry (PR #276, `tools/awareness_studio_research/**`,
owned by Claude A) and the hypothesis/experiment registry
(`tools/research_cycle/**`, owned by Antigravity C, **already merged to
`main`**). Both are read-only here — this package never imports either,
and never imports `tools/awareness_studio_research_loop/compiler.py` or
`state_machine.py` (PR #283, also read-only) — every adapter is a pure
function over plain dicts, validated against fixtures shaped like the
real record types, checked by reading their source (`git show`), never by
importing or modifying them.

**A structurally valid research cycle is not a validated scientific
result.** This module's job is contract compatibility, not scientific
correctness — it never runs a solver, never performs statistical
inference (see `adapt_experiment_evidence_update`'s explicit refusal to
classify a p-value into PASS/FAIL), and never certifies that anything it
adapts is true.

## Why a fresh branch instead of merging PR #283

This branch starts from `origin/main` as instructed. Because
`tools/awareness_studio_research_loop/**` (PR #283) is not yet on `main`,
merging it in was attempted first but declined by the environment's
safety controls; the resulting design is arguably better anyway — an
adapter/contract layer should validate a producer's output against a
*documented* contract without needing to import the consumer's
implementation. `contract_adapters.py` is therefore self-contained
(stdlib only) and encodes the orchestrator's contract as data (mirrored
constants, commented against the real
`docs/awareness_studio/research_cycle_orchestration.md`), not as a hard
import dependency. "Targeted orchestrator tests" and "evidence-registry
tests" (see Test Plan below) were run against read-only snapshots
extracted via `git archive` into a scratch directory outside this
worktree — never merged, never committed here.

## Confirmed contract mismatches (migration diagnostics)

Every one of these was found by reading the real, already-existing code
(`tools/awareness_studio_research/models.py` for PR #276;
`tools/research_cycle/schema.py`, already on `main`, for the hypothesis
registry) and comparing it against the orchestrator's documented
contract — not invented. Running
`python -m scripts.validate_awareness_cycle_integration` against the
bundled fixtures reproduces all of them.

### Hypothesis records (`HypothesisRecord.v1` → `hypothesis_registry`)

| Orchestrator expects | Real registry has | Diagnostic |
|---|---|---|
| `claim_ids: list[str]` | no such field (`evidence_links`/`contradictory_evidence_links` instead, of unverified semantics) | `ambiguous_mapping` / `missing_field` — **never** substituted with `evidence_links` |
| `statement: str` | `precise_claim: str` | renamed, not lost — mapped directly |
| `null_prediction: str` | `null_prediction: str` | **compatible**, same field name |
| `falsification_criterion: str` | `falsification_criterion: str` | **compatible**, same field name |
| — | `epistemic_label` (6-value vocabulary, e.g. `"preregistered_empirical"`) | no orchestrator equivalent field; best-effort hint via `map_epistemic_label_to_evidence_class`, always flagged `ambiguous_mapping` |
| — | `contradictory_evidence_links` lives on the *hypothesis* | orchestrator expects contradiction tracking on a separate `theory_state` input — different locus entirely |

### Experiment plans (`ExperimentPlan.v1` → `experiment_plans`)

| Orchestrator expects | Real registry has | Diagnostic |
|---|---|---|
| `experiment_id` | `plan_id` | renamed, not lost |
| `synthetic: bool` | `is_synthetic: bool` | renamed, not lost |
| `falsification_criterion` | not present on the plan (lives on the hypothesis, same field name) | `missing_field` — caller must carry it over from `adapt_hypothesis_record`'s output for the same `hypothesis_id` |
| `metrics: [{name, unit, feature_family}]` | `variables: dict` + free-text `analysis_protocol` | `missing_field` — no unit/feature_family concept exists; never guessed |
| `held_out_split_locked` / `is_predictive` / `preregistered` | **do not exist at all** | `missing_field` ×3 — the orchestrator's `locked_holdout` gate is structurally unsatisfiable from this registry's export today |
| `dataset_checksum` | not a direct field; `checksum` is the **plan's own content-integrity hash**, not a dataset hash | `missing_field` unless `provenance.dataset_checksum` is explicitly present — `checksum` is **never** substituted (that would silently claim data provenance the value doesn't carry) |

### Evidence updates — an overloaded term across two registries

Both upstream systems call a record type "evidence update", with
completely different shapes:

- **Claude A's** (`tools/awareness_studio_research/store.py`): a
  versioning event, `{entity_type, entity_id, update_type, reason}`,
  where `entity_type ∈ {source, claim, correlate, hypothesis_link,
  dataset_link, experiment_link}` — **never** `"hypothesis"`.
- **Antigravity C's** (`EvidenceUpdate.v1`): a rich experimental-result
  record (`evidence_id`, `experiment_id`, `source_checksum`/
  `experiment_checksum`, `data_type`, `is_synthetic`, `is_out_of_sample`,
  `observed_effect_size`/`observed_p_value`, `is_contradictory`/
  `contradiction_details`) — combining what the orchestrator splits
  across `execution_results` + `null_surrogate_results` +
  `validation_reports` + a per-hypothesis contradiction flag.

`adapt_evidence_update` targets the former; `adapt_experiment_evidence_update`
targets the latter and fans it into three orchestrator-shaped pieces
(execution record, null-test record, contradiction record).

**The confirmed structural gap:** the orchestrator's `EVIDENCE_UPDATE_READY`
gate (PR #283, `state_machine.py`) only advances a hypothesis on
`entity_type == "hypothesis"`. Claude A's registry never emits that
literal — the closest real event is `entity_type == "hypothesis_link"`
(a claim-graph link, not a hypothesis-outcome event). `adapt_evidence_update`
flags this every time it sees a `hypothesis_link` update
(`ambiguous_mapping`) and **does not** auto-remap it — a human must
decide whether a `hypothesis_link` update should ever count as a
hypothesis's evidence update, since neither registry currently emits an
event both sides would recognize as one.

### Human review

The orchestrator's `reviewer_decisions` contract uses a 4-value enum
(`approved`/`rejected`/`pending`/`not_required`) as a separate record per
subject. The real `HypothesisRecord.v1.human_review_gate` is a single
`{passed: bool, reviewer, timestamp, review_notes}` object embedded on
the hypothesis. `adapt_human_review_gate` maps `passed=true` → `"approved"`
unambiguously, but `passed=false` cannot distinguish "not yet reviewed"
from "reviewed and rejected" — mapped to `"pending"` with an
`ambiguous_mapping` diagnostic (harmless for cycle-state purposes, since
both `"pending"` and `"rejected"` block progression identically in the
orchestrator's state machine, but the ambiguity itself is not resolved).

### Source/claim/checksum compatibility (mostly clean)

`source_id`/`claim_id` are real, deterministic 16-hex-character strings
(`tools/awareness_studio_research/checksum.py`); `source_checksum` is a
64-character sha256 hex digest of normalized abstract/title text. Neither
assumption is baked into the orchestrator's contract (ids/checksums are
treated as opaque non-empty strings throughout), so these are
**compatible**. `claim_status` (`empirical`/`theoretical`/`proxy`/
`speculative`/`unsupported`) and `evidence_tier`/`verification_status`
match the orchestrator's assumed vocabulary exactly.

## Never-coerce guards (requirement 4)

Enforced directly in the adapter functions (see the module docstring
comments at each site), and covered by dedicated tests:

1. **formal → proxy**: `adapt_ledger_row` never demotes a valid
   `scientific_status`; an unrecognized value becomes `"unknown"`, never
   a specific weaker *or* stronger label.
2. **empirical → synthetic** (and the reverse): `adapt_experiment_evidence_update`
   treats `is_synthetic` as authoritative over `data_type` and flags
   (never silently resolves) any disagreement between them.
3. **theory → observation**: `adapt_extracted_claim` passes `claim_status`
   through verbatim; `"theoretical"` is never reported as `"empirical"`.
4. **disputed source → confirmed source**: `adapt_literature_source`
   passes `verification_status`/`status` through verbatim; a `"disputed"`
   source is never upgraded to `"verified"`/`"active"`.
5. **prediction → causal effect**: no adapter adds or infers a `"causal"`
   `claim_class`, and `adapt_hypothesis_record` carries `predicted_direction`/
   `precise_claim` through as descriptive text only.

## Migration diagnostic kinds

`MISSING_FIELD`, `INCOMPATIBLE_TYPE`, `UNSUPPORTED_VERSION`,
`AMBIGUOUS_MAPPING`, `UNVERIFIED_PROVENANCE`, `SYNTHETIC_ONLY_INPUT`.
Every `Diagnostic` carries `{kind, field, detail, record_id}`. An adapter
never raises: a record failing a `MISSING_FIELD` check is dropped from
the adapted bundle (never fabricated), with the diagnostic preserved so
nothing is lost silently.

## Fixtures

`fixtures/awareness_studio_research_loop/integration_contracts/`:

- `literature_registry_export_sample.json` — real Claude A shape, with
  content-addressed ids/checksums computed using the same algorithms as
  `tools/awareness_studio_research/checksum.py`, including one disputed
  source.
- `hypothesis_registry_sample.json` — real `HypothesisRecord.v1` shape,
  one reviewed/ready hypothesis and one unreviewed/exploratory one.
- `experiment_plans_sample.json` — real `ExperimentPlan.v1` shape, one
  empirical and one synthetic plan.
- `experiment_evidence_updates_sample.json` — real `EvidenceUpdate.v1`
  shape, one clean empirical result and one synthetic, contradictory one.

## CLI

```bash
python -m scripts.validate_awareness_cycle_integration \
    --output-dir artifacts/awareness_cycle_integration \
    --now 2026-01-01T00:00:00+00:00
```

Defaults to the bundled fixtures above; pass `--literature-export`,
`--hypothesis-registry`, `--experiment-plans`, or
`--experiment-evidence-updates` to point at a different exported file.
Writes `contract_integration_report.json` (`allow_nan=False`,
deterministic given the same inputs and `--now`).

## Determinism and safety

Stdlib-only; no network access; no imports of the two upstream packages
or of the orchestrator's `compiler.py`/`state_machine.py`; no dynamic
`exec`/`eval`. Every adapter is a pure function of its input dict.
