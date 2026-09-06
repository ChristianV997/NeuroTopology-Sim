"""Root conftest – ensures the repository root is on sys.path for all tests."""
from __future__ import annotations
import gc
import os
import random
import sys
import subprocess
import pytest
import numpy as np
from pathlib import Path

# Ensure plotting tests are headless before any test module imports pyplot.
os.environ.setdefault("MPLBACKEND", "Agg")

# Add the repo root so that bare ``from core.topology import ...`` imports work
# when pytest is invoked from any working directory.
sys.path.insert(0, str(Path(__file__).parent))
_repo_root = Path(__file__).parent
if os.name == "nt":
    # Lets `tools.make_compat` be found as `make` on Windows (see
    # _rewrite_windows_make below). Unnecessary elsewhere, and prepending the
    # repo root to PATH on every platform risks a repo-root file silently
    # shadowing a same-named system executable in subprocess calls.
    os.environ["PATH"] = str(_repo_root) + os.pathsep + os.environ.get("PATH", "")


def _rewrite_windows_make(args):
    if os.name == "nt" and isinstance(args, (list, tuple)) and args and args[0] == "make":
        return [sys.executable, "-m", "tools.make_compat", *args[1:]]
    return args


_subprocess_run = subprocess.run
_subprocess_check_call = subprocess.check_call
_subprocess_check_output = subprocess.check_output
_subprocess_popen = subprocess.Popen
_TEST_SUBPROCESS_TIMEOUT_S = 120


def _with_test_timeout(keyword):
    if keyword.get("timeout") is None:
        keyword["timeout"] = _TEST_SUBPROCESS_TIMEOUT_S
    return keyword


def _run_with_make_compat(args, *positional, **keyword):
    return _subprocess_run(_rewrite_windows_make(args), *positional, **_with_test_timeout(keyword))


def _check_call_with_make_compat(args, *positional, **keyword):
    return _subprocess_check_call(_rewrite_windows_make(args), *positional, **_with_test_timeout(keyword))


def _check_output_with_make_compat(args, *positional, **keyword):
    return _subprocess_check_output(_rewrite_windows_make(args), *positional, **_with_test_timeout(keyword))


def _popen_with_make_compat(args, *positional, **keyword):
    return _subprocess_popen(_rewrite_windows_make(args), *positional, **keyword)


# Keep the real Popen class: third-party libraries reference it as a type in
# annotations. The convenience helpers above are bounded on every platform;
# only the Windows Popen wrapper is needed for make compatibility.
subprocess.run = _run_with_make_compat
subprocess.check_call = _check_call_with_make_compat
subprocess.check_output = _check_output_with_make_compat
if os.name == "nt":
    subprocess.Popen = _popen_with_make_compat
for _thread_env in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_thread_env, "1")


@pytest.fixture(autouse=True)
def isolate_test_process_state():
    """Restore test-mutated RNG/display state and collect Python cycles."""
    python_random_state = random.getstate()
    numpy_random_state = np.random.get_state()
    torch = sys.modules.get("torch")
    torch_random_state = torch.get_rng_state() if torch is not None else None
    yield
    pyplot = sys.modules.get("matplotlib.pyplot")
    if pyplot is not None:
        pyplot.close("all")
    random.setstate(python_random_state)
    np.random.set_state(numpy_random_state)
    if torch is not None and torch_random_state is not None:
        torch.set_rng_state(torch_random_state)
    gc.collect()
