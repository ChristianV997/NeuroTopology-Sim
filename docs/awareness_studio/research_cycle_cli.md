# Research Cycle Inspection CLI

Owner: `tools/research_cycle_cli/**`, `scripts/inspect_research_cycle.py`,
`tests/research_cycle_cli/**`.

## What this is

A **read-only** operator tool for inspecting research-cycle state: which
cycles exist and what state they're in, which claims lack provenance,
which hypotheses have no experiment, which runs lack artifacts, which
artifacts lack validation, which evidence is synthetic/proxy/descriptive/
formal, which records are duplicated or superseded, which outputs are
stale, and what's blocking a release or report. It never writes to any
data source, never executes anything it reads, never contacts the
network, and never invents a record that wasn't actually found.

## Batch 1 sources (read-only, not imported)

This CLI is a protocol-compatible reader against three independently
owned systems' output formats. It does not import any of them — every
reader in `tools/research_cycle_cli/` is a plain-dict parser mirroring
the shape documented in the real (Batch 1 / codex) source, read via
inspection, never as a hard dependency:

- **The research-cycle ledger** — a SQLite database (`tools/research_cycle_cli/ledger_reader.py`
  mirrors the schema in `apps/awareness_studio/src/awareness_studio/research_cycle/ledger.py`):
  tables `cycles`, `records`, `record_links`, `events`. Opened with SQLite's
  own `mode=ro` URI flag, so it is structurally impossible for this CLI
  to write to it. Nine record types live in the `records` table's
  `payload_json` (`source_snapshot`, `evidence_record`, `claim`,
  `hypothesis`, `experiment_spec`, `run_record`, `artifact_manifest`,
  `validation_report`, `theory_revision`), all sharing the nine-value
  `evidence_class` vocabulary and the eight-value `status` vocabulary
  below.
- **The scientific claim gate's report** (`tools/research_cycle_cli/claim_gate_reader.py`
  mirrors `tools/research_claim_gate/gate.py`'s `ClaimGateResult.to_dict()`):
  a JSON array/object or JSONL file of per-claim decisions.
- **The simulation-artifact extractor's report(s)** (`tools/research_cycle_cli/artifact_reader.py`
  mirrors `tools/simulation_artifacts/extractor.py`'s `extract_run()`
  return value): one JSON file per scanned run directory, as written by
  `scripts/export_simulation_evidence.py`.

No "evidence graph writer" module was found in this checkout (searched
`origin/main` and same-day Batch 1 branches) — the ledger's own
`record_links` table (`parent_id`/`child_id` pairs, scoped per cycle)
**is** the evidence graph this CLI exposes under the `graph` mode. If a
dedicated evidence-graph export format is introduced later, this CLI's
`graph` mode is the natural place to add a second reader for it.

If a source isn't supplied, or a Batch 1 module's real output isn't
available in a given environment, every mode still runs — the
unavailable source is reported as `"available": false` with an explicit
`error`, never silently skipped or fabricated.

### Shared vocabularies (`guardrails.py`)

