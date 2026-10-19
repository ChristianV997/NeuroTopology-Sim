# Batch 3 provenance join

This command performs a bounded, read-only structural audit over explicitly
declared JSON documents beneath one artifact root. It reports lineage gaps and
contradictions; it does not decide whether a scientific result is true, does
not promote evidence, and does not repair any source record.

```powershell
python scripts/run_batch3_provenance_join.py `
  --artifact-root path/to/artifacts `
  --input-manifest cycle-export.json `
  --input-manifest RunRecord.json `
  --input-manifest manifest.json `
  --input-manifest source-manifest.json `
  --input-manifest evidence-bundle.json
```

Every `--input-manifest` is required and must name one JSON document under the
root. Document type is determined only by its embedded existing schema—not by
its filename. The tool does not discover manifests, read SQLite databases,
download or unpack data, import producers/solvers, or invoke subprocesses. It
prints its deterministic JSON report to stdout; the inspected root remains
unchanged. Redirect the report only to a destination outside the audited root.

## Reused contracts

- `runs.RunRecordV1` (`schema_version` `0.1` or legacy `1`) is the sole run
  record contract. Its `run_id`, `dataset_id`, `input`, `config`, `git_commit`,
  and explicit `artifacts` paths are read as declared; missing data is not
  inferred.
- `awareness-studio-research-cycle.v1` JSON exports are checked using the
  `canonical_json` / `sha256_json` rule in the ledger models. Record and event
  checksums, event sequences/hash chains, IDs, cycle references, typed record
  links, and materialized `record_links` are cross-checked. When a referenced
  ancestor cycle is not supplied, the report says it is unresolved rather than
  inventing a record.
- `NTS.IntegrationArtifactManifest.v1` entries are verified against raw file
  bytes and declared sizes, matching `tools.integration_bridge.artifact_manifest`.
- `NeuroTopologySim.SimulationArtifactLineage.v1` report checksums,
  configuration fingerprints, artifact hashes, and producer diagnostics are
  checked using the rules in `tools.simulation_artifacts`.
- `EvidenceBundleV1` identity and explicit artifact/transition/coordinate
  references follow `evidence.bundle` and `evidence.validation` field shapes.
  `artifact_ids` are registry IDs while `artifact_paths` are role-to-path
  entries (for example, `source`); the auditor does not equate those two
  namespaces. It checks internal artifact registry-decision IDs and hashes
  each declared path. It does not redo the bundle's claim/evidence ceiling or
  banned-phrase policy, or claim that an embedded registry decision proves
  the registry's external state.
- Dataset identity joins use typed keys. `RunRecordV1.dataset_id` and
  `EvidenceBundleV1.dataset_id` may resolve only to
  `EmpiricalSourceManifest.v1.dataset_identifier`. Ledger
  `source_snapshot_ids` resolve only to `source_snapshot` records. A matching
  string in a different record type, metadata field, or identifier namespace
  does not create a join. Typed ledger edges are resolved against the target
  record type declared by the research-cycle model; generic `parent_ids`,
  `child_ids`, and materialized `record_links` use only the ledger's canonical
  `record_id` namespace. For each known ledger record type, serialized
  `record_id` must be present and equal its type-specific identifier field;
  mismatched or missing identifiers are errors and are never inferred. Unknown
  record types are not used as generic or typed join endpoints, and a typed
  reference field on a record type that does not define that edge is reported
  as unsupported rather than joined. Unknown or malformed typed references are
  reported; they are not silently reinterpreted.
- Unknown or non-join-classifiable present `origin`, `data_mode`,
  `artifact_type`, ledger record type, or document schema values are emitted as
  structured `unverifiable_*` findings. Recursively traversed fields use RFC
  6901 JSON Pointer locations; unknown ledger record types identify the record
  index, and unknown document schemas identify the input document. Null values
  and nested fields are retained rather than silently omitted. Current-main
  artifact schemas do not define `artifact_type`,
  so any such field is reported as unverifiable. The source-manifest schema's
  `external_solver` and `unavailable` origins are recognized labels but are
  not mapped to synthetic/empirical comparison classes. `UNVERIFIABLE` is never a
  successful classification. A schema that is not present on current `main` is not
  reverse-engineered from filenames or an unmerged branch. In particular, the
  source-pack manifest associated with open PR #391 is not supported here until
  its contract is integrated on `main`; the unrelated `benchmark_packs`
  schema is not substituted for it.
