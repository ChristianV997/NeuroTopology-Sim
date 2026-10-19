# Grid plan schema (`grid_plan_v2`)

Status: **HOLD / SYNTHETIC_ONLY**. This document describes a planning
schema. It is not a simulation result, not a detector ROC, not a power
claim, and not evidence that any upstream gate has been verified.

`neurotopology_sim/` is not a package in this repo. The module lives at
`tools/simulation_runtime/grid_plan.py`. No `neurotopology_sim/__init__.py`
file is added. `tools/simulation_runtime/__init__.py` is unchanged.

`grid_plan_v1` is rejected. v2 changes what counts as an independent
sample and what can open a gate.

## CampaignManifest v1 gap

`CampaignManifest` (`simulation_campaign_manifest_v1` in
`tools/simulation_runtime/types.py`) is the workload object this plan
expands into. It is not bumped.

| Field | Role here |
| --- | --- |
| `schema_version` | Always `simulation_campaign_manifest_v1`. |
| `campaign_id` | Derived from the config hash prefix. |
| `created_at` | Fixed sentinel `1970-01-01T00:00:00+00:00`. |
| `code_commit` | The same local `HEAD` SHA as `code_version_id`, or `UNKNOWN`. |
| `configuration_hash` | Same digest as `config_hash`. |
| `seed` | `master_seed`. |
| `units` | One `WorkUnit` per cell. `command` is empty. `parameter_case` holds the cell. |
| `environment` | Synthetic hold labels. `detector_roc` is null. |
| `resource_policy` | Inert placeholders. Not the scientific budget. |

`CampaignManifest` has no `planned` / `blocked` / `running` / `completed` /
`failed` field and no gate-evidence field. `Outcome.PASS` is a process
outcome. It is not a gate and not a scientific status. `grid_plan_v2`
does not write it.

## Evidence records this module will read

`tools.evidence_promotion_gate.reporting.write_report(payload, output)`
requires `output`. The planner imports that function and inspects its
signature. There is no default path, so there is no committed location
to read. Until `write_report` grows a default path that is tracked on
main, every gate stays `missing`.

When a default path exists, `execute` reads that path only as a git blob
at the local main SHA (`git ls-tree` / `git show <main>:<path>`). It does
not walk the worktree. Untracked files and uncommitted files do not count.
Command-center payloads and RAG packs are not that shape and are ignored.

The blob text must equal `serialize_json` of a `results_payload` object:

- `schema_version`: `EvidencePromotionGate.v1`
- `scientific_pass`: false
- `case_count` equal to `len(results)`
- `results[]`: `PromotionResult.to_dict` keys, plus optional `verified_at_commit`, `source_sha`, and `limitations_recorded`

`reporting` defines no hash field. The planner recomputes
`compute_config_hash` over the writer-shaped body (result keys only,
excluding `verified_at_commit`). `PromotionResult` forces `scientific_pass`
false and has no artifact SHA, log pointer, verifier, or freshness field.
This module does not edit `schema.py` and does not add a gate registry file.

One `case_id` maps to one gate, by exact string match. A report whose
`results` contain more than one distinct `case_id` opens no gate. The same
`case_id` in more than one report blocks that gate (`duplicate_record`).
A report cannot open a second gate.

A single-result blob opens its gate only when all of the following hold:

- `case_id` equal to that gate id
- `promotion_decision` whose name starts with `ADMISSIBLE_`
- `scientific_pass` not true
- `verified_at_commit` equal to 40 lowercase hex characters
- that commit an ancestor of local `origin/main` (else local `main`) and
  an ancestor of the blob's last commit on main (`git rev-list -1`)
- ancestry checked with `git merge-base --is-ancestor` and no fetch

A commit is an ancestor of itself. `verified_at_commit` equal to the main
tip is accepted only when the blob was last committed on main at that tip.
A file that is merely present in the tip tree from an older commit does not
satisfy a tip claim, and a file that is not on main does not satisfy it either.

`record_root` is a test seam. Passing a path labels the plan
`TEST_FIXTURE_NOT_EVIDENCE`. The path is not opened and cannot become
`admissible_on_ancestor`.

No writer default path is committed on main at the audited commit
`19c3203573082f8bc41f7da226b52dc20a49fdb0`. Every resolvable gate is
therefore `missing`, and every cell stays blocked. A caller dict, list,
or boolean passed to `execute` is not read, even when it says `ADMISSIBLE_*`
and names an ancestor commit.

If `git` is missing, the clone is shallow (`git rev-parse
--is-shallow-repository` is `true`), or main cannot be resolved, every
gate is `missing` and every cell stays blocked. The plan records
`gate_source_failure` as `git_missing`, `shallow_clone`, or
`main_unresolved`. Ancestry is local git only. This module does not fetch.

