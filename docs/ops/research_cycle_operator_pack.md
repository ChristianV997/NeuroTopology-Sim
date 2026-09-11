# Research-cycle operator pack

Read-only orchestrator for **existing** research-cycle audit and validation CLIs.
It does not invent duplicate runners, download data, install packages, mutate git,
start daemons, or execute solvers unless `--allow-solver` is explicit.

**Infrastructure PASS is not a scientific PASS.**
**Synthetic fixtures are not an empirical PASS.**
Inventory is not evidence. This pack never labels scientific results as validated
because infrastructure checks passed.

## Wrappers (not interchangeable)

| Family | Entry | Notes |
| --- | --- | --- |
| POSIX | `scripts/run_research_cycle_audit.sh --output-dir DIR` | bash; uses `python3`/`python` |
| Windows PowerShell | `scripts/run_research_cycle_audit.ps1 -OutputDir DIR` | pwsh/Windows PowerShell; uses `python`/`python3`/`py` |
| Direct | `python -m ops.research_cycle --output-dir DIR` | shared orchestrator |

`--output-dir` is required. Writes happen only under that directory.

## Commands

```bash
# POSIX dry-run with bundled fixtures (no downloads, no solver)
bash scripts/run_research_cycle_audit.sh --output-dir /tmp/rcop-out

# Inventory (no audit writes unless --output-dir is set)
python -m ops.research_cycle inventory --json

# Catalog schema check
python -m ops.research_cycle validate-catalog
```

```powershell
pwsh -File scripts/run_research_cycle_audit.ps1 -OutputDir C:\tmp\rcop-out
```

## Steps (catalog order)

| # | id | Wraps | Default |
| --- | --- | --- | --- |
| 1 | `repository_state` | `git rev-parse HEAD`, `git rev-parse --abbrev-ref HEAD`, `git status --porcelain` | read-only builtin |
| 2 | `schema_validation` | `python -m governance.validate` | existing governance CLI |
| 3 | `research_plan_audit` | `scripts/validate_research_cycle.py --registry` | fixture registry if omitted |
| 4 | `claim_gate` | `scripts/validate_research_claims.py --input/--output` | fixture claims |
| 5 | `artifact_manifest` | `scripts/validate_empirical_source_manifest.py` | fixture manifest |
| 6 | `evidence_graph` | `scripts/compile_research_state.py` (uses `tools.research_report.graph`) | fixture manifest |
| 7 | `cache_policy` | `python -m dataset_acquisition.export_plan` `metadata_only` | no `--execute`, no network |
| 8 | `simulation_campaign` | `scripts/run_benchmark_matrix.py --dry-run` | never `run_research_campaign.py` |
| 9 | `release_evidence` | `scripts/evaluate_performance_release_evidence.py` | performance-only fixture pair |
| 10 | `targeted_tests` | pytest on a **fixed** subset of existing research-cycle / claims / release tests | never `run_tests_isolated.py` |
| 11 | `finite_json_no_network` | `tools.streaming.memory_telemetry.json_safe` / `dumps` | scans `--output-dir` JSON |

Optional extras (`--include-optional`): `release_blockers`, `dataset_provenance`,
`local_ops_healthcheck`, `platform_compat`. Optional steps still write only under
`--output-dir`. `tools.local_ops.runner` loop/daemon mode is not invoked.

Missing wrapped tools are reported as **NOT_AVAILABLE**. They are never silent skip-as-pass.

## Flags

| Flag | Meaning |
| --- | --- |
| `--output-dir` | Required for audit. Only allowed write root. |
| `--catalog` | Catalog JSON (default `ops/research_cycle/catalog.json`) |
| `--registry` / `--claims` / `--empirical-manifest` / `--provenance` | Inputs for wrapped CLIs |
| `--research-state-manifest` / `--performance-pair` / `--candidates` | Inputs for wrapped CLIs |
| `--candidate-id` / `--cache-target-root` | Cache-policy dry-run identity (declared path only) |
| `--benchmark-matrix` | Campaign dry-run matrix |
| `--steps` | Comma-separated step ids |
| `--allow-solver` | Opt-in only. Default campaign stays `--dry-run` and never launches PITNN solvers. |
| `--include-optional` | Run optional catalog extras |
| `--timeout-s` | Override every child timeout |
| `--now` | Frozen timestamp for deterministic reports |
| `--shell-family` | `posix` or `powershell` (wrappers set this) |
| `--no-surfaces` | Skip Obsidian / command-center / RAG emission under `--output-dir` |

## Exit codes

| Code | Status | Meaning |
| --- | --- | --- |
| 0 | PASS | Every selected step passed |
| 10 | INCOMPLETE | Wrapped CLI reported incomplete/unavailable data; no FAILURE/BLOCKED |
| 20 | BLOCKED | Safety gate (missing `--output-dir`, write leak, network token, solver without opt-in, forbidden git) |
| 30 | FAILURE | Child failed or timed out |
| 40 | NOT_AVAILABLE | Catalog/python/git/wrapped CLI missing |

Worst status wins: FAILURE > BLOCKED > NOT_AVAILABLE > INCOMPLETE > PASS.

POSIX and PowerShell wrappers use the same mapping (`20` if `--output-dir` is omitted,
`40` if Python is missing).

## Safety guarantees

1. Read-only default: no mutating git; no deletes.
2. No automatic downloads / network (`--allow-network` is blocked; proxy env cleared).
3. No automatic deletion.
4. No git merge, reset, force-push, or branch rewrite.
5. No package installation.
6. No hidden daemon (`local_ops.runner` loop is not wrapped).
7. No solver execution unless `--allow-solver` (and even then this pack does not invoke `scripts/run_research_campaign.py`).
8. Explicit `--output-dir` required.
9. Bounded timeout on every child command.
10. PowerShell and POSIX wrappers are separate files with separate `--shell-family` values.
11. Missing commands → `NOT_AVAILABLE`, never PASS.
12. Output is finite JSON (`allow_nan=False`; non-finite floats become `null`) plus Markdown.
13. Exit codes distinguish PASS / INCOMPLETE / BLOCKED / FAILURE / NOT_AVAILABLE.
14. Scientific-integrity statements are always present in the report.

## Fixtures

Dry-run defaults (when operator inputs are omitted) live under
`tests/ops/research_cycle/fixtures/`. They are synthetic. They do not authorize
empirical claims.

## Makefile cycle (owned path)

See `ops/research_cycle/Makefile` for `validate-catalog`, `inventory`, `syntax-posix`,
`syntax-pwsh`, `test`, `audit-fixtures`, and `cycle`.
