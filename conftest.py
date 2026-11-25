"""Root conftest - ensures isolation, deterministic seeds, network guards, and clean environments."""
from __future__ import annotations
import gc
import os
import random
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Generator

import numpy as np
import pytest

# Add the repo root so that bare ``from core.topology import ...`` imports work
# when pytest is invoked from any working directory.
_repo_root = Path(__file__).resolve().parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

if os.name == "nt":
    # Lets `tools.make_compat` be found as `make` on Windows.
    os.environ["PATH"] = str(_repo_root) + os.pathsep + os.environ.get("PATH", "")


def _rewrite_windows_make(args: Any) -> Any:
    if os.name == "nt" and isinstance(args, (list, tuple)) and args and args[0] == "make":
        return [sys.executable, "-m", "tools.make_compat", *args[1:]]
    return args


_subprocess_run = subprocess.run
_subprocess_check_call = subprocess.check_call
_subprocess_check_output = subprocess.check_output
_subprocess_popen = subprocess.Popen
_TEST_SUBPROCESS_TIMEOUT_S = 120


def _with_test_timeout(keyword: dict[str, Any]) -> dict[str, Any]:
    if keyword.get("timeout") is None:
        keyword["timeout"] = _TEST_SUBPROCESS_TIMEOUT_S
    return keyword


def _run_with_make_compat(args: Any, *positional: Any, **keyword: Any) -> Any:
    return _subprocess_run(_rewrite_windows_make(args), *positional, **_with_test_timeout(keyword))


def _check_call_with_make_compat(args: Any, *positional: Any, **keyword: Any) -> Any:
    return _subprocess_check_call(_rewrite_windows_make(args), *positional, **_with_test_timeout(keyword))


def _check_output_with_make_compat(args: Any, *positional: Any, **keyword: Any) -> Any:
    return _subprocess_check_output(_rewrite_windows_make(args), *positional, **_with_test_timeout(keyword))


def _popen_with_make_compat(args: Any, *positional: Any, **keyword: Any) -> Any:
    return _subprocess_popen(_rewrite_windows_make(args), *positional, **keyword)


# Keep the real Popen class because third-party libraries reference it in type
# annotations. The convenience helpers are bounded on every platform; only
# Windows needs the Popen wrapper for make compatibility.
subprocess.run = _run_with_make_compat
subprocess.check_call = _check_call_with_make_compat
subprocess.check_output = _check_output_with_make_compat
if os.name == "nt":
    subprocess.Popen = _popen_with_make_compat

# Keep native BLAS/OpenMP/MKL thread pools strictly bounded to 1 per test worker
for _thread_env in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_thread_env, "1")

# Default global deterministic seed
DEFAULT_TEST_SEED = 42


@pytest.fixture(autouse=True)
def deterministic_seed(request: pytest.FixtureRequest) -> Generator[int, None, None]:
    """Ensure every test begins with deterministic PRNG state across random and numpy."""
    seed_marker = request.node.get_closest_marker("seed")
    seed = seed_marker.args[0] if seed_marker and seed_marker.args else DEFAULT_TEST_SEED

    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass

    try:
        import torch
        torch.manual_seed(seed)
    except ImportError:
        pass

    yield seed


@pytest.fixture(autouse=True)
def isolate_test_process_state() -> Generator[None, None, None]:
    """Restore RNG/display state and collect native-backed Python cycles."""
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


@pytest.fixture(autouse=True)
def block_unauthorized_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Enforce strict offline discipline: prevent network requests unless test is marked with @pytest.mark.network."""
    if "network" in request.keywords:
        return

    orig_connect = socket.socket.connect

    def guarded_connect(self: Any, address: Any) -> Any:
        host = address[0] if isinstance(address, (list, tuple)) and address else address
        # Allow localhost / loopback communication for local test servers if any
        if host in ("localhost", "127.0.0.1", "::1"):
            return orig_connect(self, address)
        raise RuntimeError(
            f"Unauthorized network connection to {address!r} blocked during test execution. "
            "NeuroTopology-Sim tests must run strictly offline. "
            "If this test explicitly requires external network, mark it with @pytest.mark.network."
        )

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


@pytest.fixture(autouse=True)
def collect_numpy_garbage() -> Generator[None, None, None]:
    """Release cyclic Python objects after each test."""
    yield
    gc.collect()


@pytest.fixture
def isolated_test_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide a dedicated, clean scratch directory isolated from the working tree."""
    scratch = tmp_path / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NEUROTOPOLOGY_TEST_SCRATCH", str(scratch))
    return scratch
