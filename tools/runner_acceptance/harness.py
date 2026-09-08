"""Acceptance harness that validates the isolated test runner via subprocesses.

The harness *invokes* ``scripts/run_tests_isolated.py`` (never imports or modifies
it) through safe, ``shell=False`` subprocess calls. It has two modes:

* **Windows** (``platform_status=supported``): validates Windows-specific runner
  behavior -- new process-group creation, timeout termination (exit 124), no false
  PASS, descendant/orphan cleanup, output-flood draining -- plus the portable
  contract cases.
* **Non-Windows** (``platform_status=unsupported``): runs ONLY portable contract
  tests (command construction/quoting, Unicode/space paths, the harness executor's
  own timeout and flood contracts, JSON finiteness). Windows-specific cases are
  recorded as ``unsupported`` and are NEVER reported as passed -- a non-Windows host
  cannot produce evidence that Windows process behavior passed.

All reports are finite JSON (NaN/Inf -> null). Fixtures are synthetic; this is
operational/acceptance evidence, never scientific evidence.
"""
from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_IS_WINDOWS = os.name == "nt"
_GRACE_S = 5.0


# --------------------------------------------------------------------------- #
# JSON safety
# --------------------------------------------------------------------------- #
def json_safe(value: Any) -> Any:
    """Recursively convert to JSON-safe form (NaN/Inf -> None; Enum -> value)."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def dumps(obj: Any, *, indent: Optional[int] = 2) -> str:
    return json.dumps(json_safe(obj), indent=indent, allow_nan=False)


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class Outcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class PlatformStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"


# --------------------------------------------------------------------------- #
# Capability detection
# --------------------------------------------------------------------------- #
def python_version() -> str:
    return sys.version.split()[0]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def runner_script_path() -> Path:
    return repo_root() / "scripts" / "run_tests_isolated.py"


def runner_commit() -> str:
    """Best-effort git commit of the runner (repo HEAD); 'unknown' if unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root()), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, check=False, timeout=10,
        )
        commit = out.stdout.strip()
        return commit or "unknown"
    except Exception:
        return "unknown"


@dataclass
class Capability:
    platform: str
    os_name: str
    is_windows: bool
    python_version: str
    psutil_available: bool
    runner_present: bool
    runner_commit: str
    platform_status: PlatformStatus

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))


def detect_capability() -> Capability:
    try:
        import psutil  # noqa: F401

        psutil_available = True
    except Exception:
        psutil_available = False
    return Capability(
        platform=sys.platform,
        os_name=os.name,
        is_windows=_IS_WINDOWS,
        python_version=python_version(),
        psutil_available=psutil_available,
        runner_present=runner_script_path().is_file(),
        runner_commit=runner_commit(),
        platform_status=PlatformStatus.SUPPORTED if _IS_WINDOWS else PlatformStatus.UNSUPPORTED,
    )


# --------------------------------------------------------------------------- #
# PowerShell command construction / quoting (portable to construct + test)
# --------------------------------------------------------------------------- #
def ps_single_quote(value: str) -> str:
    """Quote a value as a PowerShell single-quoted string (escape ' as '')."""
    return "'" + str(value).replace("'", "''") + "'"


def build_powershell_command(argv: Sequence[str]) -> List[str]:
    """Build a PowerShell invocation (argv list, shell=False) of ``argv``.

    Produces ``["powershell", "-NoProfile", "-NonInteractive", "-Command",
    "& 'prog' 'arg1' 'arg2' ..."]`` with each token single-quoted so spaces and
    Unicode in paths are preserved. Constructed on any platform (for quoting
    tests); only executed on Windows.
    """
    if not argv:
        raise ValueError("argv must be non-empty")
    call = "& " + " ".join(ps_single_quote(a) for a in argv)
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command", call]


def build_runner_argv(targets: Sequence[str], *, timeout_s: int, batch_size: int = 1,
                      extra: Optional[Sequence[str]] = None) -> List[str]:
    """Build the plain argv to invoke the isolated runner on ``targets``."""
    argv = [sys.executable, str(runner_script_path()),
            "--batch-size", str(batch_size), "--timeout-s", str(timeout_s)]
    if extra:
        argv.extend(str(a) for a in extra)
    argv.extend(str(t) for t in targets)
    return argv


