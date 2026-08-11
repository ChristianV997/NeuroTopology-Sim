# External Tool Integration Registry + Adapter Contract

Status: **governance and planning layer only.** This document describes the
`external_tools/` package as it exists today: a registry that classifies
external tools/libraries/platforms by license risk, commercial-use status,
and integration mode, plus a schema (`AdapterContractV1`) that a future
adapter must satisfy. **No adapter is implemented by this milestone** -- not
for MNE, not for BIDS, not for fMRIPrep/Nilearn, not for MOABB/EEGDash, and
no live EEG streaming was added. Nothing in this document should be read as
claiming any of those integrations exist yet.

## Why this registry exists

`reports/` (see `docs/evidence_report_generator.md`) made this repository's
first sellable artifact: point at derived EEG/fMRI artifacts, get a governed
`EvidenceBundleV1`, get a guarded `EvidenceReportV1`. The obvious next lever
is accepting *more kinds* of derived artifacts -- the ones the broader
neuroinformatics ecosystem (MNE, BIDS, fMRIPrep, Nilearn, MOABB, EEGDash,
GUDHI, Ripser, NetworkX, BrainFlow, ...) already produces every day.

Before writing a single line of adapter code for any of those, this repo
needs an honest answer to three questions per candidate tool:

1. **Is its license compatible with a commercial core product?** GPL,
   AGPL, proprietary, and unverified licenses all carry different, real
   constraints that a rushed `pip install` would not surface.
2. **What kind of integration does it actually deserve?** A pure permissive
   library (GUDHI, NetworkX) is a different case from a heavyweight
   external pipeline invoked via subprocess (fMRIPrep) or a closed
   commercial competitor's platform (a clinical qEEG vendor) that should
   only ever be studied as a reference point, never integrated.
3. **What would an adapter for it be *not* allowed to claim?** Every
   existing schema in this repo (`TransitionRecordV1`, `EvidenceBundleV1`,
   `EvidenceReportV1`, ...) already enforces a claim/evidence ceiling and a
   banned-phrase firewall. A tool-specific adapter must inherit those
   ceilings, not invent a side door around them.

`external_tools/` answers all three, structurally and testably, before any
adapter exists. This is the same "classify, then build" discipline this
repository already applied to datasets (`benchmarks/`, see
`docs/benchmark_dataset_registry.md`) -- now applied to *tools* instead of
*datasets*.

## Why integrate outputs, not rebuild algorithms

This repository's own `core/topology.py`, `analysis/`, and `validation/`
modules already implement real topology, connectivity, and statistical
methods against real EEG/fMRI signal. The external tools tracked here are
not competitors to reimplement against -- most of them (MNE, GUDHI, Ripser,
NetworkX, Nilearn) are **already real dependencies of this repository**
(see `requirements.txt`), used directly by existing pipelines. The gap this
registry identifies is not "we lack these algorithms" -- it is "we have no
governed adapter that turns *their* output artifacts into *this repo's*
canonical artifact contracts" (`DatasetRecordV1` / `ArtifactRecordV1` /
`TransitionRecordV1` / `PhaseSpaceCoordinateV1` / `EvidenceBundleV1` /
`EvidenceReportV1`). Building that adapter path is strictly cheaper and
lower-risk than reimplementing BIDS parsing, fMRIPrep's spatial
normalization, or MOABB's benchmark harness from scratch -- and it is the
only path that lets a lab hand this repository artifacts it already
produces with its existing, trusted toolchain.

## Free/open P0 integrations

The seed registry's `P0` tier (`external_tools/registry_seed.json`) is the
highest-leverage, safest tier: permissive-licensed (MIT/BSD-3-Clause/
Apache-2.0) libraries or metadata-import-only tools with a direct fit to
this repo's existing artifact pipeline. Several are **already real,
declared dependencies** of this repository (confirmed against
`requirements.txt` and live import checks this session):

