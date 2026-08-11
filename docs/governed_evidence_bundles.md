# Governed Evidence Bundles

Status: **implemented substrate, no downstream consumers yet.** This
document describes the `evidence/` package as it exists today. It does not
describe, and should not be read as promising, any of the future modules
listed in [Limitations and future work](#limitations-and-future-work) --
those are explicitly out of scope for this milestone.

## What an `EvidenceBundleV1` is

`transitions/` (`docs/transition_science_foundation.md`), `phase_space/`
(`docs/phase_space_coordinates.md`), and `benchmarks/`
(`docs/benchmark_dataset_registry.md`) each solve one piece of governed
evidence production: a durable transition-record schema, a derived
phase-space coordinate schema, and a discovery-vs-confirmation use policy.
Nothing before this milestone recorded, in one place, *which* registry
decision authorized *which* transition records and phase-space coordinates
for *one* source artifact -- a future consumer had to manually reconstruct
that chain by cross-referencing exporter output directories, registry
files, and CLI invocation history.

`EvidenceBundleV1` is that durable object. One bundle records:

- the source artifact read (`artifact_paths`, `artifact_ids`)
- the registry's use decision for that artifact/dataset (`registry_decisions`)
- every `TransitionRecordV1` produced (`transition_record_ids` / `_paths`)
- every `PhaseSpaceCoordinateV1` produced, if requested (`phase_space_coordinate_ids` / `_paths` / trajectory paths)
- the weakest applicable claim/evidence ceiling (`claim_scope_ceiling`, `evidence_level_ceiling`)
- what was actually generated (`generated_claim_scope`, `generated_evidence_levels`)
- an honest, aggregated null-control status (`null_control_summary`)
- any contamination updates actually applied (`contamination_updates`)
- non-empty `limitations`

**A governed evidence bundle is still not a theory result.** It asserts
nothing beyond what the `TransitionRecordV1`/`PhaseSpaceCoordinateV1`
artifacts it references already state. It is a reproducible artifact
manifest -- what was read, what was authorized, what was produced, and what
that production is allowed to claim -- nothing more.

## How it links registry, transitions, phase-space, and contamination

```
BenchmarkRegistry.check_use(dataset/artifact, requested_use)
        |
        v  (fails closed if denied, before any output is written)
tools.export_ds005620_pitnn_transitions.export() / tools.export_ds000245_fmri_transitions.export()
        |
        v  writes TransitionRecordV1 artifacts via TransitionStore
[optional] phase_space.export_from_transitions.export()
        |
        v  writes PhaseSpaceCoordinateV1 artifacts via PhaseSpaceStore
[optional] BenchmarkRegistry.mark_seen(dataset/artifact, seen_by="exploration")
        |
        v  writes an updated registry copy (never mutates the seed in place)
EvidenceBundleV1.make(...) -> EvidenceBundleStore.write()
```

`evidence.builder.build_evidence_bundle` is the single orchestrator for this
chain. It does not reimplement any exporter logic -- it imports and calls
the same library `export()` functions the exporters' own tests already use
(`tools.export_ds005620_pitnn_transitions.export`,
`tools.export_ds000245_fmri_transitions.export`,
`phase_space.export_from_transitions.export`), and the same
`benchmarks.export_registry.BenchmarkRegistry` the benchmark registry
milestone already built.

## Why future theory/Koopman/counterfactual/atlas modules should consume bundles

None of those modules exist yet (see
[Limitations and future work](#limitations-and-future-work)). But when they
do, reading raw `outputs/transitions/`/`outputs/phase_space/` directories
directly would silently lose two things a bundle preserves: (1) whether the
registry actually authorized this data for the use being made of it now,
and (2) whether *this exact set* of transition/coordinate artifacts has
already been marked as seen by an earlier exploratory or LLM-driven step.
Consuming `EvidenceBundleV1.registry_decisions` and `.contamination_updates`
instead of raw output directories is how a future module inherits the
discovery-vs-confirmation discipline `benchmarks/` established, without
having to re-derive it from file timestamps or tribal knowledge.

## CLI examples

```bash
# ds005620, cohort_summary feature family, with phase-space + contamination marking
python -m evidence.export_bundle \
    --dataset ds005620 --feature-set cohort_summary \
    --registry benchmarks/registry_seed.json \
    --source contracts/btc_icft/ds005620/pitnn_cohort \
    --out outputs/evidence/ds005620_cohort_summary \
    --include-phase-space --mark-seen \
    --updated-registry-out outputs/evidence/ds005620_cohort_summary/registry_updated.json

# ds005620, spatial_defect_map feature family (distinct from cohort_summary --
# see docs/transition_science_foundation.md's "Two ds005620 feature families")
python -m evidence.export_bundle \
    --dataset ds005620 --feature-set spatial_defect_map \
    --registry benchmarks/registry_seed.json \
    --source contracts/btc_icft/ds005620/pitnn_cohort \
    --out outputs/evidence/ds005620_spatial_defect_map \
    --include-phase-space

# ds000245 fMRI graph/connectivity (Schaefer-100/motion-corrected variant)
python -m evidence.export_bundle \
    --dataset ds000245 --feature-set schaefer100_motcorr \
    --registry benchmarks/registry_seed.json \
    --source contracts/fmri_tda/ds000245 \
    --out outputs/evidence/ds000245_schaefer100_motcorr \
    --include-phase-space
```

Output structure:

```
outputs/evidence/<bundle_name>/
  EvidenceBundle.json
  transitions/
    <transition_id>/TransitionRecord.json
    <transition_id>/TransitionTrajectory.csv
  phase_space/                                (only with --include-phase-space)
    <transition_id>/PhaseSpaceCoordinates.json
    <transition_id>/PhaseSpaceTrajectory.json
  registry_updated.json                       (only with --mark-seen)
```

Supported `(--dataset, --feature-set)` combinations
(`evidence.builder.DISPATCH`): `(ds005620, cohort_summary)`,
`(ds005620, spatial_defect_map)`, `(ds000245, schaefer100_motcorr)`,
`(ds000245, kmeans100)`. `ds005917` and `ds006644` have no dispatch entry --
see [Prohibited/blocked datasets](#prohibited-uses-and-blocked-datasets).

## Registry requirements

`--registry <path>` is effectively required: omitting it without also
passing `--no-registry` fails closed before reading any artifact
(`registry_path is required unless --no-registry is explicitly given`).
`--no-registry` is an explicit, named legacy/unauthorized-use escape hatch
-- a bundle built this way carries `registry_path=None` and an empty
`registry_decisions` list, so a reader always knows a bundle was built
without registry authorization.

When a registry is used, the builder checks `requested_use` (default
`transition_export`) against both the dataset record and, if a matching
`ArtifactRecordV1` exists for the selected feature set
(`evidence.builder.DISPATCH[...]["artifact_kind"]`), the artifact record
too -- and fails closed on either denial, before any file is written. If
`--include-phase-space` is given, `phase_space.export_from_transitions`
independently re-checks `phase_space_export` for the same dataset (defense
in depth: each layer enforces itself regardless of caller), and that
decision is also recorded in `registry_decisions`.

## `mark_seen` behavior

`--mark-seen` marks the dataset (and any matched artifact) as
`seen_by="exploration"` with a note identifying the bundle's
`requested_use`, via `benchmarks.split_policy.mark_seen` -- the same
mechanism `benchmarks/` already exposes, not a new contamination
vocabulary. It requires `--registry` and `--updated-registry-out`
(enforced, fails closed otherwise); the updated registry is written **only**
to the explicit output path, never back to the file at `--registry`. The
bundle owns contamination bookkeeping for the whole build: even when
`--include-phase-space` is also given, `phase_space.export_from_transitions`
is called with its own `mark_seen=False` internally, so a dataset is marked
seen once per bundle build, not once per sub-step.

## Claim/evidence ceilings

`claim_scope_ceiling`/`evidence_level_ceiling` are the *weakest* applicable
bound: when a registry is used, they start from the matched
`DatasetRecordV1`'s own ceiling fields; when `--include-phase-space` is
given, `claim_scope_ceiling` is further capped at
`phase_space.coordinate.PHASE_SPACE_MAX_CLAIM_SCOPE`
(`"exploratory_metric"`), since a phase-space coordinate can never carry a
stronger scope regardless of its source. In `--no-registry` legacy mode
there is no registry-derived bound to apply, so the ceiling defaults to the
*widest* allowed value and is narrowed only by phase-space's own hard cap
when applicable -- a narrowest-first default would make `--no-registry`
unusable, since the underlying exporters always produce
`exploratory_metric`/L2-L4 records regardless of registry involvement.
`generated_claim_scope`/`generated_evidence_levels` are the actual
weakest/observed values across every referenced `TransitionRecordV1`; a
bundle fails its own `validate()` if either exceeds its ceiling.

## Null-control honesty

`null_control_summary` is aggregated from every referenced
`TransitionRecordV1`'s own `null_control_summary.status`
(`evidence.builder._aggregate_null_control`): `"passed"` only if at least
one real per-transition status is `"passed"`; `"failed"` if any is
`"failed"`; `"not_provided"` if every one is `"not_provided"`/`"not_applicable"`;
`"mixed"` otherwise. `evidence.validation.validate_bundle` independently
re-checks this: a bundle claiming `"passed"` with no backing per-transition
`"passed"` entry, or claiming anything other than `"not_provided"` when
every per-transition entry is `"not_provided"`, fails validation.

## Limitations

- No downstream consumer exists yet -- a bundle sitting on disk is not
  itself evidence of anything beyond what its own referenced artifacts
  state.
- `evidence.builder.DISPATCH` is a fixed lookup table, not a plugin system.
  Extending to a new dataset/feature set means adding one entry and (if the
  underlying exporter doesn't already have one) an optional registry hook
  on that exporter, following the `tools.export_ds000245_fmri_transitions.py`
  / `tools.export_ds005620_pitnn_transitions.py` pattern.
- `artifact_ids` resolution is best-effort name matching
  (`ArtifactRecordV1.artifact_kind` against `DISPATCH`'s recorded kind); a
  registry that renames or omits the matching artifact record still allows
  the build to proceed on the dataset-level decision alone.
- A bundle's own `validate()` checks internal consistency (paths exist, IDs
  match, ceilings respected, no banned phrases); it does not re-validate
  the referenced `TransitionRecordV1`/`PhaseSpaceCoordinateV1` files'
  *own* structural validity beyond confirming their identity fields match
  what the bundle claims -- `evidence.builder.build_evidence_bundle`
  guarantees that at build time (both exporters raise before returning an
  invalid record), but a bundle read back later trusts the files on disk.

## Prohibited uses and blocked datasets

Per this repository's governance conventions (`benchmarks.split_policy`,
`sciencer_d.btc_icft.report_guardrails`), no `EvidenceBundleV1`, regardless
of its contents, may be used to assert a clinical diagnosis, a treatment
recommendation, a validated consciousness biomarker, spiritual/meditative
attainment, or mechanistic/causal proof -- `requested_use` values encoding
those claims are always blocked (`benchmarks.split_policy.ALWAYS_BLOCKED_USES`),
checked both by the registry before any export and again by
`EvidenceBundleV1.validate()`.

`ds005917` and `ds006644` have no `evidence.builder.DISPATCH` entry: no
code path in this package can build a bundle for either, because neither
has a committed *structured* artifact (only a prose report is committed --
see `docs/benchmark_dataset_registry.md`'s candidate/unstructured
discussion). Even bypassing `DISPATCH` and calling the registry directly,
`benchmarks/registry_seed.json` restricts both datasets to
`allowed_uses=["documentation"]`, so `transition_export`/`phase_space_export`
are denied at the registry layer independently of the dispatch table --
two independent blocks, not one.

Every free-text field on a bundle (`limitations`, `metadata`,
`null_control_summary`, `validation_summary`) is recursively scanned
against the repository's shared banned-phrase list
(`sciencer_d.btc_icft.report_guardrails.BANNED_REPORT_PHRASES` plus the
transition layer's addendum), and validation fails closed on a hit.

## Evidence report generator (first downstream consumer)

`reports/` (see `docs/evidence_report_generator.md`) is the first module to
actually consume an `EvidenceBundleV1` end to end: it turns one bundle into
a deterministic, template-based `EvidenceReportV1` (Markdown + JSON) --
executive summary, registry authorization, contamination status,
transition/phase-space counts, null-control status, claim/evidence
ceilings, explicit blocked interpretations, and reproducibility commands.
No LLM call is made; every value is copied or counted from the bundle and
its referenced artifacts, never recomputed or promoted.
`evidence.export_bundle`'s optional `--include-report`/`--report-out` flags
(added by that milestone, default off, backward-compatible) build both in
one invocation, recording `{"report_id", "generated_files"}` under
`bundle.metadata["report"]` when used. `EvidenceBundleV1`'s own schema and
`--include-phase-space`/`--mark-seen`/registry-check behavior were
otherwise unchanged.

`adapters.mne_bids` (see `docs/mne_bids_adapter.md`) is the first producer
of an `EvidenceBundleV1` that is not one of `evidence.builder.DISPATCH`'s
fixed `(dataset, feature_set)` entries -- its `--include-evidence-bundle`
flag calls a new, additive `evidence.builder.build_generic_evidence_bundle()`
function that reads already-written `TransitionRecordV1` artifacts
directly rather than calling a dataset-specific exporter, so a lab's own
`dataset_id` never needs a `DISPATCH` entry to reach this schema.
`build_evidence_bundle`'s own signature, `DISPATCH`, and behavior are
unchanged by this addition.

## Limitations and future work

**Not implemented by this milestone** (listed only to show what this
substrate is for -- none of these descriptions is a commitment to a
design): a Theory Competition Engine that would consume
`EvidenceBundleV1.registry_decisions` to decide train/test eligibility;
Koopman/DMD development-vs-validation gating keyed off bundle contamination
state; Counterfactual Reachable Sets' model-development gating; a
Phenomenology parser; a Holo-Atlas LLM interpreter that would call
`mark_seen(..., seen_by="llm")` through a bundle rather than the registry
directly; a Consciousness Atlas that would weight evidence by bundle
provenance. `tools.export_ds005620_pitnn_transitions.py` and
`tools.export_ds000245_fmri_transitions.py` are the only exporters with an
optional registry hook so far; a third dataset's exporter would need the
same pattern added before it could join `evidence.builder.DISPATCH`.
