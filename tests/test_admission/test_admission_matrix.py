"""Comprehensive test suite for test admission matrix and capability gating."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import pytest

from tools.test_admission.matrix import (
    AdmissionMatrixEvaluator,
    load_admission_matrix_file,
    load_admission_records_from_dict,
)
from tools.test_admission.models import (
    ActionWhenUnavailable,
    AdmissionCategory,
    AdmissionDecision,
    DockerPolicy,
    MemoryClass,
    NetworkPolicy,
    PlatformCapabilities,
    ScientificRelevance,
    TestAdmissionRecord,
    TimeoutClass,
)
from tools.test_admission.probe import probe_platform_capabilities
from scripts.validate_test_admission import main as cli_main, run_admission_validation


class TestAdmissionMatrix:
    """Rigorous verification of the admission decision engine."""

    def test_torch_unavailable(self, base_capabilities: PlatformCapabilities):
        """When torch or CUDA is unavailable, GPU test must produce SKIP_OPTIONAL_DEPENDENCY."""
        caps = copy.deepcopy(base_capabilities)
        caps.has_cuda = False
        caps.installed_packages["torch"] = None

        record = TestAdmissionRecord(
            test_group="gpu_test",
            category=AdmissionCategory.GPU,
            required_packages=["torch"],
            required_platform_capabilities=["cuda"],
            action_when_unavailable=ActionWhenUnavailable.SKIP,
        )

        evaluator = AdmissionMatrixEvaluator(caps)
        result = evaluator.evaluate_record(record)

        assert result.decision == AdmissionDecision.SKIP_OPTIONAL_DEPENDENCY
        assert result.is_skipped is True
        assert result.is_blocked is False
        assert result.is_runnable is False
        assert "cuda" in result.reason.lower() or "torch" in result.reason.lower()

    def test_cripser_unavailable(self, base_capabilities: PlatformCapabilities):
        """When cripser is optional and absent, TDA test must produce SKIP_OPTIONAL_DEPENDENCY."""
        caps = copy.deepcopy(base_capabilities)
        caps.installed_packages["ripser"] = "0.6.4"
        caps.installed_packages["cripser"] = None

        record = TestAdmissionRecord(
            test_group="tda_filtration_test",
            category=AdmissionCategory.TDA,
            required_packages=["ripser"],
            optional_packages=["cripser"],
            action_when_unavailable=ActionWhenUnavailable.SKIP,
        )

        evaluator = AdmissionMatrixEvaluator(caps)
        result = evaluator.evaluate_record(record)

        assert result.decision == AdmissionDecision.SKIP_OPTIONAL_DEPENDENCY
        assert result.is_skipped is True
        assert "cripser" in result.missing_optional_packages
        assert result.missing_required_packages == []

    def test_docker_unavailable(self, base_capabilities: PlatformCapabilities):
        """When Docker is required but daemon is absent, test must produce BLOCK_DOCKER_UNAVAILABLE."""
        caps = copy.deepcopy(base_capabilities)
        caps.has_docker = False

        record = TestAdmissionRecord(
            test_group="container_test",
            category=AdmissionCategory.DOCKER,
            docker_policy=DockerPolicy.REQUIRED,
            action_when_unavailable=ActionWhenUnavailable.BLOCK,
        )

        evaluator = AdmissionMatrixEvaluator(caps)
        result = evaluator.evaluate_record(record)

        assert result.decision == AdmissionDecision.BLOCK_DOCKER_UNAVAILABLE
        assert result.is_blocked is True
        assert "docker" in result.reason.lower()

        # If Docker is optional, absence produces SKIP_OPTIONAL_DEPENDENCY
        record_opt = copy.deepcopy(record)
        record_opt.docker_policy = DockerPolicy.OPTIONAL
        result_opt = evaluator.evaluate_record(record_opt)
        assert result_opt.decision == AdmissionDecision.SKIP_OPTIONAL_DEPENDENCY
        assert result_opt.is_skipped is True

    def test_windows_symlink_unavailable(self, base_capabilities: PlatformCapabilities):
        """When running on Windows without symlink privileges, test must produce SKIP_UNSUPPORTED_PLATFORM or SKIP."""
        caps = copy.deepcopy(base_capabilities)
        caps.os_name = "windows"
        caps.is_windows = True
        caps.is_posix = False
        caps.has_symlinks = False

        record = TestAdmissionRecord(
            test_group="symlink_dependent_test",
            category=AdmissionCategory.CORE_CPU,
            required_platform_capabilities=["symlinks"],
            action_when_unavailable=ActionWhenUnavailable.SKIP,
        )

        evaluator = AdmissionMatrixEvaluator(caps)
        result = evaluator.evaluate_record(record)

        assert result.decision == AdmissionDecision.SKIP_OPTIONAL_DEPENDENCY
        assert result.is_skipped is True
        assert "symlinks" in result.unmet_platform_capabilities

    def test_required_dependency_missing_blocks(self, base_capabilities: PlatformCapabilities):
        """Missing required dependencies must NEVER pass or silently skip; must produce BLOCK_MISSING_REQUIRED_DEPENDENCY."""
        caps = copy.deepcopy(base_capabilities)
        caps.installed_packages.pop("scipy", None)
        caps.installed_packages["scipy"] = None

        record = TestAdmissionRecord(
            test_group="core_math_test",
            category=AdmissionCategory.CORE_CPU,
            required_packages=["scipy"],
            action_when_unavailable=ActionWhenUnavailable.BLOCK,
        )

        evaluator = AdmissionMatrixEvaluator(caps)
        result = evaluator.evaluate_record(record)

        assert result.decision == AdmissionDecision.BLOCK_MISSING_REQUIRED_DEPENDENCY
        assert result.is_blocked is True
        assert result.is_runnable is False
        assert "scipy" in result.missing_required_packages

    def test_optional_dependency_missing_skips(self, base_capabilities: PlatformCapabilities):
        """Missing optional dependencies must produce structured skips without failing."""
        caps = copy.deepcopy(base_capabilities)
        caps.installed_packages["pybv"] = None

        record = TestAdmissionRecord(
            test_group="eeg_writer_test",
            category=AdmissionCategory.MNE_EEG,
            required_packages=["numpy"],
            optional_packages=["pybv"],
            action_when_unavailable=ActionWhenUnavailable.SKIP,
        )

        evaluator = AdmissionMatrixEvaluator(caps)
        result = evaluator.evaluate_record(record)

        assert result.decision == AdmissionDecision.SKIP_OPTIONAL_DEPENDENCY
        assert result.is_skipped is True
        assert "pybv" in result.missing_optional_packages
        assert "pybv" in result.reason

    def test_network_forbidden_policy_blocks(self, base_capabilities: PlatformCapabilities):
        """Tests that declare required live network access must be blocked by offline policy."""
        caps = copy.deepcopy(base_capabilities)
        caps.network_available = False

        record = TestAdmissionRecord(
            test_group="online_api_call",
            category=AdmissionCategory.CORE_CPU,
            network_policy=NetworkPolicy.REQUIRED,
        )

        evaluator = AdmissionMatrixEvaluator(caps)
        result = evaluator.evaluate_record(record)

        assert result.decision == AdmissionDecision.BLOCK_NETWORK_POLICY
        assert result.is_blocked is True
        assert "network" in result.reason.lower()

    def test_unknown_capability_fails_validation(self):
        """Unknown platform capability requirements must trigger INVALID_CONFIGURATION."""
        record = TestAdmissionRecord(
            test_group="alien_hardware_test",
            category=AdmissionCategory.CORE_CPU,
            required_platform_capabilities=["quantum_telepathic_interface"],
        )

        evaluator = AdmissionMatrixEvaluator()
        result = evaluator.evaluate_record(record)

        assert result.decision == AdmissionDecision.INVALID_CONFIGURATION
        assert result.is_blocked is True
        assert "Unknown platform capability" in result.reason

    def test_malformed_admission_records(self):
        """Malformed admission records (empty group or invalid enum) must yield INVALID_CONFIGURATION."""
        record_empty = TestAdmissionRecord(
            test_group="",
            category=AdmissionCategory.CORE_CPU,
        )
        evaluator = AdmissionMatrixEvaluator()
        result_empty = evaluator.evaluate_record(record_empty)
        assert result_empty.decision == AdmissionDecision.INVALID_CONFIGURATION

        raw_dict = {
            "test_group": "bad_cat_test",
            "category": "not_a_valid_category_ever",
        }
        records = load_admission_records_from_dict({"records": [raw_dict]})
        result_bad = evaluator.evaluate_record(records[0])
        assert result_bad.decision == AdmissionDecision.INVALID_CONFIGURATION

    def test_deterministic_matrix_output(self, base_capabilities: PlatformCapabilities):
        """Evaluating the same configuration twice must produce identical results."""
        config_path = Path(__file__).resolve().parents[2] / "configs" / "test_admission" / "admission_matrix.yaml"
        records = load_admission_matrix_file(config_path)

        evaluator1 = AdmissionMatrixEvaluator(base_capabilities)
        report1 = evaluator1.evaluate_matrix(records)

        evaluator2 = AdmissionMatrixEvaluator(base_capabilities)
        report2 = evaluator2.evaluate_matrix(records)

        dict1 = report1.to_dict()
        dict2 = report2.to_dict()

        assert json.dumps(dict1, sort_keys=True) == json.dumps(dict2, sort_keys=True)
        assert len(report1.evaluations) == len(report2.evaluations)

    def test_no_network_operation(self, block_network):
        """Probing and matrix evaluation must execute completely offline without socket calls."""
        # This will raise an exception if socket.socket() is invoked
        caps = probe_platform_capabilities()
        evaluator = AdmissionMatrixEvaluator(caps)

        record = TestAdmissionRecord(
            test_group="offline_test",
            category=AdmissionCategory.CORE_CPU,
            required_packages=["numpy"],
        )
        res = evaluator.evaluate_record(record)
        assert res.decision in (AdmissionDecision.RUN, AdmissionDecision.BLOCK_MISSING_REQUIRED_DEPENDENCY)

    def test_cli_runner(self, tmp_path: Path):
        """Tests the CLI script execution and JSON output generation."""
        out_json = tmp_path / "report.json"
        report, exit_code = run_admission_validation(
            config_path=Path(__file__).resolve().parents[2] / "configs" / "test_admission" / "admission_matrix.yaml",
            output_path=out_json,
            format_type="summary",
            strict=False,
        )

        assert exit_code == 0
        assert out_json.is_file()
        loaded = json.loads(out_json.read_text(encoding="utf-8"))
        assert loaded["schema"] == "NeuroTopologySim.TestAdmissionMatrix.v1"
        assert len(loaded["evaluations"]) >= 10