| tool_id | Already a dependency? | Existing usage in this repo |
|---|---|---|
| `mne-python` | Yes (mne 1.12.1) | `sciencer_d/btc_icft/pipelines/extract_mne_signal_blocks.py` (P19.1, not wired to transitions/evidence) |
| `mne-bids` | Yes (mne_bids 0.19.0) | declared, not yet used for `DatasetRecordV1` ingestion |
| `nilearn` | Yes | `dual_engine/fmri_tda_pipeline.py` |
| `gudhi` | Yes | `core/topology.py::compute_cubical_persistence` |
| `ripser-py` / `persim` | Yes | `analysis/itct/`, PLV-graph persistence code |
| `networkx` | Yes | `analysis/connectivity_topology.py` |
| `keplermapper` | Yes | `tools/export_mapper_graph_for_vortex_field.py` |
| `eegdash` | Yes (eegdash 0.8.4) | declared, but **entirely unused** by any pipeline today |

The rest of the P0 tier (`pybids`, `bids-validator`, `fmriprep`, `moabb`)
are not yet declared dependencies but are permissive-licensed and would
plug into an existing artifact category (`DatasetRecordV1` metadata,
fMRIPrep-derivative ingestion) without needing a license exception.

## Paid/hardware/API candidates

`hardware_sdk`, `commercial_neurofeedback`, and `clinical_qeeg` category
tools (OpenBCI, Muse SDK, Emotiv Cortex, Neurosity SDK, and the
generically-named "Myndlift-style" / "NeuroGuide-style" / "Neurable-style"
platform placeholders) are recorded with `integration_mode` in
`paid_api`/`paid_hardware`/`reference_only` and `priority` in
`P3`/`reference` -- never `dependency` or `optional_backend`
(`external_tools.validation` rule 5 enforces this structurally). Live EEG
acquisition is explicitly out of scope for this milestone; these records
exist so that if/when a live-acquisition feature is scoped later, the
license and commercial posture of each hardware path is already documented
rather than discovered mid-implementation.

The three generically-named commercial platform entries
(`myndlift-style-clinical-neurofeedback-platform`,
`neuroguide-style-qeeg-platform`, `neurable-style-licensing-platform`)
represent **categories** of closed commercial competitor, per the mission
spec that introduced them -- no specific vendor's product, dashboard,
report, or SDK was inspected, scraped, or copied to produce these records.
Their `provenance` field says so explicitly.

## License/commercial-use risk policy

