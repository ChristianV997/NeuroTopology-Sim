# Retrofit inventory reports (Phase 4)

This note describes the **Phase 4 Release / Evidence** reports only.

They are an **engineering inventory** of a local checkout plus the offline
tool-source registry. They are **not scientific evidence**, not a
scientific `PASS`, not launch authority, and not a K>100 gate.

Producer: [`tools/retrofit_inventory/reporting.py`](../tools/retrofit_inventory/reporting.py)

Schema: [`configs/retrofit_inventory/report_schema.json`](../configs/retrofit_inventory/report_schema.json)

Consumed (not rewritten) inputs:

- `build_inventory_snapshot` / `snapshot_to_json` from
  [`tools/retrofit_inventory/scanner.py`](../tools/retrofit_inventory/scanner.py)
- `InventorySnapshot` and related models from
  [`tools/retrofit_inventory/models.py`](../tools/retrofit_inventory/models.py)
- `load_tool_sources` from
  [`tools/retrofit_inventory/tool_sources.py`](../tools/retrofit_inventory/tool_sources.py)
- Fail-closed validators from
  [`tools/retrofit_inventory/validators.py`](../tools/retrofit_inventory/validators.py)

## What these reports are

Six deterministic JSON files, written with `json.dumps(..., sort_keys=True)`
and a trailing newline. Default operator output directory (gitignored):

```
artifacts/retrofit_inventory/
  repository_inventory.json
  artifact_inventory.json
  tool_admission_inventory.json
  ownership_collision_report.json
  retrofit_priority_report.json
  scientific_claim_risk_report.json
```

`write_report_bundle` writes **only** those six filenames under the given
`output_dir`. Do not commit large generated inventories. Real outputs stay
under `artifacts/` (gitignored).

### How to produce them

```python
from datetime import datetime, timezone
from tools.retrofit_inventory.reporting import build_report_bundle, write_report_bundle

frozen = datetime(2026, 9, 6, 0, 0, tzinfo=timezone.utc)
bundle = build_report_bundle(
    repo_root,
    output_dir="artifacts/retrofit_inventory",
    offline=True,
    _now=frozen,  # tests must inject a frozen clock
)
# bundle["reports"]["scientific_claim_risk_report.json"]["scientific_claim_status"]
# is always "not_evidence"
```

`build_report_bundle`:

1. Scans the local root with `build_inventory_snapshot` (or uses an injected
   snapshot in tests).
2. Loads `configs/retrofit_inventory/tool_sources.yaml` via `load_tool_sources`
   (or uses injected rows).
3. Calls QA validators. Failures are **errors**, never warnings.
4. Builds the six envelopes. If validation fails, `status` is `error` and
   `errors` is populated. The module does **not** invent a clean snapshot
   or a clean 15-row registry.

`offline=True` is the only supported mode. `offline=False` is ignored and
recorded as a warning; reporting never imports `requests` / `httpx` /
`urllib` / MarketOS and never opens a network client.

The CLI that will write these files for operators is Integration Phase 5
(`scripts/build_retrofit_inventory.py`). This phase does not add that script.

## Common envelope

Every report includes:

| Field | Meaning |
|---|---|
| `timestamp` | ISO-8601. Inject `_now` / `generated_at` for determinism. |
| `repository_commit` | `snapshot.commit_sha`. |
| `source_hashes` | Snapshot digest, `tool_sources.yaml` content hash (when present), inventory/report schema versions, optional `report_schema.json` hash. |
| `status` | `ok` \| `error` \| `incomplete`. |
| `warnings` | Non-fatal notes (may be empty). |
| `errors` | Fail-closed validation errors. |
| `limitations` | Always includes: inventory ≠ scientific evidence. |
| `next_actions` | Always includes: do not treat as PASS; Integration Phase 5 CLI. |

`status=error` means validators or a fail-closed load/scan found problems.
`status=incomplete` means a required input was missing (no snapshot, or no
tool rows) **and** there were no validation errors. `status=ok` means both
inputs were present and validators returned an empty error list.

