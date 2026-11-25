"""Pin the root conftest optional-dependency skip policy.

The policy may only convert a missing *optional-profile* module into a skip, and
only outside CI, so it can never hide a base dependency or turn a red optional
job green.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def policy(request):
    # Executing the root conftest a second time re-wraps subprocess helpers; restore them afterwards.
    saved = {name: getattr(subprocess, name) for name in ("run", "check_call", "check_output", "Popen")}
    try:
        spec = importlib.util.spec_from_file_location("nts_root_conftest_policy_under_test", ROOT / "conftest.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        yield module
    finally:
        for name, value in saved.items():
            setattr(subprocess, name, value)


def _requirement_names(path: Path) -> set[str]:
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        match = re.match(r"[A-Za-z0-9_.-]+", line)
        if match:
            names.add(match.group(0).lower().replace("_", "-"))
    return names


def test_allowlist_entries_are_declared_only_in_non_base_profiles(policy):
    base = _requirement_names(ROOT / "requirements-base.txt")
    optional: set[str] = set()
    for path in ROOT.glob("requirements-*.txt"):
        if path.name != "requirements-base.txt":
            optional |= _requirement_names(path)
    for module, dist in policy.OPTIONAL_MODULE_DISTRIBUTIONS.items():
        dist = dist.lower().replace("_", "-")
        assert dist not in base, f"{module} is a base dependency and must not be skippable"
        assert dist in optional, f"{module} ({dist}) is not declared in any optional requirements profile"


def test_only_allowlisted_missing_modules_convert(policy):
    assert policy._missing_optional_module(ModuleNotFoundError("x", name="mne")) == "mne"
    assert policy._missing_optional_module(ModuleNotFoundError("x", name="mne.io")) == "mne"
    assert policy._missing_optional_module(ModuleNotFoundError("x", name="numpy")) is None
    assert policy._missing_optional_module(ImportError("cannot import name")) is None
    assert policy._missing_optional_module(None, "E   ModuleNotFoundError: No module named 'qutip'") == "qutip"
    assert policy._missing_optional_module(None, "E   ModuleNotFoundError: No module named 'scipy'") is None
    assert policy._missing_optional_module(None, "") is None


def test_policy_is_off_in_ci_and_in_strict_mode(policy, monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("NTS_STRICT_OPTIONAL_DEPS", raising=False)
    assert policy._optional_skip_enabled() is True
    monkeypatch.setenv("CI", "true")
    assert policy._optional_skip_enabled() is False
    monkeypatch.delenv("CI")
    monkeypatch.setenv("NTS_STRICT_OPTIONAL_DEPS", "1")
    assert policy._optional_skip_enabled() is False