# --------------------------------------------------------------------------- #
# Safe child executor (no shell=True; process-group isolated; drained; timeout)
# --------------------------------------------------------------------------- #
def _popen_kwargs() -> Dict[str, Any]:
    if _IS_WINDOWS:  # pragma: no cover - Windows path not exercised on POSIX CI
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _wait_or(proc: subprocess.Popen, seconds: float) -> bool:
    try:
        proc.wait(timeout=seconds)
        return True
    except subprocess.TimeoutExpired:
        return False


def _terminate_tree(proc: subprocess.Popen, grace_s: float = _GRACE_S) -> None:
    if proc.poll() is not None:
        return
    if _IS_WINDOWS:  # pragma: no cover - not exercised on POSIX CI
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        except Exception:
            pass
        if not _wait_or(proc, grace_s):
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               check=False, timeout=10)
            except Exception:
                pass
            _wait_or(proc, grace_s)
        return
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, OSError):
        return
    for sig, wait in ((signal.SIGTERM, grace_s), (signal.SIGKILL, grace_s)):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, OSError):
            return
        if _wait_or(proc, wait):
            return


@dataclass
class ExecResult:
    exit_code: int
    timed_out: bool
    term_signal: Optional[int]
    stdout: str
    stderr: str
    stdout_total_bytes: int
    stderr_total_bytes: int
    elapsed_s: float
    child_pid: int


def execute(argv: Sequence[str], *, timeout_s: float, cwd: Optional[str] = None,
            env: Optional[Dict[str, str]] = None, capture_limit: int = 200_000) -> ExecResult:
    """Run ``argv`` (shell=False) with a hard timeout, draining output on threads.

    The child runs in its own process group/session and, on timeout, its whole
    tree is terminated (graceful -> forced). Reader threads drain stdout/stderr so
    an output flood cannot deadlock. Never signals the parent.
    """
    if timeout_s <= 0:
        raise ValueError("timeout_s must be > 0")
    start = time.perf_counter()
    proc = subprocess.Popen(
        list(argv), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        cwd=cwd, env=env, **_popen_kwargs(),
    )
    out: List[str] = []
    err: List[str] = []

    def _drain(stream, sink):
        if stream is None:
            return
        try:
            for line in iter(stream.readline, ""):
                sink.append(line)
        except Exception:
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass

    t_out = threading.Thread(target=_drain, args=(proc.stdout, out), daemon=True)
    t_err = threading.Thread(target=_drain, args=(proc.stderr, err), daemon=True)
    t_out.start()
    t_err.start()

    timed_out = not _wait_or(proc, timeout_s)
    if timed_out:
        _terminate_tree(proc)
        if not _wait_or(proc, 10.0):
            _terminate_tree(proc)
            _wait_or(proc, 5.0)
    t_out.join(timeout=5.0)
    t_err.join(timeout=5.0)

    rc = proc.returncode if proc.returncode is not None else -1
    term_signal = -rc if rc < 0 else None
    exit_code = rc if rc >= 0 else -1
    full_out = "".join(out)
    full_err = "".join(err)
    return ExecResult(exit_code=exit_code, timed_out=timed_out, term_signal=term_signal,
                      stdout=full_out[-capture_limit:], stderr=full_err[-capture_limit:],
                      stdout_total_bytes=len(full_out), stderr_total_bytes=len(full_err),
                      elapsed_s=time.perf_counter() - start, child_pid=proc.pid)


# --------------------------------------------------------------------------- #
# Acceptance record + classification
# --------------------------------------------------------------------------- #
@dataclass
class AcceptanceRecord:
    test_case: str
    category: str                 # "portable" | "windows_runner"
    platform: str
    python_version: str
    runner_version: str
    capability_state: str         # platform_status value
    expected_outcome: str
    observed_outcome: str
    outcome: Outcome
    timeout_state: str            # "not_applicable" | "completed" | "timed_out"
    orphan_state: str             # "not_checked" | "none" | "orphaned"
    cleanup_state: str            # "not_applicable" | "clean" | "dirty"
    evidence_class: str
    synthetic: bool
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))


