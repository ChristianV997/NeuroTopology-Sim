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
`02520d44d662d394a2ff0822c0d3170a2d34213a`. `four_sphere_forward_model`
and `winding` are pinned to merge commits and stay
`promotion_report_missing`. Every other dependency pin is null, so those
gates are `dependency_not_merged_on_main`, and every cell stays blocked.
A caller dict, list, or boolean passed to `execute` is not read, even
when it says `ADMISSIBLE_*` and names an ancestor commit.

If `git` is missing, the clone is shallow (`git rev-parse
--is-shallow-repository` is `true`), or main cannot be resolved, every
gate is `missing` and every cell stays blocked. The plan records
`gate_source_failure` as `git_missing`, `shallow_clone`, or
`main_unresolved`. Ancestry is local git only. This module does not fetch.

`ci_discovery` is blocking and stays blocked. The fixed core lists in
`.github/workflows/ci.yml`, the core test step of
`.github/workflows/required-checks.yml`, and `docker/ci/core.Dockerfile`
(`CMD`) do not name `tests/simulation_runtime/test_grid_plan.py`. Pull
request #425 merged the Round 6 discovery step
(`.github/workflows/round6_experimental_tests.py`), which can select
`simulation_grid_planner` when these paths change. That discovery does
not open this gate. `dmd_crouzeix` is recorded and is nonblocking.

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

Per-class ids are derived inside the planner from the seeds:
`calibration-pos-seed{seed}-u{index:06d}`, `calibration-neg-seed{seed}-u{index:06d}`,
and the same shape for `evaluation-pos` and `evaluation-neg`. The combined
`calibration_unit_ids` list is the positive ids followed by the negative
ids. Caller-supplied id lists are `caller_unit_ids_rejected`. Window-style
ids such as `s1_w0` and `s1_w1` cannot be passed in and cannot inflate N.
`roles_are_disjoint` is the computed pairwise disjointness of the four
class sets. A shared id is `unit_id_overlap`. `n` equal to
`len(unit ids) * nested_per_unit` when `nested_per_unit > 1` is
`windows_counted_in_n`. Trial and compute budgets use the independent-unit
counts only. Derived id lists are not stored on the re-parseable
configuration input.

`h0`, `h1`, and `score_definition_id` are required. The score id is a
reference. This module does not compute a score. The threshold is a
non-empty finite mapping. `threshold_hash` covers `h0`, `h1`,
`score_definition_id`, `threshold`, `calibration_unit_ids`, the calibration
positive and negative id lists, `calibration_seed`, `estimand`,
`interval_method`, `unit_aggregation`, `n_positive_calibration`,
`n_negative_calibration`, `nested_per_unit`, and `unit_score_rule`.
Calibration ids are derived before that hash. Evaluation ids,
`n_independent_evaluation`, and the evaluation class counts are read only
after it. That ordering is in-process only. It is not a preregistration
record. A caller-supplied `evaluation_manifest` is rejected. Changing
`estimand`, `interval_method`, `unit_aggregation`, a calibration class
count, or `nested_per_unit` changes `threshold_hash`. Changing
`evaluation_seed` or an evaluation class count changes `config_hash` and
does not change `threshold_hash`.

`unit_score_rule` is the declaration `max_window_score`. It is the
per-unit score for AUC and average precision and is consistent with
`cluster_any_event_rate`. Nothing is scored. The any-event rule makes FPR
depend on `nested_per_unit`: a longer window nest can raise the chance
that a negative unit's max window score crosses the threshold. That
dependence is recorded on `metric_spec`. It is not a computed FPR.

Wilson floors come from `analysis.binomial_planning.plan_sample_size`.
There is no second sample-size helper. `required_n` is applied separately
to `n_positive_calibration`, `n_negative_calibration`,
`n_positive_evaluation`, `n_negative_evaluation`, and to each independent
total. A count below that #405 floor is rejected and is not emitted. It
is not labeled `UNDERPOWERED_DRY_RUN`.

