# Benchmark Dataset Registry + Split/Holdout Governance

Status: **implemented substrate, no downstream consumers yet.** This
document describes the `benchmarks/` package as it exists today. It does
not describe, and should not be read as promising, any of the future
modules listed in [Future work](#limitations-and-future-work) -- those are
explicitly out of scope for this milestone.

## Why dataset/artifact roles matter

`transitions/` (see `docs/transition_science_foundation.md`) and
`phase_space/` (see `docs/phase_space_coordinates.md`) both track, per
record, a `claim_scope` and an `evidence_level` -- how strong a claim a
*single artifact* is allowed to make. Neither tracks something different
but equally important: **how many independent times has this dataset
already been looked at, and by what?**

A dataset that has been repeatedly explored -- fed into reports, used to
tune feature mappings, summarized by an LLM, or used to generate a
hypothesis -- is no longer a fair test of that same hypothesis. Reusing it
as if it were fresh, independent evidence is a well-known failure mode
(non-independence / data leakage / researcher degrees of freedom), and
nothing in `transitions/` or `phase_space/` prevents it: those packages
validate that a *single* record is honestly labeled, not that a *dataset*
hasn't already been spent.

`benchmarks/` closes that gap. It tracks, per dataset and per
feature-family-level artifact, a **role** (where in the discovery-to-
confirmation pipeline it currently sits) and a **contamination status**
(what has already touched it), and it gates every requested *use* of that
dataset/artifact against both.

## Core principle: discovery vs. confirmation

> A dataset or artifact can be used for discovery **or** confirmation of a
> given claim, but never both for the same claim.

Concretely:

- **Discovery** covers `exploration` and `development` roles: looking at
  data, tuning feature mappings, generating a hypothesis, picking a model.
- **Confirmation** covers `locked_internal_validation`,
  `locked_external_validation`, and `prospective` roles: testing a
  hypothesis that was fixed *before* this specific evidence was consulted.

Once a record has been used for discovery, `benchmarks.split_policy`
refuses every confirmatory use of it (`final_claim_confirmation`,
`cross_dataset_replication_claim`, `prospective_prediction_claim`) --
regardless of what its `allowed_uses` list says -- until it is retired or a
genuinely independent artifact is created. This is enforced in code
(`_can_use`'s role check), not left as a data-hygiene convention a seed
file could accidentally violate.

## How dataset contamination works

Every `DatasetRecordV1` / `ArtifactRecordV1` carries a `contamination_status`:

| Status | Meaning |
|---|---|
| `unseen` | Nothing in this repository has consulted it yet |
| `seen_by_exploration` | Read by exploratory pipelines/reports |
| `seen_by_llm` | Read by (or summarized through) an LLM |
| `seen_by_theory_generation` | Used to generate or shape a hypothesis |
| `seen_by_model_selection` | Used to pick a model/feature set/threshold |
| `confirmatory_locked` | Locked for validation via `benchmarks.holdout_lock` |
| `validation_consumed` | The validation lock has been used once and spent |
| `retired` | No longer usable except for documentation/history |

`benchmarks.split_policy.mark_seen(record, seen_by=...)` moves a record
into one of the four `seen_by_*` states and appends a free-text provenance
entry to `seen_by` (e.g. `"exploration:tools/export_ds005620_pitnn_transitions.py"`)
so the *specific* consumer is recorded, not just the fact that *some*
consumer touched it. It refuses to run on a record already at
`confirmatory_locked`, `validation_consumed`, or `retired` -- those are
managed by `benchmarks.holdout_lock`, not by further discovery exposure.

## How LLM/theory exposure affects validation eligibility

`seen_by_llm` and `seen_by_theory_generation` are singled out because they
are the two contamination routes a future Holo-Atlas interpreter or Theory
Competition Engine would create automatically, without anyone manually
calling `mark_seen`. A record at either status is refused for
`internal_validation` or `external_validation` outright (rule 2 in
`benchmarks.split_policy._can_use`) -- an LLM that has already read a
dataset's numbers cannot later "independently" validate a theory against
those same numbers, and neither can a theory-generation module that used
the dataset to shape the hypothesis it is now being asked to test.

## Holdout locks

`locked_internal_validation` / `locked_external_validation` roles require
an explicit `validation_lock` (issued by `benchmarks.holdout_lock.lock_for_validation`):

```python
from benchmarks.holdout_lock import lock_for_validation, consume_validation_lock

lock_for_validation(
    record, locked_by="operator", reason="preregistered replication",
    claim_family="propofol_awake_sedated_transition_effect",
)
```

The lock records `locked_at`, `locked_by`, `reason`, and
`allowed_claim_family`, and moves `contamination_status` to
`confirmatory_locked`. A validation use only succeeds when its
`claim_family` argument matches the lock's `allowed_claim_family` exactly
-- a lock issued for one claim cannot silently authorize a different one.
`consume_validation_lock` marks it spent (`contamination_status` ->
`validation_consumed`); a spent lock can never be reused as fresh
validation, mirroring `research_runtime.stage_policy.StageLock`'s
issue/consume-once pattern (see that module's docstring) but keyed to a
claim family and stored inside the record itself rather than in a separate
run-envelope directory.

`prospective` role additionally requires an explicit
`prospective_protocol_id` -- a prospective claim needs a protocol that was
registered before the predicted outcome was known, and this field is where
that protocol's identity is recorded.

## Relationship to `TransitionRecordV1` and `PhaseSpaceCoordinateV1`

`benchmarks/` does not modify either schema and is entirely optional today:

- `transitions.record.TransitionRecordV1` and
  `phase_space.coordinate.PhaseSpaceCoordinateV1` are unaffected --
  `benchmarks/` was built with **zero changes** to `transitions/` or
  `phase_space/`.
- The one integration point that exists is **opt-in**:
  `tools/export_ds000245_fmri_transitions.py` accepts an optional
  `--registry <path>` / `registry_path=` argument. When omitted (the
  default), behavior is byte-identical to before this milestone. When
  given, the exporter looks up `dataset_id="ds000245"` in the registry and
  calls `benchmarks.split_policy.can_use_dataset(record, requested_use)`
  *before* reading any artifact -- if the requested use is not permitted,
  the exporter fails closed (`ExportError`) and writes nothing.
- `tools/export_ds005620_pitnn_transitions.py` is unmodified; it can adopt
  the same optional pattern later without a schema change, since the hook
  lives entirely in the calling exporter, not in `TransitionRecordV1`.

This is the intended shape for the future consumers listed in
[Limitations and future work](#limitations-and-future-work): a Theory
Competition Engine's train/test split, a Koopman/DMD development-vs-
validation split, or a Holo-Atlas interpreter's evidence weighting would
all call `benchmarks.split_policy.assert_allowed_use` (or the registry's
`check_use`) before consuming a dataset for that purpose -- but none of
those modules exist yet, and this milestone does not build them.

## How to validate the registry

```bash
# validate every record in a registry file
python -m benchmarks.export_registry --registry benchmarks/registry_seed.json --validate

# list datasets / artifacts
python -m benchmarks.export_registry --list-datasets
python -m benchmarks.export_registry --list-artifacts

# check whether a use is currently permitted
python -m benchmarks.export_registry --check-use ds005620 transition_export
python -m benchmarks.export_registry --check-use ds005620 final_claim_confirmation   # denied

# mutating operations always require --out (never silently overwrite the input file)
python -m benchmarks.export_registry --mark-seen ds005620 --seen-by llm --out /tmp/updated.json
python -m benchmarks.export_registry \
    --lock-for-validation <record_id> --claim-family <name> \
    --reason "preregistered replication" --locked-by operator --out /tmp/updated.json
```

Programmatically:

```python
from benchmarks.export_registry import BenchmarkRegistry

registry = BenchmarkRegistry.load("benchmarks/registry_seed.json")
errors = registry.validate()          # {} if every record is valid
allowed, reason = registry.check_use("ds005620", "transition_export")
```

Validation checks two independent things per record (see
`benchmarks.validation`): structural well-formedness (known role, known
contamination status, non-empty limitations, required provenance, no
banned overclaim phrases -- reusing
`sciencer_d.btc_icft.report_guardrails.BANNED_REPORT_PHRASES` and
`transitions.governance.TRANSITION_EXTRA_BANNED_PHRASES` rather than a
sixth copy of that list) and existence-on-disk for committed artifacts
(skipped for `record_kind="candidate_unstructured"` records and for
`external=True` paths).

## Seed registry contents

`benchmarks/registry_seed.json` seeds **4 datasets and 6 artifacts**, all
built from real, already-integrated repository state -- no fabricated
records:

| dataset_id | role | modality | committed structured artifact? | notes |
|---|---|---|---|---|
| `ds005620` | `development` | EEG | yes (2 feature families) | propofol awake->sedated; `pitnn_cohort_summary` + `spatial_defect_map` artifact records, matching the two distinct feature families documented in `docs/transition_science_foundation.md` |
| `ds000245` | `development` | fMRI | yes (2 parcellation variants) | CTL/ODN/ODP cross-sectional group contrast; `fmri_graph_cohort_result_schaefer100_motcorr` + `fmri_graph_cohort_result_kmeans100` artifact records |
| `ds005917` | `exploration` | fMRI | **no** -- candidate/unstructured | only a prose report is committed; `allowed_uses=["documentation"]` only |
| `ds006644` | `exploration` | fMRI | **no** -- candidate/unstructured | only a prose report is committed; `allowed_uses=["documentation"]` only |

Every seeded record's `contamination_status` is `seen_by_exploration` --
none of these four datasets is fresh. All four are registered with
`current_role` at most `development`/`exploration`, never
`locked_internal_validation`/`locked_external_validation`/`prospective`,
and every one's `forbidden_uses` lists `final_claim_confirmation`,
`cross_dataset_replication_claim`, and `prospective_prediction_claim`
explicitly, in addition to the six always-blocked claim types below. This
is a conservative seed on purpose: nothing in this repository today is
registered as ready for confirmatory use of anything.

`ds005917`/`ds006644` are recorded honestly as candidate/unstructured: the
underlying dataset has been processed by
`tools/stream_process_ds005917.py`/`tools/stream_process_ds006644.py`, but
only a Markdown report is committed (see
`docs/dataset_scouting_ledger.md`) -- their `ArtifactRecordV1.record_kind`
is `"candidate_unstructured"`, `path` points at the real, committed
`REPORT_*.md` file, and `limitations` states plainly that no structured,
machine-parseable artifact exists. No exporter should read that path as a
JSON/CSV source.

## Dataset/artifact role policy

Roles (`benchmarks.split_policy.DATASET_ROLES`): `exploration`,
`development`, `locked_internal_validation`, `locked_external_validation`,
`prospective`, `retired`, `deprecated`.

Uses (`benchmarks.split_policy.ALLOWED_USES`): `transition_export`,
`phase_space_export`, `feature_design`, `theory_generation`,
`model_selection`, `internal_validation`, `external_validation`,
`prospective_prediction`, `visualization`, `documentation`.

Confirmatory claim types layered on top of the use vocabulary
(`CONFIRMATORY_CLAIM_USES`): `final_claim_confirmation`,
`cross_dataset_replication_claim`, `prospective_prediction_claim` -- these
require a `locked_internal_validation`/`locked_external_validation`/
`prospective` role *and* (for the two validation roles) a valid,
unconsumed, matching-claim-family lock; `exploration`/`development` records
are refused unconditionally.

## Prohibited uses

Six claim types are **always** blocked, regardless of role, lock state, or
what a record's own `allowed_uses` says (`benchmarks.split_policy.ALWAYS_BLOCKED_USES`,
checked first, before any other rule):

- `clinical_claim`
- `diagnostic_claim`
- `treatment_claim`
- `consciousness_biomarker_claim`
- `spiritual_attainment_claim`
- `mechanistic_causal_claim`

This registry cannot itself be configured to permit any of the above --
`benchmarks.validation` also rejects any record whose `allowed_uses`
contains one of them, so a misconfigured seed file cannot silently
re-enable them either. As with `transitions/` and `phase_space/`, every
record's free text (`limitations`, `metadata`, `display_name`/
`artifact_kind`) is scanned against the repository's shared banned-phrase
list, and validation fails closed on a hit.

## Limitations and future work

- **No downstream consumer exists yet.** A `DatasetRecordV1`/`ArtifactRecordV1`
  sitting in the registry is not itself evidence of anything; it only
  records how a dataset *may* be used going forward.
- **Not implemented by this milestone** (listed only to show what this
  substrate is for -- none of these descriptions is a commitment to a
  design): a Theory Competition Engine that would consult
  `benchmarks.split_policy` for train/test splits; Koopman/DMD development-
  vs-validation gating; Counterfactual Reachable Sets' model-development
  gating; a Phenomenology parser; a Holo-Atlas LLM interpreter that would
  call `mark_seen(..., seen_by="llm")` on every dataset it reads; a
  Consciousness Atlas that would weight evidence by contamination status.
- **Only one exporter has the optional registry hook** today
  (`tools/export_ds000245_fmri_transitions.py`); `tools/export_ds005620_pitnn_transitions.py`
  and any future exporter can adopt the same `registry_path`/`requested_use`
  parameter pattern without a schema change.
- **The registry is a JSON file, not a database.** `BenchmarkRegistry.save`
  overwrites its target path wholesale; concurrent mutation from multiple
  processes is not supported, matching every other filesystem store in this
  repository (`transitions.store.TransitionStore`, `phase_space.store.PhaseSpaceStore`).
  Mutating CLI operations always require an explicit `--out` and never
  silently overwrite the input registry.
- **Contamination is manually recorded, not automatically detected.**
  Nothing currently scans the repository to notice when a dataset has been
  read by a new tool and calls `mark_seen` automatically; that instrumentation,
  if ever built, is future work.
