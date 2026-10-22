# Batch 3 Offline Integration Harness

Status: **implemented**. Deterministic, fixture-only runner that composes
merged-main research-cycle stages into one synthetic end-to-end workflow for
**execution-order and failure-propagation** testing.

It does **not** reimplement adapters, benchmark scientific performance, download
data, install packages, execute harvested code, or run arbitrary commands from a
manifest.

Owned paths:

- `tools/batch3_offline_integration/`
- `tests/tools/batch3_offline_integration/`
- `docs/tools/batch3_offline_integration.md`
- `scripts/run_batch3_offline_integration.py`

## Related harnesses (not forked)

Audited and left alone because they solve different problems:

| Path | Purpose |
|---|---|
| `tools/release_readiness/research_cycle_smoke/` | Release-decision matrix over static stage fixtures |
| `ops/research_cycle/runner.py` | Subprocess catalog operator pack (argv allowlist) |
| `tests/integration/research_cycle/` | File-chain contract inspector |
| `tools/research_cycle_preflight/` | Single preflight gate (reused here as a stage) |
| `scripts/assemble_ecosystem_run.py` | Topology ecosystem assembly |

## Fixed allowlist (in-process callables)

1. `load_synthetic_fixture` — local fixture producer
2. `plan_quality` → `tools.research_plan_quality.rubric.evaluate_plan`
3. `claim_gate` → `tools.research_claim_gate.gate.evaluate_claim`
4. `preflight` → `tools.research_cycle_preflight.compose.run_preflight`
5. `registry_probe` → `tools.research_cycle.registry.ResearchCycleRegistry`
6. `release_evaluate` → `tools.research_cycle_release.evaluator.evaluate_research_cycle_release`
7. `optional_artifact_lineage` — fixture substitute only; caller paths are never scanned

The artifact-lineage slot is deliberately a fixture substitute. A caller-supplied
`--prior-run-dir` is rejected without scanning the directory; run trees may
contain participant or dataset payloads. The report records the rejection and
does not reflect the path or its contents. Missing optional components are
represented by a clearly marked fixture substitute with
`actual_upstream_producer_ran=false`.

## Input and resource boundary

- `--fixture-name` accepts only one of the five source-controlled filenames in
  the bundled `fixtures/` directory; absolute paths, traversal, separators,
  symlinks, and junctions are rejected.
- Both the primary request fixture and `release_bundle_synthetic.json` are read
  through the same contained `_read_fixture` loader: opened read-only and capped
  at 1 MiB. Where the platform exposes `O_NOFOLLOW`, it is used for the final
  file open alongside `stat.S_ISREG` verification. This is not a defense against
  hostile concurrent replacement of parent directories (TOCTOU) or a compromised
  checkout.
- Malformed, duplicate-key, non-finite, non-object, or oversized fixtures
  produce a rejected stage and a nonzero CLI status; rejected external paths are
  represented as `<rejected>` in reports.
- An empty stage selection, a duplicate stage selection, or an unknown
  forced-failure stage are invalid API inputs rather than successful runs.
- A bounded API stage selection is diagnostic/partial only. The overall
  `workflow_executed_successfully` flag is true only when every globally
  required stage is selected and explicitly succeeds; optional-only, partial, or
  prerequisite-skipped selections cannot pass through vacuous truth.
- Required stages fail closed: `plan_quality` requires `overall_status == "READY_FOR_EXECUTION"`,
  `claim_gate` requires an explicit admissible engineering/synthetic decision with
  `scientific_pass == False`, `preflight` requires `cleared_for_execution == True`
  and `operational_readiness == "READY"`, `registry_probe` requires registered
  hypothesis and plan records, and `release_evaluate` requires `decision == "SYNTHETIC_ONLY"`
  with `synthetic_flag == True` and `scientific_pass_emitted == False`. Required
  stages cannot satisfy downstream dependencies via `fixture_substituted`.
- The runner creates no intermediate or temporary files. `--output` is an
  explicit caller-selected report destination.
- The no-network guard (`no_network()`) replaces Python socket entry points
  (`socket.socket`, `socket.create_connection`, `socket.getaddrinfo`) during
  execution. It is an in-process Python guard, not an operating-system sandbox;
  it does not claim to constrain native C extensions, pre-cached socket
  references, or unrelated processes.
- No caller-provided run directory is opened, no dataset is downloaded, and no
  participant payload is read by this fixture-only runner.

## Result semantics

- `evidence_class = batch3_offline_integration_engineering`
- `result_label = ENGINEERING_ONLY` (release stage may surface `SYNTHETIC_ONLY`)
- `workflow_executed_successfully` is distinct from scientific validity
- `scientific_validity_claimed` / `scientific_pass_emitted` always false
- No network access, installs, dataset downloads, or caller-run scans

## CLI

```bash
python -m tools.batch3_offline_integration \
  --fixture-name workflow_request.json \
  --output /tmp/batch3_offline_integration_report.json

# or
python scripts/run_batch3_offline_integration.py --json-stdout
```

Exit code `0` only when required stages succeed in allowlist order and no input
is rejected. Invalid fixture paths and unsupported `--prior-run-dir` inputs
exit nonzero with a structured JSON report when `--json-stdout` is requested.
