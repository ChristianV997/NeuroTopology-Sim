# Phase Space Coordinates v1

Status: **implemented substrate, no downstream consumers yet.** This
document describes the `phase_space/` package as it exists today. It is the
first consumer of `TransitionRecordV1` (see
[`transition_science_foundation.md`](transition_science_foundation.md)).

## What a phase-space coordinate is — and is not

> A phase-space coordinate is **not a consciousness measure.** It is an
> operational summary of named, measurable transition features, carrying
> explicit provenance, confidence, missing-feature status, limitations, and
> claim scope.

Concretely, one `PhaseSpaceCoordinateV1` answers a narrow question: *given
the features this transition record actually carries, how much of the
record's total measured change is attributable to the features this
repository has grouped under axis X?* That is all. It is not a position in
any validated state space, not a level of anything, and not evidence that
the axis names correspond to real dimensions of experience.

Two properties make the layer safe to build on:

1. **It cannot invent data.** An axis is estimated only from features named
   in the record's own `feature_names`. Anything else is `insufficient_data`
   with the missing feature names listed — never an imputed or defaulted
   number.
2. **It cannot strengthen a claim.** `output_claim_scope` is the weaker of
   the source record's scope and this layer's hard ceiling
   (`exploratory_metric`). Grouping coordinates into a trajectory inherits
   the *weakest* member's scope, never the strongest.

## Position in the pipeline

```
raw EEG / fMRI  →  existing pipelines  →  TransitionRecordV1  →  PhaseSpaceCoordinateV1
                                          (transitions/)          (phase_space/)
```

**Raw pipeline output must not bypass the transition layer.** `phase_space/`
imports from `transitions/` and never reads a recording, a BIDS tree, or a
pipeline CSV directly. This keeps one governed choke point — the transition
record — where condition labels, null-control status, preprocessing
provenance, and claim scope are already established and validated.

## Axes

Nine operational axes are registered in `phase_space/axes.py`. Each declares
the exact canonical `transitions.features` names it reads. An axis is a
**grouping convention defined by this repository**, not a validated
construct.

| Axis | Source features | Confidence ceiling |
|---|---|---|
| `integration` | `connectivity.mean_plv`, `connectivity.global_efficiency`, `connectivity.degree`, `connectivity.modularity` | moderate |
| `differentiation` | `complexity.entropy`, `complexity.lz_complexity`, `topology.persistence_landscape_area`, `topology.betti1`, `topology.spatial_defect_betti1` | moderate |
| `metastability` | `dynamics.kuramoto_metastability`, `dynamics.leida_dwell_time`, `dynamics.transition_probability`, `transition.variance` | moderate |
| `accessibility_proxy` | `complexity.pcist_proxy`, `transition.hysteresis`, `transition.velocity` | **low** |
| `precision_stability_proxy` | `qc.signal_quality`, `transition.variance`, `dynamics.kuramoto_r` | **low** |
| `topological_organization` | `topology.q_abs`, `topology.q_net`, `topology.f_dress`, `topology.defect_density`, `topology.betti1`, `topology.spatial_defect_betti1`, `topology.h1_persistence`, `topology.bottleneck_distance`, `topology.persistence_landscape_area` | moderate |
| `temporal_continuity` | `transition.velocity`, `transition.acceleration`, `transition.dwell_time`, `transition.hysteresis` | moderate |
| `generative_depth_proxy` | `phenomenology.generative_depth` | **low** (placeholder) |
| `self_model_proxy` | `phenomenology.self_reference` | **low** (placeholder) |

Notes on the deliberately conservative entries:

- **`accessibility_proxy` is not a consciousness level, awareness measure, or
  responsiveness score.** It is pinned to `low` confidence unconditionally,
  because a defensible accessibility estimate would need direct
  perturbational (e.g. TMS-EEG) or behavioural-response evidence, and this
  layer has no mechanism to detect or verify either.
- **`precision_stability_proxy`** mixes recording-quality (`qc.*`) and
  neural-dynamics features, so a change in it may reflect data quality
  rather than physiology. Also pinned to `low`.
- **`generative_depth_proxy` and `self_model_proxy` are placeholders.** They
  map only to `phenomenology.*` features, which this repository does not
  produce, so they return `insufficient_data` for every record it can
  currently generate. Registering the names reserves and documents them; it
  does not imply any capacity to detect selfhood, self-awareness, or
  generative depth.
- **`integration` does not sign-flip `connectivity.modularity`,** even though
  modularity conventionally moves opposite to the other three. v1 reports
  raw per-feature contributions and lists exactly which features
  contributed, so a downstream reader applies their own convention rather
  than silently inheriting an undocumented one.

Axis names pass the same forbidden-token firewall as feature names
(`transitions.features.FORBIDDEN_NAME_TOKENS`), so no axis can be introduced
whose *name alone* asserts a clinical, diagnostic, or contemplative-attainment
claim.

## Status and confidence semantics

`status` ∈ `{estimated, insufficient_data, not_applicable, failed_validation}`