`ci_discovery` is blocking. The fixed test lists in
`.github/workflows/ci.yml`, `.github/workflows/required-checks.yml`, and
`docker/ci/core.Dockerfile` do not collect `tests/simulation_runtime`.
That workflow change must not land before this repair is merged:
`ci_discovery` is currently the only gate this planner keeps closed by
itself. `dmd_crouzeix` is recorded and is nonblocking.

`GATE_INTEGRATION_STATE` and the gate-id list are hand-written audit
labels. `integration_is_evidence` is false on every resolution row. They
are not evidence. A promotion-gate report committed on main wins if it
conflicts with those labels.

## Per-cell fields

Every cell carries:

| Field | Rule |
| --- | --- |
| `independent_unit` | `simulation_seed`, `subject`, or `recording`. Synthetic plans accept only `simulation_seed`. |
| `n_independent_calibration` | Count of calibration unit ids. Checked against `plan_sample_size`. Must equal `n_positive_calibration + n_negative_calibration`. |
| `n_independent_evaluation` | Count of evaluation unit ids. Checked against `plan_sample_size`. Must equal the evaluation class counts. |
| `n_positive_*` / `n_negative_*` | Independent positive and negative units in that split. Seeds, never windows. |
| `nested_unit` | `window`, `trial`, or `none`. |
| `nested_per_unit` | Nested observations per independent unit. Never added into N. `none` requires `1`. |
| `unit_aggregation` | Required when `nested_per_unit > 1`. `cluster_any_event_rate` is the named #426 value (`synthetic_forward_roc.py:194`; `cluster_ids` on `operating_point` and `compute_roc`). Any other string is `invalid_unit_aggregation`. When nesting is 1 and the field is omitted, the stored value is `not_required` with `named_on_pr_426` false. |
| `interval_method` | `cluster_bootstrap_over_independent_unit` or `wilson_on_independent_unit`. Window-level methods are rejected. |
| `estimand` | Required text. |
| `power_claim` | Always `none`. |

`calibration_unit_ids` and `evaluation_unit_ids` are derived inside the
planner from `calibration_seed` / `evaluation_seed` and the independent
counts: `{role}-seed{seed}-u{index:06d}`. Caller-supplied id lists are
`caller_unit_ids_rejected`. Window-style ids such as `s1_w0` and `s1_w1`
cannot be passed in and cannot inflate N. `roles_are_disjoint` is
`set(calibration).isdisjoint(set(evaluation))`. A unit id in both derived
sets is `unit_id_overlap`. `n` equal to `len(unit ids) * nested_per_unit`
when `nested_per_unit > 1` is `windows_counted_in_n`. Trial and compute
budgets use the independent-unit counts only. Derived id lists are not
stored on the re-parseable configuration input.

`h0`, `h1`, and `score_definition_id` are required. The score id is a
reference. This module does not compute a score. The threshold is a
non-empty finite mapping. `threshold_hash` covers `h0`, `h1`,
`score_definition_id`, `threshold`, `calibration_unit_ids`,
`calibration_seed`, `estimand`, `interval_method`, and `unit_aggregation`.
Calibration ids are derived before that hash. Evaluation ids,
`n_independent_evaluation`, and the evaluation class counts are read only
after it. That ordering is in-process only. It is not a preregistration
record. A caller-supplied `evaluation_manifest` is rejected. Changing
`estimand`, `interval_method`, or `unit_aggregation` changes
`threshold_hash`. Changing `evaluation_seed` or an evaluation class count
changes `config_hash` and does not change `threshold_hash`.

Wilson floors come from `analysis.binomial_planning.plan_sample_size`.
There is no second sample-size helper. Counts below the #405 required n
are rejected and are not emitted. They are not labeled
`UNDERPOWERED_DRY_RUN`.

The engineering minimum, not a power guarantee, is at least 100
independent positive units and 100 independent negative units in
calibration and the same pair in evaluation. An emitted plan with any of
those four counts below 100 is `smoke_only` and `UNDERPOWERED_DRY_RUN`.
A plan whose four counts are each at least 100 is
`ENGINEERING_THRESHOLD_MET` with execution mode `held`. That label is
still not a power analysis. This planner does not accept or verify a
power analysis (`power_analysis_supplied` is false). `power_claim` stays
`none`. Neither label launches the grid.

`roles_are_disjoint` is the computed disjointness of the two derived id
sets. It is not proof of statistical independence. Independent draws need
per-seed RNG streams downstream.

## Declared metrics

`metric_spec` is a declaration block inside the plan hash. Every metric
has `computed: false` and `value: null`. This module does not import or
reimplement PR #426 (`55115149c7443ca8b325dc4dbf65d6900c9fdd79`). The names
`tpr`, `fpr`, `precision`, `auc`, and `average_precision` are recorded as
`NOT_INTEGRATED`. `accuracy` is an additional declared proportion with the
same status.