The engineering minimum, not a power guarantee, is at least 100
independent positive units and 100 independent negative units in
calibration and the same pair in evaluation. An emitted plan with any of
those four counts below 100 is `smoke_only` and `UNDERPOWERED_DRY_RUN`.
A plan whose four counts are each at least 100 is
`ENGINEERING_THRESHOLD_MET` with execution mode `held`. That label is
still not a power analysis. This planner does not accept or verify a
power analysis (`power_analysis_supplied` is false). `power_claim` stays
`none`. Neither label launches the grid.

`roles_are_disjoint` is the computed disjointness of the four derived id
sets. Disjoint id sets are not statistical independence. Independent draws
need per-seed RNG streams downstream.

## Declared metrics

`metric_spec` is a declaration block inside the plan hash. Every metric
has `status: NOT_INTEGRATED`, `integration: NOT_INTEGRATED`,
`computed: false`, and `value: null`. This module does not import or
reimplement pull request #426. That pull request is unmerged, so its head
is not a pin and `source_head` is null. The names `tpr`, `fpr`,
`precision`, `auc`, and `average_precision` are recorded as
`NOT_INTEGRATED`. `accuracy` is an additional declared proportion with the
same status. No ROC, average-precision, or Wilson interval on observed
scores is computed. `plan_sample_size` supplies only the planning floor
(`required_n` and the design width).

Wilson intervals are declared only for proportions at the frozen
threshold: `tpr`, `fpr`, `precision`, and `accuracy`. Numerator and
denominator fields are counted in independent units (seeds), never
windows. The planning floor from `plan_sample_size` covers class counts.
It does not cover precision's Wilson interval. When the predicted-positive
count is zero, precision falls back to
`precision_undefined_no_predicted_positives`. `auc` and
`average_precision` are not proportions. Their declared `interval_method`
is `cluster_bootstrap_over_independent_unit`. Tie-aware AUC means ties
count 0.5 (Mann-Whitney midrank). Stepwise average precision means the
sum of precision at each recall step, with no interpolation. Those
sentences are the contract. No score is ranked here.

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
(`planned_outputs` plus one artifact per cell). Independent units are the
declared calibration and evaluation seeds. Nested samples are in that
product, not only the cell count. `expected_artifact_count` above
`ABSOLUTE_MAX_ARTIFACTS` (`ABSOLUTE_MAX_CELLS` plus the planned-output
count) is `over_budget`. `estimated_callback_invocations`
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
record, the gate contract (`pinned_commit`, module path, API symbols),
`grid_execution` (`NOT_RUN`), `h0`, `h1`, `score_definition_id`, the
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

The data lock is a string denylist, not a complete guard. A config string
or `record_root` string that names `ds005620`, BIDS, a participant, or an
empirical input is `locked_input`. The planner opens no data paths.
`record_root` is not opened. A renamed or encoded empirical path can pass
the denylist and still cannot be read, because this module never opens it.

`would_execute` lists cells, seeds, splits, and cost with `executed`
false. `execute` sets `aborted` and `abort_gate` at the first blocking
gate that is not `admissible_on_ancestor`, with `partial_launch` false.
No cell is launched.

## Gate ids

Blocking. A pin may name only a commit that `git merge-base --is-ancestor`
accepts against local main, and only when `(merged_pr, pinned_commit)`
equals `MERGED_PIN_PAIRS`. A null pin yields
`dependency_not_merged_on_main`. An open-pull-request head supplied as a
pin yields `pin_not_ancestor_of_main`. A pin that is still an ancestor
but is not the registered merge commit yields `merged_pr_mismatch`.
Two gates that cite the same module path yield `duplicate_module_claim`.
Pull-request numbers and heads in `informational_candidate` are
citations. Gate evaluation does not read them, and they are not part of
`config_hash`. `merged_pr` is part of `config_hash`.

A gate is eligible only when all of these hold:

