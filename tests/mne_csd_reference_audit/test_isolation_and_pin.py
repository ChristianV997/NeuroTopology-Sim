from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tools.mne_csd_reference_audit import pin

REPO_ROOT = Path(__file__).resolve().parents[2]

# Every module of the package is imported in the clean process before the check, so an import-time load of MNE in any
# module fails here, whatever its syntax. A load that happens only when a function is called is caught by the AST
# guards below.
_ISOLATED = """
import importlib, pkgutil, socket, sys
sys.path.insert(0, sys.argv[1])
def _blocked(*a, **k):
    raise SystemExit("network access attempted")
socket.socket.connect = _blocked
socket.create_connection = _blocked
import tools.mne_csd_reference_audit as package
for module in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
    importlib.import_module(module.name)
from tools.mne_csd_reference_audit.report import build_report
report = build_report()
print(report["status"], "mne" in sys.modules, report["evidence_class"])
"""


def test_reference_runs_in_a_clean_process_without_mne_or_network():
    proc = subprocess.run(
        [sys.executable, "-I", "-c", _ISOLATED, str(REPO_ROOT)],
        capture_output=True, text=True, timeout=300, cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    status, mne_loaded, evidence = proc.stdout.strip().splitlines()[-1].split()
    assert status == "HOLD"
    assert mne_loaded == "False"
    assert evidence == "SYNTHETIC_ONLY"


# AST-based guards. Source text is not matched, so string literals (including the samples below) never trigger them.
# A violation in the package is any of:
#   - an import that names mne, or imports or aliases a dynamic loader (import_module, __import__, exec, eval, runpy,
#     builtins, and the spec or exec helpers);
#   - any reference to such a name or attribute, whether called, bound to a variable, or passed on;
#   - a getattr whose attribute name is a denied name or is not a string literal.
# For the skip guard, a violation is a skip, skipif, xfail, importorskip or applymarker used as an attribute, as a call,
# or imported. A local variable with one of those names is not a violation.
_DENIED_LOADERS = {
    "__import__", "import_module", "exec", "eval", "compile", "builtins", "__builtins__", "runpy",
    "run_module", "run_path", "spec_from_file_location", "module_from_spec", "exec_module",
}
_SKIP_NAMES = {"skip", "skipif", "xfail", "importorskip", "applymarker"}


def _mne_violations(source: str) -> list[str]:
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        # Fail closed: a file the guard cannot parse cannot be shown to avoid MNE.
        return ["unparseable source"]
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [f"import {a.name}" for a in node.names
                      if a.name == "mne" or a.name.startswith("mne.") or a.name.split(".")[0] in _DENIED_LOADERS]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "mne" or module.startswith("mne.") or module.split(".")[0] in _DENIED_LOADERS:
                found.append(f"from {module} import ...")
            found += [f"from {module} import {a.name}" for a in node.names
                      if a.name in _DENIED_LOADERS or a.name == "mne"]
        elif isinstance(node, ast.Name) and node.id in _DENIED_LOADERS:
            found.append(f"name {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in _DENIED_LOADERS:
            found.append(f"attribute .{node.attr}")
        elif isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Name) and func.id == "getattr") or (
                isinstance(func, ast.Attribute) and func.attr == "getattr"
            ):
                attr = node.args[1] if len(node.args) > 1 else None
                if not (isinstance(attr, ast.Constant) and isinstance(attr.value, str)) or attr.value in _DENIED_LOADERS:
                    found.append("getattr with a computed or denied attribute name")
    return found