`external_tools.validation` enforces twelve structural rules (see that
module's docstring and `ALLOWED_*` constants for the full vocabulary). The
two that matter most for a commercial product:

- **Rule 4 (fail closed):** `copyleft_medium` (GPL-family), `agpl_high`,
  `proprietary_high`, and `unknown_high` license-risk tools can never have
  `integration_mode="dependency"` in this registry -- unconditionally, with
  no per-record override. This milestone does not implement a separate
  "non-commercial research track" schema, so the only paths available to a
  GPL/AGPL/proprietary/unknown tool are `adapter_only`, `external_cli`,
  `reference_only`, `paid_api`, `paid_hardware`, or `avoid_core` --
  never a live import into the commercial core.
- **Rule 12 (no fabricated confidence):** a tool with `license="unknown"`
  must carry `license_risk="unknown_high"` and
  `metadata.review_needed=true`. This registry does not guess exact license
  terms for hardware vendor SDKs (OpenBCI, Muse, Emotiv Cortex, Neurosity)
  or for the one mission-listed tool (`EEGPrep`) whose exact package
  identity could not be confirmed this session -- each is recorded as
  `unknown`/`unknown_high`/`review_needed` rather than assumed safe.

`giotto-tda` is the clearest concrete case: this repository's own
`README.md` already documents it as "AGPLv3, flagged as copyleft, not
default." `external_tools/registry_seed.json` now makes that existing
policy machine-queryable (`integration_mode="avoid_core"`,
`license_risk="agpl_high"`, `priority="avoid"`) instead of leaving it only
in prose. `braindecode` is a real example of a *mixed*-license tool: its
own package metadata states it is "primarily licensed under the
BSD-3-Clause License" but that "some components... are licensed under the
Creative Commons Attribution-NonCommercial 4.0 International License" --
recorded conservatively as `license_risk="copyleft_medium"`,
`current_status="blocked_pending_license_review"` until the NC-restricted
components are specifically enumerated by a human reviewer.

License data in the seed registry was gathered this session via each
project's own PyPI JSON metadata and/or GitHub repository license
badge/file -- not fabricated, and not treated as a substitute for
independent legal review before any adapter ships.

## Reference-only competitor handling

`EEGLAB`, `FieldTrip`, and `Brainstorm` are recorded as
`category="reference_competitor"`, `integration_mode="reference_only"`,
`priority="reference"` -- all three are real, mature, GPL-3.0-family MATLAB
toolboxes. Their entries exist so this repository can cite what a
comparable mature toolbox exposes (for documentation/comparison purposes)
without their GPL copyleft ever becoming a dependency constraint, and
without any of their code being copied. `external_tools.validation` rule 6
enforces this structurally: `integration_mode="reference_only"` requires
`priority="reference"`, which in turn is excluded from
`ExternalToolRegistry.recommended_next()` unconditionally.

## What to emulate legally from external tools

- **Their artifact/output *shapes*** (e.g., "a BIDS layout has
  `participants.tsv` + `events.tsv`", "fMRIPrep emits spatially normalized
  BOLD + confound regressors") are public, documented facts about data
  formats -- safe to design an adapter's `input_artifact_kinds`/
  `output_artifact_kinds` around.
- **Public API/SDK surface documented in their own official docs** (e.g.,
  MNE's `Raw`/`Epochs` objects, GUDHI's `CubicalComplex`) is safe to call
  as a declared dependency, subject to the license tier above.
- **Never**: scraping a proprietary dashboard, copying a paid platform's
  report template or clinical scoring logic, or extracting a closed SDK's
  internal (undocumented) implementation. `external_tools.validation`'s
  `EXTERNAL_TOOL_EXTRA_BANNED_PHRASES` list (additive to the shared
  `sciencer_d.btc_icft.report_guardrails` / `transitions.governance` base)
  scans every free-text field on every record for exactly this kind of
  language and fails validation on a hit.

## Adapter contract structure

`AdapterContractV1` (`external_tools/adapter_contract.py`) is the schema a
future adapter must satisfy -- not an adapter itself. Its `adapter_id` is a
deterministic `sha256[:16]` over `(tool_id, adapter_name)` only, mirroring
`benchmarks.artifact_registry.compute_artifact_id`'s identity-hash
convention. Every contract:

- Declares `output_targets` restricted to this repo's real canonical
  schemas (`DatasetRecordV1`, `ArtifactRecordV1`, `TransitionRecordV1`,
  `PhaseSpaceCoordinateV1`, `EvidenceBundleV1`, `EvidenceReportV1`, or
  `external_metadata_only`) -- never a new, tool-specific schema.
- Declares non-empty `feature_namespaces`, matching the
  `family.feature`-style namespacing `TransitionRecordV1.feature_names`
  already uses.
- Must include `"source_tool_version"` in `provenance_requirements` --
  encoding "adapter must preserve source-tool version and preprocessing/
  parameter provenance when applicable" as a checkable field, not a prose
  promise.
- Must include `"fail_closed_if_required_metadata_missing"` in
  `validation_requirements` -- the same encoding for "adapter must fail
  closed if required metadata is absent."
- Defaults `forbidden_outputs` to a fixed six-item floor (clinical,
  diagnostic, treatment, consciousness-biomarker, spiritual-attainment,
  mechanistic-causal claims) that validation refuses to let any contract
  shrink, mirroring `reports.evidence_report._blocked_claims_template`'s
  fixed-template approach.
- Defaults `allowed_claim_scope_ceiling="exploratory_metric"` and
  `evidence_level_ceiling="L0_computational_artifact"`, both validated
  against the same `transitions.governance.ALLOWED_CLAIM_SCOPES` /
  `ALLOWED_EVIDENCE_LEVELS` every other schema in this repo already uses --
  the clinical/diagnostic/mechanistic scopes an adapter must never claim
  are not merely capped, they do not exist in that allowed set at all.
- Defaults `implementation_status="planned"`; `"implemented"` is only
  accepted if `metadata.implementation_verified=true` is explicitly set --
  no contract in this milestone's seed data claims a working adapter
  exists, and none currently does.

## Recommended implementation order

`ExternalToolRegistry.recommended_next()` ranks by: `P0` before `P1`
before `P2`/`P3`; `permissive_low` license risk (or an explicit
`adapter_only_recommended` commercial-use status) before anything else;
an `integration_mode` that plugs directly into an existing pipeline
(`metadata_import`, `adapter_only`, `optional_backend`, `dependency`)
before a heavier `external_cli`/other path; and a concrete fit with this
repo's artifact pipeline (non-empty `artifact_outputs`/
`feature_namespaces`) as a tie-breaker. It unconditionally excludes
`reference_only`, `avoid_core`, `proprietary_high`, `unknown_high`, and
`blocked_pending_license_review`/`blocked_proprietary` tools, regardless of
how they'd otherwise rank.

```bash
python -m external_tools.export_registry --recommended-next --limit 10
```

## Why MNE/BIDS is the next highest-leverage adapter

Three independent facts converge on **MNE + BIDS** as the next milestone,
not a fresh registry query:

1. **Already partially present.** `mne` and `mne-bids` are both already
   real, declared, importable dependencies of this repository -- there is
   no new license review or `pip install` risk to clear.
2. **Already prototyped, just not wired up.** A narrow P19.1 prototype
   (`sciencer_d/btc_icft/pipelines/extract_mne_signal_blocks.py`, see
   `docs/eeg_mne_adapter_runbook.md`) already extracts fixed signal windows
   via MNE for several onboarded datasets -- it simply does not yet emit
   `ArtifactRecordV1`/`TransitionRecordV1` artifacts.
3. **Every currently-onboarded EEG dataset would benefit immediately.**
   Every one of this repository's 16+ onboarded EEG datasets is already a
   BIDS-shaped OpenNeuro dataset read by a dataset-specific script; a real
   `mne`+`mne-bids` adapter would replace N one-off readers with one
   governed, provenance-tracked ingestion path.

`recommended_next()` reflects this: `mne-python`, `mne-bids`, `gudhi`,
`networkx`, and `eegdash` all rank at the top of the P0 tier this session
(verified via `python -m external_tools.export_registry --recommended-next`).

## How this supports productized reports, SaaS, SDK/API, and clinical-research analytics

The chain this registry prepares, without building any of it yet:

```
external tool's own real output (MNE Raw/Epochs, a BIDS layout,
fMRIPrep derivatives, a MOABB dataset split, ...)
        |
        v   a future adapter satisfying AdapterContractV1
DatasetRecordV1 / ArtifactRecordV1 / TransitionRecordV1 / PhaseSpaceCoordinateV1
        |
        v   evidence.builder.build_evidence_bundle (already real, PR #188)
EvidenceBundleV1
        |
        v   reports.evidence_report.build_report (already real, PR #189)
EvidenceReportV1  (Markdown + JSON)
```

Every stage after "a future adapter" already exists and is already tested.
The commercial arc this unlocks -- "upload/point to derived artifacts from
a tool your lab already uses -> get a governed bundle -> get a guarded
report" -- was true before this milestone only for this repo's own native
pipelines. This registry is what lets that same promise extend to MNE/BIDS/
fMRIPrep/MOABB-produced artifacts without first deciding, ad hoc and under
deadline pressure, whether each tool's license is safe to depend on.

## Limitations

- No adapter is implemented. `AdapterContractV1` is a schema only; no code
  in this repository currently satisfies it for any tool.
- License data was gathered via each project's own public package-index
  metadata and/or repository license file/badge this session -- treated as
  a strong signal, not a substitute for a dedicated legal review before any
  adapter ships, particularly for the mixed-license (`braindecode`) and
  heavyweight-pipeline (`fmriprep`, whose optional FreeSurfer dependency's
  license was not independently verified) cases.
- Four hardware-vendor SDK records (OpenBCI, Muse SDK, Emotiv Cortex,
  Neurosity SDK) and one mission-listed tool (`EEGPrep`) are recorded as
  `license="unknown"`/`license_risk="unknown_high"`/
  `metadata.review_needed=true` because this session could not
  independently verify their exact license/developer-agreement terms (or,
  for `EEGPrep`, even confirm a specific unambiguous package identity)
  without fabricating a claim.
- The three commercial-competitor-platform records
  (`myndlift-style-...`, `neuroguide-style-...`, `neurable-style-...`) are
  deliberately generic category placeholders, not verified descriptions of
  any specific real product.
- `ExternalToolRegistry.recommended_next()`'s ranking heuristic is a
  simple, documented, four-key sort -- not a scored/weighted model, and not
  a substitute for a human decision about which adapter to build next.