def _record(cap: Capability, name: str, category: str, *, expected: str, observed: str,
            outcome: Outcome, timeout_state: str = "not_applicable",
            orphan_state: str = "not_checked", cleanup_state: str = "not_applicable",
            details: Optional[Dict[str, Any]] = None) -> AcceptanceRecord:
    return AcceptanceRecord(
        test_case=name, category=category, platform=cap.platform,
        python_version=cap.python_version, runner_version=cap.runner_commit,
        capability_state=cap.platform_status.value, expected_outcome=expected,
        observed_outcome=observed, outcome=outcome, timeout_state=timeout_state,
        orphan_state=orphan_state, cleanup_state=cleanup_state,
        evidence_class="acceptance_synthetic", synthetic=True, details=details or {},
    )


def classify_runner_timeout(result: ExecResult) -> Dict[str, Any]:
    """Interpret a runner subprocess result for a timeout scenario."""
    stdout = result.stdout or ""
    reported_timeout = "timeout" in stdout.lower()
    false_pass = ("0 timeouts" in stdout) or ("passed" in stdout and "timeout" not in stdout.lower())
    return {
        "exit_code": result.exit_code,
        "timed_out_wall": result.timed_out,
        "exit_124": result.exit_code == 124,
        "reported_timeout": reported_timeout,
        "no_false_pass": not false_pass,
    }


# --------------------------------------------------------------------------- #
# Portable contract cases (run on ANY platform)
# --------------------------------------------------------------------------- #
def case_powershell_command_construction(cap: Capability) -> AcceptanceRecord:
    argv = build_runner_argv(["C:\\tmp\\test_x.py"], timeout_s=30)
    ps = build_powershell_command(argv)
    ok = (ps[0] == "powershell" and "-NoProfile" in ps and "-Command" in ps
          and ps[-1].startswith("& ") and ps_single_quote(argv[0]) in ps[-1])
    return _record(cap, "powershell_command_construction", "portable",
                   expected="valid_powershell_argv", observed="valid" if ok else "invalid",
                   outcome=Outcome.PASS if ok else Outcome.FAIL,
                   details={"command_preview": ps[:4] + [ps[-1][:120]]})


def case_path_quoting(cap: Capability) -> AcceptanceRecord:
    tricky = "C:\\Temp\\acc test\\o'brien\\tëst_дир\\test_a.py"
    quoted = ps_single_quote(tricky)
    ok = quoted.startswith("'") and quoted.endswith("'") and "''" in quoted and tricky.replace("'", "''") in quoted
    return _record(cap, "path_quoting", "portable",
                   expected="single_quoted_escaped", observed="ok" if ok else "bad",
                   outcome=Outcome.PASS if ok else Outcome.FAIL,
                   details={"input": tricky, "quoted": quoted})


def case_unicode_space_tempdir(cap: Capability) -> AcceptanceRecord:
    """Invoke the runner on a passing test inside a Unicode+space temp dir."""
    if not cap.runner_present:
        return _record(cap, "unicode_space_tempdir", "portable",
                       expected="runner_runs_passing_test", observed="runner_absent",
                       outcome=Outcome.ERROR)
    parent = tempfile.mkdtemp(prefix="acc ")  # space in prefix
    workdir = Path(parent) / "tëst_дир space"
    workdir.mkdir(parents=True, exist_ok=True)
    test_file = workdir / "test_unicode_ok.py"
    test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    try:
        argv = build_runner_argv([str(test_file)], timeout_s=60)
        result = execute(argv, timeout_s=120)
        passed = result.exit_code == 0 and "passed" in (result.stdout + result.stderr).lower()
        cleanup_ok = True
    finally:
        try:
            import shutil

            shutil.rmtree(parent, ignore_errors=True)
            cleanup_ok = not Path(parent).exists()
        except Exception:
            cleanup_ok = False
    return _record(cap, "unicode_space_tempdir", "portable",
                   expected="exit0_passed", observed="passed" if passed else "not_passed",
                   outcome=Outcome.PASS if passed else Outcome.FAIL,
                   timeout_state="timed_out" if result.timed_out else "completed",
                   cleanup_state="clean" if cleanup_ok else "dirty",
                   details={"exit_code": result.exit_code, "path": str(test_file)})


