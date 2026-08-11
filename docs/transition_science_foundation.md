# Transition Science Foundation

Status: **implemented substrate, no downstream consumers yet.** This
document describes the `transitions/` package as it exists today. It does
not describe, and should not be read as promising, any of the future
modules listed in [Future consumers](#future-consumers) — those are
explicitly out of scope for this milestone.

## Why transitions, not conditions

Most of this repository's existing pipelines are organized around
**condition comparison**: awake vs. sedated, drug vs. placebo, baseline vs.
experience, wake vs. N2/N3/REM. That framing is scientifically sound for a
single two-arm contrast, but it does not compose. Every new contrast needs
its own ad hoc pair of labels, its own script, and its own report, and nothing
in the repository durably records the shape of the change itself — how fast
a subject moved from one state to another, whether the change was
recoverable, how confident the state labels were, what evidence level backs
the claim.

The `transitions/` package reorganizes around the **transition** as the
first-class object instead: one canonical `TransitionRecordV1` per observed
or hypothesized source-state → target-state change, carrying its own
trajectory, provenance, governance, and limitations. A condition comparison
is then just the special case of a transition record with a well-labeled
`source_state`/`target_state` pair — but the same schema also covers
unlabeled exploratory transitions, cohort-level aggregates, and transitions
observed in modalities that don't yet exist in this repository, without
inventing a new ad hoc format each time.

This is **infrastructure for future work**, not a new empirical claim.
Building `TransitionRecordV1` does not itself say anything about
consciousness, anesthesia depth, or meditative attainment — it says how to
*durably represent* an observed change so that future analysis can consume
it consistently.

## Relationship to existing repository infrastructure

This package is additive. It does not replace or duplicate:

- **`runs/run_record.py` (`RunRecordV1`)** — the canonical *pipeline run*
  artifact ("this pipeline executed, here's what it produced").
  `TransitionRecordV1` is the canonical *state-transition* artifact ("this
  state change was observed/hypothesized, here's its trajectory"). A single
  pipeline run can produce zero, one, or many transition records; the two
  schemas are siblings, not a hierarchy, and deliberately share the same
  `to_dict`/`from_dict`/`to_json`/`from_json`/deterministic-ID conventions
  so they feel familiar side by side.
- **`research_runtime/`** — a tightly-coupled toolkit built for one specific
  preregistered campaign (the DS003969 state-transition development
  protocol): `protocol.py`'s `ProtocolSpec`, `stage_policy.py`'s
  single-use `StageLock` for confirmatory/external stage gating,
  `envelope.py`'s write-once `RunEnvelope` (which already reserves a
  `transition_operators.json` slot for that protocol's Markov-operator
  output), `feature_adapter.py`'s real-EEG window enrichment, and
  `transitions.py`'s k-means state-fitting + discrete Markov transition
  operators (`fit_feature_state_model`, `transition_operator`,
  `operator_metrics`, `jensen_shannon_distance`). That module computes
  *aggregate* transition-matrix statistics for one campaign; it never
  materializes an individual state-to-state edge as its own durable,
  governance-scoped artifact. `transitions.TransitionRecordV1` fills
  exactly that gap and is deliberately modality- and campaign-agnostic —
  any pipeline's per-window metric CSV can be exported into one, not just
  DS003969's.
- **`sciencer_d/btc_icft/ontology/`** — the DS005620 M/T/C/Q/O label-contract
  promotion ladder (`ClaimScope`: `engineering_runtime` →
  `ontology_candidate`/`rejected`, `PromotionState`). That vocabulary
  encodes a specific claim-promotion pipeline for one dataset's marker→
  topology→substrate→theory→ontology bridge claims. This package's
  `claim_scope`/`evidence_level` vocabulary (below) is deliberately
  different and narrower — scoped to *transition artifacts specifically* —
  and is not a substitute for that ontology system. What this package does
  reuse is `sciencer_d.btc_icft.report_guardrails.BANNED_REPORT_PHRASES`
  and `validate_safe_text`, the repo's single source of truth for banned
  overclaim language, rather than declaring a fifth copy of that phrase
  list (three others already existed before this package:
  `sciencer_d/btc_icft/ontology/safe_language.py`,
  `tools/validate_ontology_claim_language.py`,
  `tools/check_claim_guardrails.py`).

## The canonical object: `TransitionRecordV1`

`transitions.record.TransitionRecordV1` is a stdlib-only dataclass. Its
fields fall into six groups:

| Group | Fields |
|---|---|
| Identity | `dataset_id`, `subject_id`, `session_id`, `record_level`, `modality`, `source_state`, `target_state` |
| Description | `transition_class`, `time_axis`, `feature_names`, `intervention` |
| Data | `trajectory_artifact`, `delta_summary`, `velocity_summary`, `duration` |
| Provenance | `preprocessing_provenance`, `repo_commit`, `created_at` |
| Governance | `claim_scope`, `evidence_level`, `null_control_summary`, `state_label_confidence`, `limitations` |
| Storage/extension | `artifact_paths`, `metadata`, `transition_id`, `schema_version` |

### Deterministic IDs

`transition_id` is a `sha256[:16]` over exactly seven fields — `dataset_id`,
`subject_id`, `session_id`, `source_state`, `target_state`, `modality`, and
the sorted `feature_names` set — mirroring `runs.run_record.build_run_id`'s
"stable hash excludes `created_at` and artifact paths" convention. Two
records built from identical values for those seven fields always get the
same ID, regardless of what else differs (`transition_class`, `limitations`
text, `claim_scope`, timestamps, ...); changing any one of the seven always
changes it. `record.validate()` recomputes the ID and flags a mismatch, so a
hand-edited or corrupted `transition_id` field is caught rather than
silently trusted.

### Validation is fail-closed

`record.validate()` returns a list of error strings (never raises directly;
`validate_or_raise()` wraps it) and enforces, among other rules:

- `dataset_id` is always required.
- `source_state`/`target_state` are required *unless* `claim_scope` is
  `computational_artifact` or `exploratory_metric` — the claim scope itself
  is the "this is an explicitly unlabeled exploratory transition"
  declaration; there is no separate boolean flag to forget to set.
  `dataset_specific` and `cross_subject_dataset_specific` always require
  both states.
- `record_level="cohort"` records must not carry a `subject_id`;
  `record_level="subject"` records must.
- `limitations` must be non-empty.
- All feature names must pass `transitions.features` namespace validation.
- All claim/evidence/null-control rules from `transitions.governance` (next
  section).

## Feature namespace (`transitions.features`)

Every feature name is `namespace.local_name`. Ten namespaces are allowed:
`spectral`, `topology`, `connectivity`, `dynamics`, `complexity`, `qc`,
`transition`, `phenomenology`, `phase_space`, `experimental`. A starter
registry of ~35 canonical names (e.g. `topology.q_net`,
`connectivity.mean_plv`, `spectral.alpha_power`,
`complexity.pcist_proxy`) is guaranteed to pass; new names under a *known*
namespace also pass (namespace membership is the real gate, not an
exhaustive name allowlist — new metrics shouldn't require editing this file
every time). Non-namespaced names and unknown namespaces always fail.
Independent of namespace, any name containing a diagnosis/treatment/
clinical/biomarker/consciousness-detection/jhāna/cessation/enlightenment/
spiritual-attainment token (Unicode-normalized, so `jhāna` and `jhana` are
both caught) fails outright — a feature can never *name itself* into a
claim its data can't support. `experimental.*` passes structurally here;
`transitions.governance` is what caps its claim scope.

## Governance (`transitions.governance`)

Four claim scopes are allowed for this milestone's automated validator:
`computational_artifact`, `exploratory_metric`, `dataset_specific`,
`cross_subject_dataset_specific`. Nine are always blocked, regardless of
evidence supplied: `clinical`, `diagnostic`, `treatment`,
`consciousness_biomarker`, `mechanistic_causal`, `spiritual_attainment`,
`enlightenment_detection`, `jhana_detection`, `cessation_detection`. Any
other string fails closed as "not a recognized scope" rather than being
silently accepted.

Five evidence levels exist, from weakest to strongest claim:
`L0_computational_artifact`, `L1_synthetic_validation`,
`L2_single_subject_real_signal`, `L3_dataset_specific_effect`,
`L4_cross_subject_dataset_specific`. `dataset_specific` additionally
requires `dataset_id`, both states, and a non-`None` `state_label_confidence`;
`cross_subject_dataset_specific` requires either `record_level="cohort"` or
an explicit `metadata.subject_count >= 2` — cohort evidence has to be
*stated*, not inferred from the absence of a subject ID.

**Null-control status is never silently "passed."** `null_control_summary`
defaults to `{"status": "not_provided"}` (never `None`), and the four valid
statuses — `not_provided`, `not_applicable`, `failed`, `passed` — are
explicit and mutually exclusive. A record with no null-control status field
at all fails validation; it cannot be misread as a passing control.

Finally, every free-text field (`limitations`, `metadata`, `transition_class`,
`intervention`, `preprocessing_provenance`) is recursively scanned against
`sciencer_d.btc_icft.report_guardrails.BANNED_REPORT_PHRASES` plus a small
transition-specific addendum (`jhana detected`, `cessation detection`,
`spiritual attainment`, `mechanistic proof`, `validated biomarker`, ...).

## Trajectory metrics (`transitions.metrics`)

Eight generic, modality-agnostic functions operate on plain numeric
arrays/lists: `trajectory_mean_delta`, `transition_velocity`,
`transition_acceleration`, `transition_variance`, `dwell_time_summary`,
`hysteresis_summary`, `label_balance_check`, `subject_pairing_check`. None
of them interpret what a feature *means* — they compute endpoint deltas,
first/second differences, run-length dwell statistics, and forward/backward
path divergence, and nothing else. Malformed input (empty, ragged, NaN)
raises `ValueError` with a specific message. Genuinely insufficient data
(fewer than 3 timepoints for acceleration, no recovery leg for hysteresis,
no overlapping subjects for pairing) returns an explicit
`{"status": "insufficient_data", "reason": ...}` dict rather than a
fabricated number — this is the same "never silently substitute a plausible
value for a missing one" discipline the null-control status field enforces.

## Storage (`transitions.store.TransitionStore`)

One directory per `transition_id`, following the naming convention already
established by `sciencer_d.btc_icft.runtime.snapshots.ScienceRuntimeSnapshotStore`
(`write`/`read`/`list`). `TransitionStore(root).write(record, trajectory=...)`
writes `TransitionRecord.json` and, if a trajectory is given,
`TransitionTrajectory.csv`, updating `record.trajectory_artifact` and
`record.artifact_paths["trajectory"]` first so the two files stay
consistent. No database dependency; every method is a handful of lines over
`pathlib`/`json`/`csv`.

## Exporting from existing outputs

```bash
python -m transitions.export_from_results \
    --dataset ds005620 \
    --input outputs/pitnn_cohort/ds005620/subjects/sub-1010.json \
    --out artifacts/transitions/ds005620 \
    --source-state awake --target-state sedated \
    --transition-class anesthesia_induction \
    --modality eeg \
    --subject sub-1010
```

The exporter reads a flat CSV or JSON table (one row per timepoint/window,
file order assumed to be time order), maps recognizable column names (e.g.
`q_net`, `mean_plv`, `alpha_power`) onto the canonical feature namespace via
a fixed alias table generated from `transitions.features.CANONICAL_FEATURES`
itself (so the two can't drift), and skips any column it can't unambiguously
classify rather than guessing. If *no* columns can be classified, or the
input file is malformed, it fails closed with a specific error and writes
nothing. `--source-state`/`--target-state`/`--transition-class`/`--modality`
are required arguments — state labels are never inferred from filenames,
column values, or metric values. Defaults are deliberately conservative:
`claim_scope=computational_artifact`, `evidence_level=L0_computational_artifact`,
`null_control_summary={"status": "not_provided"}` (this exporter never reads
null/surrogate data). Every exported record's `limitations` explicitly state
that it is "not a validated consciousness biomarker, clinical assessment, or
diagnostic output."

## First real-output integration: ds005620 PITNN/cohort topology

The generic exporter above (`transitions.export_from_results`) is
demonstrated on synthetic fixtures only. This section documents a second,
concrete exporter — `tools/export_ds005620_pitnn_transitions.py` — that
consumes a **real, already-computed, git-committed** repository artifact and
proves the transition layer is not merely a synthetic test package.

**Exporter added**: `tools/export_ds005620_pitnn_transitions.py`, a
standalone tool (not a flag on the analysis script that produces the source
artifact, to avoid conflating "re-run the cohort analysis" with "convert its
already-written output" — the exporter never re-runs
`tools/analyze_pitnn_cohort_ds005620.py` or touches raw EEG data).

**Input artifact it consumes**: `contracts/btc_icft/ds005620/pitnn_cohort/`
— `cohort_summary.json`, `cohort_per_subject.csv`, `pairing.json`,
`RunRecord.json`. This directory is committed to the repository (unlike
`outputs/`, which is gitignored), produced by
`tools/analyze_pitnn_cohort_ds005620.py` from
`tools/stream_pitnn_cohort_ds005620.py`'s per-subject EEG topology output
for the real, 20-subject ds005620 propofol cohort (schema
`NeuroTopologySim.DS005620PITNNCohort.v1`). The exporter validates this
schema tag before parsing anything else and fails closed on a mismatch.

**Records it emits**: one `TransitionRecordV1` per subject with a paired
awake/sedated row in `cohort_per_subject.csv` (20 for the real committed
cohort), plus one cohort-level record built from the same artifact's
per-feature subject-median statistics (`topology_tests.*.paired_wilcoxon_subject_means`).
Three features are mapped onto the canonical namespace, matching
`tools/analyze_pitnn_cohort_ds005620.py`'s own `_METRICS` tuple exactly:

| Source column | Canonical feature |
|---|---|
| `awake_landscape_area` / `sedated_landscape_area` | `topology.persistence_landscape_area` |
| `awake_beta1` / `sedated_beta1` | `topology.betti1` (a per-condition **mean** across `windows_per_condition` windows — fractional, not a single-window integer count; documented in `preprocessing_provenance.betti1_definition`) |
| `awake_mean_plv` / `sedated_mean_plv` | `connectivity.mean_plv` |

Each record's two-point trajectory (`awake` → `sedated`) is written through
`transitions.store.TransitionStore`, both as `TransitionRecord.json` and a
2-row `TransitionTrajectory.csv`; `delta_summary`/`velocity_summary` are
computed via the existing `transitions.metrics` functions, unmodified.
`bayes_factor`/`verdict` (PITNN-specific, not a canonical transition
feature) and the subject's real source file paths (from `pairing.json`) are
preserved in `metadata`, not silently dropped.

**Claim scope and evidence-level policy**: every record — subject-level and
cohort-level — uses `claim_scope="exploratory_metric"`, per this milestone's
instruction and because the source artifact's own conclusion (PITNN
`NOT_SUPPORTED` for all 20 subjects; none of the three subject-blocked
permutation tests reached p < 0.05) does not support a stronger scope.
`evidence_level` differs by record level, reflecting evidentiary *strength*
of the underlying data, not a claim-scope escalation:
`L2_single_subject_real_signal` for subject records, and
`L4_cross_subject_dataset_specific` only for the cohort record, which
carries `metadata.subject_count` from the artifact's real
`n_paired_subjects` field (20 in the committed cohort — never a fabricated
count).

`null_control_summary` is set **honestly per record, from real data, not
hardcoded**: subject-level records have no per-subject null-control test in
the source artifact, so their status is `not_provided`. The cohort record's
status is computed dynamically from the source's own
`subject_blocked_permutation` p-values (`method:
permutation_test_subject_blocked_paired`, real p-values/effect sizes for
all three exported features, embedded verbatim in `per_feature`) against
α = 0.05 — `"failed"` if none reach significance, `"passed"` if at least one
does. For the real committed cohort artifact today, this evaluates to
`"failed"` (p = 0.075, 0.44, 0.27 for the three features) — the exporter
does not soften or reinterpret that outcome. MixedLM p-values on the same
data are smaller for two features but are recorded only informationally
under `metadata.additional_statistics`, never substituted into
`null_control_summary`, to avoid presenting the more favorable test as the
null control.

**What it does not claim**: no clinical, diagnostic, treatment, biomarker,
mechanistic-causal, or consciousness-detection interpretation. Every
record's `limitations` state explicitly that it is an exploratory EEG
topology artifact exported from an existing analysis output (no raw data
reprocessed), that condition labels are inherited from the source and not
independently re-verified, that `velocity_summary` reflects a two-point
condition-summary trajectory rather than a continuously sampled time
series, and (per subject/cohort) the real PITNN verdict and Bayes-factor
context so a reader cannot mistake the transition record for confirmation
of the anesthesia hypothesis.

**How to run it**:

```bash
python tools/export_ds005620_pitnn_transitions.py \
    --input contracts/btc_icft/ds005620/pitnn_cohort \
    --out outputs/transitions/ds005620_pitnn
```

Fails closed with a clear message if `--input` doesn't exist, if
`cohort_summary.json`/`cohort_per_subject.csv` is missing or has an
unrecognized schema tag, if the CSV has no rows, or if every subject row is
malformed (a single malformed subject row is skipped with an explicit
reason in the printed summary and in the returned `skipped` list, rather
than failing the whole export — but the export still fails if *zero*
subjects can be exported). Re-running is deterministic: the same input
always produces the same `transition_id`s.

**Fixtures vs. real output**: the exporter's tests
(`tests/test_export_ds005620_pitnn_transitions.py`) use small, 1–2-subject
synthetic fixtures modeled on the *shape* of the real committed artifact —
not the real 20-subject data — so the test suite stays fast and
self-contained. No new empirical result is produced or implied by these
fixtures; the real, 20-subject export (verified manually during this
integration, not re-asserted in the fast test suite) reads the actual
committed `contracts/btc_icft/ds005620/pitnn_cohort/` files already in the
repository, so no local dataset generation or raw-data re-fetch is required
to reproduce it.

**Future work** (as of the initial `cohort_summary` integration): extend
this pattern to the `spatial_defect_map` per-subject `qabs`/`beta1` series
in the same `cohort_summary.json` -- **done, see the next section** -- and
to `outputs/pitnn_cohort/ds005620/subjects/*.json`'s per-window feature
vectors (still gitignored, so any such exporter's tests would still need
fixtures); reuse this exporter's mapping/governance pattern for other
datasets' committed cohort artifacts once they exist remains open.

### Two ds005620 feature families: cohort_summary vs. spatial_defect_map

`cohort_summary.json` contains **two real, differently-computed feature
families**, both exportable via the same tool
(`tools/export_ds005620_pitnn_transitions.py --feature-set <name>`):

| `--feature-set` | Source location | Features | Method |
|---|---|---|---|
| `cohort_summary` (default) | `cohort_per_subject.csv` + `topology_tests.*` | `topology.persistence_landscape_area`, `topology.betti1`, `connectivity.mean_plv` | Windowed persistent cubical homology, averaged across `windows_per_condition` windows per condition |
| `spatial_defect_map` | `cohort_summary.json['spatial_defect_map']` | `topology.q_abs`, `topology.spatial_defect_betti1` | Spatial defect/vortex counting in a single condition snapshot |

**Why this split matters**: both families independently produce a
"beta1"-named quantity in the raw source data --
`cohort_per_subject.csv`'s `{awake,sedated}_beta1` (fractional, e.g. 1.333,
because it is a *mean across 3 windows*) and
`spatial_defect_map.per_subject[].{awake,sedated}_beta1` (small integers,
e.g. 2, 4, because it is a *single-snapshot spatial count*). These are
genuinely different topological measurements that happen to share a short
name in the source data. Exporting both under the canonical feature name
`topology.betti1` would silently conflate them for any downstream reader
that only inspects `feature_names` — exactly the failure mode this
milestone exists to prevent. The fix applied:

