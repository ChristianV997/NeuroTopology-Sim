# Grid plan schema (`grid_plan_v1`)

Status: **HOLD / SYNTHETIC_ONLY**. This document describes a planning
schema. It is not a simulation result, not a performance claim, and not
evidence that any upstream gate has been verified.

`neurotopology_sim/` is not a package in this repo. The module lives at
`tools/simulation_runtime/grid_plan.py`. No `neurotopology_sim/__init__.py`
file is added. `tools/simulation_runtime/__init__.py` is unchanged.

## What v1 already has

`CampaignManifest` (`simulation_campaign_manifest_v1` in
`tools/simulation_runtime/types.py`) is the workload object this plan
expands into. Existing fields:

| Field | Role |
| --- | --- |
| `schema_version` | Always `simulation_campaign_manifest_v1` here. Not bumped. |
| `campaign_id` | Derived from the config hash prefix. |
| `created_at` | Fixed sentinel `1970-01-01T00:00:00+00:00` so a dry-run is deterministic. |
| `code_commit` | `not_recorded`. This planner does not shell out to git. |
| `configuration_hash` | Same digest as `config_hash` (see below). |
| `seed` | `master_seed`. |
| `units` | One `WorkUnit` per grid cell. `command` is empty. `parameter_case` holds the cell. |
| `environment` | Synthetic hold labels only. No hostname capture. |
| `resource_policy` | Inert placeholders (`max_workers=1`, retries `0`, timeout `0`). Not the scientific budget. |

`WorkUnit` also has `parameter_case`, which is where axis values, null id,
and source id are stored. `CampaignState` tracks `is_complete`,
`active_unit`, and `UnitResult.outcome`.

## What v1 does not have

Run states `planned`, `blocked`, `running`, `completed`, and `failed` are
not fields of `CampaignManifest` or `CampaignState`. The closest runtime
vocabulary is `Outcome` (`PASS`, `CORRECTNESS_FAILURE`, `TIMEOUT`,
`DEPENDENCY_MISSING`, `NETWORK_FAILURE`, `DISK_FAILURE`, `MEMORY_FAILURE`,
`UNKNOWN_FAILURE`, `NOT_RUN`). `Outcome.PASS` is a process outcome. It is
not a gate and not a scientific status. `grid_plan_v1` does not write it.

Gate evidence is also absent: no gate id, promotion decision, artifact SHA,
log pointer, verifier, timestamp, or freshness field exists on the manifest,
the work unit, or the campaign state.

Those gaps stay in the wrapper. v1 is not bumped.

`tools/evidence_promotion_gate/schema.py` (`EvidencePromotionGate.v1`) is
the decision authority. `PromotionResult` has `promotion_decision` and
forces `scientific_pass` false. It does **not** have artifact SHA, log
pointer, verifier, timestamp, or freshness fields. `grid_plan_v1` wraps
those missing fields and does not edit `schema.py`. It does not call the
evaluator and does not upgrade a decision.

## Wrapper

`schema_version` is `grid_plan_v1`. `status_label` is always
`HOLD_SYNTHETIC_ONLY`.

Emitted `run_state` values are only `planned` (dry-run, or a gate check
that opened without a launch) and `blocked` (execution refused). The tokens
`running`, `completed`, and `failed` are reserved. A document that declares
them is rejected. Parsing a config never emits `completed`.

## Scientific inputs

Closed config keys: `schema_version`, `axes`, `null_model_ids`,
`source_model_ids`, `master_seed`, `calibration_seed`, `evaluation_seed`,
`calibration_samples`, `evaluation_samples`, `wilson_confidence_level`,
`wilson_target_full_width`, optional `wilson_design_p`, `max_cells`,
`max_trials`, `max_compute_units`, `compute_units_per_trial`,
`max_evidence_age_s`, optional `nuisance_scenario_id`.

Axes are mappings `{name, unit, values, minimum, maximum}`. Names are
identifiers. Units are non-empty strings (for example `dB`, `mm`). Every
value must be finite and inside `[minimum, maximum]`, with
`minimum <= maximum`. Empty axes, empty value lists, duplicate names, and
duplicate values are rejected. NaN and Inf are rejected.

Cell count is the product of axis lengths, null ids, and source ids.
Enumeration sorts axes by name, then walks each axis's declared value
order, then the declared null-id order, then the declared source-id order.
Cells are `cell-0000` upward.

Null ids, closed: `synthetic_phase_shuffle`, `synthetic_iaaft`,
`synthetic_time_reverse`.

Source ids, closed: `synthetic_single_dipole`, `synthetic_patch`,
`synthetic_noise_only`.