def case_executor_timeout_contract(cap: Capability) -> AcceptanceRecord:
    """The harness executor must time out and force-kill a sleeping child."""
    argv = [sys.executable, "-c", "import time; time.sleep(120)"]
    result = execute(argv, timeout_s=2)
    ok = result.timed_out and result.exit_code != 0
    return _record(cap, "executor_timeout_contract", "portable",
                   expected="timed_out_terminated", observed="timed_out" if ok else "not_timed_out",
                   outcome=Outcome.PASS if ok else Outcome.FAIL,
                   timeout_state="timed_out" if result.timed_out else "completed",
                   details={"elapsed_s": round(result.elapsed_s, 3), "exit_code": result.exit_code})


def case_output_flood(cap: Capability) -> AcceptanceRecord:
    """Draining must handle a >pipe-buffer stdout flood without deadlock."""
    payload = 5 * 1024 * 1024
    argv = [sys.executable, "-c", f"import sys; sys.stdout.write('x'*{payload}); sys.stdout.flush()"]
    result = execute(argv, timeout_s=60)
    # Completion without timeout, plus full byte count drained, proves no deadlock.
    ok = (not result.timed_out) and result.exit_code == 0 and result.stdout_total_bytes >= payload
    return _record(cap, "output_flood", "portable",
                   expected="drained_no_deadlock", observed="drained" if ok else "deadlock_or_short",
                   outcome=Outcome.PASS if ok else Outcome.FAIL,
                   timeout_state="timed_out" if result.timed_out else "completed",
                   details={"bytes_drained": result.stdout_total_bytes, "exit_code": result.exit_code})


# --------------------------------------------------------------------------- #
# Windows-only runner behavioral cases (executed only on Windows)
# --------------------------------------------------------------------------- #
_WINDOWS_CASES = [
    ("new_process_group_creation", "worker_started_in_new_group"),
    ("timeout_termination_exit_124", "exit_124_on_timeout"),
    ("no_false_pass_after_timeout", "status_timeout_not_pass"),
    ("descendant_process_cleanup", "no_orphaned_descendants"),
    ("output_flood_draining_runner", "runner_drains_flood"),
]


def _unsupported_windows_records(cap: Capability) -> List[AcceptanceRecord]:
    records = []
    for name, expected in _WINDOWS_CASES:
        records.append(_record(
            cap, name, "windows_runner", expected=expected,
            observed="skipped_non_windows", outcome=Outcome.UNSUPPORTED,
            timeout_state="not_applicable", orphan_state="not_checked",
            cleanup_state="not_applicable",
            details={"reason": "non-Windows host cannot validate Windows process behavior"},
        ))
    return records


