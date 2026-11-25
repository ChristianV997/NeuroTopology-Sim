# Batch 3 provenance-firewall audit snapshot

Evidence cutoff: 2026-10-18 23:03:57 America/Mexico_City (2026-10-19 05:03:57 UTC).
This snapshot was refreshed from GitHub PR/check metadata and local static review
in isolated worktrees. CI output was treated as untrusted diagnostic data. No
participant data, harvested repository content, or external scientific service
was accessed; no dependency was installed and no PR was merged.

## Decision

Maintain **HOLD / SYNTHETIC_ONLY**. PR #392 has a narrowly scoped compatibility
fix on its existing branch and its latest hosted core, Awareness, Smoke, and
Ontology checks have passed. However, its focused pytest suite could not run in
the available environment, and the current required workflows do not discover
that suite. Its branch also targets a stale `main` base and lacks human approval
evidence. PR #404 is a documentation-only snapshot update; its new head has not
yet received hosted checks or review. Neither PR is declared integration-ready.

This audit is not a scientific, legal, provenance-authenticity, or data-rights
determination. Checksums can establish agreement with specified bytes or
serialization only; structural joins do not establish honest collection,
source authenticity, consent, data-use rights, legal compatibility, cohort or
participant identity, model correctness, biological validity, causation, or
scientific truth.

## Live refs and PR state

Refs and PR metadata were refreshed at the evidence cutoff. The recorded PR
base SHA is the base revision GitHub reports for each open PR; it is not the
current live `main` SHA.

| Ref | State | Base SHA | Head branch | Head SHA at cutoff |
| --- | --- | --- | --- | --- |
| `main` | live default branch | — | `main` | `ed9c6426e8f1cb614b58e6588a80b184592eecb7` |
| #390 | open, non-draft | `19c3203573082f8bc41f7da226b52dc20a49fdb0` | `batch3/codex-d-report-firewall` | `53cfbea94e686ce082075b3f3d96c5c02bbfdbf2` |
| #391 | open, draft | `19c3203573082f8bc41f7da226b52dc20a49fdb0` | `batch1/hermes-a-safe-source-harvest` | `ffd24dbc9fe3e1695af1e8d656754f89c4e7f4aa` |
| #392 | open, non-draft | `19c3203573082f8bc41f7da226b52dc20a49fdb0` | `batch3/codex-c-provenance-join` | `2bc992d8e455f0426e1050cfe0413135f6ef4bec` |
| #404 | open, non-draft | `19c3203573082f8bc41f7da226b52dc20a49fdb0` | `batch3/codex-d-provenance-firewall-review` | `5c2c58f1a898ef895f407a5e763c5ed763dbb669` before this document refresh |

The #392 head includes commit `2bc992d8e455f0426e1050cfe0413135f6ef4bec`,
fast-forwarded to its existing PR branch from parent
`5e38aa23342bea05f0a8d144fad4c07ef96ad0bd`. It changes only the existing
auditor, focused test, and tool-documentation paths. The #404 head above is the
source snapshot for this document update; the update itself will create a new
PR head.

## Exact paths and relationship

The refreshed GitHub file list for #392 is:

- `docs/tools/batch3_provenance_join.md`
- `scripts/run_batch3_provenance_join.py`
- `tests/tools/batch3_provenance_join/__init__.py`
- `tests/tools/batch3_provenance_join/helpers.py`
- `tests/tools/batch3_provenance_join/test_audit.py`
- `tests/tools/batch3_provenance_join/test_safety_and_cycles.py`
- `tools/batch3_provenance_join/__init__.py`
- `tools/batch3_provenance_join/auditor.py`
- `tools/batch3_provenance_join/models.py`

PR #404 changes only `docs/reviews/batch3_provenance_firewall_audit.md`.
Those paths do not overlap. #404 is downstream documentation about the
audited PRs and must describe the exact #392 source snapshot it reviewed; it
does not implement or certify #392 behavior.

PR #391 remains a draft and its source-pack contract is not present in the
current `main` tree at `ed9c6426e8f1cb614b58e6588a80b184592eecb7`. The checked-in
`tools/public_repo_harvest/` tree has no `source_pack.py`, and a scoped source
pack search found no source-pack manifest contract (the unrelated HTML report
pack renderer is not that schema). #392 therefore correctly reports such
documents as unsupported/unverifiable; no #391 schema support is claimed.
There is no certified source-pack-to-join adapter or merge order for #391/#392.

## #392 current-head audit

Static inspection was performed against the fetched PR head before the
compatibility fix, then the exact fix and added test were reviewed in the
isolated #392 worktree. The following contract behaviors were verified by code
inspection and existing focused test definitions; pytest execution was not
available locally:

