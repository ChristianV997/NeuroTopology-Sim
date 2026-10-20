# Awareness Studio Orchestrator — Evidence States

Status: implemented for `apps/awareness_studio/src/awareness_studio/orchestrator/orchestrator.py`.
Tests: `apps/awareness_studio/tests/orchestrator/`.

This page defines how the orchestrator labels an output, and what that label allows.
It does not establish that any output is scientifically valid. A passing test shows
only that a guard works; it is not scientific evidence.

## Why this exists

The orchestrator is a 9-stage pipeline. In dry-run mode it emits planning artifacts,
and in live mode no solver is implemented yet. Without an explicit gate, a mock,
synthetic, proxy, or partially failed output could be mistaken for a measurement when
it is copied into a claim-bearing store or a release record. The gate classifies each
artifact it reads, and withholds metric values from every output that is not
evidence-ready.

## Evidence states

| State | Meaning | Evidence-ready? |
|---|---|---|
| `mock` | Output from a mock or stub substitute. | No, never |
| `synthetic` | Synthetic demonstration data. | No, never |
| `proxy` | Proxy inference. Never formal or empirical. | No, never |
| `engineering` | Software or interface verification. | Yes, if all identity blocks are present |
| `empirical` | Measurement on declared, identified inputs. | Yes, if all identity blocks are present |
| `planning` | Dry-run planning output. | No |
| `review_required` | Awaiting human review, such as hypotheses, validation checks, or a dry-run card. | No |
| `invalid` | Malformed, conflicting, or unsupported. Rejected. | No |
| `incomplete` | Identity or lineage is missing, the run status is unrecognized, or the run is partial. | No |
| `failed` | Execution failed. | No |
| `blocked` | Not authorized, not implemented, or not executed. | No |

`EVIDENCE_READY_STATES` is exactly `{engineering, empirical}`. Every other state is
non-evidence. `_DECLARED_CLASS_STATES` covers every member of
`awareness_studio.research_cycle.EvidenceClass`. A test fails if a class is added without
an explicit mapping, so the two vocabularies cannot drift apart silently.

## Dry-run rule

A dry run emits only `planning` or `review_required` states, and nothing in a dry run is
admitted as evidence.

- The result object enforces this at construction. A dry run with any other
  `evidence_state` raises `ValueError`.
- Each stage's output is stamped with its state. For example, `execute` and `digest` are
  `planning`, and `validate` and `draft_report` are `review_required`.
- An execute-stage result that carries metrics has those metrics replaced with `null`,
  and its state stays `planning`.
- A run card that would be evidence-ready is reported as `review_required` with the reason
  `dry_run_no_admission`. Its metric is `null`, and `run_cards_evidence_ready` is `0`.
- The run id includes a digest of the run-card files, so different card sets never share an
  output directory, event log, or ledger. Identical card sets still produce identical ids.
- Planning records in the ledger (the seeded claim and evidence record, the hypotheses, and
  the experiment specs) use `HYPOTHESIS`, which is not a promotable class. The configuration
  snapshot keeps `ENGINEERING_FACT` because it describes the software configuration rather
  than a measurement. The ledger's own default for an experiment spec is `ENGINEERING_FACT`;
  the orchestrator overrides it for dry-run plans.
- Migration: the seeded records changed content, so a dry run whose outputs were written
  before this change cannot be re-run into the same output directory. The ledger's
  immutability check raises `ImmutableCycleError`. Delete `outputs/orchestrator/<run_id>/`
  or use a different seed.

One pinned exception: the ledger's `execution_outcome` event for a dry-run `execute` stage
keeps the status `BLOCKED`, because an existing ledger integration test asserts it. Its
payload carries `evidence_state: planning`. The status is a ledger status, not an evidence
state.

A live run is `blocked` at every stage, because no solver is implemented here. A live run
can admit an identified card's metric into the event log, and only there (see below).

## Run-status vocabulary

Each declared status is matched against a fixed vocabulary. The status keys checked are
`status`, `execution_state`, and `state`. A present key whose value is null, blank, or not
text makes the artifact `invalid`. When more than one key is present, every one is checked.
The most severe category wins, in this order: failed, incomplete, unrecognized, blocked,
planning, review.

