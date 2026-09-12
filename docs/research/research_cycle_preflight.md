# Research-Cycle Preflight

Owner: `tools/research_cycle_preflight/**`, `scripts/validate_research_cycle_preflight.py`,
`tests/research_cycle_preflight/**`.

## What this is

A deterministic, read-only **gate**, not a scientific conclusion. It
composes four already-merged, canonical validators through read-only
adapters and reports whether it is safe to spend compute on a research
cycle's plan, before any expensive simulation runs:

- `tools/research_plan_quality` -- the 20-dimension research-plan rubric
  (`evaluate_plan`).
- `tools/research_claim_gate` -- the scientific claim gate
  (`evaluate_claim`).
- `tools/simulation_artifacts` -- the read-only simulation-artifact
  lineage extractor (`extract_run`).
- `tools/data_access/policy_enforcement/policy` -- the declared
  data-access policy (`DEFAULT_POLICY`), read as a reference contract.

None of these four modules is modified, duplicated, or reimplemented.
`tools/research_cycle_preflight/adapters.py` calls each one exactly as
published and returns its own output (or an equivalent plain dict)
unmodified.

## Two separate decision axes

This task requires "separate operational readiness and scientific
admissibility states," so the preflight never merges them into one
status:

| Axis | States | Source |
|---|---|---|
| `operational_readiness` | `READY`, `NEEDS_REVISION`, `BLOCKED` | the plan rubric's own three-way `overall_status`, further downgraded by the data-access classification and prior-run artifact lineage |
| `scientific_admissibility` | `ADMISSIBLE`, `REVIEW_REQUIRED`, `DOWNGRADED`, `BLOCKED`, `INCOMPLETE`, `NOT_APPLICABLE` | the claim gate's 8-state `DECISION_STATES`, bucketed the same way as the scientific-release-conformance suite's four-way taxonomy, plus `NOT_APPLICABLE` when no claim was supplied |

`cleared_for_execution` is `True` only when `operational_readiness ==
"READY"` **and** `scientific_admissibility` is not `BLOCKED` or
`INCOMPLETE`. A `REVIEW_REQUIRED` or `DOWNGRADED` claim does not, on its
own, stop the *engineering* side of the cycle from running -- it flags
that the eventual claim will need review or downgrade after execution,
which is a different concern from whether it is safe to spend compute
right now. This asymmetry is a deliberate design choice, not an
oversight: see "Known limitations" below.

Everything fails closed. An empty or malformed request produces
`operational_readiness = "BLOCKED"`, never a default pass -- there is no
code path that treats a missing plan, missing claim, or unreadable
prior-run directory as automatically safe.

## Requirement-by-requirement mapping

### 1. Compose existing validators through read-only adapters

`tools/research_cycle_preflight/adapters.py`: `run_plan_rubric`,
`run_claim_gate`, `run_artifact_lineage`, `classify_data_access`. Each
adapter's only job is input normalization and fail-closed error
handling around one real validator call. Verified in
`tests/research_cycle_preflight/test_adapters.py`.

### 2. Require or explicitly classify

| Required classification | Carried by |
|---|---|
| Source identity and checksum | plan rubric: `source_quality_provenance`, `dataset_identity_checksum` |
| Condition labels | plan rubric: `condition_label_validity` |
| Pairing and sample size | plan rubric: `pairing_sample_size_adequacy` |
| Locked preprocessing | plan rubric: `preprocessing_lock` |
| Split strategy | plan rubric: `split_strategy` |
| Null-model metadata | plan rubric: `null_model_specification` |
| Multiplicity metadata | plan rubric: `multiplicity_correction` |
| Artifact lineage | `simulation_artifacts.extract_run` via `run_artifact_lineage` |
| Finite outputs | `extract_run`'s own non-finite rejection (forces `status="BLOCKED"`) plus this preflight's own `allow_nan=False` serialization |
| Resource budgets | plan rubric: `compute_resource_budget` |
| Network policy | `classify_data_access` against `DataAccessPolicy.network_enabled_by_default` / `NETWORK_ACCESS_NOT_APPROVED` in the claim gate when a claim requests network access |
| Bounded-download policy | `classify_data_access` against `DataAccessPolicy.bounded_transfer_required`, `full_dataset_download_policy`, `checksum_policy` |
| Partial/failed/timeout states | `extract_run`'s own status vocabulary (`PARTIAL`, `FAILED`, `CONFLICTING`, `BLOCKED`, `COMPLETE`) via `run_artifact_lineage` |
| Claim calibration | plan rubric: `claim_calibration`, plus the claim gate's full decision when a claim is supplied |

`tests/research_cycle_preflight/test_adapters.py::test_every_plan_rubric_dimension_this_task_requires_exists_on_the_real_rubric`
and `test_plan_rubric_adapter_reports_all_dimensions` guard this table
against drift if the real rubric's dimension names ever change.

### 3. Fail closed before execution when hard blockers exist

`operational_readiness` starts from the plan rubric's own hard-blocker
logic (a `blocker` or `missing` criterion status forces
`overall_status = "BLOCKED"`), then `compose.run_preflight` adds two
more hard-blocker sources: a `BLOCKED` data-access classification
(full-dataset download requested, or a network request with no bounded-
transfer declaration) and a prior run whose lineage status is `FAILED`,
`CONFLICTING`, or `BLOCKED`. See
`tests/research_cycle_preflight/test_invariants.py::test_cleared_for_execution_defaults_to_false_not_true`.

### 4. Never emit