1. **Different canonical feature names.** `topology.betti1` (cohort_summary)
   vs. `topology.spatial_defect_betti1` (spatial_defect_map) — both valid
   `topology.*` names per `transitions.features` (new names under a known
   namespace need no registry change), but textually and namespace-locally
   distinct, so a reader of bare `feature_names` cannot conflate them even
   without reading further metadata. `topology.q_abs` needed no renaming:
   it only appears in `spatial_defect_map`, so it is already unambiguous.
2. **`metadata.feature_definitions`** on every record (both feature sets):
   an exact, source-specific prose definition of each exported feature name,
   including an explicit cross-reference telling a reader which *other*
   feature set's similarly-named quantity it is not the same as.
3. **`metadata.feature_set_id`** (`"ds005620_pitnn_cohort_summary"` or
   `"ds005620_spatial_defect_map"`) on every record — an explicit, greppable
   tag identifying which feature family produced it, independent of
   `feature_names` and never mutated after export.
4. **No new first-class `TransitionRecordV1` field.** A `feature_set_id`
   field on the schema itself, or in the deterministic-ID basis, was
   considered per this milestone's brief and rejected: the two feature
   sets already use fully disjoint `feature_names`
   (`{persistence_landscape_area, betti1, mean_plv}` vs.
   `{q_abs, spatial_defect_betti1}`), and `transitions.record.compute_transition_id`'s
   basis already includes `feature_names` — so `transition_id` can never
   collide between them for the same subject/dataset/session/state/modality,
   with **no schema change and no risk to existing IDs**. This was verified
   directly: exporting the real committed cohort produces the *same*
   `cohort_summary` cohort `transition_id` (`e59e1431abd38f12`) as before
   this milestone, and a *different*, non-colliding
   `spatial_defect_map` cohort `transition_id`
   (`2e7230df10b9154c`). `tests/test_export_ds005620_spatial_defect_transitions.py`
   asserts this non-collision property directly, per-subject and at the
   cohort level, not just for the specific two IDs above.

