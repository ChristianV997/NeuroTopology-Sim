"""Root conftest – ensures the repository root is on sys.path for all tests."""
from __future__ import annotations
import sys
import gc
import os
import subprocess
import pytest
from pathlib import Path

# Add the repo root so that bare ``from core.topology import ...`` imports work
# when pytest is invoked from any working directory.
sys.path.insert(0, str(Path(__file__).parent))
_repo_root = Path(__file__).parent
os.environ["PATH"] = str(_repo_root) + os.pathsep + os.environ.get("PATH", "")


def _rewrite_windows_make(args):
    if os.name == "nt" and isinstance(args, (list, tuple)) and args and args[0] == "make":
        return [sys.executable, "-m", "tools.make_compat", *args[1:]]
    return args


_subprocess_run = subprocess.run
_subprocess_check_call = subprocess.check_call
_subprocess_check_output = subprocess.check_output
_subprocess_popen = subprocess.Popen


def _run_with_make_compat(args, *positional, **keyword):
    return _subprocess_run(_rewrite_windows_make(args), *positional, **keyword)


def _check_call_with_make_compat(args, *positional, **keyword):
    return _subprocess_check_call(_rewrite_windows_make(args), *positional, **keyword)


def _check_output_with_make_compat(args, *positional, **keyword):
    return _subprocess_check_output(_rewrite_windows_make(args), *positional, **keyword)


def _popen_with_make_compat(args, *positional, **keyword):
    return _subprocess_popen(_rewrite_windows_make(args), *positional, **keyword)


subprocess.run = _run_with_make_compat
subprocess.check_call = _check_call_with_make_compat
subprocess.check_output = _check_output_with_make_compat
subprocess.Popen = _popen_with_make_compat
for _thread_env in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_thread_env, "1")


@pytest.fixture(autouse=True)
def collect_numpy_garbage():
    """Release cyclic Python objects after each test without touching arrays."""
    yield
    gc.collect()
