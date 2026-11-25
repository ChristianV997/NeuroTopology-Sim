# Capability snapshots

Additive sidecar for optional-backend probe state. This layer calls
`shared.tooling.capability_registry` and does not change `RunRecordV1`.

Owned files:

- `shared/tooling/capability_snapshot.py`
- `tests/tooling/test_capability_snapshot.py`
- `docs/tooling/capability_snapshots.md`

Do not edit the registry YAML or `capability_registry.py` from this layer.

## Schema

`NeuroTopologySim.CapabilitySnapshot.v1`

Each tool record stores:

- `tool_name`
- `availability`
- `version` (`null` when unknown or not imported)
- `capability_category`
- `provenance`
- `network_requirement`
- `determinism_state`
- `shapes`
- `units`
- `memory_risk`
- `unavailability_reason` (`null` when available)
- `classification`
- `scientific_support` (always `not_claimed`)

A listed package name is never installed support.

## Attaching to a run without changing RunRecordV1

Write a sidecar file next to the canonical record:

```text
runs/<run_id>/RunRecord.json
runs/<run_id>/capability_snapshot.json
```

Or keep an extra mapping that is *not* `RunRecordV1`:

```python
from shared.tooling.capability_snapshot import (
    ATTACHMENT_KEY,
    attach_capability_snapshot,
    capture_snapshot,
    serialize_snapshot,
)

snapshot = capture_snapshot(offline=True, allow_remote=False)
sidecar = attach_capability_snapshot({"run_id_ref": "abc123"}, snapshot=snapshot)
Path("runs/abc123/capability_snapshot.json").write_text(serialize_snapshot(snapshot))
```

`attach_capability_snapshot` refuses mappings that look like `RunRecordV1`
(`schema_version` + `run_kind`). Downstream runners must not copy snapshot
fields into the canonical record schema.

## Offline and remote policy

- Default `offline=True`.
- Live/optional-network tools (`pylsl`, `brainflow`) are `offline_blocked`.
- `notebooklm_mcp` stays `opt_in_required` and is never connected here.
- Unknown tool ids and malformed snapshot payloads raise
  `CapabilitySnapshotError`.
- Importing this module does not import optional scientific backends.