**Cohort-level asymmetry, faithfully preserved, not smoothed over**: the
source artifact reports a cohort-level aggregate (`mean_qabs_awake`/
`mean_qabs_sedated` + a paired Wilcoxon test) for `q_abs`, but *no*
cohort-level aggregate for the spatial defect count. Rather than compute one
by averaging the per-subject integers ourselves — which the source artifact
itself does not assert — the `spatial_defect_map` cohort record's
`feature_names` is `["topology.q_abs"]` only;
`topology.spatial_defect_betti1` appears in subject-level records but is
never given a fabricated cohort summary.

**Null-control honesty across a subtler case**: `spatial_defect_map`'s only
cohort-level statistical test is a plain paired Wilcoxon signed-rank test
(`paired_wilcoxon_qabs`), not a permutation/surrogate-based null-control
test like `cohort_summary`'s `subject_blocked_permutation`. These are not
the same evidentiary category — a permutation test constructs an empirical
null by shuffling condition labels; a Wilcoxon test does not. The exporter
does not relabel the Wilcoxon result as a null control to give this feature
set a `"passed"`/`"failed"` verdict it doesn't have evidence for;
`null_control_summary.status` is `"not_provided"` for every
`spatial_defect_map` record, and the Wilcoxon result is preserved,
unrelabeled, in `metadata.additional_statistics.paired_wilcoxon_qabs`.

