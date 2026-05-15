"""
Safe command runner for the local agent research loop (P23).

Every command is evaluated by command_guard before execution.
Blocked commands are never passed to subprocess.

stdlib only.
"""
from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from tools.local_agents.command_guard import CommandDecision, CommandPolicy, evaluate_command


@dataclass
class SafeCommandResult:
    """Outcome of running a single command through the safe runner."""
    command: str
    allowed: bool
    blocked_reason: str
    exit_code: Optional[int]
    stdout: str
    stderr: str
    elapsed_s: float
    dry_run: bool


def run_safe_command(
    command: str,
    policy: Optional[CommandPolicy] = None,
    cwd: Optional[str] = None,
    timeout_s: int = 120,
    dry_run: bool = False,
    _runner: Optional[Callable] = None,
) -> SafeCommandResult:
    """
    Evaluate command against policy, then run it (or skip if dry_run/blocked).

    _runner is injectable for tests: callable(parts, cwd, timeout) -> (exit_code, stdout, stderr)
    """
    decision: CommandDecision = evaluate_command(command, policy)

    if not decision.allowed:
        return SafeCommandResult(
            command=command,
            allowed=False,
            blocked_reason=decision.reason,
            exit_code=None,
            stdout="",
            stderr="",
            elapsed_s=0.0,
            dry_run=dry_run,
        )

    if dry_run:
        return SafeCommandResult(
            command=command,
            allowed=True,
            blocked_reason="",
            exit_code=0,
            stdout="(dry-run: not executed)",
            stderr="",
            elapsed_s=0.0,
            dry_run=True,
        )

    t0 = time.monotonic()
    try:
        if _runner is not None:
            parts = shlex.split(command)
            exit_code, stdout, stderr = _runner(parts, cwd, timeout_s)
        else:
            parts = shlex.split(command)
            proc = subprocess.run(
                parts,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout_s,
            )
            exit_code = proc.returncode
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - t0
        return SafeCommandResult(
            command=command,
            allowed=True,
            blocked_reason="",
            exit_code=-1,
            stdout="",
            stderr=f"Command timed out after {timeout_s}s",
            elapsed_s=elapsed,
            dry_run=False,
        )
    except Exception as exc:
        elapsed = time.monotonic() - t0
        return SafeCommandResult(
            command=command,
            allowed=True,
            blocked_reason="",
            exit_code=-1,
            stdout="",
            stderr=str(exc),
            elapsed_s=elapsed,
            dry_run=False,
        )

    elapsed = time.monotonic() - t0
    return SafeCommandResult(
        command=command,
        allowed=True,
        blocked_reason="",
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        elapsed_s=round(elapsed, 3),
        dry_run=False,
    )


def run_command_sequence(
    commands: list[str],
    policy: Optional[CommandPolicy] = None,
    cwd: Optional[str] = None,
    timeout_s: int = 120,
    dry_run: bool = False,
    continue_on_error: bool = False,
    _runner: Optional[Callable] = None,
) -> list[SafeCommandResult]:
    """Run a sequence of commands, stopping on failure unless continue_on_error."""
    results: list[SafeCommandResult] = []
    for cmd in commands:
        result = run_safe_command(cmd, policy, cwd, timeout_s, dry_run, _runner)
        results.append(result)
        if not dry_run and result.allowed and result.exit_code not in (0, None):
            if not continue_on_error:
                break
    return results