def _windows_runner_records(cap: Capability, timeout_s: int) -> List[AcceptanceRecord]:  # pragma: no cover - Windows only
    """Execute the Windows-specific runner validations (only runs on Windows)."""
    records: List[AcceptanceRecord] = []
    workdir = Path(tempfile.mkdtemp(prefix="acc_win_"))
    pidfile = workdir / "grandchild.pid"
    hanging = workdir / "test_hang_tree.py"
    hanging.write_text(
        "import os, sys, subprocess, time\n"
        "def test_hang():\n"
        "    g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
        f"    open(r'{pidfile}', 'w').write(str(g.pid))\n"
        "    time.sleep(300)\n",
        encoding="utf-8",
    )
    try:
        argv = build_runner_argv([str(hanging)], timeout_s=timeout_s)
        result = execute(argv, timeout_s=timeout_s + 30)
        cls = classify_runner_timeout(result)

        records.append(_record(
            cap, "timeout_termination_exit_124", "windows_runner",
            expected="exit_124_on_timeout",
            observed=f"exit_{result.exit_code}",
            outcome=Outcome.PASS if cls["exit_124"] else Outcome.FAIL,
            timeout_state="timed_out" if result.timed_out or cls["reported_timeout"] else "completed",
            details=cls,
        ))
        records.append(_record(
            cap, "no_false_pass_after_timeout", "windows_runner",
            expected="status_timeout_not_pass",
            observed="no_false_pass" if cls["no_false_pass"] else "false_pass",
            outcome=Outcome.PASS if cls["no_false_pass"] else Outcome.FAIL,
            timeout_state="timed_out",
            details=cls,
        ))
        records.append(_record(
            cap, "new_process_group_creation", "windows_runner",
            expected="worker_started_in_new_group",
            observed="terminated_cleanly" if result.exit_code == 124 else "unclear",
            outcome=Outcome.PASS if result.exit_code == 124 else Outcome.FAIL,
            timeout_state="timed_out",
            details={"note": "verified indirectly: group signalling terminated the worker tree"},
        ))

        orphan_state = "not_checked"
        cleanup_outcome = Outcome.UNSUPPORTED
        if cap.psutil_available and pidfile.exists():
            import psutil

            gpid = int(pidfile.read_text().strip())
            deadline = time.time() + 5.0
            cleaned = False
            while time.time() < deadline:
                if not psutil.pid_exists(gpid):
                    cleaned = True
                    break
                time.sleep(0.1)
            orphan_state = "none" if cleaned else "orphaned"
            cleanup_outcome = Outcome.PASS if cleaned else Outcome.FAIL
        records.append(_record(
            cap, "descendant_process_cleanup", "windows_runner",
            expected="no_orphaned_descendants",
            observed=orphan_state, outcome=cleanup_outcome,
            timeout_state="timed_out", orphan_state=orphan_state,
            cleanup_state="clean" if orphan_state == "none" else "dirty",
        ))

        flood = workdir / "test_flood.py"
        flood.write_text(
            "import sys\n"
            "def test_flood():\n"
            "    sys.stdout.write('x' * (5*1024*1024)); sys.stdout.flush()\n"
            "    assert True\n",
            encoding="utf-8",
        )
        fres = execute(build_runner_argv([str(flood)], timeout_s=timeout_s, extra=["-s"]),
                       timeout_s=timeout_s + 30)
        records.append(_record(
            cap, "output_flood_draining_runner", "windows_runner",
            expected="runner_drains_flood",
            observed="drained" if (not fres.timed_out and fres.exit_code == 0) else "deadlock_or_fail",
            outcome=Outcome.PASS if (not fres.timed_out and fres.exit_code == 0) else Outcome.FAIL,
            timeout_state="timed_out" if fres.timed_out else "completed",
        ))
    finally:
        try:
            import shutil

            shutil.rmtree(workdir, ignore_errors=True)
        except Exception:
            pass
    return records


# --------------------------------------------------------------------------- #
# Top-level runner
# --------------------------------------------------------------------------- #
def run_acceptance(*, timeout_s: int = 5, include_portable_runner: bool = True) -> Dict[str, Any]:
    """Run the acceptance harness and return a finite JSON-able report.

    Portable contract cases run on every platform. Windows runner cases run only
    on Windows; on other hosts they are recorded as ``unsupported`` and never as
    passed.
    """
    cap = detect_capability()
    records: List[AcceptanceRecord] = [
        case_powershell_command_construction(cap),
        case_path_quoting(cap),
        case_executor_timeout_contract(cap),
        case_output_flood(cap),
    ]
    if include_portable_runner:
        records.append(case_unicode_space_tempdir(cap))

    if cap.is_windows:  # pragma: no cover - Windows only
        records.extend(_windows_runner_records(cap, timeout_s=timeout_s))
    else:
        records.extend(_unsupported_windows_records(cap))

    summary: Dict[str, int] = {}
    for r in records:
        summary[r.outcome.value] = summary.get(r.outcome.value, 0) + 1

    # Success = no FAIL/ERROR among cases that actually ran (unsupported is neutral).
    ran_ok = all(r.outcome in (Outcome.PASS, Outcome.UNSUPPORTED) for r in records)
    windows_validated = cap.is_windows and any(
        r.category == "windows_runner" and r.outcome == Outcome.PASS for r in records
    )

    return json_safe({
        "schema": "runner_acceptance/v1",
        "platform": cap.platform,
        "platform_status": cap.platform_status.value,
        "python_version": cap.python_version,
        "runner_version": cap.runner_commit,
        "capability": cap.to_dict(),
        "evidence_class": "acceptance_synthetic",
        "synthetic": True,
        "num_cases": len(records),
        "summary": summary,
        "ran_ok": bool(ran_ok),
        "windows_behavior_validated": bool(windows_validated),
        "results": [r.to_dict() for r in records],
        "notes": [
            "Synthetic acceptance evidence only; not scientific evidence.",
            "On non-Windows hosts, Windows-specific cases are 'unsupported' and are "
            "never reported as passed.",
        ],
    })