Every report carries a literal `never_emits` block:
`scientific_pass: false`, `formal_bayes_factor: null`,
`causal_confirmation: false`, `biological_confirmation: false`,
`topology_confirmation: false`. These are structural constants from
`tools/research_cycle_preflight/models.py::NEVER_EMITTED`, not derived
from input, so a caller cannot flip them by injecting matching field
names into the request -- see
`test_invariants.py::test_injecting_fake_confirmation_fields_into_the_request_has_no_effect`.
Fabricated provenance is prevented the same way the plan rubric and
claim gate already prevent it: an absent field stays `null`/`missing`
and is never filled in by this preflight (`test_no_fixture_ever_fabricates_provenance`).

### 5. Deterministic finite JSON with separate states

`compose.run_preflight` returns one dict with `operational_readiness`
and `scientific_admissibility` as separate top-level fields (never
merged), a `report_sha256` computed last and excluding itself, and
`json.dumps(..., allow_nan=False)` succeeding on every fixture
(`test_report_is_finite_json`, `test_fixtures_are_deterministic_across_repeated_evaluation`).

### 6. Required test scenarios

One fixture per scenario in
`tests/research_cycle_preflight/fixtures/*.json`, each isolating
exactly one failure mode and verified against the real composed
validators before being locked into `conftest.py::EXPECTED_CASES`:

| Scenario | Fixture | operational_readiness | scientific_admissibility | cleared_for_execution |
|---|---|---|---|---|
| Complete engineering plan | `complete_plan` | `READY` | `NOT_APPLICABLE` | `True` |
| A plan with only warning-level gaps | `needs_revision_plan` | `NEEDS_REVISION` | `NOT_APPLICABLE` | `False` |
| Missing provenance | `missing_provenance` | `BLOCKED` | `NOT_APPLICABLE` | `False` |
| Synthetic-only inputs | `synthetic_only_inputs` | `READY` | `BLOCKED` (`CLAIM_SYNTHETIC_ONLY`) | `False` |
| Partial run | `partial_run` | `NEEDS_REVISION` | `NOT_APPLICABLE` | `False` |
| Network violation | `network_violation` | `BLOCKED` | `NOT_APPLICABLE` | `False` |
| Unsupported claim | `unsupported_claim` | `READY` | `BLOCKED` (`CLAIM_REJECTED`) | `False` |
| Invalid labels | `invalid_labels` | `BLOCKED` | `NOT_APPLICABLE` | `False` |
| Missing null metadata | `missing_null_metadata` | `BLOCKED` | `NOT_APPLICABLE` | `False` |
| Non-finite artifacts | `non_finite_artifacts` | `BLOCKED` | `NOT_APPLICABLE` | `False` |

`complete_plan` is the only fixture cleared for execution
(`test_complete_plan_is_the_only_fixture_cleared_for_execution`),
proving this suite discriminates rather than blocking or passing
everything.

### 7. gstack/Graphite

No gstack/Graphite stack tooling was used or mutated while building
this task; git worktrees and branches were managed with plain `git`
only.

## Known limitations

- **`REVIEW_REQUIRED`/`DOWNGRADED` claims do not block operational
  readiness.** A claim that needs post-hoc review or downgrade is a
  scientific-admissibility concern, not proof that the plan is unsafe
  to run. If a project wants any non-`ADMISSIBLE` claim to also halt
  execution, that is a one-line change to
  `compose._ADMISSIBILITY_PERMITS_EXECUTION` -- deliberately left
  narrow here rather than guessed at.
- **`PARTIAL`/`INCOMPLETE` prior-run lineage downgrades to
  `NEEDS_REVISION`, not `BLOCKED`.** Only `FAILED`, `CONFLICTING`, and
  `BLOCKED` prior-run states are hard operational blockers. A partial
  checkpoint is a normal, resumable state in this repository's
  extractor vocabulary; treating every partial run as a hard stop would
  make legitimate checkpoint-and-resume workflows impossible to
  preflight.
  This suite does not encode "timeout" as its own state because the
  real extractor has no distinct `TIMEOUT` status -- a timed-out
  simulation is represented as `FAILED`, matching
  `docs/release/scientific_conformance.md`'s documented gap for the
  claim gate's own `FUTURE_PAST_LEAKAGE` vocabulary.
- **Data-access classification is declarative, not a source-code
  scanner.** `tools/data_access/policy_enforcement/scanner.py` audits
  production *source files* for policy violations; this preflight
  classifies a *declared request* for one research cycle against the
  same policy object. Running the full repository scanner is out of
  scope for a per-cycle preflight and remains a separate, existing
  tool.

## The report

Single-request mode (real usage):

```bash
python -m scripts.validate_research_cycle_preflight \
    --request path/to/request.json --output-dir artifacts/research_cycle_preflight
```

Writes `research_cycle_preflight_report.json` with `schema_version`,
`evidence_class: "research_cycle_preflight"`, `generated_at`,
`operational_readiness`, `operational_blockers`,
`scientific_admissibility`, `cleared_for_execution`,
`validators_composed` (the four adapters' full output),
`never_emits`, a `note` stating this is not a scientific conclusion,
and `report_sha256`. Exit code `0` when `cleared_for_execution`, `1`
otherwise.

Self-check mode (no `--request`): runs this suite's own fixture battery
and writes `research_cycle_preflight_self_check.json`, always exiting
`0` (its purpose is regression coverage, not gating a specific cycle).

A request is a plain JSON object with up to four optional keys:
`plan`, `claim`, `prior_run_dir`, `data_access_request`.

## This is a gate, not a scientific conclusion

`cleared_for_execution: true` means the declared plan, claim (if any),
prior-run lineage (if any), and data-access request all passed the
composed engineering checks -- it says nothing about whether any result
this cycle eventually produces is true. See `never_emits` on every
report for the explicit, structural reminder of that boundary.
