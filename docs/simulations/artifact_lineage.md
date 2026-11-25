# Simulation artifact lineage

`scripts/export_simulation_evidence.py` is a read-only extractor for an existing local simulation run directory. It indexes files and small metadata artifacts; it does not execute a solver, import scientific runtimes, download data, or infer dataset labels, biological meaning, or causal interpretation.

## Input and output

Use an explicit local path:

```text
python scripts/export_simulation_evidence.py \
  --run-dir path/to/run \
  --json-out path/to/evidence.json \
  --markdown-out path/to/evidence.md
```

Supported inputs include `RunRecord.json`, `summary.json`, `metrics.json`, `metrics.csv`, checkpoint/resume manifests, validation/quality reports, finite JSON artifacts, resource telemetry, null-model outputs, and partial/failed-run markers. Every indexed file receives a deterministic relative path, role, size, mtime metadata, and SHA-256 checksum. Duplicate content is reported separately from duplicate paths.

The JSON report contains an artifact manifest, run-level provenance, input/configuration/dependency fingerprints, evidence class, claim scope, completeness status, parent/child relationships, diagnostics, and an optional ledger reference. A missing ledger is recorded as a non-blocking absent reference. Output reports are written only when explicitly requested.

## Completeness and safety

`RunRecord.json` plus a summary or metrics artifact are required for `COMPLETE`. Missing provenance is `INCOMPLETE`; malformed JSON or non-finite values are `BLOCKED`; failed and partial markers produce `FAILED` and `PARTIAL`, respectively. Conflicting run IDs produce `CONFLICTING`. No partial or failed run can be reported complete.

Synthetic output is labeled `synthetic_demo_only`. Evidence class and claim scope are read from explicit metadata or remain `unknown`/`unspecified`; the extractor never promotes them. NaN and Infinity are explicit errors, never silently accepted. Incremental scans may reuse a prior checksum only when both size and nanosecond modification time match. The extractor does not verify that metadata claims are scientifically true; it preserves and surfaces them for review.