The two allowlists are disjoint. Unknown ids are rejected. These strings
are planning labels, not generators.

Seeds are pairwise-distinct non-negative integers. The split algorithm is
`disjoint_fixed_seed_blocks`. Trial identity is
`(cell_index, role, trial_index)` with roles `calibration` and
`evaluation`. The same fixed seeds are stored on every cell. Roles do not
share an index space.

`calibration_samples` and `evaluation_samples` must each be integers greater
than or equal to `required_n` from
`analysis.binomial_planning.plan_sample_size` at the declared Wilson
full-width, confidence level, and design proportion (`null` means the
uniform worst case at `p = 0.5`). There is no second sample-size helper.
If that search cannot find an `n` inside `max_trials`, the config is
`over_budget`.

Budgets reject a plan when cell count, trial count
(`cells * (calibration_samples + evaluation_samples)`), or compute units
(`trials * compute_units_per_trial`) exceed the declared maxima. Hard
ceilings, independent of the declared budget, are 4096 cells and 1,000,000
trials. Equality with a declared maximum is accepted. Over-budget configs
are rejected before cells are built.

## Canonical hash

`config_hash` is `tools.simulation_runtime.atomic_io.compute_config_hash`
of the scientific payload only. That function sorts mapping keys, so key
order does not change the digest. List order does: axis values, null ids,
and source ids are ordered inputs.

The payload includes schema version, axes (name, unit, values, range),
null and source ids, the three seeds, both sample counts, the split
algorithm id, the Wilson inputs, the three budgets, `compute_units_per_trial`,
`max_evidence_age_s`, the required gate ids, the ADMISSIBLE decision names
read from the evidence schema, `EvidencePromotionGate.v1`, and
`nuisance_scenario_id`. Changing a scientific parameter, a seed, or that
gate policy changes the digest.

Derived cells, the campaign manifest, evidence records, and `checked_at`
are not part of `config_hash`. Evidence records get a separate
`evidence_hash` from the same `compute_config_hash` function when every
required gate parsed. A boolean cannot change the scientific digest, and it
cannot authorize execution.

## Gate check

Required gate ids:

- `four_sphere_forward_model`
- `planar_geometry_winding_hodge`
- `csd`
- `phase_surrogate`

`execute` refuses unless each id appears once as a record with:

- `promotion_decision` equal to a `PROMOTION_DECISIONS` value whose name
  starts with `ADMISSIBLE_` (today: `ADMISSIBLE_FOR_DESCRIPTIVE_REVIEW`,
  `ADMISSIBLE_FOR_ENGINEERING_REPORT`)
- `artifact_sha256`: 64 lowercase hex characters
- `log_pointer`: non-empty string
- `verifier`: non-empty string
- `verified_at`: timezone-aware ISO-8601 timestamp

Freshness is `checked_at - verified_at`. Age must be finite, non-negative,
and less than or equal to `max_evidence_age_s`. Missing, HOLD, BLOCK,
`VERIFIED`, `PASS` or any other `Outcome` value, a bare boolean, a
self-declared label, a duplicate, an unknown id, a stale timestamp, a
future timestamp, a naive timestamp, or a missing SHA/log/verifier all
leave `run_state=blocked`. `scientific_pass` is not an accepted field.

An opened check sets `gate_check.opened` true and leaves `run_state` at
`planned`. It does not set `running` or `completed`, and it does not call
the simulation callback. `dry_run` never evaluates evidence and never calls
that callback.

## Trust boundary

`grid_plan_v1` reads decisions. It does not create or upgrade them, does
not open artifact paths, and does not recompute a SHA from disk. A
well-formed SHA is a schema check, not file verification and not a
scientific result. ADMISSIBLE means the evidence schema allowed descriptive
review or an engineering report. The plan label stays
`HOLD_SYNTHETIC_ONLY`.

Empty `WorkUnit.command` values are planning records. Do not pass the
embedded manifest to `SimulationCampaignRunner`. This module never calls
that runner.

`nuisance_scenario_id` is an optional opaque token. It is not resolved.
PR #408 `NuisanceGridConfig` (`sim/nuisance_scenarios`, unmerged) builds
synthetic scenario objects and ids such as
`nuis_chi1.00_snr+0.0dB_jit0.00mm_rawcart_seed42`. That package is scenario
generation, not this run plan. `grid_plan` does not import it.

Gemini Revision 8 is not an input to this schema.

## Dry-run

`dry_run(config)` validates, hashes, and lists cells. `run_state` is
`planned`. `execution.launched` and `execution.completed` are false.
`gate_check.opened` is false. Invalid configs raise `GridPlanError` and do
not build a completed manifest.