1. `pinned_commit` is non-null and an ancestor of main.
2. `required_module_path` is a blob in that main tree
   (`module_missing_on_main` when it is not).
3. `required_api_symbols` are bound on the module body of that blob.
   The check is `ast.parse` of `git show` and reads only top-level
   names. Nested definitions do not count. The module is not imported
   (`symbols_missing_on_main` when a name is absent).
4. A promotion report at the `write_report` default path is a blob on
   main and passes the one-`case_id` admissibility checks. A matching
   text pin does not open the gate by itself. When the pin, module,
   symbols, and module blob match audited main and that report is absent,
   the status is `promotion_report_missing`, not `dependency_not_merged_on_main`
   and not `admissible_on_ancestor`. The blob of the module at
   `pinned_commit` must equal the blob at `AUDITED_MAIN_SHA`. A difference,
   including a pin of the file-adding commit, is `pin_blob_mismatch_main`
   and `stale`. `added_in_commit` records the introducing commit and is
   not a pin. `implementation_blob_sha` is the blob at the pin.
5. Direct tests are collected by CI. `ci_discovery` stays blocked.
   Pull request #425 merged discovery. That selection does not open the gate.

One gate's report never satisfies another gate. `run_state` stays
`blocked`, `opened` stays false, and `sweep_reachable` stays false while
any blocking gate is short of `admissible_on_ancestor`.

There are ten blocking gates. `winding_hodge` is split. `winding` is
pinned to merge commit `9abf3abeebd1c210d59df44b4d208678d203404c` of
pull request #413 (`neurotopology_sim/experimental/topology/winding.py`
on main). The file was added at `eefabe97690caeec33f3777a05d2acbe0398ea6b`
and later commits changed the blob; the pin stays the merge SHA. The
blob at that pin matches audited main (`39084e1735206c616a1befdaddf8b83f23365bdf`).
The pin does not open the gate: there is no main-tracked promotion
report, so the status is `promotion_report_missing`.
`four_sphere_forward_model` is the same shape: added at
`1b3465d4410a531e4686ba3b2dc0d0ae052c6e93` (blob
`158500ffc5bc2d519b2264613be64a522347bd2f`), pinned at the #418 merge,
implementation blob `ba01dad6e21e89ed3cf54179bbc7319975987465`.
`hodge` is `neurotopology_sim/experimental/topology/hodge_2d.py` observed
on open pull request #423. Re-ls-remote still returns
`eb5bfa288144d3150d2ec8a85b1f90ed5fd8e5c9`, not the cited prefix
`ea7a3b99`. #414 remains `5a8e6485be08f68757c46b7e7beda70bf9a0d4b6`,
#416 remains `757668e9b739d7423fa1493aec550072aa105829`, and #426 remains
`8c422e9c295510c1e71b373181f9eb1c44871a25`.
The pin stays null, so the gate stays `dependency_not_merged_on_main`.
Open pull requests #396 and #385 also ship Hodge code; the contract cites
the production module on #423. `phase_dispersion_module` has no path and
no symbols (`contract_declared_unobserved`) and stays unpinned. No open
pull request fetched for this audit ships a `phase_dispersion` module.
A path under `tools/phase_uncertainty/` is `substitute_module_rejected`.
Pull request #403 is not that module. `surrogate_null` stays unpinned.
Pull request #417 is not merged. Pull request #430
(`e5e1136631d500dddab7a5b31d6916962b5da5e3`) is stacked on #417 and is
not on main. A hosted-green adversarial suite on the exact merged #417
candidate is required before a pin. #430 green alone does not count.
`contract_declared_unobserved` rows stay `module_missing_on_main` and
cannot become admissible. `phase_score_limitations_recorded` is a
separate limitations row and still requires `limitations_recorded: true`
once its pin is an ancestor.

Observed rows use `contract_source: candidate_head_observed`. The head
SHA on that row is informational. It is not a pin, gate status does not
read it, and it is not part of `config_hash`. Symbols are the public
top-level names parsed from `git show <head>:<path>`.

