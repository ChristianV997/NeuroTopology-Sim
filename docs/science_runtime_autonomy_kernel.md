# Science Runtime Autonomy Kernel (P18.2)

---

## Purpose

P18.2 adds a lightweight replay-safe runtime/autonomy layer around the
existing P18.1 DS005620 benchmark chain. It does NOT clone my_OS. It does NOT
add frontend, WebSocket, Redis, Celery, vector DB, or UI code.

The kernel provides:

- Deterministic replay-safe event envelopes (sha256 `replay_hash`)
- Append-only JSONL event log
- Structured runtime state loaded from P18.1 artifacts
- Runtime snapshots with sha256 IDs
- Task registry of 17 known pipeline tasks
- Real/local preflight check
- Artifact manifest, evidence packet, and paper skeleton generators
- CI workflow for DS005620 E2E mock
- `make ds005620-autonomy-check` target

---

## Safe Claim

ScienceR-Dsim now has a lightweight replay-safe runtime kernel for DS005620
benchmark execution artifacts, adapted from my_OS patterns, without changing
scientific claim semantics.

---

## Modules

### `sciencer_d/btc_icft/runtime/`

| Module | Purpose |
|---|---|
| `events.py` | `ScienceEventEnvelope`, `build_event`, `deterministic_replay_hash` |
| `event_log.py` | Append-only JSONL: `append_event`, `tail_events`, `scan_events`, `clear_events` |
| `state.py` | `ScienceRuntimeState`, `build_runtime_state`, `build_runtime_snapshot` |
| `task_inventory.py` | `ScienceTaskRegistry`, `build_default_science_task_registry` (17 tasks) |
| `snapshots.py` | `ScienceRuntimeSnapshotStore`, `write_runtime_snapshot`, `restore_runtime_snapshot` |

### `sciencer_d/btc_icft/p18/ds005620_real_local_preflight.py`

Inspects all prerequisites for a live P18.1 real/local execution:
- Reviewed contract (status, join_keys)
- Metadata file (extension, existence)
- Canonical signal blocks (4 required files)
- Level M features_m_signal.csv
- Level T features_t_signal.csv

Returns `all_ready` flag and `next_action` from the chain:
`provide_metadata → run_p17_1 → run_p19_2 → run_p9 → run_p10 → run_p18_1_real_local_execute`

---

## Pipelines

### `inspect_science_runtime`

```bash
python -m sciencer_d.btc_icft.pipelines.inspect_science_runtime \
  --artifact-root outputs/btc_icft/ds005620_real_benchmark_execution_mock \
  --out outputs/btc_icft/science_runtime_inspection
```

Writes 5 artifacts:
- `runtime_state.json` — structured state from P18.1 artifacts
- `task_inventory.json` — 17-task registry
- `runtime_snapshot.json` — sha256-ID'd snapshot
- `runtime_event_log.jsonl` — `runtime_inspected` event
- `runtime_report.md` — human-readable summary

### `preflight_ds005620_real_local`

```bash
python -m sciencer_d.btc_icft.pipelines.preflight_ds005620_real_local \
  --reviewed-contract outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json \
  --metadata data/DS005620/events.tsv \
  --signal-blocks outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620 \
  --level-m outputs/btc_icft/eeg_level_m/DS005620 \
  --level-t outputs/btc_icft/eeg_level_t/DS005620 \
  --out outputs/btc_icft/ds005620_real_local_preflight
```

Returns exit code 0 when all ready, 1 when blocked.

---

## Tools

| Tool | Purpose |
|---|---|
| `tools/build_ds005620_artifact_manifest.py` | Walk execution root, write `artifact_manifest.json` |
| `tools/export_ds005620_evidence_packet.py` | Write `evidence_packet.json`, `evidence_packet.md`, `notion_import_payload.json` |
| `tools/generate_ds005620_paper_skeleton.py` | Write `paper_skeleton.md`, `reviewer_checklist.md`, `negative_space_disclaimers.md` |

---

## Makefile Targets

