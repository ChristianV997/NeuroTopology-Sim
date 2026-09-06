#!/usr/bin/env python3
"""Cross-adapter interoperability conformance runner for NeuroTopology-Sim.

Validates PR #212 (contracts), PR #214 (MNE streaming), and PR #220 (native signal)
against the 16 contract properties and produces a structured conformance report.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

CONTRACT_PROPERTIES = [
    "1. Signal chunks have shape (channels, samples)",
    "2. Channel order is deterministic",
    "3. Sampling frequency is preserved exactly",
    "4. Units and scaling are explicit",
    "5. Source checksums are deterministic",
    "6. Montage coordinates are native, safely inferred, or unavailable",
    "7. Inferred coordinates carry provenance",
    "8. Missing coordinates are never silently fabricated",
    "9. Chunk boundaries are reproducible",
    "10. Optional dependency absence yields a structured capability state",
    "11. Malformed files produce actionable errors",
    "12. No adapter performs network access",
    "13. Adapters do not import heavy optional packages at package-import time",
    "14. Interoperability adapters preserve metadata when converting between formats",
    "15. Empty, truncated, and single-channel inputs are handled deterministically",
    "16. Numeric values are finite or explicitly null",
]


def check_capabilities() -> tuple[list[str], list[str]]:
    adapters_found = []
    missing_capabilities = []

    # PR #212: Contracts
    try:
        if importlib.util.find_spec("shared.interop.contracts"):
            adapters_found.append("PR212_Contracts")
        else:
            missing_capabilities.append("PR212_Contracts (shared.interop.contracts not present in checkout)")
    except (ModuleNotFoundError, ValueError):
        missing_capabilities.append("PR212_Contracts (shared.interop.contracts not present in checkout)")

    # PR #214: MNE streaming adapter
    try:
        if importlib.util.find_spec("sciencer_d.btc_icft.io.eeg_mne_adapter"):
            try:
                mod = importlib.import_module("sciencer_d.btc_icft.io.eeg_mne_adapter")
                if hasattr(mod, "iter_mne_signal_chunks"):
                    adapters_found.append("PR214_MNE_Streaming")
                else:
                    missing_capabilities.append("PR214_MNE_Streaming (iter_mne_signal_chunks not found in eeg_mne_adapter)")
            except Exception as e:
                missing_capabilities.append(f"PR214_MNE_Streaming (Import failed: {e})")
        else:
            missing_capabilities.append("PR214_MNE_Streaming (eeg_mne_adapter module not present)")
    except (ModuleNotFoundError, ValueError):
        missing_capabilities.append("PR214_MNE_Streaming (eeg_mne_adapter module not present)")

    # Optional dependency: MNE package
    try:
        if not importlib.util.find_spec("mne"):
            missing_capabilities.append("mne (optional package not installed)")
    except (ModuleNotFoundError, ValueError):
        missing_capabilities.append("mne (optional package not installed)")

    # PR #220: Native signal adapter
    try:
        if importlib.util.find_spec("sciencer_d.btc_icft.io.eeg_native_adapter"):
            adapters_found.append("PR220_Native_Signal")
        else:
            missing_capabilities.append("PR220_Native_Signal (eeg_native_adapter module not present in checkout)")
    except (ModuleNotFoundError, ValueError):
        missing_capabilities.append("PR220_Native_Signal (eeg_native_adapter module not present in checkout)")

    return adapters_found, missing_capabilities


def run_cmd(args: list[str], desc: str) -> dict[str, Any]:
    print(f"--> {desc}...")
    res = subprocess.run(args, capture_output=True, text=True)
    passed = res.returncode == 0
    return {
        "description": desc,
        "passed": passed,
        "returncode": res.returncode,
        "stdout": res.stdout.strip(),
        "stderr": res.stderr.strip(),
    }


def main():
    print("=" * 70)
    print("NeuroTopology-Sim Interoperability Conformance Validation")
    print("=" * 70)

    adapters_tested, missing_capabilities = check_capabilities()

    report = {
        "status": "PASS",
        "contracts_tested": CONTRACT_PROPERTIES,
        "adapters_tested": adapters_tested if adapters_tested else ["Reference_Idealized_Adapter"],
        "missing_capabilities": missing_capabilities,
        "test_results": {},
    }

    # 1. Compilation and Syntax Check
    compile_res = run_cmd(
        [sys.executable, "-m", "py_compile", "tests/interop_conformance/validator.py", "tests/interop_conformance/test_conformance_rules.py"],
        "Validating Python compilation of conformance suite",
    )
    report["test_results"]["compilation"] = "PASS" if compile_res["passed"] else "FAIL"
    if not compile_res["passed"]:
        report["status"] = "FAIL"
        print(compile_res["stderr"])

    # 2. Conformance Tests Execution
    conf_res = run_cmd(
        [sys.executable, "-m", "pytest", "-v", "tests/interop_conformance"],
        "Running full cross-adapter conformance test suite",
    )
    report["test_results"]["conformance_suite"] = "PASS" if conf_res["passed"] else "FAIL"
    if not conf_res["passed"]:
        report["status"] = "FAIL"
        print(conf_res["stdout"])
        print(conf_res["stderr"])

    # 3. Existing Interop Tests (if available)
    if Path("tests/interop").exists():
        interop_res = run_cmd(
            [sys.executable, "-m", "pytest", "-v", "tests/interop"],
            "Running existing interoperability contract tests (PR #212)",
        )
        report["test_results"]["existing_interop_tests"] = "PASS" if interop_res["passed"] else "FAIL"
        if not interop_res["passed"]:
            report["status"] = "FAIL"
    else:
        report["test_results"]["existing_interop_tests"] = "SKIPPED (Directory not in current checkout)"

    # 4. Adapter Tests from PR #214 / PR #220 (if available)
    if Path("tests/eeg/test_mne_streaming_adapter.py").exists():
        pr214_res = run_cmd(
            [sys.executable, "-m", "pytest", "-v", "tests/eeg/test_mne_streaming_adapter.py"],
            "Running PR #214 MNE adapter tests",
        )
        report["test_results"]["pr214_adapter_tests"] = "PASS" if pr214_res["passed"] else "FAIL"
        if not pr214_res["passed"]:
            report["status"] = "FAIL"
    else:
        report["test_results"]["pr214_adapter_tests"] = "SKIPPED (PR #214 test file not in current checkout)"

    if Path("tests/eeg/test_native_adapter.py").exists():
        pr220_res = run_cmd(
            [sys.executable, "-m", "pytest", "-v", "tests/eeg/test_native_adapter.py"],
            "Running PR #220 Native adapter tests",
        )
        report["test_results"]["pr220_adapter_tests"] = "PASS" if pr220_res["passed"] else "FAIL"
        if not pr220_res["passed"]:
            report["status"] = "FAIL"
    else:
        report["test_results"]["pr220_adapter_tests"] = "SKIPPED (PR #220 test file not in current checkout)"

    # 5. Governance Validation
    gov_res = run_cmd(
        [sys.executable, "-m", "governance.validate"],
        "Running governance specification validation",
    )
    report["test_results"]["governance_validation"] = "PASS" if gov_res["passed"] else "FAIL"
    if not gov_res["passed"]:
        report["status"] = "FAIL"
        print(gov_res["stderr"])

    print("\n" + "=" * 70)
    print(f"CONFORMANCE STATUS: {report['status']}")
    print("=" * 70)
    print("Structured Conformance Report:")
    print(json.dumps(report, indent=2))

    sys.exit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