| Category | Statuses | Resulting state |
|---|---|---|
| completed | `COMPLETED`, `COMPLETE`, `SUCCESS`, `OK`, `ENGINEERING_EXECUTION_COMPLETE` | no change |
| failed | `FAILED`, `FAIL`, `FAILURE`, `ERROR`, `ERRORED`, `INFRASTRUCTURE_FAILURE`, `SUCCESS_WITH_ERRORS`, `ABORTED`, `CANCELLED`, `CANCELED`, `KILLED`, `CRASHED` | `failed` |
| incomplete | `PARTIAL`, `TIMEOUT`, `TIMED_OUT`, `NOT_RUN`, `INCOMPLETE`, `INCONCLUSIVE`, `RUNNING`, `IN_PROGRESS` | `incomplete` |
| blocked | `BLOCKED`, `NOT_IMPLEMENTED` | `blocked` |
| planning | `PLANNING`, `PLANNING_ONLY`, `PLANNED`, `PENDING` | `planning` |
| review | `REVIEW_REQUIRED`, `EVIDENCE_READY_FOR_REVIEW` | `review_required` |
| anything else | unrecognized | `incomplete` |

Rules:

- Evidence-ready requires at least one declared status, and every declared status must be in
  the completed category. A single unrecognized status is enough to block readiness.
- Verdict words are not run statuses. `sim/run_cards.py` derives `PASS` and `FAIL` from a
  metric threshold, so `PASS` is unrecognized here and `FAIL` counts as a failed run.
- A non-evidence marker (`mock`, `synthetic`, `proxy`, `planning`) is never overridden by a
  status. A `COMPLETED` status cannot rescue synthetic data.

## Classification

`classify_artifact(artifact)` is applied to each run card and to each execute-stage result
that carries metrics. It returns an `EvidenceDecision` with a state, reasons, and missing
identity blocks. It fails closed in these cases:

- The artifact is not an object, or has no `run_id`, or its `run_id` is not a plain
  identifier (`[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`).
- Any value is non-finite, not JSON-compatible, under a non-string key, or nested deeper
  than 64 levels.
- `scientific_pass` or `scientific_evidence` is present and not `false`. A non-null
  `formal_bayes_factor` is rejected.
- `mock` or `synthetic` is present and is not a boolean. The string `"true"` and the integer
  `1` are rejected.
- `data_mode` is not text, or is outside the known set. The known set is the marker modes
  plus `empirical`, `measured`, `engineering`, `benchmark`, and `real`. A mode such as
  `demo` is unknown.
- Two markers conflict, or a marker conflicts with the declared class. For example,
  synthetic data declared as `engineering_fact`.
- The declared class is unknown, or it is `formal_statistical_evidence`. That class requires
  a `formal_bayes_factor`, which this package keeps `null`.
- No evidence class is declared. The result is `incomplete`, not evidence.
- A ready state has no declared run status, or has an incomplete identity block.
- An unexpected error during classification is itself a rejection: `invalid`, with the
  reason `unexpected_value`.

Reasons never echo untrusted text. Each reason is a fixed code. The only artifact-derived
text in a reason is a recognized status token, and that token comes from the fixed
vocabulary above.

## Identity contract

An `engineering` or `empirical` artifact is evidence-ready only when all four identity
blocks are present. If any is missing, the state is `incomplete` and the missing block is
named in `missing_identities`.

| Block | Required content |
|---|---|
| `source_identity` | `uri` (non-empty) and `sha256` (64 hex characters) |
| `input_identity` | a mapping with `sha256` (64 hex characters) |
| `execution_identity` | `run_id` matching the artifact, non-empty `code_commit`, integer `seed` (not boolean), and `command_identity` (64 hex characters) |
| `artifact_lineage` | `status` equal to `COMPLETE`, and `artifact_sha256` (64 hex characters) |

These blocks are shape-checked and self-declared. Nothing recomputes a digest from artifact
bytes, so a well-formed block is not proof that the bytes match. Verifying identity against
bytes is a separate step that is not implemented here.

The contract is defined in the orchestrator's own vocabulary. It does not read the canonical
`RunRecordV1` directly. A future adapter must map a RunRecord into these blocks, and that
mapping is out of scope here.

## Metrics: null, never zero

