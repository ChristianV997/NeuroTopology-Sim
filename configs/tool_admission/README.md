# Tool admission registry

Machine-readable admission contract for external research tools.
Consumed by a future integration agent. This directory does not import
production code and must not execute solvers, downloaders, or live APIs.

## Files

| Path | Role |
|---|---|
| `tool_registry.yaml` | Per-tool admission records |
| `tool_policies.yaml` | Global constraints the integrator must enforce |
| `source_registry.json` | Evidence URLs and license sources (no credentials) |

Schema version: `1.0`
Review date: `2026-09-05`
Inspected base: `62637a4b9c82c0c258bfc49e28dee1af757b1c25` (`origin/main`)

## Allowed integration modes

`integrate` | `emulate` | `copy_pattern` | `reference` | `reject`

## Allowed admission_status values

`admitted` | `admitted_optional` | `experimental` | `deferred` | `reference_only` | `rejected`

`PASS` is forbidden. Tool admission is not a scientific falsification verdict.
`K > 100` remains the only scientific PASS condition and is owned by PITNN
governance, not by this registry.

## Test policy

Tests under `tests/tool_admission/` read only these files. They must not
browse, download, authenticate, or import `sim/`, `tools/`, or dashboard code.