| Target | Command |
|---|---|
| `ds005620-build-manifest` | Build artifact manifest from mock E2E root |
| `ds005620-export-evidence` | Export evidence packet |
| `ds005620-paper-skeleton` | Generate paper skeleton |
| `ds005620-inspect-runtime` | Inspect runtime state |
| `ds005620-preflight` | Run real/local preflight (no-args, shows blockers) |
| `ds005620-test-runtime` | Run all 8 P18.2 test files |
| `ds005620-autonomy-check` | Full gate: mock E2E → validate → manifest → evidence → skeleton → inspect → test |

---

## CI

`.github/workflows/ds005620-e2e.yml` triggers on btc_icft changes and runs:

1. `pytest tests/btc_icft/` — 629 tests
2. `make ds005620-e2e-mock` — full chain
3. `make validate-ds005620-e2e` — artifact validator
4. `make ds005620-autonomy-check` — kernel check
5. `make ds005620-ontology-check` — ontology claim evaluation (see `docs/ontology_layer.md`)

---

## Evidence Packet Promotion Decision

The evidence packet always records `promotion_decision: "engineering_runtime_validated_only"`.

A successful mock E2E run does NOT demonstrate, measure, or assert:
- Internal subjective experience of any kind
- Awareness, sentience, or any related property
- Liberation, enlightenment, or soteriological states
- Any metaphysical or ontological claim about any subject

---

## Event Model

```python
@dataclass
class ScienceEventEnvelope:
    event_id: str        # uuid4[:12]
    type: str
    ts: str              # ISO 8601 UTC
    source: str
    payload: dict
    replay_hash: str     # sha256[:16] of {type, payload}
    event_version: int   # always 1
    correlation_id: Optional[str]
    sequence_id: Optional[int]
```

`replay_hash` is deterministic: same type + same payload → same hash.
Different sources or timestamps do NOT affect the hash.

---

## RuntimeState Next-Action Chain

| Current state | Next action |
|---|---|
| No execution artifact | `run_mock_e2e` |
| Mock E2E not run | `run_mock_e2e` |
| Manifest missing | `build_artifact_manifest` |
| Evidence packet missing | `export_evidence_packet` |
| Paper skeleton missing | `generate_paper_skeleton` |
| All done | `ready_for_real_local_preflight_or_review` |

---

## Guardrails

P18.2 does NOT:
- Clone my_OS wholesale
- Add frontend, WebSocket, Redis, Celery, vector DB, or UI code
- Reimplement P18.1
- Implement Level O/C/Q
- Download datasets
- Make empirical, metaphysical, ontological, or soteriological claims
- Use any of the 15 banned phrase substrings

All P18.2 artifacts are scanned for banned phrases before output.
The paper skeleton and evidence packet both include explicit negative-space
statements that avoid naming the forbidden concepts literally.

---

## P21 DS005620 Autonomous Iteration Runtime

P21 adds a safe autonomous iteration controller that runs all safe mock/validation/planning/gate steps in order, records decisions in a structured event log, and stops at manual real-data or human-review boundaries.

**Safe claim**: P21 adds a safe autonomous iteration runtime that executes mock/planning/validation steps, records decisions, and stops at manual real-data or human-review boundaries.

**Module**: `sciencer_d/btc_icft/runtime/ds005620_autonomous_iteration.py`

**CLI**: `python -m sciencer_d.btc_icft.pipelines.run_ds005620_autonomous_iteration`

**Makefile targets**:
- `make ds005620-autonomous-iteration` — run all 14 safe auto steps
- `make ds005620-autonomous-iteration-dry-run` — plan without executing

**Outputs** (`outputs/btc_icft/ds005620_autonomous_iteration/`):
- `iteration_state.json`, `iteration_plan.json`, `iteration_results.json`
- `iteration_decision_log.json`, `iteration_next_action.json`
- `iteration_artifact_index.json`, `iteration_report.md`, `iteration_events.jsonl`

**The loop never executes real DS005620 data, downloads data, confirms peer review, or weakens any guardrail.**

See `docs/ds005620_autonomous_iteration_runtime.md` for full documentation.
