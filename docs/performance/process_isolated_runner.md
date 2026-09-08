# Process-Isolated Memory Benchmark Runner

Runs each benchmark configuration in its own **child process** so peak-RSS and
timeouts are attributable per configuration, and a hung or crashing child cannot
corrupt sibling measurements or take down the parent. This directly addresses the
integrated branch's timeout cases and the fact that peak RSS includes interpreter
and scientific-library imports (not chunk working set).

- Runner: `tools/streaming/process_runner.py`
- Orchestrator + self-contained child workload: `scripts/run_process_isolated_benchmark.py`
- Tests: `tests/performance/test_process_isolated_runner.py`

The runner imports no streaming/kernel/benchmark code and runs no scientific
workload. It launches an arbitrary child *command* (argv) and parses the child's
telemetry JSON.

> **Scientific-integrity note.** Fixtures are synthetic and deterministic —
> performance evidence only, never scientific evidence. A timeout or crash is an
> operational outcome, **not** a result.

## Why process isolation

- **Attributable peak RSS.** `ru_maxrss` (POSIX) is a *process-lifetime* peak. In
  a single long-lived process, one config's peak is contaminated by every earlier
  config and by imports. A fresh child per config makes the peak attributable —
  though it still includes that child's interpreter + imported libraries, so it is
  **not** the chunk working set (compare like-for-like on the same host).
- **Timeout containment.** A hung configuration is killed without affecting others.
- **Crash containment.** A segfault or `MemoryError` in one child does not abort
  the matrix.

## Outcomes

Each child is classified into exactly one `Outcome`:

| Outcome | Meaning |
| --- | --- |
| `pass` | exit 0, telemetry parsed, `correctness_ok` not false, required metrics present |
| `correctness_failure` | child reported `correctness_ok: false` |
| `timeout` | exceeded the hard timeout; process group terminated |
| `child_crash` | non-zero exit or killed by a signal (not our timeout) |
| `missing_metric` | ran and parsed, but a **required** metric is absent |
| `infrastructure_failure` | could not launch, or exit 0 with no parseable telemetry |

Correctness failure, timeout, and crash are kept distinct from a pass; missing
metrics are distinct from infrastructure failures.

## Telemetry captured per child

`exit_code`, `term_signal`, `timed_out`, `elapsed_s`, `stdout`/`stderr` (truncated
with a flag), `checksum`, `tracemalloc_peak_bytes`, `peak_rss_bytes` (child-emitted
via `resource`), `parent_sampled_peak_rss_bytes` (best-effort psutil polling of the
child tree), `correctness_ok`, `missing_metrics`, `parse_error`, and the raw
`telemetry`. Unavailable metrics are `null` — never `0`.

Two RSS sources are provided and may differ:
- **child-emitted** `peak_rss_bytes` — the child's own `ru_maxrss` (process-lifetime
  peak for that child).
- **parent-sampled** `parent_sampled_peak_rss_bytes` — max over polled samples of the
  child tree's summed RSS. This is approximate (polling can miss short spikes) and
  is `null` when `psutil` is unavailable.

## Timeout handling & orphan cleanup

- Children start in a new session/process group (`start_new_session=True` on POSIX;
  `CREATE_NEW_PROCESS_GROUP` on Windows).
- On timeout the whole group/tree is terminated: **POSIX** sends `SIGTERM` to the
  group, waits a grace period, then `SIGKILL`; **Windows** sends `CTRL_BREAK`, then
  falls back to `taskkill /F /T`. Grandchildren are killed with the group, so no
  orphans are left. After termination the pipes are drained to avoid deadlock.
- A timeout never yields a checksum or a "valid" measurement; it is recorded as
  `timeout` with `timed_out: true`.

## Bounded parallelism & sequential mode

`run_matrix(..., max_workers=N)` runs at most `N` children concurrently via a
thread pool (each thread owns one subprocess). `sequential=True` (or `max_workers=1`)
runs configurations one at a time in input order for deterministic diagnosis.
There is no unbounded fan-out; process count is capped by `max_workers`.

## Atomic JSON reports

Reports are written with a temp file in the destination directory followed by
`os.replace`, so a crash mid-write never leaves a partial report. All numbers are
finite (`json_safe` maps NaN/Inf to `null`); `json.dumps(..., allow_nan=False)` is
used so invalid JSON can never be emitted.

## Usage

```bash
# Bounded matrix, sequential, atomic report:
python scripts/run_process_isolated_benchmark.py \
    --samples-list 20000 80000 --channels-list 8 32 \
    --timeout-s 60 --sequential --output out/report.json

# Bounded parallelism (at most 2 children at once):
python scripts/run_process_isolated_benchmark.py --max-workers 2 --json
```

Programmatic:

```python
from tools.streaming.process_runner import run_matrix, build_python_command

def builder(cfg):
    return build_python_command("scripts/run_process_isolated_benchmark.py",
                                ["child", "--config-json", __import__("json").dumps(cfg)])

report = run_matrix(builder, [{"samples": 20000, "channels": 8, "seed": 0}],
                    timeout_s=60, sequential=True, output_path="out/report.json")
```

Exit code of the CLI is `0` when every configuration passed, else `1`.

## Cross-platform notes

- Commands are built as **argv lists** (`build_python_command`) and run with
  `shell=False`, avoiding POSIX-vs-PowerShell quoting differences. To run through
  PowerShell explicitly, wrap the argv with
  `["powershell", "-NoProfile", "-Command", ...]`.
- Windows termination uses `CREATE_NEW_PROCESS_GROUP` + `CTRL_BREAK`/`taskkill`;
  POSIX uses session process groups. The POSIX path is exercised in CI; the
  Windows path is implemented but not covered by these tests.

## Limitations

- `peak_rss_bytes` includes interpreter and imported-library memory; it is **not**
  the chunk working set and is hardware/allocator dependent. Use it for
  per-configuration, same-host comparisons only.
- Parent-sampled RSS is best-effort and approximate (poll interval; psutil-gated).
- `ru_maxrss` is process-lifetime, so even in a fresh child it reflects that child's
  maximum including imports, not a single operation's delta.
- Wall time is machine-dependent; a timeout indicates non-completion within the
  budget on this host, not a scientific outcome.
- The bundled child workload is a synthetic allocation for exercising the runner;
  replace the command builder to drive a real benchmark.
```
