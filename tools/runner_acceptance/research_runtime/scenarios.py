"""Scenario runners for cross-platform research runtime acceptance."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

from .contracts import (
    AcceptanceScenarioResult,
    FailureClassification,
    ScenarioOutcome,
    dumps_finite_json,
    json_safe,
)
from .fixtures import (
    build_chunk_cache_plan_fixture,
    build_simulation_checkpoint_fixture,
    execute_atomic_write_fixture,
    probe_production_chunk_cache,
    probe_production_simulation_runner,
    simulate_cache_eviction_fixture,
    simulate_resumable_transfer_fixture,
)
from .platform_checks import (
    build_powershell_command,
    check_windows_file_locking,
    detect_powershell,
    has_posix_process_groups,
    is_posix,
    is_windows,
    normalize_windows_path,
    terminate_process_tree,
)


def run_portable_path_and_serialization(work_dir: Path) -> AcceptanceScenarioResult:
    """Validates cross-platform path handling and finite JSON serialization."""
    t0 = time.perf_counter()
    res = AcceptanceScenarioResult(
        test_case="portable_path_and_serialization",
        category="portable_contracts",
        platform_rule="Rule 1: Run portable tests everywhere",
        status=ScenarioOutcome.PASS,
    )

    try:
        # 1. Path manipulation across separators
        rel = Path("nested") / "dir" / "file.txt"
        norm_str = str(rel).replace("\\", "/")
        assert norm_str == "nested/dir/file.txt", f"Unexpected path norm: {norm_str}"

        # 2. Finite JSON serialization with NaN and Inf
        raw_data = {
            "valid_number": 42.0,
            "nan_val": float("nan"),
            "inf_pos": float("inf"),
            "inf_neg": float("-inf"),
            "nested": [{"val": 3.14}, {"bad": float("nan")}],
        }
        json_str = dumps_finite_json(raw_data)
        parsed = json.loads(json_str)

        assert parsed["valid_number"] == 42.0
        assert parsed["nan_val"] is None
        assert parsed["inf_pos"] is None
        assert parsed["inf_neg"] is None
        assert parsed["nested"][1]["bad"] is None

        res.artifact_checksum = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
        res.metadata["json_length"] = len(json_str)
    except Exception as exc:
        res.status = ScenarioOutcome.FAIL
        res.failure_classification = FailureClassification.NON_FINITE_NUMERIC
        res.error_message = f"Serialization check failed: {exc}"

    res.duration_ms = (time.perf_counter() - t0) * 1000.0
    return res


def run_windows_path_normalization(work_dir: Path) -> AcceptanceScenarioResult:
    """Validates Windows extended-length paths and UNC paths (Windows only)."""
    t0 = time.perf_counter()
    res = AcceptanceScenarioResult(
        test_case="windows_path_normalization",
        category="windows_reliability",
        platform_rule="Rule 2: Run Windows-specific tests only on Windows; Rule 3: On POSIX record as UNSUPPORTED",
        status=ScenarioOutcome.PASS,
    )

    if not is_windows():
        res.status = ScenarioOutcome.UNSUPPORTED
        res.unsupported_reason = "Windows extended-length paths and drive normalization are Windows-specific and unsupported on POSIX."
        res.duration_ms = (time.perf_counter() - t0) * 1000.0
        return res

    try:
        # Test long path prefix
        long_sub = "a" * 250
        norm_long = normalize_windows_path(f"C:/{long_sub}/file.txt")
        assert norm_long.startswith("\\\\?\\"), f"Expected \\\\?\\ prefix for long path, got: {norm_long[:10]}"

        # Test forward slash normalization
        norm_short = normalize_windows_path("C:/folder/subfolder/file.json")
        assert "/" not in norm_short, f"Forward slashes remaining: {norm_short}"

        # Test UNC path normalization
        norm_unc = normalize_windows_path(f"//server/share/{long_sub}")
        assert norm_unc.startswith("\\\\?\\UNC\\"), f"Expected \\\\?\\UNC\\ prefix, got: {norm_unc[:15]}"

        res.metadata["normalized_long_len"] = len(norm_long)
    except Exception as exc:
        res.status = ScenarioOutcome.FAIL
        res.failure_classification = FailureClassification.CONTRACT_VIOLATION
        res.error_message = f"Windows path normalization failed: {exc}"

    res.duration_ms = (time.perf_counter() - t0) * 1000.0
    return res


def run_powershell_smoke(work_dir: Path) -> AcceptanceScenarioResult:
    """Validates PowerShell command construction without shell=True."""
    t0 = time.perf_counter()
    res = AcceptanceScenarioResult(
        test_case="powershell_smoke",
        category="powershell_command",
        platform_rule="Rule 2: Run Windows-specific tests only on Windows / PowerShell hosts; Rule 3: On POSIX record as UNSUPPORTED if absent",
        status=ScenarioOutcome.PASS,
    )

    available, exe_path, ver = detect_powershell()
    if not available or not exe_path:
        res.status = ScenarioOutcome.UNSUPPORTED
        res.unsupported_reason = "PowerShell executable (pwsh or powershell.exe) is not available on this host."
        res.duration_ms = (time.perf_counter() - t0) * 1000.0
        return res

    cmd = build_powershell_command("Write-Output 'POWERSHELL_ACCEPTANCE_OK'; [math]::Sqrt(144)", exe=exe_path)
    res.command = cmd

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        res.exit_code = proc.returncode
        if proc.returncode != 0:
            res.status = ScenarioOutcome.FAIL
            res.failure_classification = FailureClassification.COMMAND_CONSTRUCTION
            res.error_message = f"PowerShell exited with code {proc.returncode}: {proc.stderr.strip()}"
        else:
            out_lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            assert "POWERSHELL_ACCEPTANCE_OK" in out_lines, f"Token not found in: {out_lines}"
            assert "12" in out_lines, f"Math result 12 not found in: {out_lines}"
            res.metadata["powershell_version"] = ver
            res.metadata["executable"] = exe_path
    except subprocess.TimeoutExpired:
        res.status = ScenarioOutcome.FAIL
        res.timeout_state = True
        res.failure_classification = FailureClassification.TIMEOUT
        res.error_message = "PowerShell execution timed out."
    except Exception as exc:
        res.status = ScenarioOutcome.FAIL
        res.failure_classification = FailureClassification.SUBPROCESS_ERROR
        res.error_message = f"PowerShell invocation failed: {exc}"

    res.duration_ms = (time.perf_counter() - t0) * 1000.0
    return res


def run_atomic_replace(work_dir: Path) -> AcceptanceScenarioResult:
    """Validates atomic artifact writes using staging and os.replace."""
    t0 = time.perf_counter()
    res = AcceptanceScenarioResult(
        test_case="atomic_replace",
        category="atomic_writes",
        platform_rule="Rule 1: Run portable tests everywhere",
        status=ScenarioOutcome.PASS,
    )

    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        dst = work_dir / "atomic_target.dat"
        dst.write_bytes(b"INITIAL_PAYLOAD_V0")

        new_payload = b"UPDATED_PAYLOAD_V1_ATOMIC_HASH_VERIFIED"
        spec = execute_atomic_write_fixture(dst, new_payload)

        assert spec.replace_success is True
        assert dst.exists()
        assert dst.read_bytes() == new_payload
        res.artifact_checksum = spec.checksum_sha256
        res.metadata["written_bytes"] = spec.written_bytes
    except Exception as exc:
        res.status = ScenarioOutcome.FAIL
        res.failure_classification = FailureClassification.CONTRACT_VIOLATION
        res.error_message = f"Atomic replace failed: {exc}"

    res.duration_ms = (time.perf_counter() - t0) * 1000.0
    return res


def run_windows_locked_file_cleanup(work_dir: Path) -> AcceptanceScenarioResult:
    """Validates Windows mandatory file-locking and safe retry cleanup (Windows only)."""
    t0 = time.perf_counter()
    res = AcceptanceScenarioResult(
        test_case="locked_file_cleanup",
        category="windows_file_locks",
        platform_rule="Rule 2: Run Windows-specific tests only on Windows; Rule 3: On POSIX record as UNSUPPORTED",
        status=ScenarioOutcome.PASS,
    )

    if not is_windows():
        res.status = ScenarioOutcome.UNSUPPORTED
        res.unsupported_reason = "Windows mandatory file locking (ERROR_SHARING_VIOLATION / PermissionError on open files) is Windows-specific and unsupported on POSIX."
        res.duration_ms = (time.perf_counter() - t0) * 1000.0
        return res

    lock_file = work_dir / "locked_file_probe.tmp"
    lock_info = check_windows_file_locking(lock_file)

    if not lock_info["locked_operation_failed"]:
        res.status = ScenarioOutcome.FAIL
        res.failure_classification = FailureClassification.FILE_LOCK
        res.error_message = f"Expected open file to fail deletion on Windows, but it succeeded: {lock_info}"
    else:
        res.metadata["detected_error_type"] = lock_info["error_type"]
        res.metadata["detected_error_message"] = lock_info["error_message"]

    res.duration_ms = (time.perf_counter() - t0) * 1000.0
    return res


def run_process_timeout_termination(work_dir: Path) -> AcceptanceScenarioResult:
    """Validates process timeout detection, termination, and clean exit."""
    t0 = time.perf_counter()
    res = AcceptanceScenarioResult(
        test_case="timeout_termination",
        category="process_timeout",
        platform_rule="Rule 1: Run portable tests everywhere",
        status=ScenarioOutcome.PASS,
    )

    # Subprocess that sleeps for 20 seconds
    script = (
        "import time, sys\n"
        "sys.stdout.write('SLEEPING\\n')\n"
        "sys.stdout.flush()\n"
        "time.sleep(20)\n"
    )
    cmd = [sys.executable, "-c", script]
    res.command = cmd

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Read the initial output
        line = proc.stdout.readline() if proc.stdout else ""
        assert "SLEEPING" in line

        # Wait with a short timeout of 1.0s
        proc.wait(timeout=1.0)
        # Should NOT reach here
        res.status = ScenarioOutcome.FAIL
        res.failure_classification = FailureClassification.CONTRACT_VIOLATION
        res.error_message = "Process exited before timeout."
    except subprocess.TimeoutExpired:
        res.timeout_state = True
        killed, how = terminate_process_tree(proc.pid, timeout_s=3.0)
        proc.wait(timeout=3.0)
        res.exit_code = proc.returncode
        res.orphan_cleanup_state = "clean" if killed else "orphans_detected"
        res.metadata["termination_method"] = how
    except Exception as exc:
        res.status = ScenarioOutcome.FAIL
        res.failure_classification = FailureClassification.SUBPROCESS_ERROR
        res.error_message = f"Timeout test error: {exc}"
    finally:
        if proc.poll() is None:
            terminate_process_tree(proc.pid)

    res.duration_ms = (time.perf_counter() - t0) * 1000.0
    return res


def run_process_tree_cleanup(work_dir: Path) -> AcceptanceScenarioResult:
    """Validates that killing a parent process cleans up child/grandchild processes."""
    t0 = time.perf_counter()
    res = AcceptanceScenarioResult(
        test_case="process_tree_cleanup",
        category="orphan_cleanup",
        platform_rule="Rule 1: Run portable tests everywhere",
        status=ScenarioOutcome.PASS,
    )

    work_dir.mkdir(parents=True, exist_ok=True)
    # Script that spawns a grandchild and writes grandchild PID to file
    pid_file = work_dir / "grandchild.pid"
    if pid_file.exists():
        pid_file.unlink()

    pid_file_posix = str(pid_file.resolve()).replace("\\", "/")
    parent_script = (
        "import subprocess, sys, time\n"
        f"child = subprocess.Popen([sys.executable, '-c', 'import time, os; open(\"{pid_file_posix}\", \"w\").write(str(os.getpid())); time.sleep(30)'])\n"
        "time.sleep(30)\n"
    )

    cmd = [sys.executable, "-c", parent_script]
    res.command = cmd

    parent = subprocess.Popen(cmd)
    grandchild_pid = None

    try:
        # Wait up to 5 seconds for grandchild PID file to appear
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if pid_file.exists():
                txt = pid_file.read_text().strip()
                if txt.isdigit():
                    grandchild_pid = int(txt)
                    break
            time.sleep(0.1)

        assert grandchild_pid is not None, "Failed to capture grandchild PID."
        res.metadata["parent_pid"] = parent.pid
        res.metadata["grandchild_pid"] = grandchild_pid

        # Kill the entire process tree starting from parent
        killed, how = terminate_process_tree(parent.pid, timeout_s=3.0)
        parent.wait(timeout=3.0)

        # Verify grandchild is also dead
        time.sleep(0.5)
        grandchild_alive = False
        if is_windows():
            chk = subprocess.run(
                ["tasklist", "/FI", f"PID eq {grandchild_pid}"],
                capture_output=True,
                text=True,
                check=False,
            )
            grandchild_alive = str(grandchild_pid) in chk.stdout
        else:
            try:
                os.kill(grandchild_pid, 0)
                grandchild_alive = True
            except OSError:
                grandchild_alive = False

        if grandchild_alive:
            res.status = ScenarioOutcome.FAIL
            res.orphan_cleanup_state = "orphans_detected"
            res.failure_classification = FailureClassification.PROCESS_ORPHAN
            res.error_message = f"Grandchild process {grandchild_pid} survived parent termination."
            terminate_process_tree(grandchild_pid)
        else:
            res.orphan_cleanup_state = "clean"
            res.metadata["tree_cleanup_method"] = how
    except Exception as exc:
        res.status = ScenarioOutcome.FAIL
        res.failure_classification = FailureClassification.SUBPROCESS_ERROR
        res.error_message = f"Process tree cleanup failed: {exc}"
    finally:
        if parent.poll() is None:
            terminate_process_tree(parent.pid)
        if grandchild_pid:
            terminate_process_tree(grandchild_pid)

    res.duration_ms = (time.perf_counter() - t0) * 1000.0
    return res


def run_unicode_and_utf8_paths(work_dir: Path) -> AcceptanceScenarioResult:
    """Validates creation and file operations in deep Unicode paths."""
    t0 = time.perf_counter()
    res = AcceptanceScenarioResult(
        test_case="unicode_paths",
        category="unicode_support",
        platform_rule="Rule 1: Run portable tests everywhere",
        status=ScenarioOutcome.PASS,
    )

    try:
        unicode_dir = work_dir / "исследование_研究_🧪_greek_αβγ" / "poddir_ñ_é"
        unicode_dir.mkdir(parents=True, exist_ok=True)

        target_file = unicode_dir / "контракт_データ_📊.json"
        payload_data = {
            "title": "Кросс-платформенное тестирование",
            "symbols": ["α", "β", "γ", "δ", "π", "∑", "🧪", "🧠"],
            "accuracy": 0.9998,
        }
        content = json.dumps(payload_data, ensure_ascii=False, indent=2)
        target_file.write_text(content, encoding="utf-8")

        # Read back and verify content and SHA256
        read_back = target_file.read_text(encoding="utf-8")
        parsed = json.loads(read_back)
        assert parsed["title"] == payload_data["title"]
        assert parsed["symbols"] == payload_data["symbols"]

        res.artifact_checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        res.metadata["unicode_path"] = str(target_file)
    except Exception as exc:
        res.status = ScenarioOutcome.FAIL
        res.failure_classification = FailureClassification.ENCODING_ERROR
        res.error_message = f"Unicode path handling failed: {exc}"

    res.duration_ms = (time.perf_counter() - t0) * 1000.0
    return res


def run_bounded_output_streaming(work_dir: Path) -> AcceptanceScenarioResult:
    """Validates bounding of subprocess output to prevent unbounded memory growth."""
    t0 = time.perf_counter()
    res = AcceptanceScenarioResult(
        test_case="bounded_output",
        category="bounded_streaming",
        platform_rule="Rule 1: Run portable tests everywhere",
        status=ScenarioOutcome.PASS,
    )

    # Subprocess printing 5,000 lines
    script = (
        "import sys\n"
        "for i in range(5000):\n"
        "    sys.stdout.write(f'OUTPUT_LINE_FLOOD_{i:06d}_PADDING_BYTES_1234567890\\n')\n"
    )
    cmd = [sys.executable, "-c", script]
    res.command = cmd

    try:
        max_bytes = 32 * 1024  # 32 KiB cap
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        captured = []
        bytes_read = 0
        truncated = False

        while True:
            chunk = proc.stdout.read(4096) if proc.stdout else ""
            if not chunk:
                break
            captured.append(chunk)
            bytes_read += len(chunk.encode("utf-8"))
            if bytes_read >= max_bytes:
                truncated = True
                break

        proc.terminate()
        proc.wait(timeout=2.0)
        res.exit_code = proc.returncode

        assert bytes_read >= max_bytes or truncated, "Expected buffer cap reached."
        res.metadata["bytes_captured"] = bytes_read
        res.metadata["capped_at_bytes"] = max_bytes
        res.metadata["truncated"] = truncated
    except Exception as exc:
        res.status = ScenarioOutcome.FAIL
        res.failure_classification = FailureClassification.SUBPROCESS_ERROR
        res.error_message = f"Bounded output test failed: {exc}"

    res.duration_ms = (time.perf_counter() - t0) * 1000.0
    return res


def run_malformed_child_output(work_dir: Path) -> AcceptanceScenarioResult:
    """Validates robust decoding of non-UTF8 or binary corrupted child output."""
    t0 = time.perf_counter()
    res = AcceptanceScenarioResult(
        test_case="malformed_child_output",
        category="error_resilience",
        platform_rule="Rule 1: Run portable tests everywhere",
        status=ScenarioOutcome.PASS,
    )

    # Subprocess writing raw invalid UTF-8 bytes to stdout
    script = (
        "import sys\n"
        "sys.stdout.buffer.write(b'VALID_HEADER_\\xff\\xfe\\x80\\x7f_CORRUPTED_STREAM\\n')\n"
        "sys.stdout.buffer.flush()\n"
    )
    cmd = [sys.executable, "-c", script]
    res.command = cmd

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
        res.exit_code = proc.returncode

        # Decoding with replace to prevent crash
        decoded = proc.stdout.decode("utf-8", errors="replace")
        assert "VALID_HEADER_" in decoded
        assert "\ufffd" in decoded or "\\x" in repr(decoded), "Expected replacement characters for malformed bytes."

        res.metadata["decoded_preview"] = decoded.strip()
    except Exception as exc:
        res.status = ScenarioOutcome.FAIL
        res.failure_classification = FailureClassification.ENCODING_ERROR
        res.error_message = f"Malformed child output handling failed: {exc}"

    res.duration_ms = (time.perf_counter() - t0) * 1000.0
    return res


def run_posix_signal_behavior(work_dir: Path) -> AcceptanceScenarioResult:
    """Validates POSIX process group signals (POSIX only)."""
    t0 = time.perf_counter()
    res = AcceptanceScenarioResult(
        test_case="posix_signal_behavior",
        category="posix_signals",
        platform_rule="Rule 4: On Windows, record POSIX-only behavior as UNSUPPORTED, never PASS",
        status=ScenarioOutcome.PASS,
    )

    if is_windows() or not has_posix_process_groups():
        res.status = ScenarioOutcome.UNSUPPORTED
        res.unsupported_reason = "POSIX signals and process groups (os.killpg, SIGKILL) are POSIX-specific and unsupported on Windows."
        res.duration_ms = (time.perf_counter() - t0) * 1000.0
        return res

    try:
        # On POSIX: spawn process in new group and kill group
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(20)"],
            preexec_fn=os.setpgrp,  # type: ignore
        )
        pgid = os.getpgid(proc.pid)
        import signal
        os.killpg(pgid, signal.SIGKILL)
        proc.wait(timeout=3.0)
        res.exit_code = proc.returncode
        res.orphan_cleanup_state = "clean"
        res.metadata["posix_pgid"] = pgid
    except Exception as exc:
        res.status = ScenarioOutcome.FAIL
        res.failure_classification = FailureClassification.SUBPROCESS_ERROR
        res.error_message = f"POSIX signal scenario failed: {exc}"

    res.duration_ms = (time.perf_counter() - t0) * 1000.0
    return res


def run_bounded_chunk_cache_planning(work_dir: Path) -> AcceptanceScenarioResult:
    """Validates chunk cache planning and probes production module presence."""
    t0 = time.perf_counter()
    res = AcceptanceScenarioResult(
        test_case="bounded_chunk_cache_planning",
        category="batch1_cache",
        platform_rule="Rule 1: Run portable tests everywhere",
        status=ScenarioOutcome.PASS,
    )

    try:
        # 1. Black-box contract fixture verification
        plan = build_chunk_cache_plan_fixture(
            total_bytes=10 * 1024 * 1024,
            chunk_size_bytes=2 * 1024 * 1024,
            budget_bytes=6 * 1024 * 1024,
        )
        assert plan.chunk_count == 5
        assert len(plan.planned_chunks) == 5

        evict_dir = work_dir / "cache_evict_test"
        evict_plan = simulate_cache_eviction_fixture(
            cache_dir=evict_dir,
            file_sizes_bytes=[2 * 1024 * 1024, 2 * 1024 * 1024, 4 * 1024 * 1024],
            budget_limit_bytes=4 * 1024 * 1024,
        )
        assert evict_plan.resulting_size_bytes <= evict_plan.budget_limit_bytes
        assert len(evict_plan.evicted_keys) > 0

        # 2. Production implementation probe
        has_prod, msg = probe_production_chunk_cache()
        res.metadata["production_probe"] = {
            "available": has_prod,
            "message": msg,
        }
        res.metadata["chunk_count"] = plan.chunk_count
        res.metadata["evicted_keys"] = evict_plan.evicted_keys

        # If production module is not yet present on origin/main, mark integration status in metadata
        if not has_prod:
            res.metadata["integration_status"] = "PENDING_ORIGIN_MAIN"
    except Exception as exc:
        res.status = ScenarioOutcome.FAIL
        res.failure_classification = FailureClassification.CONTRACT_VIOLATION
        res.error_message = f"Chunk cache planning failed: {exc}"

    res.duration_ms = (time.perf_counter() - t0) * 1000.0
    return res


def run_resumable_transfer_metadata(work_dir: Path) -> AcceptanceScenarioResult:
    """Validates resumable transfer chunk persistence and recovery."""
    t0 = time.perf_counter()
    res = AcceptanceScenarioResult(
        test_case="resumable_transfer_metadata",
        category="batch1_transfer",
        platform_rule="Rule 1: Run portable tests everywhere",
        status=ScenarioOutcome.PASS,
    )

    try:
        xfer_dir = work_dir / "xfer_test"
        meta = simulate_resumable_transfer_fixture(xfer_dir, num_chunks=6, chunk_size=2048)

        assert meta.is_complete is True
        assert meta.transferred_bytes == meta.total_expected_bytes
        assert len(meta.completed_chunks) == 6
        assert len(meta.checksum_sha256) == 64

        final_file = Path(meta.destination_path)
        assert final_file.exists()
        assert final_file.stat().st_size == meta.total_expected_bytes

        res.artifact_checksum = meta.checksum_sha256
        res.metadata["transfer_id"] = meta.transfer_id
        res.metadata["total_bytes"] = meta.total_expected_bytes
    except Exception as exc:
        res.status = ScenarioOutcome.FAIL
        res.failure_classification = FailureClassification.CONTRACT_VIOLATION
        res.error_message = f"Resumable transfer simulation failed: {exc}"

    res.duration_ms = (time.perf_counter() - t0) * 1000.0
    return res


def run_simulation_checkpoint_recovery(work_dir: Path) -> AcceptanceScenarioResult:
    """Validates simulation checkpoint persistence, recovery, and module probe."""
    t0 = time.perf_counter()
    res = AcceptanceScenarioResult(
        test_case="simulation_checkpoint_recovery",
        category="batch1_simulation",
        platform_rule="Rule 1: Run portable tests everywhere",
        status=ScenarioOutcome.PASS,
    )

    try:
        ckpt_dir = work_dir / "sim_checkpoints"
        ckpt = build_simulation_checkpoint_fixture(ckpt_dir, step_index=75, total_steps=150)

        assert Path(ckpt.checkpoint_file).exists()
        assert ckpt.is_recoverable is True
        assert len(ckpt.state_payload_hash) == 64
        assert len(ckpt.rng_state_hash) == 64

        has_prod, msg = probe_production_simulation_runner()
        res.metadata["production_probe"] = {
            "available": has_prod,
            "message": msg,
        }
        res.metadata["checkpoint_file"] = ckpt.checkpoint_file
        res.metadata["step_index"] = ckpt.step_index
        res.artifact_checksum = ckpt.state_payload_hash

        if not has_prod:
            res.metadata["integration_status"] = "PENDING_ORIGIN_MAIN"
    except Exception as exc:
        res.status = ScenarioOutcome.FAIL
        res.failure_classification = FailureClassification.CONTRACT_VIOLATION
        res.error_message = f"Simulation checkpoint fixture failed: {exc}"

    res.duration_ms = (time.perf_counter() - t0) * 1000.0
    return res