**How to run each feature set**:

```bash
python tools/export_ds005620_pitnn_transitions.py \
    --input contracts/btc_icft/ds005620/pitnn_cohort \
    --out outputs/transitions/ds005620_pitnn \
    --feature-set cohort_summary   # default; --feature-set may be omitted

python tools/export_ds005620_pitnn_transitions.py \
    --input contracts/btc_icft/ds005620/pitnn_cohort \
    --out outputs/transitions/ds005620_spatial_defect_map \
    --feature-set spatial_defect_map
```

**Claim scope / evidence level for `spatial_defect_map`**: identical policy
to `cohort_summary` — `claim_scope="exploratory_metric"` for every record;
`evidence_level="L2_single_subject_real_signal"` per subject and
`"L4_cross_subject_dataset_specific"` only for the cohort record (real
`metadata.subject_count` from the source's `n_subjects`).

**What remains future work**: `spatial_defect_map`'s spatial defect
positions/coordinates themselves (not just the per-condition Q_abs/count
summaries) are not exported here; a richer spatial-trajectory record would
need a dedicated `topology.spatial_defect_*` sub-namespace decision beyond
this milestone's scope. `outputs/pitnn_cohort/ds005620/subjects/*.json`'s
per-window vectors remain unexported (gitignored, would need fixtures).

## Extension guidelines

- **Adding a feature**: if it fits an existing namespace, just use it —
  `transitions.features` does not need editing for new names under a known
  namespace. Add it to `CANONICAL_FEATURES` only if it should also gain a
  ready-made CSV column alias in the exporter.
- **Adding a claim scope or evidence level**: do not add ad hoc new values
  by editing a record's `claim_scope` string in place. Extending
  `ALLOWED_CLAIM_SCOPES`/`ALLOWED_EVIDENCE_LEVELS` is a governance decision,
  not a data decision — it belongs in a PR that explicitly discusses why
  the new scope's requirements are adequate, following the same discipline
  `sciencer_d/btc_icft/ontology/evidence.py`'s evidence-requirement matrix
  already uses for its own promotion ladder.
- **Adding a new pipeline's export path**: prefer calling
  `transitions.export_from_results.export()` (the library function, not
  just the CLI) directly from the pipeline once its metric output already
  exists as a CSV/JSON, rather than hand-building a `TransitionRecordV1`
  from scratch — the alias table and column-inference logic are meant to be
  reused.
- **Stage-gating a transition record**: if a transition record needs to be
  produced only after a `research_runtime.stage_policy.StageLock` is
  consumed (e.g. for a confirmatory-stage claim), gate the *export call*,
  not the schema — `TransitionRecordV1` itself has no opinion about stage
  gating.

## Limitations of this milestone

- No downstream consumer exists yet. A `TransitionRecordV1` sitting on disk
  is not, by itself, evidence of anything beyond what its own
  `claim_scope`/`evidence_level`/`limitations` state.
- The exporter's feature-column inference is heuristic (name-matching, not
  semantic). It will silently skip a genuinely relevant column whose name
  doesn't match the alias table rather than guess wrong — this trades
  completeness for safety, but does mean an export can be less complete
  than the source file.