- Ledger keys include record type and the `record_id` namespace. Declared
  dataset joins use `EmpiricalSourceManifest.v1.dataset_identifier`; typed
  ledger fields resolve only to their contract-declared record type. Generic
  `parent_ids`, `child_ids`, and materialized links use the ledger's canonical
  record-ID namespace. Equal text across types/namespaces is not enough to
  create a join. Unknown record types cannot satisfy those joins; unsupported
  known typed-reference fields are reported rather than interpreted.
- Missing, malformed, or mismatched ledger identities are not inferred.
  Unknown origins, `data_mode`, artifact types, record types, and document
  schemas are emitted as unverifiable findings. The declared
  `external_solver` and `unavailable` labels are not mapped to synthetic or
  empirical. Recursive JSON locations escape `~` and `/` per RFC 6901.
- License-like keys are detected recursively by `license`/`licence` substring,
  including compound names such as `licensee_id`, and reported at escaped
  locations. Current-main schemas do not define typed license records or
  relationships. License values are therefore unresolved and never joined by
  text; conflicting or unknown declarations are not treated as a license
  decision or legal clearance. The report remains structurally incomplete
  where those warnings are present.
- Contract-defined checksum rules are applied only at their documented scopes.
  `SourceSnapshot.source_sha256`, `RunRecordLink.run_record_sha256`, and
  untyped source-version pins are not assigned guessed scopes or compared to
  unrelated bytes/metadata. Source URLs are not fetched. A matching hash does
  not authenticate where bytes came from or who collected them.
- Explicit path selection, bounded manifest/artifact/total-byte/file/inventory
  limits, traversal rejection, duplicate-key and non-finite JSON rejection,
  symlink handling, cycle-loop detection, and deterministic findings are
  present. Tests define adversarial cases for typed collisions, unsupported
  edges, malformed inputs, origin/type/license variants, JSON Pointer escaping,
  checksum scope, cycles, replacement races, traversal, and symlinks where the
  platform permits.
- The report describes `CLEAN`, `INCOMPLETE`, and `INVALID` as structural
  auditor states and sets `scientific_validation` to false. It does not promote
  evidence or verify citation/source truth.

The refreshed fix addresses a reproduced compatibility gap in `_is_link`:
Python 3.10/3.11 do not provide `Path.is_junction()`, and the earlier helper
returned false for a modeled directory stat result carrying Windows reparse
metadata when that method was absent. `_is_link` now checks `lstat` symlink
mode and available Windows reparse attributes/tag before using
`Path.is_junction()` when present. The new focused regression fixture models
both metadata routes without the pathlib junction method. It is not a test on
an actual Windows junction; the committed test could not be run locally because
pytest is unavailable.

File-opening limits remain intentionally narrow. On platforms that expose
`O_NOFOLLOW`, it protects the final path component at open time; it does not
prevent hostile parent-directory races. Pre/post `lstat` and descriptor
`fstat` checks detect ordinary identity changes, but not all hostile races or
metadata restoration. Windows reparse detection depends on metadata exposed by
the runtime/filesystem. Inventory is for a stable snapshot, not a hostile
concurrently-mutated tree.

## Local validation and hosted CI

Local commands were run in the isolated #392 worktree using bundled Python
3.12.14. No packages were installed.

| Command | Result |
| --- | --- |
| `python -m pytest -q tests/tools/batch3_provenance_join` | **Not run:** exit 1, `No module named pytest`. |
| `python scripts/run_tests_isolated.py --root tests/tools/batch3_provenance_join --batch-size 2 --timeout-s 90` | **Not run:** exit 1 before tests, `pytest-timeout is required`. |
| `python scripts/validate_release_blockers.py --format json` | **Not run:** exit 1, `ModuleNotFoundError: No module named 'yaml'`. |
| `python -m compileall -q tools/batch3_provenance_join tests/tools/batch3_provenance_join scripts/run_batch3_provenance_join.py` | Passed. |
| `python scripts/run_batch3_provenance_join.py --help` | Passed. |
| Manual local-fixture smoke: two legacy Windows reparse-metadata cases and `valid_fixture` audit serialized with `allow_nan=False` | Passed: two metadata detections; fixture report `INCOMPLETE`; finite JSON serialized (9,037 bytes). This is not a pytest-suite pass. |
| Static scan for network/subprocess/eval/exec imports or calls in auditor and CLI | No matches. This regex scan is not a dedicated security scanner. |
| `git diff --check` | Passed. |

The core workflows use explicit test-file allowlists:
`.github/workflows/required-checks.yml:52-68` and
`.github/workflows/ci.yml:142-157`. They list core test modules but do not list
`tests/tools/batch3_provenance_join/`; Awareness Studio runs its own package
tests. Thus the current required workflow does not demonstrate discovery of
the #392 focused suite. CI-workflow ownership belongs to #425; no workflow was
edited here.