- `LEDGER_STATUSES`: `PENDING, IN_PROGRESS, COMPLETED, INCONCLUSIVE, BLOCKED, FAILED, REVIEW_REQUIRED, FINALIZED`.
- `EVIDENCE_CLASSES` (identical across the ledger, the claim gate, and
  this repo's own earlier compilers): `engineering_fact, benchmark_result,
  synthetic_demonstration, descriptive_empirical, proxy_inference,
  formal_statistical_evidence, hypothesis, speculation, unsupported_claim`.
- `CLAIM_GATE_DECISIONS`: `CLAIM_ADMISSIBLE, CLAIM_REQUIRES_REVIEW,
  CLAIM_DOWNGRADED, CLAIM_REJECTED, CLAIM_INCOMPLETE, CLAIM_SYNTHETIC_ONLY,
  CLAIM_PROVENANCE_INVALID, CLAIM_NOT_COMPARABLE`.
- `ARTIFACT_RUN_STATUSES`: `COMPLETE, INCOMPLETE, PARTIAL, FAILED, CONFLICTING, BLOCKED`.

A value outside its vocabulary is never guessed into a nearby one — it's
kept as `"unknown"` and a `unknown_vocabulary_value` diagnostic is
recorded.

## "Frozen / active / blocked / failed / incomplete" mapping

A ledger cycle's `finalized` flag and `status` field are independent —
`classify_cycles` (`queries.py`) puts a cycle in every group its data
actually supports, so a cycle can be `frozen` (finalized) in any terminal
status:

| Group | Condition |
|---|---|
| `frozen` | `finalized = true` |
| `active` | `status = "IN_PROGRESS"` |
| `blocked` | `status = "BLOCKED"` |
| `failed` | `status = "FAILED"` |
| `incomplete` | `status ∈ {PENDING, REVIEW_REQUIRED, INCONCLUSIVE}` |
| `other` | anything else (including `COMPLETED`/`FINALIZED` on their own) |

## CLI modes

```bash
python -m scripts.inspect_research_cycle <mode> \
    --ledger-db path/to/ledger.sqlite3 \
    --claim-gate-report path/to/claims.json \
    --artifacts-dir path/to/artifact_reports/ \
    --format json
```

| Mode | Answers |
|---|---|
| `summary` | The full deterministic overview (default mode's natural entry point). |
| `cycle` | Cycle state and group membership; add `--cycle-id` to focus on one cycle. |
| `claims` | Every ledger claim + claim-gate result, and which claims lack provenance. |
| `hypotheses` | Every ledger hypothesis, and which have no `experiment_spec` targeting them. |
| `artifacts` | Artifact reports, which runs lack artifacts, which artifacts lack validation, orphan reports. |
| `graph` | The ledger's `record_links` (parent/child pairs) plus a `record_id → {record_type, cycle_id}` index. |
| `blockers` | The unified blocker list that also drives the exit code. |
| `stale` | Each artifact report's own `stale` diagnostic (from its manifest diff — never recomputed here). |
| `export` | Writes `inspection_report.json`, `inspection_report.md`, `inspection_summary.txt` to `--output-dir` (**required** for this mode only) and also prints the terminal summary. |
| `validate` | Fast schema-conformance check: source availability + diagnostics only, no query suite. |

`--format {text,json,markdown}` (default `text`) controls every mode
except `export`, which always writes all three. `--now` pins
`generated_at` (and therefore `report_sha256`) for deterministic runs.

## Safety guarantees (enforced in code, not just documented)

1. **Read-only by default** — `ledger_reader.py` opens the SQLite file
   with the `mode=ro` URI flag; no `INSERT`/`UPDATE`/`DELETE`/`CREATE`
   statement exists anywhere in this package.
2. **No hidden writes** — every mode except `export` only ever prints to
   stdout.
3. **Export writes only to an explicitly supplied output directory** —
   `export` mode raises (`error: export mode requires --output-dir`,
   exit 2) if `--output-dir` is omitted; no default/implicit path exists.
4. **No network access** — no `socket`/`urllib`/`requests`/`subprocess`
   import anywhere in the package (see `test_no_heavy_imports.py`'s
   static AST scan).
5. **No solver imports** — same scan also rejects `mne`/`scipy`/`torch`/
   `ripser`/`gudhi`/`boto3`/`botocore`/`sklearn`.
6. **No automatic retries** — every read happens exactly once; a failure
   becomes a diagnostic, not a retry loop.
7. **No claim promotion** — this CLI reports `evidence_class`/`decision`
   values exactly as read; it contains no code path that upgrades one
   value to another.
8. **No automatic deletion** — no delete/remove call anywhere in the
   package.
9. **No dataset downloads** — `artifact_reader.py` reads only
   already-exported report *files*, never a run directory or dataset
   itself.
10. **Missing records must be reported, not invented** — every `_reader.py`
    module returns `"available": false` + an explicit `error` string for
    an absent/unreadable source, and every query function reports an
    empty result rather than fabricating one when its inputs are absent.
11. **Synthetic and proxy evidence must remain visibly labeled** —
    `evidence_class_breakdown` keeps ledger records, claim-gate results,
    and artifact reports in three separate, always-visible buckets; nothing
    is merged into one ambiguous total.
12. **Invalid JSON must produce an explicit diagnostic** — every reader
    catches `json.JSONDecodeError`/`sqlite3.Error` and emits an
    `invalid_json`/`invalid_database` diagnostic rather than raising or
    silently skipping the record.

## Exit codes

| Code | Meaning | Condition |
|---|---|---|
| `0` | Clean | No invalid data, no blockers, no missing sources, no incomplete-signal findings. |
| `1` | Incomplete | A source wasn't supplied/found, or a non-blocking gap was found (missing provenance, a hypothesis without an experiment, a run without artifacts, an artifact without validation, a stale output) — but nothing invalid or explicitly blocked. |
| `2` | Invalid | At least one `invalid_json`/`invalid_database` diagnostic was recorded — checked first, since findings computed against unparseable data can't be trusted. |
| `3` | Blocked | At least one blocker exists (a `BLOCKED`/`FAILED` cycle, a `CLAIM_REJECTED`/`CLAIM_PROVENANCE_INVALID` claim-gate decision, or an `invalid_*` diagnostic that also matches a blocker condition) and nothing invalid was found first. |

## Determinism

`compile_inspection(...)` is a pure function of its arguments and the
contents of the files/database it's pointed at — no network calls, no
wall-clock reads unless `--now`/`now=` is omitted. Every list in the
report is explicitly sorted before being returned. `report_sha256` is a
sha256 of the full report (`json.dumps(..., sort_keys=True,
allow_nan=False)`), computed last and excluded from its own input — two
runs against the same sources and the same `--now` produce byte-identical
JSON.

## No solver imports, no heavy dependencies

`tools/research_cycle_cli/**` and `scripts/inspect_research_cycle.py`
import only the Python standard library (`sqlite3`, `json`, `hashlib`,
`pathlib`, `dataclasses`, `argparse`, `datetime`) — no `mne`, `scipy`,
`torch`, `ripser`, `gudhi`, `boto3`/`botocore`, or `sklearn`, and no
`socket`/`urllib`/`requests`/`subprocess`. Verified by a static AST
import scan in `tests/research_cycle_cli/test_no_heavy_imports.py`, plus
an isolated subprocess run of the CLI in the same file.
