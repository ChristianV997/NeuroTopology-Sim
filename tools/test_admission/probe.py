"""Deterministic offline probe of host environment and platform capabilities.

Probes packages and system capabilities strictly without external network access,
socket calls, or mutating the environment.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from typing import Mapping

from tools.test_admission.models import PlatformCapabilities


def probe_package(package_name: str) -> str | None:
    """Probes if a Python package is installed, returning its version or None."""
    name = package_name.strip()
    # Normalize common package aliases
    import_name = name
    if name == "scikit-learn":
        import_name = "sklearn"
    elif name == "pyyaml":
        import_name = "yaml"

    try:
        spec = importlib.util.find_spec(import_name)
        if spec is None:
            return None
    except (ModuleNotFoundError, ValueError):
        return None

    # Try metadata lookup for version
    try:
        return importlib.metadata.version(name)
    except Exception:
        pass

    try:
        return importlib.metadata.version(import_name)
    except Exception:
        return "installed"


def probe_symlink_capability() -> bool:
    """Tests if the current filesystem and user account permit creating symlinks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "target.txt"
        target.write_text("symlink_test", encoding="utf-8")
        link = Path(tmpdir) / "link.txt"
        try:
            os.symlink(target, link)
            return link.is_symlink()
        except (OSError, NotImplementedError):
            return False


def probe_docker_capability() -> bool:
    """Checks whether the Docker CLI and daemon are locally accessible."""
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return False
    try:
        # Run docker info with very short timeout, pure local check
        proc = subprocess.run(
            [docker_bin, "info"],
            capture_output=True,
            timeout=3,
            text=True,
        )
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, OSError, Exception):
        return False


def probe_cuda_capability() -> bool:
    """Checks if CUDA / GPU acceleration is locally available."""
    try:
        if importlib.util.find_spec("torch"):
            import torch
            return bool(torch.cuda.is_available())
    except Exception:
        pass
    return False


def probe_cloud_qpu_capability() -> bool:
    """Checks if cloud QPU credentials/endpoints are locally configured."""
    qpu_env_keys = [
        "QISKIT_IBM_TOKEN",
        "IBM_QUANTUM_TOKEN",
        "AWS_BRAKET_TOKEN",
        "IONQ_API_KEY",
        "RIGETTI_API_KEY",
    ]
    return any(bool(os.environ.get(k)) for k in qpu_env_keys)


def probe_external_solver_capability() -> bool:
    """Checks if optional external mathematical solvers are available."""
    for solver in ("cvxpy", "scipy.optimize", "z3"):
        try:
            if importlib.util.find_spec(solver):
                return True
        except Exception:
            continue
    return False


def probe_platform_capabilities(packages_to_check: Sequence[str] | None = None) -> PlatformCapabilities:
    """Performs a deterministic, offline probe of the current platform capabilities."""
    system = platform.system().lower()
    is_windows = (system == "windows")
    is_linux = (system == "linux")
    is_darwin = (system == "darwin")
    is_posix = (os.name == "posix")

    has_symlinks = probe_symlink_capability()
    has_docker = probe_docker_capability()
    has_cuda = probe_cuda_capability()
    has_cloud_qpu = probe_cloud_qpu_capability()
    has_external_solver = probe_external_solver_capability()

    installed_packages: dict[str, str | None] = {}
    default_packages = [
        "numpy", "scipy", "pytest", "mne", "ripser", "cripser", "torch",
        "pybv", "edfio", "matplotlib", "h5py", "nwbwidgets", "pydantic",
        "z3", "cvxpy",
    ]
    all_packages = set(default_packages)
    if packages_to_check:
        all_packages.update(packages_to_check)

    for pkg in sorted(all_packages):
        installed_packages[pkg] = probe_package(pkg)

    cpu_cores = os.cpu_count()

    total_mem = None
    try:
        import psutil
        total_mem = round(psutil.virtual_memory().total / (1024 ** 3), 2)
    except Exception:
        total_mem = None

    return PlatformCapabilities(
        os_name=system,
        is_windows=is_windows,
        is_posix=is_posix,
        is_linux=is_linux,
        is_darwin=is_darwin,
        has_symlinks=has_symlinks,
        has_docker=has_docker,
        has_cuda=has_cuda,
        has_gpu=has_cuda,
        has_cloud_qpu=has_cloud_qpu,
        has_external_solver=has_external_solver,
        installed_packages=installed_packages,
        network_available=False,  # Enforce offline policy by default
        cpu_cores=cpu_cores,
        total_memory_gb=total_mem,
    )
