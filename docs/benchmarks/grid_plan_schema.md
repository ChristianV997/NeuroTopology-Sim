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

`tools.evidence_promotion_gate.reporting.results_payload` writes JSON:

- `schema_version`: `EvidencePromotionGate.v1`
- `scientific_pass`: false
- `results[]`: objects from `PromotionResult.to_dict`, matched by `case_id`

`PromotionResult` has `promotion_decision` and forces `scientific_pass`
false. It has no `verified_at_commit`, artifact SHA, log pointer, verifier,
or freshness field. This module does not edit `schema.py` and does not
add a gate registry file.

`execute` reads only JSON files that already have that report shape.
Command-center payloads (`command-center-evidence-promotion/v1`) and RAG
packs are ignored. A report whose top-level `scientific_pass` is not
false is ignored. The default directory is the repository tree. Callers
may pass `record_root` as a directory of already-written reports. That
path is not a decision object.

A gate id resolves only when one `results[]` row has:

- `case_id` equal to that gate id
- `promotion_decision` whose name starts with `ADMISSIBLE_`
- `scientific_pass` not true
- `verified_at_commit` equal to 40 lowercase hex characters
- that commit an ancestor of current `origin/main` (else local `main`),
  checked with `git merge-base --is-ancestor` and no fetch

No such report is on main at the audited commit
`19c3203573082f8bc41f7da226b52dc20a49fdb0`. Every resolvable gate is
therefore `missing`, and every cell stays blocked. A caller dict, list,
or boolean passed to `execute` is rejected as a gate decision and is not
read, even when it says `ADMISSIBLE_*` and names an ancestor commit.

`ci_discovery` is blocking and is not opened by a promotion record. The
fixed test lists in `.github/workflows/ci.yml`,
`.github/workflows/required-checks.yml`, and `docker/ci/core.Dockerfile`
do not collect `tests/simulation_runtime`. `dmd_crouzeix` is recorded and
is nonblocking.

Integration labels (`NOT_INTEGRATED`, `BLOCKED`, `NONBLOCKING`) are audit
constants in the module. They are not a second registry and they do not
replace the report scan.

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

`calibration_unit_ids` and `evaluation_unit_ids` are explicit lists.
`roles_are_disjoint` is `set(calibration).isdisjoint(set(evaluation))`.
A unit id in both sets is `unit_id_overlap`. `n` equal to
`len(unit ids) * nested_per_unit` when `nested_per_unit > 1` is
`windows_counted_in_n`. Trial and compute budgets use the independent-unit
counts only.

`h0`, `h1`, and `score_definition_id` are required. The score id is a
reference. This module does not compute a score. The threshold is a
non-empty finite mapping. Its hash, with `h0`, `h1`, and
`score_definition_id`, is recorded before `evaluation_unit_ids` or
`n_independent_evaluation` is read. A caller-supplied `evaluation_manifest`
is rejected. The evaluation manifest is built only after that hash exists.

Wilson floors come from `analysis.binomial_planning.plan_sample_size`.
There is no second sample-size helper. Meeting a width bound is not a
power guarantee.

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
counts, nesting, the interval method, estimand, `power_claim`, `h0`,
`h1`, `score_definition_id`, the threshold, `threshold_hash`, Wilson
inputs, budgets, blocking and nonblocking gate ids, the ADMISSIBLE
decision names, and `EvidencePromotionGate.v1`.

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
from disk and it does not open a gate. A SHA inside a promotion report is
also not checked. The only resolution path is `case_id` plus an
ADMISSIBLE decision plus `verified_at_commit` ancestry of current main,
read from a report the evidence-promotion writer already shapes.

`execute(config, gate_evidence, ...)` does not read `gate_evidence`.
Passing a fabricated ADMISSIBLE record leaves every cell blocked.
A report whose `verified_at_commit` is not an ancestor of main leaves
every cell blocked.

Empty `WorkUnit.command` values must not be handed to
`SimulationCampaignRunner`. This module never calls that runner.

Provenance records `schema_version` `grid_plan_v2`, generator
`tools.simulation_runtime.grid_plan`, `base_sha` (the local main ref used
for the ancestor check), `audited_main_sha`, and `code_commit`
`not_recorded`.

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
and `ci_discovery` is blocked: **BLOCKED**.