On #392 head `2bc992d8e455f0426e1050cfe0413135f6ef4bec`, the hosted checks
completed successfully by 05:02 UTC: Required Checks run
[39202337524](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39202337524)
had both core and Awareness pass; Smoke run
[39202337560](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39202337560)
and Ontology run
[39202337688](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39202337688)
also passed. This is a green hosted check set, but it does not demonstrate the
focused #392 suite because that path is omitted from the workflow allowlists.
On the previous #392 head `5e38aa23342bea05f0a8d144fad4c07ef96ad0bd`, Required Checks run
[39183762879](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39183762879)
had a failing Awareness job; core passed, and Smoke and Ontology runs
[39183762865](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39183762865)
and
[39183762883](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39183762883)
passed. That prior-head result does not predict completion on the new head.
The connector returned no job-log text for the failure, so no failure signature
is asserted here.

For comparison, the latest live-main runs at the exact SHA above completed
successfully: Required Checks
[39202526614](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39202526614),
Smoke
[39202526666](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39202526666),
and Ontology Claim Language
[39202526599](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39202526599).
These main results do not clear a red or pending PR check. Earlier successful
runs on `f6951115bcbf83b75bf20481085a5dad9c25c7e6` were superseded when main
advanced.

Before this document refresh, #404 head
`5c2c58f1a898ef895f407a5e763c5ed763dbb669` had Required Checks run
[39167669334](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39167669334)
with core passed and Awareness failed; Smoke
[39167669450](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39167669450)
and Ontology
[39167669404](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39167669404)
passed. Those checks apply only to the pre-refresh document head. No hosted
result for the replacement document commit was available at the cutoff.

## Other PR state: historical evidence is not a current source review

PR #390 advanced from the previously reported `e7fe8252c3a7a9dbd675b324691de803d7d194b6`
to live head `53cfbea94e686ce082075b3f3d96c5c02bbfdbf2`. Current metadata shows
core passed in Required Checks run
[39182948367](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39182948367),
Awareness failed in that run, and Smoke
[39182948377](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39182948377)
and Ontology
[39182948357](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39182948357)
passed. The previous report's 28-test local result and named regression cases
were associated with the older `e7fe…` head. This refresh did not rerun or
re-review the current #390 source head; those older tests are historical
evidence only, not proof of current-head behavior.

PR #391 remains an open draft at `ffd24dbc9fe3e1695af1e8d656754f89c4e7f4aa`,
based on `19c3203573082f8bc41f7da226b52dc20a49fdb0`. Its Required Checks run
[39009196915](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39009196915)
had core passed and Awareness failed; Smoke
[39009196945](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39009196945)
and Ontology
[39009196922](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39009196922)
passed. The current #391 source diff and historical license-scope observations
were not re-audited in this refresh. Keep those observations unresolved; do
not represent them as confirmed current defects or cleared findings.

## Reviews, branch state, and disposition

GitHub reports #392 as `MERGEABLE` and #404 as `UNKNOWN`; both have an empty
review decision. Their review submissions are Copilot quota-limit notices only; there
are no inline review threads or approving human reviews in the refreshed data.
The GitHub branch-protection endpoint for `main` returned HTTP 404, “Branch not
protected.” That endpoint result is an access/configuration observation only;
it does not establish whether other repository or organization rules apply.
No protection was bypassed.

The PRs still target base SHA `19c3203573082f8bc41f7da226b52dc20a49fdb0`,
which is behind live main `ed9c6426e8f1cb614b58e6588a80b184592eecb7`. A path
comparison from that base to live main found no changes in the #392 or #404
owned paths; main's intervening changes are outside those surfaces. Do not
rebase or merge another agent's branch to hide this difference. The coordinator
must handle integration against live main in its prescribed order.

Disposition at this evidence cutoff:

- #392: **CODE_READY: no** (focused pytest and bounded runner could not execute,
  and hosted CI does not discover the focused suite). **INTEGRATION_READY: no**
  (stale base, no human approval evidence, and no focused hosted test evidence).
- #404: **DOCUMENT_REVIEWED: yes for the stated snapshot only.** Its new commit
  still needs hosted checks and review. **INTEGRATION_READY: no** (new-head CI
  and approval evidence unavailable; base is stale).
- #390/#391: current PR states and checks above are metadata only. No current
  source-level clearance is implied by this report.

Maintain **HOLD / SYNTHETIC_ONLY**. No heuristic warning, source-pack metadata,
checksum, hash chain, structural join, or report in this audit establishes a
scientific claim or changes the evidence gate.