- `SourceSnapshot` has no typed reference to `EmpiricalSourceManifest.v1`, and
  current `ResearchCycleLedger` event payloads are free-form without a typed
  target-reference contract. Neither metadata identifiers nor gate-event
  payload strings are used to invent those joins; positive status claims
  remain `INCOMPLETE` unless a supported record-level contract can establish
  them.
- Current-main schemas do not define a license record or typed license
  relationship. Present keys containing `license` or `licence` (including
  compound names such as `licensee_id`, `license_id`, `license_ref`, URL-like,
  and SPDX-like variants) therefore produce explicit `unverifiable_license_*`
  findings with RFC 6901-escaped JSON Pointer locations and are never resolved
  by matching their text. This is structural coverage only, not data-use-rights
  or legal clearance.
- `SourceSnapshot.source_sha256` is format-checked, but its schema does not
  define raw bytes versus normalized text/excerpt scope, so the auditor does
  not hash or fetch `source_uri` to guess a match. Arbitrary
  `RunRecord.input.source_sha256` values are not paired with snapshot
  checksums, and untyped `source_version` pins are reported unverifiable rather
  than compared to free-form `SourceSnapshot.metadata`.

## Bounds and outcomes

Default limits are 2 MiB per input manifest or referenced JSON record, 64 MiB
per referenced artifact, 256 MiB total bytes read/hashed, 10,000 regular files,
and 50,000 filesystem entries encountered during root inventory (including
directories and special entries). Directory enumeration stops at the entry
limit without retaining a partial inventory. Symlinks, detectable Windows
reparse points (including junctions, using reparse metadata where exposed),
absolute paths in embedded references, traversal, and references outside the
root are rejected. Explicit CLI input manifests may be absolute only when they
resolve beneath the supplied artifact root. JSON duplicate keys and non-finite
values are rejected. Artifact hashing is streamed in 1 MiB blocks. A declared
`local_root` source subtree is recognized as input and not recursively read or
inventoried.

On platforms exposing `O_NOFOLLOW`, file opens reject a final-component symlink
at open time, in addition to pre/post `lstat` and descriptor `fstat` identity
checks. `O_NOFOLLOW` applies only to that final component; it does not prevent
parent-directory races. Identity checks detect ordinary replacement and
concurrent-write races, but they are not a defense against a hostile process
that races parent components or restores file metadata. Bounded inventory
skips links visible during enumeration, but is likewise intended for a stable
root rather than a concurrently hostile tree. Run the auditor over a stable,
read-only artifact snapshot when concurrent adversarial mutation is in scope.

`CLEAN` means no structural findings under the supplied inputs and limits.
`INCOMPLETE` means one or more references, versions, or status claims are
unverifiable. `INVALID` means malformed, contradictory, unsafe, or checksum-
invalid content. These are auditor states, not scientific outcomes.

Canonical checksum scope is reported separately for each existing contract.
In particular, `RunRecordLink.run_record_sha256` is required by the current
ledger schema, but current-main documentation does not specify whether it
hashes raw RunRecord bytes or canonical RunRecord JSON; the tool explicitly
marks that checksum scope unverifiable rather than guessing. The current
`SourceSnapshot` type and `EmpiricalSourceManifest.v1` required fields have no
typed license field. Missing typed license references are reported as a schema
coverage gap; textual `license_id` / `license_ref` values remain unverifiable
until a source/license record contract is present on `main`.

Open Batch 2/3 producer PRs are not loaded or imported. When their source/license
formats are absent from current `main`, only explicit fixtures can exercise
those fields. The auditor does not verify source authenticity, data-use rights
or legal clearance, cohort/participant identity, physical or statistical model
correctness, empirical validity, or scientific claims. It does not establish
causation or biological interpretation. The repository posture remains
`HOLD / SYNTHETIC_ONLY`; this tool cannot change it.