`grid_execution` is `NOT_RUN`. `opened` stays false, and the simulation
callback is refused, including when a document says otherwise. A module
blob with the declared names at an ancestor of main does not open a gate
when the promotion report is not a blob on main.

Abort order is the blocking-id order. The first blocking gate that is not
`admissible_on_ancestor` is `abort_gate`.

| Gate | Source | Module | Pin | Status while the plan is closed |
| --- | --- | --- | --- | --- |
| `four_sphere_forward_model` | merged #418; added in `1b3465d4410a531e4686ba3b2dc0d0ae052c6e93`; blob `ba01dad6e21e89ed3cf54179bbc7319975987465` | `physics/eeg_forward/four_sphere.py` | `02520d44d662d394a2ff0822c0d3170a2d34213a` | `promotion_report_missing` |
| `planar_geometry` | candidate_head_observed, #416 `757668e9b739d7423fa1493aec550072aa105829` | `neurotopology_sim/experimental/geometry/planar_triangulation.py` | null | `dependency_not_merged_on_main` |
| `winding` | merged #413; added in `eefabe97690caeec33f3777a05d2acbe0398ea6b`; blob `39084e1735206c616a1befdaddf8b83f23365bdf` | `neurotopology_sim/experimental/topology/winding.py` | `9abf3abeebd1c210d59df44b4d208678d203404c` | `promotion_report_missing` |
| `hodge` | candidate_head_observed, #423 `eb5bfa288144d3150d2ec8a85b1f90ed5fd8e5c9` | `neurotopology_sim/experimental/topology/hodge_2d.py` | null | `dependency_not_merged_on_main` |
| `csd_full_matrix_pinned_mne` | candidate_head_observed, #414 `5a8e6485be08f68757c46b7e7beda70bf9a0d4b6` | `neurotopology_sim/experimental/preprocessing/spherical_csd.py` | null | `dependency_not_merged_on_main` |
| `phase_dispersion_module` | contract_declared_unobserved | none | null | `dependency_not_merged_on_main` |
| `phase_score_limitations_recorded` | limitations_record | none | null | `dependency_not_merged_on_main` |
| `surrogate_null` | candidate_head_observed, #417 `c39f715c84e928c0204b8c58ef9e40bc1f0ab684` | `tools/surrogate_nulls/nulls.py` | null | `dependency_not_merged_on_main` |
| `roc_metrics` | candidate_head_observed, #426 `8c422e9c295510c1e71b373181f9eb1c44871a25` (stub; symbols not verified on that head) | `neurotopology_sim/experimental/benchmarks/synthetic_forward_roc.py` | null | `dependency_not_merged_on_main` |
| `ci_discovery` | ci_collection | `tests/simulation_runtime/test_grid_plan.py` | null, and blocked | `ci_discovery_blocked` |

Public top-level symbols, in blob order:

