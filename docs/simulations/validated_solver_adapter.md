# Validated local solver adapter

This adapter executes only an explicitly declared, locally available deterministic workload. The caller must provide an exact argv allowlist, code commit, configuration, seed, input identity, provenance, output root, resource budget, and evidence class. Commands use `shell=False`; no solver is discovered, imported, constructed, or downloaded by the adapter.

The default is network-disabled. Python workloads receive a temporary socket guard; non-Python workloads are blocked unless the caller explicitly opts into network-enabled mode. The environment fixes hash seed, locale, timezone, source date, and common numerical thread counts. Output paths must remain inside the explicit output root.

## Success contract

A workload must exit successfully, write every declared output and a finite `completion_manifest.json` with `complete: true`, pass containment checks, and remain within the output budget. Only then does the adapter atomically emit `artifact_manifest.json` and a canonical RunRecordV1-compatible `RunRecord.json`. Artifact checksums are SHA-256 values. Failed, partial, interrupted, blocked, and timed-out executions receive null/empty checksums and never receive a canonical successful run record.

The record preserves code commit, configuration, seed, input identity, provenance, evidence class, resource telemetry, output references, `scientific_pass: false`, and `formal_bayes_factor: null`. A successful local execution is engineering evidence only; it is not scientific validation, empirical provenance, biological evidence, or causal evidence.

## States and recovery

`PASS` is the fully validated execution state. `FAILED` covers non-zero exit and malformed, missing, non-finite, or over-budget output. `TIMEOUT` and `PARTIAL` terminate/withhold canonical output. `BLOCKED` covers missing provenance, allowlist mismatch, unsafe paths, or network policy. `NOT_IMPLEMENTED` means no local adapter implementation is registered for the requested workload.

The execution report is atomically written. On replay, a prior `PASS` report is reused only when the stable run identity and every output checksum still match; otherwise the workload runs again. No external services, AWS, OpenNeuro, DANDI, package installation, daemons, or unrestricted shell execution are used.
