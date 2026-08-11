# Safe Curated Dataset Acquisition Planner v1

Status: **implemented.** This document describes the `dataset_acquisition/`
package as it exists today. It does not describe, and should not be read
as promising, any of the capabilities listed in [Future work](#future-work)
-- those are explicitly out of scope for this milestone.

This package is the fourth link in the chain that started with
`dataset_importers/` (see `docs/dataset_candidate_importers.md`):

```
MOABB / EEGDash catalog metadata
        |
        v   dataset_importers (candidate scouting -- PR #193)
DatasetCandidateRecordV1  (scouting record, never evidence)
        |
        v   dataset_acquisition (this package)
DatasetAcquisitionPlanV1  (dry-run-first plan, never a download)
        |
        v   dataset_acquisition.executor  (execute=True, local-only in v1)
DatasetAcquisitionManifestV1  (what actually happened, still not evidence)
        |
        v   dataset_acquisition.executor.run_bids_handoff (optional)
DatasetRecordV1 / ArtifactRecordV1  (still current_role="exploration")
        |
        v   a human writes an explicit condition/state mapping
adapters.mne_bids  ->  TransitionRecordV1  ->  ...  ->  EvidenceReportV1
```

## Why safe acquisition planning exists

`dataset_importers` can rank public datasets, but nothing in this
repository could previously turn "candidate X looks promising" into a
bounded local copy of that dataset's metadata/files without risking an
accidental large download, a license/access mistake, cache chaos across
repeated runs, or a candidate silently contaminating a validation split.
This package is the controlled substrate between "I found a good
candidate" and "I have local files a human can look at" -- nothing more.

## No-download-by-default policy

- `DatasetAcquisitionPlanV1.dry_run` defaults `True` and stays `True`
  unless `requested_action="execute_download"` **and** every safety flag
  was explicitly supplied and nothing is blocked (mission rule 6).
- `allow_network`/`allow_raw_data` both default `False` (rules 7/8).
- `dataset_acquisition.executor.execute_acquisition_plan(plan,
  execute=False, ...)` -- the default -- never touches the network or the
  filesystem beyond reading the plan object itself; it always returns a
  `planned_only` manifest.
- Even with `execute=True`, v1 has **no implemented remote-fetch path** for
  any catalog (`eegdash_metadata_query`, `moabb_planned_fetch`,
  `openneuro_external_cli_plan`, `datalad_external_cli_plan`,
  `manual_url_manifest` all raise `ExecutorError` if actually attempted).
  Only `scan_existing_local`/`verify_existing_local` -- reading files
  already present under `target_root` -- ever write/read real files, and
  neither performs any network I/O. This is enforced at three independent
  layers: the planner pre-populates `blocked_reasons` for any
  `execute_download` request against an unimplemented mode; plan
  validation refuses to call an unblocked plan "clean" if its mode is
  unimplemented (rule against a clean `execute_download` in an
  unimplemented mode); and the executor itself re-checks the same set
  before doing anything, independent of what a (possibly stale,
  hand-edited) plan file claims.
- A static source-guard test
  (`test_no_network_calls_are_ever_made_by_executor_source`,
  `test_cli_never_downloads_raw_data`) additionally asserts neither
  `executor.py` nor `export_plan.py` references a network-fetch or
  data-download API at all, as a regression guard independent of runtime
  behavior.

## Dry-run vs. execute

Two independent gates, both required for anything beyond a local
scan/verify to happen:

1. **Plan-time**: `make_acquisition_plan(..., allow_network=, allow_raw_data=,
   explicit_execute_confirmed=)` -- if any is missing (or license/access/
   disk-limit/size checks fail), the resulting plan carries
   non-empty `blocked_reasons` and `dry_run=True`, and validates cleanly
   *as a blocked plan*. This lets a plan document why a request can't
   proceed, without ever raising just for being blocked.
2. **Execute-time**: `execute_acquisition_plan(plan, execute=True,
   allow_network=, allow_raw_data=, ...)` -- the executor's own flags must
   independently agree with the plan's; a caller cannot silently escalate
   a stale plan's permissions by only supplying `execute=True` at
   execution time.

## Disk limit policy

- `disk_limit_bytes` is required for `execute_download` (rule 9).
- `estimated_size_bytes` is **never invented**: it is populated only from
  `DatasetCandidateRecordV1.metadata["estimated_size_bytes"]` if the
  source candidate's own metadata explicitly supplied it as an integer;
  otherwise it stays `None`.
- `estimated_size_bytes > disk_limit_bytes` blocks `execute_download`
  (rule 11).
- An unknown `estimated_size_bytes` also blocks `execute_download` unless
  `force_unknown_size=True` is explicitly passed (rule 12) -- recorded in
  `plan.metadata["force_unknown_size"]` so the override is visible in the
  written plan, not just implied by CLI flags at the time it ran.

## License/access blocking

`license_risk in {"unknown_high", "proprietary_high"}` or `access_status
in {"restricted", "unknown"}` blocks `execute_download` (rule 10) -- the
planner never constructs a "clean" (`blocked_reasons=[]`) execute plan for
a disqualified candidate; validation independently re-checks the same
condition and fails a plan that claims to be clean while carrying a
disqualifying license/access.

## Target-root safety

`dataset_acquisition.store.validate_target_root` (rules 13/14) fails
closed unless `target_root` is:

- a relative path (no leading `/` or `~`);
- free of `..` traversal segments;
- under `outputs/` or `data/` -- both already covered by `.gitignore`
  (`outputs/`, `data/raw/`, `data/ds[0-9]{6}*`), so a real acquisition
  never lands in a tracked source directory (`adapters/`,
  `dataset_importers/`, `core/`, ...);
- resolvable to a path that is actually still inside the repository root.

This check runs before anything else in `make_acquisition_plan` and again
inside plan validation, so a hand-edited plan JSON with an unsafe
`target_root` can never pass validation even if it bypassed the planner.

## Manifest structure

`DatasetAcquisitionManifestV1` records what an execution actually did:
`execution_status` (`planned_only`/`blocked`/`skipped`/`acquired`/
`verified_existing`/`failed`), `acquired_paths`/`acquired_file_count`/
`acquired_size_bytes`/`checksums` (sha256, computed only for
`scan_existing_local`/`verify_existing_local`), `errors`,
`bids_metadata_summary` (populated only via the optional handoff below),
`dataset_record_paths`/`artifact_record_paths`, and `repo_commit` (the
git commit at manifest-creation time, best-effort). `planned_only`/
`blocked` manifests structurally cannot carry `acquired_paths` --
validation rejects a manifest claiming to be `planned_only` while also
listing acquired files.

## How acquisition differs from evidence

Neither a `DatasetAcquisitionPlanV1` nor a `DatasetAcquisitionManifestV1`
carries a `claim_scope`/`evidence_level`/`allowed_uses` field at all --
they are not `TransitionRecordV1`/`EvidenceBundleV1`, and nothing in this
package can produce one. Structurally enforced: `metadata` on either
object may never carry a truthy `final_claim_confirmation`/`evidence`/
`validation_ready`/`clinical_claim` key (validation rule 15); every
free-text field is scanned with the same shared banned-phrase list every
other layer in this repository uses, plus one small additive list
(`"manifest is evidence"`, `"acquisition proves"`, ...).

## Local BIDS scan handoff

`dataset_acquisition.executor.run_bids_handoff(manifest, target_root=)` --
requires `manifest.execution_status in ("acquired", "verified_existing")`
(a remote/`planned_only`/`blocked`/`failed` manifest is rejected with
`ExecutorError`, matching the mission's "only for local/verified paths,
not remote planned-only records" requirement). It calls
`adapters.mne_bids.scan_bids_metadata`/`make_dataset_record_from_bids`/
`make_artifact_records_from_bids` directly -- the same functions
`adapters.mne_bids`'s own CLI (`--scan-bids-only`) uses -- with
`mapping_provided=False`, so the resulting `DatasetRecordV1` never gains
`transition_export` in `allowed_uses` and no `TransitionRecordV1` is ever
produced at this stage. CLI: `--scan-bids-after-acquisition` (only valid
alongside `--plan ... --execute`, and only proceeds if the resulting
manifest is `acquired`/`verified_existing`).

## How this supports the commercial plan

- **Safe public demo dataset selection**: a scored candidate can be turned
  into a bounded local scan without a human needing to remember disk/
  license caveats by hand each time.
- **Reproducible benchmark packs**: `plan_id`/`manifest_id` are both
  content-addressed (the former excludes `created_at` entirely, so
  replanning the same request is idempotent; the latter is deterministic
  given identical file content), giving a stable, greppable record of
  which local copy came from which plan.
- **Future paid lab onboarding**: a lab pointing this repository at their
  own already-local BIDS export can use `scan_existing_local`/
  `verify_existing_local` today, with the same conservative
  `DatasetRecordV1`/`ArtifactRecordV1` floor every other metadata-only
  path in this repository already uses -- no separate onboarding code
  path needed.

## Future work

**Not implemented by this milestone** -- listed only to show what this
substrate is for; none of these descriptions is a commitment to a design:

- **Curated safe download recipes** -- an actual, disk-bounded remote
  fetch implementation (mirroring `tools/streaming/base_runner.py`'s
  sync-then-delete discipline already used for OpenNeuro S3 EEG) for at
  least one acquisition_mode.
- **MOABB-specific fetch recipes** -- calling a MOABB dataset object's own
  `.get_data()` under this package's disk/license gates, once a safe,
  bounded wrapper exists.
- **EEGDash safe acquisition mode** -- using `eegdash`'s own dataset
  object/download API (distinct from its already-used metadata-only
  `find_datasets`/`search_datasets`) under the same gates.
- **OpenNeuro/datalad external-CLI planning** -- shelling out to an
  already-installed `datalad`/OpenNeuro CLI as a subprocess, still gated
  by the same disk/license checks.
- **Derived feature extraction recipes** -- turning a locally acquired
  BIDS root into the feature tables `adapters.mne_bids`/
  `adapters.fmri_derivatives` consume; explicitly out of scope for this
  milestone (mission: "It should not yet run preprocessing or feature
  extraction").
- **Benchmark-pack generator** -- bundling several acquired/verified
  manifests plus their eventual real transition records into a single
  documented, shippable pack.

This milestone does not imply that any acquired/scanned dataset has been
analyzed, does not imply clinical validity for any dataset it touches, and
does not imply consciousness or spiritual-state detection for any dataset
regardless of its subject matter.
