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
- `NeuroTopologySim.EmpiricalSourceManifest.v1` and `SourceSnapshot` IDs,
  declared source pins, and optional metadata references are joined only by
  exact declared identifiers. No filename, timestamp, URL similarity, or prose
  matching is used. `SourceSnapshot.source_sha256` is format-checked, but its
  schema does not define raw bytes versus normalized text/excerpt scope, so the
  auditor does not hash or fetch `source_uri` to guess a match. Arbitrary
  `RunRecord.input.source_sha256` values are also left unpaired with snapshot
  checksums because RunRecordV1 defines no checksum scope for that input key.

## Bounds and outcomes

Default limits are 2 MiB per input manifest or referenced JSON record, 64 MiB
per referenced artifact, 256 MiB total bytes read/hashed, and 10,000
inventoried files. Symlinks, junctions, absolute paths in embedded references,
traversal, and references outside the root are rejected. Explicit CLI input
manifests may be absolute only when they resolve beneath the supplied artifact
root. JSON duplicate keys and non-finite values are rejected. Artifact hashing
is streamed in 1 MiB blocks. A declared `local_root` source subtree is
recognized as input and not recursively read or inventoried.

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
typed license field. A missing license reference is therefore reported as a
schema coverage gap; an explicit `license_ref` is unresolved unless an exact
`license_id` is supplied.

Open Batch 2/3 producer PRs are not loaded or imported. When their source/license
formats are absent from current `main`, only explicit fixtures can exercise
those fields. This report is a structural lineage audit, not scientific
validation.