Wilson intervals are declared only for proportions at the frozen
threshold: `tpr`, `fpr`, `precision`, and `accuracy`. Numerator and
denominator fields are counted in independent units (seeds), never
windows. `auc` and `average_precision` are not proportions. Their declared
`interval_method` is `cluster_bootstrap_over_independent_unit`. Tie-aware
AUC means ties count 0.5 (Mann-Whitney midrank). Stepwise average
precision means the sum of precision at each recall step, with no
interpolation. Those sentences are the contract. No score is ranked here.

Undefined values are the token `UNDEFINED` with a reason code. They are
never silent 0 or NaN.

| Metric | Undefined when | Reason |
| --- | --- | --- |
| `auc` | either class empty | `auc_undefined_empty_class` |
| `average_precision` | no positives | `ap_undefined_no_positives` |
| `precision` | no predicted positives | `precision_undefined_no_predicted_positives` |
| `tpr` | denominator 0 | `tpr_undefined_zero_denominator` |
| `fpr` | denominator 0 | `fpr_undefined_zero_denominator` |
| `accuracy` | denominator 0 | `accuracy_undefined_zero_denominator` |

## Pre-run cost bound

`cost_estimate` is computed from `cells × independent units × nested`,
times a declared `4096` bytes per record, plus `expected_artifact_count`
(`planned_outputs` plus one artifact per cell). `estimated_callback_invocations`
is that same product, an upper bound. Nothing is executed to obtain it.
Each `WorkUnit.estimated_disk_mb` and `estimated_memory_mb` is that cell's
share of the bound. A bare `0.0` is not an estimate. The label is
`DECLARED_ESTIMATE`.

## Audit metadata

The plan records `project_status` `HOLD / SYNTHETIC_ONLY`, `code_version_id`
(the local `HEAD` SHA, or `UNKNOWN` when HEAD does not resolve),
`worktree_dirty`, and `config_digest` (the same value as `config_hash`).
`UNKNOWN` or a dirty worktree blocks `execute`. A dry run still lists the
would-execute cells, seeds, splits, and cost with `executed: false`.
`CampaignManifest.code_commit` is that same `code_version_id`. It is not
the string `not_recorded`. `code_version_id` is not part of `config_hash`.

## Closed labels

Null ids: `synthetic_phase_shuffle`, `synthetic_iaaft`,
`synthetic_time_reverse`.

Source ids: `synthetic_single_dipole`, `synthetic_patch`,
`synthetic_noise_only`.

Null ids are labels only. There is no evidence that phase shuffle or
IAAFT randomizes a spatial winding statistic. `validation/surrogate_testing.py`
and `sciencer_d/btc_icft/level_t/winding.py` are not this gate, are not
CI-collected as this contract, and are not an evidence-promotion record.

`nuisance_scenario_id` is an optional opaque token. It is not resolved.
Unmerged `NuisanceGridConfig` (`sim/nuisance_scenarios`) is not imported.

## Canonical hash

`config_hash` is `tools.simulation_runtime.atomic_io.compute_config_hash`
of the scientific payload. Mapping key order does not change the digest.
The payload includes axes, seeds, both independent-unit id lists and
counts, the four class counts, nesting, `unit_aggregation`, the interval
method, estimand, `power_claim`, the sample-size label, `execution_mode`,
the engineering minimum note, `metric_spec`, the declared bytes per
record, the required source SHAs, `h0`, `h1`, `score_definition_id`, the
threshold, `threshold_hash`, Wilson inputs, budgets, blocking and
nonblocking gate ids, the ADMISSIBLE decision names, and
`EvidencePromotionGate.v1`. `code_version_id` and `worktree_dirty` are
not part of `config_hash`.

Derived cells, caller decisions, `checked_at`, and resolved gate rows are
not part of `config_hash`. Resolved rows get a separate `evidence_hash`
from the same function. Changing a caller SHA does not change it.

## Run state

Emitted `run_state` values are `planned` (dry-run list) and `blocked`
(execution refused). `running`, `completed`, and `failed` are rejected.
Parsing a config never emits `completed`. Dry-run cells are listed and
still `blocked`, because gates were not resolved. `execute` does not call
the simulation callback and does not emit `detector_roc`.

Failure policy: `fail_closed_block_grid`.

Planned outputs: `grid_plan_document`, `cell_inventory`, `gate_resolution`,
`threshold_hash`. Forbidden outputs include `detector_roc`, `auc`, and
`roc_curve`.