def _skip_violations(source: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr in _SKIP_NAMES:
            found.append(f"attribute .{node.attr}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _SKIP_NAMES:
            found.append(f"call {node.func.id}(...)")
        elif isinstance(node, ast.ImportFrom) and any(a.name in _SKIP_NAMES for a in node.names):
            found.append(f"from {node.module} import ...")
    return found


def test_reference_package_source_never_imports_mne():
    package = REPO_ROOT / "tools" / "mne_csd_reference_audit"
    for source in package.rglob("*.py"):
        assert _mne_violations(source.read_text(encoding="utf-8")) == [], source.name


@pytest.mark.parametrize("sample", [
    "import mne",
    "from mne.preprocessing import compute_current_source_density",
    "    import mne  # indented",
    "importlib.import_module('mne')",
    "x = importlib.import_module(\"mne.io\")",
    "__import__('mne')",
    "importlib.import_module(module_name)",
    "__import__(name)",
])
def test_mne_import_guard_flags_static_and_dynamic_forms(sample):
    assert _mne_violations(sample), sample


# Regression (2026-10-20, code review): these forms passed the earlier source-text guard. Each would load MNE or run
# dynamic code without "import mne" at the start of a line.
@pytest.mark.parametrize("sample", [
    "import numpy, mne",
    "try:\n    import mne\nexcept ImportError:\n    pass",
    "from importlib import import_module as imp\nimp('mne')",
    "import importlib\nimportlib.import_module ('mne')",
    "exec('import mne')",
])
def test_mne_import_guard_flags_aliased_multi_name_and_dynamic_code_forms(sample):
    assert _mne_violations(sample), sample


# Regression (2026-10-20, code review): a loader bound to a name, or reached through getattr or runpy, is not a call to
# a denied name, so the call-only check passed it.
@pytest.mark.parametrize("sample", [
    "f = importlib.import_module\nf('mne')",
    "x = __import__\nx('mne')",
    "g = eval",
    "getattr(importlib, 'import_module')('mne')",
    "name = 'import_module'\ngetattr(importlib, name)('mne')",
    "import runpy\nrunpy.run_module('mne')",
])
def test_mne_import_guard_flags_loaders_bound_to_names_and_indirect_forms(sample):
    assert _mne_violations(sample), sample


@pytest.mark.parametrize("sample", [
    "import numpy as np",
    "mnemonic = 1",
    "# mne is the name of the reference, not an import",
    "from numpy.polynomial import legendre",
    "import importlib\nimportlib.reload(np)",
    "value = getattr(np, 'pi')",
])
def test_mne_import_guard_ignores_unrelated_text(sample):
    assert _mne_violations(sample) == [], sample


def test_required_surface_contains_no_skip_markers():
    # The Round 6 gate counts any skipped test as a failure. Every file in this directory is therefore checked,
    # including this one, which is not exempt: the guard works on the AST, so its own sample strings do not match.
    here = Path(__file__).resolve().parent
    for source in sorted(here.glob("*.py")):
        assert _skip_violations(source.read_text(encoding="utf-8")) == [], source.name


# Regression (2026-10-20, code review): a skip written as @pytest.mark.skip or applymarker was not matched by the
# earlier text pattern, which needed the literal "pytest.skip".
@pytest.mark.parametrize("sample", [
    "@pytest.mark.skip(reason='x')\ndef test_x():\n    pass",
    "def test_x(request):\n    request.applymarker(pytest.mark.skip)",
    "import pytest\npytest.skip('x')",
    "pytest.importorskip('mne')",
    "@pytest.mark.skipif(True, reason='x')\ndef test_x():\n    pass",
    "@pytest.mark.xfail\ndef test_x():\n    pass",
])
def test_skip_guard_flags_decorator_applymarker_and_call_forms(sample):
    assert _skip_violations(sample), sample


@pytest.mark.parametrize("sample", [
    "import pytest\n@pytest.mark.parametrize('x', [1])\ndef test_x(x):\n    assert x",
    "# pytest.skip is only mentioned in a comment",
    # Regression (2026-10-20, code review): a local variable named like a skip helper was flagged.
    "skip = 3\nprint(skip)",
    "def test_x(skip):\n    assert skip == 3",
])
def test_skip_guard_ignores_plain_test_code(sample):
    assert _skip_violations(sample) == [], sample


def test_pin_provenance_claims_are_currently_verified():
    source = (REPO_ROOT / "tools" / "mne_csd_reference_audit" / "pin.py").read_text(encoding="utf-8")
    assert "NOT re-verified" not in source
    assert "verified against the live tag" in source


def test_pin_is_internally_consistent():
    assert pin.MNE_TAG == f"v{pin.MNE_VERSION}"
    assert re.fullmatch(r"[0-9a-f]{40}", pin.MNE_TAG_COMMIT)
    assert re.fullmatch(r"[0-9a-f]{64}", pin.MNE_SDIST_SHA256)
    assert pin.MNE_SDIST_FILENAME == f"mne-{pin.MNE_VERSION}.tar.gz"
    assert pin.MNE_LICENSE == "BSD-3-Clause"
    for digest in pin.MNE_SOURCE_FILES.values():
        assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert pin.MNE_DEFAULTS == {"stiffness": 4, "n_legendre_terms": 50, "lambda2": 1e-5, "sphere": "auto"}


def test_report_json_is_strict_and_status_is_hold():
    from tools.mne_csd_reference_audit.report import build_report, to_json

    text = to_json(build_report())
    decoded = json.loads(text, parse_constant=lambda t: (_ for _ in ()).throw(ValueError(t)))
    assert decoded["status"] == "HOLD"
    assert decoded["levels"]["L3_mne_execution_parity"].startswith("not executed")
    assert decoded["pinned_mne"]["tag_commit"] == pin.MNE_TAG_COMMIT


def test_report_l3_status_names_the_live_test_location_and_not_a_skip():
    # Regression (2026-10-20, code review): the snapshot said "optional integration test skips", which describes a test
    # that is no longer in the gated surface. The status must point at the live comparison's actual location.
    from tools.mne_csd_reference_audit.report import build_report

    status = build_report()["levels"]["L3_mne_execution_parity"]
    assert "tests/optional_live_mne/" in status, status
    assert "integration test skips" not in status, status


# Regression (2026-10-20, reference audit): the doc said the TC ordering difference was 1.5e-10 to 1.7e-10 and the
# operator difference at most 4.4e-13. Neither figure was in any artifact, and re-measuring gave 1.8e-12 to 1.5e-10
# and about 3e-14. The snapshot now carries both measured figures per montage, so the doc quotes checked numbers.
def test_report_records_the_mne_ordering_difference_within_documented_bounds():
    from tools.mne_csd_reference_audit.report import build_report

    rows = build_report()["operator"]["montages"]
    assert rows
    for row in rows:
        assert "tc_ordering_abs_max" in row and "operator_ordering_rel_to_max" in row, row["name"]
        assert row["tc_ordering_abs_max"] < 1e-9, row
        assert row["operator_ordering_rel_to_max"] < 1e-13, row


# Regression (2026-10-20, reference audit): conftest.py holds a near-literal transcription of MNE 1.13.2 code, yet it
# carried no notice, while pin.py said no MNE code is copied. BSD-3-Clause requires the copyright notice and the
# conditions to travel with source copies, so the notice must be in the file that contains the copy.
def test_transcription_carries_the_mne_licence_notice():
    conftest = (REPO_ROOT / "tests" / "mne_csd_reference_audit" / "conftest.py").read_text(encoding="utf-8")
    assert "Copyright 2011-2025 MNE-Python authors" in conftest
    assert "Redistributions of source code must retain the above copyright notice" in conftest
    assert "BSD-3-Clause" in conftest
    # Regression (2026-10-23, post-merge audit of #402): mne/preprocessing/_csd.py lines 5-11, the file the
    # transcription copies _compute_csd from, carry a second copyright line that the notice did not keep.
    assert "Copyright 2003-2010 J\u00fcrgen Kayser" in conftest