- `normalize_metric` keeps missing, boolean, non-numeric, non-finite, and overflowing values
  as `null`.
- A genuine `0` stays `0.0`. Absence is never converted to zero.
- `admit_metrics` returns metrics only for an evidence-ready decision. Otherwise it returns
  `None`, and the report displays `withheld (no evidence-ready artifact)`.

## Where metrics can and cannot go

| Destination | Dry run | Live run |
|---|---|---|
| Run-card summary in `events.jsonl` | `null` | Admitted values only |
| Stage results in `events.jsonl` | `null` | Admitted values only |
| Research-cycle ledger | Never | Never |
| `Report.md`, `EvidenceLogDraft.md`, `OpsQueueItem.json` | Never | Admitted values only. No live stage currently produces metrics, so none appear. |

`_ledger_safe` drops `metrics` and `artifacts` keys at every depth before any stage result
reaches the ledger. Promoting an admitted metric into a claim-bearing ledger record is a
separate, reviewed step, and it is not implemented.

## Run cards

Run cards in `run_cards_dir` are untrusted inputs. The ingest stage classifies each one.

- An unreadable file is recorded as `invalid` with the reason `unreadable_file`.
- Invalid JSON, or nesting so deep that the parser fails, is recorded as `invalid` with the
  reason `malformed_json`.
- Every other card is classified as described above.

Only the classification, the run id if it is a plain identifier, and admitted metrics leave
the stage. The raw card is never forwarded. `run_cards_loaded` counts cards that parsed, not
cards that were admitted. Admission is counted separately as `run_cards_evidence_ready`,
which is always `0` in a dry run. The `source` label is the file name, which the operator
controls.

## Scientific pass and formal Bayes factor

`OrchestratorResult` is a frozen dataclass, and it enforces these invariants at construction:

- `scientific_pass` must be `False`.
- `formal_bayes_factor` must be `None`.
- `scientific_evidence` must be `False`.

Frozen construction also means the invariants cannot be bypassed by assignment afterward.
No independently approved scientific gate exists in this package. When one exists, it must
be introduced as a separate, reviewed change, not by relaxing these checks.

## Claim gate

`assess_claim(claim)` is a pure gate. It decides whether a claim is admissible, and it has
no side effects.

**It is not wired into any write path.** No code in this package calls it. The natural
chokepoint is `ResearchCycleLedger.append_record` in `research_cycle/ledger.py`, which is
outside this change. Until the gate is wired there, a claim written directly to the ledger
bypasses it.

Rules:

- Banned language fails closed, even for a planning claim. Examples: clinical, diagnostic,
  treatment, biomarker, consciousness detection, spiritual attainment, meditation stage,
  causal, mechanistic, and proves. The list is local to this package, and it is a keyword
  screen, not a semantic review.
- A claim that requests `engineering` or `empirical` must be backed by evidence that is
  evidence-ready and matches the requested state. Otherwise it is `invalid`.
- A claim with a non-null `formal_bayes_factor` is `invalid`.
- A `planning` or other non-evidence proposal is `review_required`, never evidence.

## Known limitations

- **Airtable run sync is not gated.** `integrations/airtable_sync.py` reads the same run-card
  files and upserts raw metric values into the Runs table without classification, identity
  checks, or filtering of synthetic or failed runs. It is outside this change, and it is
  listed as an unresolved blocker.
- **The claim gate is not wired** (see above).
- **Identity blocks are self-declared.** They are shape-checked, not verified against bytes.
- **No planning evidence class exists** in `research_cycle.EvidenceClass`. Seeded dry-run
  ledger records use `HYPOTHESIS`, the nearest non-promotable class. Adding a planning class
  belongs in `research_cycle/models.py`, which is outside this change.
- **The dry-run `execute` ledger status `BLOCKED` is pinned** by an existing test (see above).
- **Live execution is not implemented.** No live path in this package produces evidence-ready
  output.
- **Banned-language checks are a keyword screen**, not a semantic review.

## Running the tests

From `apps/awareness_studio/`:

```bash
PYTHONPATH=src pytest tests/orchestrator -q
```

The tests are offline and deterministic. They use synthetic fixtures only and make no
network call. `test_isolated_subprocess.py` runs a dry run in a fresh interpreter with socket
and `urlopen` disabled.
