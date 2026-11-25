"""Tests for the process-isolated benchmark runner.

Exercise real child subprocesses (via the self-contained
``scripts/run_process_isolated_benchmark.py`` child mode and small inline
children) to verify success, determinism, timeout, crash, invalid-JSON,
missing-metric handling, orphan cleanup, bounded parallelism, finite JSON, and
cross-platform command construction. No scientific workload; synthetic only.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from tools.streaming.process_runner import (
    Outcome,
    build_python_command,
    json_safe,
    run_matrix,
    run_one,
    write_atomic_json,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = str(REPO_ROOT / "scripts" / "run_process_isolated_benchmark.py")

try:
    import psutil  # noqa: F401
    _HAS_PSUTIL = True
except Exception:
    _HAS_PSUTIL = False


def _child_cmd(config, *flags):
    return build_python_command(SCRIPT, ["child", "--config-json", json.dumps(config), *flags])


def _cfg(**kw):
    base = {"samples": 10000, "channels": 4, "seed": 0}
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# Success + determinism
# --------------------------------------------------------------------------- #
def test_successful_child():
    result = run_one(_child_cmd(_cfg()), _cfg(), timeout_s=30)
    assert result.outcome == Outcome.PASS
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.checksum is not None
    assert result.tracemalloc_peak_bytes is not None and result.tracemalloc_peak_bytes >= 0
    assert result.correctness_ok is True


def test_deterministic_checksum():
    a = run_one(_child_cmd(_cfg(seed=5)), _cfg(seed=5), timeout_s=30)
    b = run_one(_child_cmd(_cfg(seed=5)), _cfg(seed=5), timeout_s=30)
    assert a.checksum == b.checksum
    assert a.outcome == b.outcome == Outcome.PASS


def test_repeated_execution_stable():
    for _ in range(3):
        r = run_one(_child_cmd(_cfg()), _cfg(), timeout_s=30)
        assert r.outcome == Outcome.PASS


# --------------------------------------------------------------------------- #
# Timeout / crash / invalid JSON
# --------------------------------------------------------------------------- #
def test_child_timeout():
    start = time.perf_counter()
    result = run_one(_child_cmd(_cfg(), "--inject-sleep", "30"), _cfg(), timeout_s=1.0)
    elapsed = time.perf_counter() - start
    assert result.outcome == Outcome.TIMEOUT
    assert result.timed_out is True
    assert elapsed < 15  # terminated promptly, not after the 30s sleep


def test_child_crash():
    result = run_one(_child_cmd(_cfg(), "--inject-crash"), _cfg(), timeout_s=30)
    assert result.outcome == Outcome.CHILD_CRASH
    assert result.exit_code == 7
    assert "injected crash" in result.stderr


def test_invalid_json_is_infrastructure_failure():
    result = run_one(_child_cmd(_cfg(), "--inject-invalid-json"), _cfg(), timeout_s=30)
    assert result.outcome == Outcome.INFRASTRUCTURE_FAILURE
    assert result.parse_error is not None
    assert result.checksum is None


def test_launch_failure_is_infrastructure_failure():
    result = run_one(["/nonexistent/definitely/not/here"], _cfg(), timeout_s=5)
    assert result.outcome == Outcome.INFRASTRUCTURE_FAILURE
    assert result.exit_code is None


# --------------------------------------------------------------------------- #
# Missing metric
# --------------------------------------------------------------------------- #
def test_missing_rss_is_null_and_optional_by_default():
    result = run_one(_child_cmd(_cfg(), "--inject-omit-rss"), _cfg(), timeout_s=30)
    assert result.peak_rss_bytes is None      # null, not zero
    assert result.outcome == Outcome.PASS     # RSS optional by default


def test_missing_required_metric_is_missing_metric():
    result = run_one(_child_cmd(_cfg(), "--inject-omit-rss"), _cfg(), timeout_s=30,
                     required_metrics=("checksum", "peak_rss_bytes"))
    assert result.outcome == Outcome.MISSING_METRIC
    assert "peak_rss_bytes" in result.missing_metrics


# --------------------------------------------------------------------------- #
# Orphan cleanup (POSIX; needs psutil to verify grandchild death)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(os.name == "nt" or not _HAS_PSUTIL,
                    reason="orphan verification uses POSIX process groups + psutil")
def test_orphan_cleanup(tmp_path):
    import psutil

    pidfile = tmp_path / "grandchild.pid"
    child_code = (
        "import os,sys,subprocess,time\n"
        "g=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'])\n"
        "open(sys.argv[1],'w').write(str(g.pid))\n"
        "sys.stdout.flush()\n"
        "time.sleep(120)\n"
    )
    argv = [sys.executable, "-c", child_code, str(pidfile)]
    result = run_one(argv, _cfg(), timeout_s=1.0)
    assert result.outcome == Outcome.TIMEOUT

    # Grandchild pid was recorded before the parent slept.
    for _ in range(50):
        if pidfile.exists() and pidfile.read_text().strip():
            break
        time.sleep(0.05)
    gpid = int(pidfile.read_text().strip())

    # After group termination the grandchild must be gone (or a reaped zombie).
    deadline = time.time() + 5.0
    cleaned = False
    while time.time() < deadline:
        if not psutil.pid_exists(gpid):
            cleaned = True
            break
        try:
            if psutil.Process(gpid).status() == psutil.STATUS_ZOMBIE:
                cleaned = True
                break
        except psutil.NoSuchProcess:
            cleaned = True
            break
        time.sleep(0.1)
    assert cleaned, f"grandchild {gpid} was orphaned"


# --------------------------------------------------------------------------- #
# Matrix: bounded parallelism, ordering, finite output
# --------------------------------------------------------------------------- #
def test_matrix_sequential_is_ordered_and_passes(tmp_path):
    configs = [_cfg(samples=s, seed=s) for s in (5000, 10000, 15000)]
    report = run_matrix(lambda c: _child_cmd(c), configs, timeout_s=30, sequential=True,
                        output_path=str(tmp_path / "report.json"))
    assert report["all_passed"] is True
    assert report["runner"]["sequential"] is True
    assert [r["config"]["samples"] for r in report["results"]] == [5000, 10000, 15000]
    # Atomic report exists and is valid finite JSON.
    written = json.loads((tmp_path / "report.json").read_text())
    assert written["num_configs"] == 3


def test_matrix_bounded_process_count(tmp_path):
    # Each child records its start/end; with max_workers=2, at most 2 overlap.
    marker_dir = tmp_path
    child_code = (
        "import sys,time,json\n"
        "idx=sys.argv[1]; d=sys.argv[2]\n"
        "start=time.time()\n"
        "time.sleep(0.4)\n"
        "end=time.time()\n"
        "open(d+'/'+idx+'.json','w').write(json.dumps({'start':start,'end':end}))\n"
        "print(json.dumps({'checksum':1.0}))\n"
    )

    def builder(config):
        return [sys.executable, "-c", child_code, str(config["idx"]), str(marker_dir)]

    configs = [{"idx": i} for i in range(6)]
    report = run_matrix(builder, configs, timeout_s=30, max_workers=2)
    assert report["runner"]["max_workers"] == 2
    assert report["all_passed"] is True

    intervals = []
    for i in range(6):
        data = json.loads((marker_dir / f"{i}.json").read_text())
        intervals.append((data["start"], data["end"]))
    # Compute maximum temporal overlap.
    events = []
    for s, e in intervals:
        events.append((s, 1)); events.append((e, -1))
    events.sort()
    concurrent = peak = 0
    for _, delta in events:
        concurrent += delta
        peak = max(peak, concurrent)
    assert peak <= 2, f"observed {peak} concurrent children, expected <= 2"


def test_matrix_summary_counts_outcomes():
    configs = [_cfg(), _cfg(seed=1)]
    builders = [
        _child_cmd(configs[0]),
        _child_cmd(configs[1], "--inject-crash"),
    ]
    report = run_matrix(lambda c: builders[configs.index(c)], configs, timeout_s=30, sequential=True)
    assert report["summary"].get("pass") == 1
    assert report["summary"].get("child_crash") == 1
    assert report["all_passed"] is False


# --------------------------------------------------------------------------- #
# Finite JSON + command construction
# --------------------------------------------------------------------------- #
def test_child_result_and_report_json_finite(tmp_path):
    result = run_one(_child_cmd(_cfg(), "--inject-omit-rss"), _cfg(), timeout_s=30)
    text = json.dumps(result.to_dict(), allow_nan=False)  # raises if NaN/Inf present
    assert "NaN" not in text and "Infinity" not in text
    assert json_safe(float("nan")) is None and json_safe(float("inf")) is None
    path = write_atomic_json(tmp_path / "r.json", {"x": float("inf"), "y": 1.0})
    loaded = json.loads(Path(path).read_text())
    assert loaded["x"] is None and loaded["y"] == 1.0


def test_windows_compatible_command_construction():
    argv = build_python_command("scripts/foo.py", ["child", "--config-json", "{}"])
    assert argv[0] == sys.executable
    assert argv[1] == "scripts/foo.py"
    assert argv[2:] == ["child", "--config-json", "{}"]
    # All argv entries are strings (argv list, not a shell string) -> shell=False safe.
    assert all(isinstance(part, str) for part in argv)


def test_invalid_runner_arguments():
    with pytest.raises(ValueError):
        run_one(_child_cmd(_cfg()), _cfg(), timeout_s=0)
    with pytest.raises(ValueError):
        run_matrix(lambda c: _child_cmd(c), [_cfg()], timeout_s=-1)
    with pytest.raises(ValueError):
        run_matrix(lambda c: _child_cmd(c), [_cfg()], timeout_s=10, max_workers=0)
