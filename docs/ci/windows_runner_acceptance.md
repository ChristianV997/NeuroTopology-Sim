# Windows Runner Acceptance Harness

A platform acceptance harness that validates `scripts/run_tests_isolated.py`
(the isolated test runner) by **invoking it through safe subprocesses**. It never
imports or modifies the runner. It exists to give Windows-specific behavioral
evidence that a POSIX CI cannot produce.

- Harness: `tools/runner_acceptance/` (`harness.py`)
- CLI: `scripts/run_windows_runner_acceptance.py`
- Tests: `tests/runner_acceptance/`

> **Honesty rule.** A non-Windows host **cannot** produce evidence that Windows
> process behavior passed. On non-Windows the harness reports
> `platform_status=unsupported`, runs only portable contract tests, and records
> every Windows-specific case as `unsupported` — never `pass`.
>
> **Scientific-integrity note.** Fixtures are synthetic; `evidence_class` is
> `acceptance_synthetic`. This is operational evidence only, never scientific
> evidence.

## Modes

| Host | `platform_status` | What runs |
| --- | --- | --- |
| Windows | `supported` | Portable contracts **plus** Windows runner validations |
| non-Windows | `unsupported` | Portable contracts only; Windows cases → `unsupported` |

## Windows validations (executed only on Windows)

- **new process-group creation** — the worker is terminated via group signalling,
  confirming it was placed in a new group.
- **timeout termination** and **exit code 124** — a hanging batch is killed and the
  runner returns 124.
- **no false PASS after timeout** — the runner reports a timeout, not a pass.
- **descendant-process cleanup / no orphan** — a grandchild spawned by the batch is
  gone after termination (verified with `psutil`).
- **output draining under stdout/stderr flood** — a batch that floods output does
  not deadlock the runner.
- **PowerShell command construction, path quoting, Unicode/space temp paths** —
  see portable contracts (construction is validated everywhere; execution through
  PowerShell only on Windows).

## Portable contracts (run on every platform)

- **PowerShell command construction** — `build_powershell_command` yields
  `powershell -NoProfile -NonInteractive -Command "& 'prog' 'arg' ..."`.
- **Path quoting** — `ps_single_quote` wraps in single quotes and escapes `'` as
  `''`, preserving spaces and Unicode.
- **Unicode + spaces in temp paths** — the runner is invoked on a passing test
  inside a temp directory whose name contains spaces and Unicode; it must exit 0.
- **Executor timeout contract** — the harness's own child executor times out and
  force-kills a sleeping child.
- **Output flood** — a 5 MB stdout flood is fully drained (byte count verified)
  without deadlock.

## Report schema (finite JSON)

Top level: `schema`, `platform`, `platform_status`, `python_version`,
`runner_version` (git commit), `capability`, `evidence_class`, `synthetic`,
`num_cases`, `summary`, `ran_ok`, `windows_behavior_validated`, `results`, `notes`.

Each `results[]` record contains: `test_case`, `category`
(`portable` | `windows_runner`), `platform`, `python_version`, `runner_version`,
`capability_state`, `expected_outcome`, `observed_outcome`, `outcome`
(`pass` | `fail` | `unsupported` | `error`), `timeout_state`
(`not_applicable` | `completed` | `timed_out`), `orphan_state`
(`not_checked` | `none` | `orphaned`), `cleanup_state`
(`not_applicable` | `clean` | `dirty`), `evidence_class`, `synthetic`, `details`.

All floats are finite or `null` (`json_safe`); output uses `allow_nan=False`.

## Usage

```bash
python scripts/run_windows_runner_acceptance.py            # human summary
python scripts/run_windows_runner_acceptance.py --json     # finite JSON
python scripts/run_windows_runner_acceptance.py --output out/acceptance.json
```

Exit code is `0` when no case failed (`unsupported` is neutral), else `1`.

## Safety

- No `shell=True`; every child is launched from an argv list.
- Children run in their own process group/session and are terminated as a tree on
  timeout (POSIX `SIGTERM`→`SIGKILL`; Windows `CTRL_BREAK`→`taskkill /F /T`). The
  parent harness process is never signalled.
- Temporary directories are removed after each case; child processes are bounded
  (one scenario at a time).

## Limitations

- **Windows evidence requires a Windows host.** On POSIX CI the Windows cases are
  `unsupported`; they are implemented but not exercised here.
- Orphan verification and peak sampling use `psutil`; without it those checks are
  skipped, but termination still works.
- The harness validates the runner *as invoked*; it depends on the runner present
  in the repo at run time (`runner_version` records the commit).
- Acceptance evidence is synthetic and operational, not scientific.
