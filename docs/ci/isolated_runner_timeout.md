# Isolated Test Runner — Timeout & Process-Group Termination

`scripts/run_tests_isolated.py` runs the suite in bounded fresh subprocesses. This
document describes a defect in its timeout handling, the fix, and the guarantees
now covered by `tests/runner/test_runner_isolation.py`.

## The defect (reproduced)

The worker subprocess was launched **without an isolated process group**:

```python
proc = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, text=True, env=env)
```

On timeout the runner called:

```python
os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
```

Because the worker inherited the **runner's** process group, `os.getpgid(child)`
returned the runner's own group, so the `SIGKILL` was delivered to the runner
itself. Reproduction on the base commit:

```
$ python -m pytest tests/runner/test_runner_isolation.py::test_timeout_termination -q
# (no pytest output) -> process killed, rc=137 (128+SIGKILL) after ~19s
```

In a full campaign this aborts the entire run the moment a timing-out batch is
reached — "a timeout blocked the whole test campaign." Two secondary defects
compounded it:

- **Pipe not drained during the wait.** Output was only read *after* the wait
  loop, so a worker that filled its stdout/stderr pipe buffer would block on
  write and never finish, turning a verbose-but-passing batch into a false
  timeout (and, with a live descendant holding the pipe, a hang).
- **Wrong hard-timeout point.** The peak-RSS monitor raised at `timeout_s + 15`,
  so the "hard timeout" was not enforced at `timeout_s`.

## The fix

Minimal, cross-platform, contained entirely in `scripts/run_tests_isolated.py`:

1. **Isolated process group/session** (`_worker_popen_kwargs`): POSIX
   `start_new_session=True`; Windows `CREATE_NEW_PROCESS_GROUP`. The worker is now
   its own group leader, so group signals never reach the runner.
2. **Escalating tree termination** (`_terminate_process_tree`): POSIX sends
   `SIGTERM` to the worker's group, waits a grace period (`_TERMINATION_GRACE_S`,
   5 s), then `SIGKILL`; Windows sends `CTRL_BREAK` then `taskkill /F /T`. The
   whole tree (including grandchildren) is terminated — no orphans.
3. **Deadlock-free draining** (`_execute_worker`): dedicated reader threads drain
   stdout/stderr continuously while the wait loop enforces the hard timeout at
   `timeout_s` and samples peak RSS (psutil, optional). Killing the tree closes
   the inherited pipes so the readers finish.
4. **Exception-safe cleanup**: `run_batch` terminates any still-running worker in
   a `finally` block, so no worker survives an error path; the per-batch temp dir
   is still removed.
5. **Preserved contracts**: timeouts remain `status="timeout"`, `exit_code=124`
   (never a pass, never skipped); batch discovery/ordering is unchanged and
   deterministic; batches run sequentially (bounded); the CLI and JSON report
   schema are unchanged.

## Behavior summary

| Situation | Outcome |
| --- | --- |
| Worker exceeds `timeout_s` | group terminated (SIGTERM→SIGKILL); `status=timeout`, `exit_code=124` |
| Worker ignores SIGTERM | force-killed after the grace period; still `timeout`/124 |
| Worker spawned a grandchild | grandchild dies with the group; no orphan |
| Worker floods stdout/stderr | drained concurrently; no deadlock, no false timeout |
| Worker fails | `status=failed`, non-zero `exit_code` |
| Worker passes | `status=passed`, `exit_code=0` |

## Regression tests

`tests/runner/test_runner_isolation.py` covers: normal success; normal failure;
child timeout; **campaign-not-self-terminated** (the core regression); timeout
reporting (never a pass, prompt); child ignoring graceful termination (SIGTERM →
forced kill escalation); no-orphan grandchild; POSIX isolated-group Popen kwargs;
stdout/stderr flood without deadlock; argv command construction; deterministic
batch order.

## Platform notes / limitations

- The POSIX path (session process groups, `SIGTERM`→`SIGKILL`) is exercised in CI.
  The Windows path (`CREATE_NEW_PROCESS_GROUP`, `CTRL_BREAK`, `taskkill /F /T`) is
  implemented but not covered by these POSIX-CI tests.
- Orphan verification uses `psutil`; if `psutil` is absent, peak-RSS sampling and
  the orphan-cleanup assertions are skipped, but termination still works (the
  wait/kill path does not depend on psutil).
- Peak RSS remains a coarse, host-dependent signal (interpreter + imported
  libraries); it is telemetry only, not a per-test memory budget.
- The hard timeout is a wall-clock backstop; when `pytest-timeout` is available it
  is also passed to pytest so an individual hanging test is caught inside the
  worker first.