Validation enforces coherence rather than trusting the writer: a
non-`estimated` coordinate must carry `value=None` and `confidence="none"`,
and an `insufficient_data` coordinate must list its `missing_features`. A
value of `0.0` with status `estimated` is a legitimate measured result (real
zero change) and is deliberately distinguishable from missing data.

`confidence` ∈ `{none, low, moderate, high}`

| Level | When v1 assigns it |
|---|---|
| `none` | any non-`estimated` status |
| `low` | estimated — the default |
| `moderate` | estimated from **≥2** contributing features **and** the source record's null control has status `passed` |
| `high` | **never — structurally unreachable in v1** |

`high` is not merely discouraged: `assign_confidence` returns no input
combination that yields it, and a test asserts this. Justifying a
high-confidence operational coordinate would require validation work
(independent replication, a preregistered effect, perturbational or
behavioural corroboration) that this layer neither performs nor can verify.
The value exists in the schema only so a future, better-evidenced version
can use it without a schema change.

## Normalization modes

| Mode | Behaviour |
|---|---|
| `raw` | Mean of contributing signed deltas, in the source features' own mixed units. Unbounded; not comparable across features or datasets. |
| `within_record` (default) | Signed share of the record's total absolute feature-change mass: `sum(contributing) / sum(abs(all))`. **Bounded to [-1, 1] by construction**, with no clamping, since `abs(sum(contributing)) ≤ sum(abs(contributing)) ≤ sum(abs(all))`. Not comparable across records with different feature sets. |
| `zscore_if_available` | Z-scores against an explicit external reference distribution supplied at `metadata.feature_reference_stats`. No transition record in this repository currently carries one, so in practice this returns `insufficient_data` — the honest answer, never a silent fallback to another mode. |

A record whose features all show exactly zero change returns
`insufficient_data` under `within_record`, because a share of zero total
change is undefined rather than zero.

## Usage

```bash
# from a TransitionStore directory (one subdirectory per transition)
python -m phase_space.export_from_transitions \
    --input outputs/transitions/ds005620_pitnn \
    --out outputs/phase_space/ds005620_pitnn \
    --normalization-mode within_record

# or from a single record file
python -m phase_space.export_from_transitions \
    --input outputs/transitions/ds005620_pitnn/<transition_id>/TransitionRecord.json \
    --out outputs/phase_space/one_record

# optional: restrict axes, skip the trajectory artifact
python -m phase_space.export_from_transitions \
    --input outputs/transitions/ds005620_pitnn \
    --out outputs/phase_space/topology_only \
    --axes topological_organization differentiation \
    --no-trajectory
```

Output layout, mirroring `TransitionStore`'s conventions:

```
<out>/<transition_id>/PhaseSpaceCoordinates.json
<out>/<transition_id>/PhaseSpaceTrajectory.json   (unless --no-trajectory)
```

The CLI fails closed with a clear message and exit code 1 if the input path
is missing, contains no `TransitionRecord.json`, or holds only unreadable
records. Its summary reports transitions read, coordinates estimated,
`insufficient_data` counts, and the output path.

### Programmatic use

```python
from phase_space import estimate_axis, estimate_coordinates

coord = estimate_axis(record, "topological_organization",
                      normalization_mode="within_record")
coords = estimate_coordinates(record)  # all registered axes
```

## Deterministic identity

`coordinate_id = sha256[:16]` over exactly `(transition_id, axis,
estimator_version, normalization_mode)`. It excludes `created_at`, the
computed value, confidence, and all free text — none of those change *which*
coordinate is being described. Re-running an unchanged estimator on an
unchanged record always reproduces the same ID; bumping `ESTIMATOR_VERSION`
deliberately produces new IDs rather than silently overwriting old ones.

`PhaseSpaceTrajectoryV1` gets an analogous, order-insensitive
`trajectory_id` over its source transition IDs, axes, normalization mode,
and estimator version.

## Trajectories

`PhaseSpaceTrajectoryV1` is a **container, not an analysis**. v1 performs no
interpolation, smoothing, curve fitting, or dynamical modelling; it groups
coordinates so a later consumer has one addressable artifact. It inherits
the weakest claim scope and evidence level among its coordinates, and flags
in its own limitations when its members span multiple datasets.

## Limitations

- Axis membership is a repository convention, not a validated construct. A
  feature belongs to an axis because this repository grouped it there.
- `within_record` values are shares of a record's own change mass and are
  **not comparable across records** with different feature sets. Comparing
  them across datasets is not supported by this layer.
- Most real coordinates derive from two-point condition-summary
  trajectories, so they reflect an endpoint contrast rather than continuous
  dynamics. Affected coordinates say so in their own `limitations`.
- Sign and magnitude carry no valence. Neither direction indicates a better,
  healthier, deeper, or more conscious state.
- No axis has been validated against any external criterion, and this layer
  performs no statistical testing of its own — it inherits whatever
  null-control status the source transition record reported.
- Only one estimator (`delta_share_v1`) exists; it reads `delta_summary` and
  ignores the trajectory CSV's full time course even when one is present.