- `four_sphere_forward_model`: `MAX_DEGREE`, `DEFAULT_MAX_DEGREE`, `DEFAULT_RESIDUAL_TOL`, `DEFAULT_TAIL_TOL`, `MAX_SCALE_RADIUS_M`, `MIN_RADIUS_M`, `CONDUCTIVITY_BOUNDS_SM`, `TAIL_VALIDATED_MIN_DEGREE`, `FourSphereError`, `FourSphereInputError`, `FourSphereQualityError`, `FourSphereGeometry`, `FourSphereResult`, `NAESS2017_TABLE1_K_VALUES`, `naess2017_table1_geometry`, `legendre_and_derivative`, `shell_transfer`, `transfer_ratios`, `forward_potentials`
- `planar_geometry`: `SCHEMA_VERSION`, `PROJECT_STATUS`, `DATA_POLICY`, `Point`, `Triangle`, `Edge`, `DegeneracyPolicy`, `ClaimLayer`, `FailureKind`, `LayerDiagnostic`, `PlanarTriangulationResult`, `orient2d`, `incircle`, `convex_hull_extreme`, `hull_boundary_with_collinear`, `validate_layers`, `triangulate_2d`, `validate_planar_mesh`
- `winding`: `TWO_PI`, `SUPPORTED_WRAP_INTERVALS`, `DEFAULT_TIE_TOL`, `DEFAULT_IDENTITY_ATOL`, `SUPPORTS_SPARSE_INCIDENCE`, `ORIGIN_SHIFT_COORDINATE_MAP`, `ArrayLike`, `WindingError`, `WindingResult`, `ChargeMomentResult`, `branch_index_floor`, `phase_winding`, `signed_first_moment`, `origin_shifted_moment`, `charge_moments`
- `hodge`: `ArrayLike`, `BoundaryCondition`, `GaugePolicy`, `MetricType`, `HodgeError`, `CochainComplexError`, `MetricError`, `IllConditionedMetricError`, `BoundaryConditionError`, `HodgeResult`, `effective_condition_number`, `validate_cochain_complex`, `validate_edge_metric`, `detect_boundary_elements`, `weighted_inner_product`, `weighted_norm_sq`, `hodge_decompose`
- `csd_full_matrix_pinned_mne`: `MNE_PIN`, `DEFAULT_LAMBDA2`, `DEFAULT_STIFFNESS`, `DEFAULT_N_LEGENDRE_TERMS`, `OUTPUT_UNIT_SI`, `DEFAULT_COINCIDENT_COS_TOL`, `DEFAULT_CONDITION_MAX`, `DEFAULT_AVG_REF_NULL_ATOL`, `SphericalCSDError`, `SphericalCSDConfig`, `SphericalCSDResult`, `compute_spherical_csd_transform`, `apply_spherical_csd`
- `surrogate_null`: `AUTO_SPECTRUM_TOL`, `CROSS_SPECTRUM_STRICT_TOL`, `MARGINAL_EXACT_TOL`, `NULL_IDS`, `EXPLORATORY_NULL_IDS`, `RANK_STATUS`, `CONTRACTS`, `SurrogateReport`, `common_phase_prichard_theiler`, `independent_phase_univariate_ft`, `draw_from_csd`, `cholesky_gaussian_cross_spectral`, `cholesky_gaussian_csd`, `zero_lag_real_part_gaussian`, `mv_iaaft_rank_adjusted`, `GENERATORS`
- `roc_metrics`: `PROJECT_STATUS`, `HIGHER_SCORE_IS_POSITIVE`, `HASH_NOTE`, `BenchmarkError`, `ConfusionCounts`, `fingerprint_sample_ids`, `cluster_any_event_rate`, `confusion_at_threshold`, `operating_point`, `compute_roc`, `select_threshold_on_calibration`, `assert_no_sample_overlap`, `evaluate_held_out`, `REQUIRED_PREREQUISITES`, `prerequisite_gate_report`, `SyntheticRunnerConfig`, `run_synthetic_operating_characteristics`, `json_safe`

`cluster_any_event_rate` is the same name cited by the unit-aggregation note at `synthetic_forward_roc.py:194` on the earlier complete head `55115149c7443ca8b325dc4dbf65d6900c9fdd79`. The current #426 tip is a stub and is not a pin. The required symbol list stays non-empty.

Nonblocking:

- `dmd_crouzeix` — `NONBLOCKING`, pin null

`GATE_INTEGRATION_STATE` marks the dependency gates, including `winding`,
`hodge`, and both phase rows, `NOT_INTEGRATED`, and `ci_discovery`
`BLOCKED`. Those labels are not evidence.

Verdict of a plan produced with this module: **BLOCKED**. HOLD /
SYNTHETIC_ONLY. `GRID_EXECUTION=NOT_RUN`. The planner can certify a
digest, declared metric names, an engineering sample-size label, a
declared byte bound, and that gates are blocked. It cannot certify that
a gate passed, that a report was produced correctly, a power claim, a
detector ROC, statistical independence, or that the grid ran.