## The six files

### `repository_inventory.json`

Files, worktrees/branches, governance paths, declared dependencies, and
overlap findings copied from the snapshot. File hashes follow the scanner
policy (`content_sha256` or `size_path_v1`). Contents of binaries, secrets,
and large files are not stored.

### `artifact_inventory.json`

Rows under `artifacts/`, `outputs/`, and `runs/` with heuristic labels
`synthetic` | `empirical` | `unknown`. Labels come from path tokens or
explicit markers in the scanner. **An empirical label is not a scientific
PASS.** `empirical_label_is_pass` is always `false`.

### `tool_admission_inventory.json`

The fifteen Phase 2 tool-source rows (when the real YAML loaded) plus
`admission_summary` (`count`, `by_adoption_recommendation`,
`by_integration_mode`). Rows are research classifications only. NotebookLM
MCP remains `experimental` / `experimental_only`. If the YAML is missing or
invalid, `tools` stays empty — the reporter does not invent a clean
registry.

### `ownership_collision_report.json`

Snapshot `overlaps` plus `report_fields.claimed_owners` (when present) and
duplicate-ownership strings from `validate_duplicate_ownership`. Basename
collisions and dual-root path overlaps are **path findings**, not label
inference and not scientific claims.

### `retrofit_priority_report.json`

Engineering priority only, derived from `adoption_recommendation` plus
offline / network / privacy risk. Sort is deterministic
(`consider` before `defer` / `reject`; offline before `requires_network`;
then `id`). **This is not a scientific ranking** and does not order tools
by topology, PCI, consciousness, or evidence strength.

### `scientific_claim_risk_report.json`

Must state all of the following:

- Inventory is not evidence.
- `scientific_claim_status` is always `not_evidence`.
- Reports never emit scientific `PASS`.
- Empirical labels ≠ `PASS`.
- The K>100 / scientific PASS gate is **out of scope** for this subsystem.

`inventory_claim_record` from QA is copied as `claim_record`. If a caller
tries to stuff `PASS` into snapshot `report_fields`, validators fail closed
and the report `status` becomes `error`. The report body still uses
`not_evidence`; it does not copy a forbidden status.

## What these reports are NOT

- Not empirical evidence.
- Not a scientific `PASS` or `FAILED` verdict on a hypothesis spec.
- Not a K>100 gate, PCI validation, or topology proof.
- Not launch authority for adapters, vendors, or live sensors.
- Not a license opinion (license strings on tool rows are research labels).
- Not an ontology, consciousness claim, or Theory of Everything.
- Not permission to download datasets, call live APIs, or store credentials.

Guardrails from `AGENTS.md` still apply: no clinical claims, no ontology
promotion, no proof claims, no real-data execution, no live APIs in tests,
no Q/Qabs/fdress proof framing.

## Determinism

- Inject `_now` or `generated_at` in tests. Do not assert wall-clock time.
- Snapshot list order comes from `InventorySnapshot.to_dict`.
- Tool rows are sorted by `id`.
- Priority candidates are sorted by the engineering key, then `id`.
- JSON dumps use `sort_keys=True` and `ensure_ascii=True`.

Two builds of the same checkout, same YAML, and same frozen clock must
byte-compare equal.

## Offline / test policy

- No `requests`, `httpx`, `urllib`, or MarketOS imports in `reporting.py`.
- No dataset downloads.
- No credentials or API keys in tests.
- Reporting tests live in `tests/retrofit_inventory/test_reporting.py` and
  import existing fixtures. They do not edit QA `validators.py`.

## Next action

Integration Phase 5 owns `scripts/build_retrofit_inventory.py` and
`docs/retrofit_inventory_cli.md`. That CLI should call
`build_report_bundle` / `write_report_bundle` and keep real outputs under
`artifacts/retrofit_inventory/`. Do not merge this draft PR from Phase 4
alone.
