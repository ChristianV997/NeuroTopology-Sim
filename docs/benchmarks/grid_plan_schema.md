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
| `code_commit` | `not_recorded`. The planner does not record HEAD as a scientific commit. |
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
- `results[]`: `PromotionResult.to_dict` keys, plus optional `verified_at_commit`

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
| `n_independent_calibration` | Count of calibration unit ids. The only calibration count checked against `plan_sample_size`. |
| `n_independent_evaluation` | Count of evaluation unit ids. The only evaluation count checked against `plan_sample_size`. |
| `nested_unit` | `window`, `trial`, or `none`. |
| `nested_per_unit` | Nested observations per independent unit. Never added into N. `none` requires `1`. |
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
`calibration_seed`, `estimand`, and `interval_method`. Calibration ids are
derived before that hash. Evaluation ids and `n_independent_evaluation`
are derived only after it. That ordering is in-process only. It is not a
preregistration record. A caller-supplied `evaluation_manifest` is
rejected. Changing `estimand` or `interval_method` changes `threshold_hash`.
Changing `evaluation_seed` changes `config_hash` and does not change
`threshold_hash`.

Wilson floors come from `analysis.binomial_planning.plan_sample_size`.
There is no second sample-size helper. `N>=100` and the #405 width floor
are engineering thresholds, not a power guarantee, unless a formal power
analysis is supplied. This planner does not accept or verify a power
analysis (`power_analysis_supplied` is false). `power_claim` stays `none`.
A plan whose independent counts are below 100, or below the #405 required
n, is labeled `UNDERPOWERED_DRY_RUN`. Counts that meet both floors are
labeled `ENGINEERING_THRESHOLD_MET` and are still not a power analysis.
Counts below the #405 required n are rejected before a plan is emitted.

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
`BOUND_NOT_A_MEASUREMENT`.

## Audit metadata

The plan records `project_status` `HOLD / SYNTHETIC_ONLY`, `code_version_id`
(the local `HEAD` SHA, or `UNKNOWN` when HEAD does not resolve), and
`config_digest` (the same value as `config_hash`). `UNKNOWN` keeps the
plan closed. The audit block also lists `master_seed`, `calibration_seed`,
`evaluation_seed`, and the derived calibration and evaluation ids.
`CampaignManifest.code_commit` stays `not_recorded`.

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
counts, nesting, the interval method, estimand, `power_claim`, the
sample-size label, the engineering threshold, `metric_spec`, the declared
bytes per record, `h0`, `h1`, `score_definition_id`, the threshold,
`threshold_hash`, Wilson inputs, budgets, blocking and nonblocking gate
ids, the ADMISSIBLE decision names, and `EvidencePromotionGate.v1`.
`code_version_id` is not part of `config_hash`.

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
for the ancestor check, or `unresolved`), `audited_main_sha`, and
`code_commit` `not_recorded`.

## Gate ids

Blocking:

- `four_sphere_oracle` — `NOT_INTEGRATED`
- `planar_embedding_winding_hodge` — `NOT_INTEGRATED`
- `csd_full_matrix_pinned_mne` — `NOT_INTEGRATED`
- `phase_score_limitations_recorded` — `NOT_INTEGRATED`
- `surrogate_randomizes_target_statistic` — `NOT_INTEGRATED`
- `roc_split_threshold_api` — `NOT_INTEGRATED`
- `ci_discovery` — `BLOCKED`

Nonblocking:

- `dmd_crouzeix` — `NONBLOCKING`

Verdict of a plan produced with this module while those reports are absent
and `ci_discovery` is blocked: **BLOCKED**. HOLD / SYNTHETIC_ONLY. The
grid is not run. The CI workflow change that would collect
`tests/simulation_runtime` must not land before this repair is merged,
because `ci_discovery` is currently the only gate this planner keeps
closed on its own.