## Second modality smoke: ds000245 fMRI graph/connectivity

The examples above use ds005620 EEG records. This section documents running
the same, unmodified `phase_space.export_from_transitions.export()` over
`tools/export_ds000245_fmri_transitions.py`'s real, non-EEG output — a smoke
test for whether this layer generalizes beyond the modality it was built
against. See
[the transition-layer doc's fMRI integration section](transition_science_foundation.md#second-modality-integration-fmri-graphconnectivity-transitions)
for how those records are produced; this section covers only what
phase-space estimation does with them.

```bash
python tools/export_ds000245_fmri_transitions.py \
    --input contracts/fmri_tda/ds000245 \
    --out outputs/transitions/ds000245_fmri \
    --write-phase-space-smoke outputs/phase_space/ds000245_fmri
```

On the real committed artifact this produces 3 cohort-level group-contrast
records (CTL→ODN, CTL→ODP, ODN→ODP) and, from them, 27 coordinates (9 axes ×
3 records):

| Axis | Status on these records | Why |
|---|---|---|
| `integration` | `estimated`, confidence `moderate` | `connectivity.global_efficiency` / `connectivity.degree` / `connectivity.modularity` are all present; each contrast's null-control status is `passed` (real permutation p < 0.05) and ≥2 features contribute, which is exactly `assign_confidence`'s condition for `moderate` |
| `differentiation`, `topological_organization` | `insufficient_data` | mapped to the canonical `topology.betti1` / `topology.spatial_defect_betti1` / `topology.persistence_landscape_area` family in `phase_space/axes.py`; the exported `topology.fmri_graph_betti0/betti1/h1_total_persistence` names are deliberately distinct (see the transition-layer doc) and are not in that list |
| `metastability`, `accessibility_proxy`, `precision_stability_proxy`, `temporal_continuity`, `generative_depth_proxy`, `self_model_proxy` | `insufficient_data` | none of their mapped source features (`dynamics.*`, `phenomenology.*`, etc.) exist in this feature family |

This is the intended behavior, not a gap discovered and left unfixed: per
this milestone's brief, no new phase-space formula or axis-membership change
was made to make more axes "light up" for this dataset — an axis either has
a genuine source feature or it honestly reports `insufficient_data`.
`output_claim_scope` never exceeds the source records' `exploratory_metric`
input scope, `confidence` never exceeds `moderate`, and 0 of the 27
coordinates fail validation. `tests/test_export_ds000245_fmri_transitions.py`
asserts this behavior (the `integration` estimate, the two topology axes'
`insufficient_data` status, and the claim-scope non-promotion) directly
against a small fixture, not just the real artifact.

## Prohibited interpretations

Per this repository's governance conventions (`AGENTS.md`,
`sciencer_d/btc_icft/report_guardrails.py`), no `PhaseSpaceCoordinateV1`,
regardless of value or confidence, may be used to assert: a clinical
diagnosis; a treatment recommendation; a validated biomarker; consciousness
detection or a consciousness level; anesthesia-depth clinical assessment; a
psychiatric diagnosis; meditation-stage, jhāna, or cessation detection;
enlightenment or spiritual-attainment inference; mechanistic proof; causal
inference from correlation; or that an LLM's interpretation of a coordinate
constitutes scientific evidence.

Every free-text field on a coordinate and trajectory is recursively scanned
against the repository's single source of truth for banned overclaim
language (`report_guardrails.BANNED_REPORT_PHRASES` plus the transition
layer's addendum), and validation fails closed on a hit.

## Benchmark dataset registry (optional, upstream of this layer)

This layer trusts whatever `TransitionRecordV1` it is given; it has no
notion of whether the *dataset* behind that record has already been
explored elsewhere. `benchmarks/` (see `docs/benchmark_dataset_registry.md`)
adds that upstream check, entirely outside this package: a future
consumer of `PhaseSpaceCoordinateV1` that needs to know whether a
coordinate's source dataset is discovery-stage or locked for confirmatory
validation should consult `benchmarks.split_policy.can_use_dataset`/
`can_use_artifact` before treating a coordinate as independent evidence.
No `phase_space/` code was changed by that milestone.

## Future consumers

The following are **not implemented** by this milestone. They are listed
only to show what this substrate is for; none of these descriptions is a
commitment to a design.

- **Theory Competition Engine** — would score competing theoretical
  predictions against the same coordinate population.
- **Koopman/DMD analysis** — would fit linear operators over coordinate
  sequences, which is why trajectories keep their source transition IDs.
- **Counterfactual Reachable Sets** — would ask which coordinate regions are
  reachable from which, generalizing the hysteresis-style features.
- **Phenomenology system** — would populate the `phenomenology.*` features
  that `generative_depth_proxy` and `self_model_proxy` currently wait on.
- **Holo-Atlas interpreter** — would read coordinates as input context for a
  natural-language summary; per the governance rules above, an LLM's output
  about a coordinate is never itself promoted to evidence.
- **Consciousness Atlas** — would aggregate coordinates across datasets,
  gated by each coordinate's own claim scope rather than a global claim.
