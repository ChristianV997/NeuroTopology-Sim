# Awareness Studio research-cycle ledger

The research-cycle ledger is an additive, local-only contract linking:

`SourceSnapshot → EvidenceRecord → Claim → Hypothesis → ExperimentSpec → RunRecord → ArtifactManifest → ValidationReport → TheoryRevision`

The `RunRecord` node is represented by `RunRecordLink`. It stores the canonical
`RunRecordV1` identifier, schema version, and checksum; it does not define or
replace `runs/run_record.py`.

## Records and evidence

Every immutable typed record includes a stable identifier, cycle identifier,
parent and child links, evidence class, claim scope, scientific limitations, and
status. The allowed evidence classes are:

`engineering_fact`, `benchmark_result`, `synthetic_demonstration`,
`descriptive_empirical`, `proxy_inference`, `formal_statistical_evidence`,
`hypothesis`, `speculation`, and `unsupported_claim`.

Synthetic demonstrations remain synthetic and cannot become empirical evidence.
Proxy measurements cannot be recorded as causal or mechanistic claims. A
complete ledger is an audit trail, not a scientific PASS, and statuses such as
`INCONCLUSIVE`, `BLOCKED`, `FAILED`, and `REVIEW_REQUIRED` are preserved.
There is no automatic claim promotion or publication behavior.

## Event contract

Each event contains `cycle_id`, stable `event_id`, monotonic per-cycle
`sequence`, `event_type`, `producer`, status, payload, `previous_hash`,
`event_hash`, and schema version `awareness-studio-research-cycle-event.v1`.
Unknown event types and malformed payloads raise explicit errors. Event hashes
form a per-cycle chain; retries with identical content are idempotent.

## Storage and recovery

`ResearchCycleLedger(path)` creates its own SQLite database. Connections enable
WAL mode, foreign keys, a busy timeout, and synchronous transactional writes.
Each mutation uses `BEGIN IMMEDIATE`, so sequence allocation is protected across
independent writers. SQLite rollback provides recovery after an interrupted
write; `recover(cycle_id)` verifies database integrity, event sequence/hash
chains, record JSON, and record checksums.

Finalizing a cycle appends a finalization event and freezes it. New records or
events are rejected after finalization. Revisions use `create_child_cycle`,
which links a new cycle to its parent without editing the frozen cycle.

## Deterministic export

`export_json(cycle_id)` returns a canonical JSON snapshot with an export
checksum. `export_jsonl(cycle_id)` returns one canonical event per line. JSON
serialization is sorted and compact, and unavailable/non-finite values become
JSON `null`; input identifiers, checksums, and scientific status remain strict.

The module performs no network access and makes no model calls. Local fixtures
are suitable for engineering tests, but cannot support biological, causal, or
other empirical claims by themselves.