A dry-run may attach `toy_scores`. Those numbers are labeled
`TOY_FIXTURE_NOT_A_RESULT`. They are not a detector ROC.

## Trust boundary

`checked_at` is caller-set. It is stored and is not a freshness proof.

An artifact SHA on a caller object is format-only. It is not recomputed
from disk and it does not open a gate. The report hash this planner stores
is `compute_config_hash` of the writer-shaped body. `reporting` does not
define a hash of its own.

`execute(config, gate_evidence, ...)` does not read `gate_evidence`.
Passing a fabricated ADMISSIBLE record leaves every cell blocked.
A hand-written report in a temporary directory, an uncommitted file in
the worktree, or a file that is not a blob on main leaves every blocking
gate non-admissible, including when `ci_discovery` is treated as open.
`verified_at_commit` equal to the main tip does not open a gate unless
that report blob itself was committed on main at that tip.

A report committed on main is trusted because it passed pull-request
review and the merger. The planner does not verify how the report was
produced, so the self-declared-label risk moves to review.

`GATE_INTEGRATION_STATE` and the gate-id list are hand-written audit
labels, not evidence. Promotion-gate reports on main win on conflict.
Ancestry uses local git only and does not fetch. A shallow clone, a
missing `git` binary, or an unresolved main ref fails closed.

Empty `WorkUnit.command` values must not be handed to
`SimulationCampaignRunner`. This module never calls that runner.

Provenance records `schema_version` `grid_plan_v2`, generator
`tools.simulation_runtime.grid_plan`, `base_sha` (the local main ref used
for the ancestor check, or `unresolved`), `audited_main_sha`,
`code_version_id`, `worktree_dirty`, and `config_digest`. Provenance does
not contain `code_commit`.

A string in the config or in `record_root` that names `ds005620`, BIDS,
a participant, or an empirical input is `locked_input`. The path is not
opened.

`would_execute` lists cells, seeds, splits, and cost with `executed`
false. `execute` sets `aborted` and `abort_gate` at the first blocking
gate that is not `admissible_on_ancestor`, with `partial_launch` false.
No cell is launched.

## Gate ids

Blocking. Each gate except `ci_discovery` has a recorded candidate SHA.
That SHA is not evidence. A gate opens only when a direct-candidate
promotion report for that one `case_id` is a git blob on local main, the
report `source_sha` equals the pin, and the usual ancestor and
`ADMISSIBLE_*` checks pass. An open pull request, a local test pass, or a
green unrelated workflow is not enough. A different `source_sha` is
`stale_source`. A missing `source_sha` is `missing_dependency`.
`phase_dispersion` also requires `limitations_recorded: true`.
`ci_discovery` has no candidate SHA and stays blocked until the CI change
lands after this repair.

| Gate | Candidate SHA | Note |
| --- | --- | --- |
| `four_sphere_forward_model` | `4b04df0bed9d34e1f4de4bb920933aa84df3a724` | Open PR head, not on main. |
| `planar_geometry` | `04d5af7321ff002bb88d75353e59aec73eabbf56` | Open PR head, not on main. |
| `winding_hodge` | `3328dd15a995a62759c4256de944e2dd8e7c9364` | Split from the old combined id. |
| `csd_full_matrix_pinned_mne` | `24ad946c1cd6142846e19e9db8b7a5325d49ef46` | Open PR head, not on main. |
| `phase_dispersion` | `42f8f9ccdb126fafaf429e7e8b20ac4e8ff5aa98` | Limitations record required. |
| `surrogate_null` | `f8939eec66e585d00966d433cc563d3d34ca0b11` | Open PR head, not on main. |
| `roc_metrics` | `55115149c7443ca8b325dc4dbf65d6900c9fdd79` | Pinned #426 SHA. |
| `ci_discovery` | none | `BLOCKED`. |

`#427` head `e64304087dba4205ee2211963a3cf40025695e9c` moved off
`27d451fa`. It is not a gate pin and not evidence.

Nonblocking:

- `dmd_crouzeix` — `NONBLOCKING`

`GATE_INTEGRATION_STATE` marks the seven dependency gates `NOT_INTEGRATED`
and `ci_discovery` `BLOCKED`. Those labels are not evidence.

Verdict of a plan produced with this module while those reports are absent
and `ci_discovery` is blocked: **BLOCKED**. HOLD / SYNTHETIC_ONLY. The
grid is not run. The CI workflow change that would collect
`tests/simulation_runtime` must not land before this repair is merged,
because `ci_discovery` is currently the only gate this planner keeps
closed on its own. The planner can certify a digest, declared metric
names, an engineering sample-size label, a declared byte bound, and that
gates are missing or blocked. It cannot certify that a gate passed, that
a report was produced correctly, a power claim, a detector ROC, statistical
independence, or that the grid ran.