- `hysteresis_summary`'s forward/backward comparison collapses each leg to
  a single mean-across-features scalar path before comparing; it is a
  coarse structural indicator, not a per-feature analysis.
- `dwell_time_summary` is sample-count-based by default; converting to
  seconds requires the caller to supply a uniform `sample_duration_s` — it
  does not handle non-uniform sampling.
- This package has not been wired into any existing pipeline's output path
  (`dual_engine/fmri_tda_pipeline.py`, the `sciencer_d/btc_icft` streamers,
  `research_runtime/`'s own campaign scripts, ...). Doing so is future
  work, deliberately not part of this milestone.

## Prohibited interpretations

Per this repository's governance conventions (`AGENTS.md`, `sciencer_d/
btc_icft/report_guardrails.py`), no `TransitionRecordV1`, no matter its
`evidence_level`, may be used to automatically assert: a clinical diagnosis;
a treatment recommendation; a validated biomarker; consciousness detection;
anesthesia-depth clinical assessment; a psychiatric diagnosis; meditation-
stage, jhāna, or cessation detection; enlightenment or spiritual-attainment
inference; mechanistic proof; causal inference from correlation; or that an
LLM's interpretation of a record constitutes scientific evidence. The
`clinical`/`diagnostic`/`treatment`/`consciousness_biomarker`/
`mechanistic_causal`/`spiritual_attainment`/`enlightenment_detection`/
`jhana_detection`/`cessation_detection` claim scopes exist specifically so
that any code path attempting one of these fails validation rather than
silently producing a record that reads as though it supports the claim.

## Future consumers

The following systems are **not implemented** by this milestone. They are
listed here only to show what a canonical transition substrate is *for* —
none of the descriptions below should be read as a commitment to a
particular design, only as the reason this schema was built the way it was.

- **Consciousness Phase Space** — would consume many `TransitionRecordV1`s'
  `delta_summary`/`velocity_summary`/`feature_names` to embed states in a
  shared coordinate system across datasets.
- **Theory Competition Engine** — would score competing theoretical
  predictions against the same `TransitionRecordV1` population rather than
  against ad hoc per-dataset comparisons.
- **Koopman/DMD analysis** — would fit linear operators to trajectory data
  read via `TransitionStore.read_trajectory`, treating each record's
  trajectory CSV as one training example.
- **Counterfactual Reachable Sets** — would use `hysteresis_summary`-style
  forward/backward divergence, generalized across many records, to ask
  which states are reachable from which.
- **Phenomenology system** — would attach first-person report data to a
  transition record via the already-reserved `phenomenology.*` feature
  namespace, without conflating it with the physiological measurements in
  other namespaces.
- **Holo-Atlas LLM interpreter** — would read `TransitionRecordV1.to_dict()`
  as *input context* for a natural-language summary, but per the governance
  rules above, an LLM's output about a record is never itself promoted to
  evidence within the record.
- **Consciousness Atlas** — would aggregate `TransitionStore.read_all()`
  across datasets into a browsable index, gated by each record's own
  `claim_scope`/`evidence_level` rather than a single global claim.
