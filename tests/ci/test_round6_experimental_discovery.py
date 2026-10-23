"""Offline regression tests for required-check candidate discovery and identity binding."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = ROOT / ".github/workflows/round6_experimental_tests.py"
_REAL_SUBPROCESS_RUN = subprocess.run
IMPLEMENTATION = "tools/simulation_runtime/grid_plan.py"
TEST = "tests/simulation_runtime/test_grid_plan.py"
MNE_SIGNAL_TEST = "tests/adapters/mne_signal_blocks/test_mne_signal_blocks.py"
MNE_SIGNAL_IMPLEMENTATIONS = (
    "adapters/mne_signal_blocks/converter.py",
    "adapters/mne_signal_blocks/fixtures.py",
    "adapters/mne_signal_blocks/reporting.py",
    "adapters/mne_signal_blocks/schema.py",
    "adapters/mne_signal_blocks/validate.py",
)


def _helper():
    spec = importlib.util.spec_from_file_location("round6_experimental_tests", HELPER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str) -> str:
    result = _REAL_SUBPROCESS_RUN(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "--all")
    _git(
        root,
        "-c", "user.name=CI Fixture",
        "-c", "user.email=ci-fixture@example.invalid",
        "commit", "-qm", message,
    )
    return _git(root, "rev-parse", "HEAD")


def _write(root: Path, relative: str, value: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _workspace_path_for_output_arg(value: str) -> Path:
    """Resolve a descriptor-path argument to its original workspace filename for race fixtures."""
    if value.startswith("/proc/"):
        try:
            return Path(os.readlink(value))
        except OSError:
            pass
    return Path(value)


def _repo(root: Path, *, with_candidate: bool = True) -> str:
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "CI Fixture")
    _git(root, "config", "user.email", "ci-fixture@example.invalid")
    _git(root, "branch", "-M", "main")
    _write(root, "README.md", "synthetic fixture only\n")
    if with_candidate:
        _write(root, IMPLEMENTATION, "def plan():\n    return ()\n")
        _write(root, TEST, "def test_plan_fixture():\n    assert True\n")
    return _commit(root, "fixture base")


def _valid_telemetry(test_file: str) -> str:
    return json.dumps({
        "completed": True,
        "exit_code": 0,
        "summary": {
            "total_files": 1,
            "total_batches": 1,
            "passed_batches": 1,
            "skipped_batches": 0,
            "failed_batches": 0,
            "timeout_batches": 0,
            "duration_s": 0.1,
            "overall_exit_code": 0,
        },
        "batches": [{
            "batch_index": 1,
            "batch_number": 1,
            "status": "passed",
            "exit_code": 0,
            "duration_s": 0.1,
            "peak_memory_mb": None,
            "failures": [],
            "stdout_tail": "1 passed in 0.01s\n",
            "stderr_tail": "",
            "files": [test_file],
            "test_files": [test_file],
            "timed_out": False,
            "timeout_status": "completed",
        }],
    })


def _fake_runner(
    command,
    *,
    junit_status: str = "passed",
    junit_xml: str | None = None,
    telemetry: str | None = None,
    **kwargs,
):
    if "scripts/run_tests_isolated.py" not in command:
        return _REAL_SUBPROCESS_RUN(command, **kwargs)
    report_path = Path(command[command.index("--report") + 1])
    test_file = command[-1]
    report_path.write_text(telemetry if telemetry is not None else _valid_telemetry(test_file), encoding="utf-8")
    junit_arg = next(arg for arg in command if arg.startswith("--pytest-arg=--junitxml="))
    junit = Path(junit_arg.removeprefix("--pytest-arg=--junitxml="))
    testcase = "<skipped message='fixture skip'/>" if junit_status == "skipped" else ""
    junit.write_text(
        junit_xml if junit_xml is not None else (
            f'<testsuite tests="1" skipped="{int(junit_status == "skipped")}" failures="0" errors="0">'
            f'<testcase classname="fixture" name="test">{testcase}</testcase></testsuite>'
        ),
        encoding="utf-8",
    )
    return SimpleNamespace(returncode=0)


class Round6DiscoveryTests(unittest.TestCase):
    def test_pinned_transport_requires_child_access_to_parent_descriptor(self):
        helper = _helper()
        if (
            not helper.sys.platform.startswith("linux")
            or not helper.Path("/proc/self/fd").is_dir()
        ):
            self.skipTest("Linux procfs descriptor transport is unavailable")

        helper._supports_pinned_output_transport.cache_clear()
        accessible = SimpleNamespace(
            returncode=0,
            stdout=helper.PINNED_OUTPUT_PROBE_MARKER.hex() + "\n",
            stderr="",
        )
        inaccessible = SimpleNamespace(returncode=1, stdout="", stderr="denied")
        try:
            with patch.object(
                helper, "_PROBE_SUBPROCESS_RUN", return_value=accessible
            ) as probe:
                self.assertTrue(helper._supports_pinned_output_transport())
            self.assertIn("/proc/", probe.call_args.args[0][-1])
            self.assertEqual(
                probe.call_args.kwargs["timeout"],
                helper.PINNED_OUTPUT_PROBE_TIMEOUT_S,
            )

            helper._supports_pinned_output_transport.cache_clear()
            with patch.object(helper, "_PROBE_SUBPROCESS_RUN", return_value=inaccessible):
                self.assertFalse(helper._supports_pinned_output_transport())
        finally:
            helper._supports_pinned_output_transport.cache_clear()

    def test_workflow_keeps_diff_checkout_and_workflow_commits_separate(self):
        workflow = (ROOT / ".github/workflows/required-checks.yml").read_text(encoding="utf-8")
        self.assertIn(
            "DIFF_BASE_SHA: ${{ github.event_name == 'workflow_dispatch' && inputs.diff_base_sha || github.event.pull_request.base.sha || github.event.before }}",
            workflow,
        )
        self.assertIn(
            "DIFF_HEAD_SHA: ${{ github.event_name == 'workflow_dispatch' && inputs.diff_head_sha || github.event.pull_request.head.sha || github.sha }}",
            workflow,
        )
        self.assertIn("diff_base_sha:\n        description:", workflow)
        self.assertIn("diff_head_sha:\n        description:", workflow)
        self.assertIn("required: true\n        type: string", workflow)
        self.assertIn("TESTED_CHECKOUT_SHA: ${{ github.sha }}", workflow)
        self.assertIn("WORKFLOW_SHA: ${{ github.workflow_sha }}", workflow)
        helper_source = HELPER_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "candidate diff head is not an ancestor of the tested checkout",
            helper_source,
        )

    def test_dispatch_never_checks_out_untrusted_candidate_tree(self):
        workflow = (ROOT / ".github/workflows/required-checks.yml").read_text(encoding="utf-8")
        dispatch = re.search(
            r"(?ms)^  workflow_dispatch:\n    inputs:\n(.*?)(?=^\S|\Z)", workflow
        )
        self.assertIsNotNone(dispatch)
        self.assertNotIn("tested_checkout_sha:", dispatch.group(1))
        self.assertNotIn("inputs.tested_checkout_sha", workflow)
        self.assertNotIn("candidate-source", workflow)
        first_checkout = re.search(
            r"(?ms)^      - uses: actions/checkout@v7\n(.*?)(?=^      - name:|\Z)",
            workflow,
        )
        self.assertIsNotNone(first_checkout)
        self.assertIn("persist-credentials: false", first_checkout.group(1))

        candidate_step = re.search(
            r"(?ms)^      - name: Discover and run changed Round 6 candidate suites\n"
            r"(.*?)(?=^      - name:|\Z)",
            workflow,
        )
        self.assertIsNotNone(candidate_step)
        self.assertIn(
            "TESTED_CHECKOUT_SHA: ${{ github.sha }}",
            candidate_step.group(1),
        )
        self.assertNotIn("candidate_root", candidate_step.group(1))
        self.assertNotIn("--root", candidate_step.group(1))
        self.assertIn("WORKFLOW_SHA: ${{ github.workflow_sha }}", candidate_step.group(1))

    def test_every_workflow_checkout_discards_persisted_credentials(self):
        workflow = (ROOT / ".github/workflows/required-checks.yml").read_text(encoding="utf-8")
        checkout_blocks = re.findall(
            r"(?ms)^      - uses: actions/checkout@v7\n(.*?)(?=^      - |^\s{0,4}\S|\Z)",
            workflow,
        )
        self.assertEqual(len(checkout_blocks), 3)
        for index, block in enumerate(checkout_blocks, start=1):
            with self.subTest(checkout=index):
                self.assertRegex(block, r"(?m)^\s+persist-credentials: false\s*$")

    def test_optional_eeg_profile_discovers_only_changed_mne_candidate_paths(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = re.search(r"(?ms)^  optional-eeg-suite:\n(.*?)(?=^  [a-zA-Z0-9_-]+:|\Z)", workflow)
        self.assertIsNotNone(job)
        eeg_job = job.group(1)
        self.assertIn("fetch-depth: 0", eeg_job)
        self.assertIn("requirements-eeg.txt", eeg_job)
        self.assertIn("--only-component mne_signal_blocks", eeg_job)
        self.assertIn("--pytest-marker requires_mne", eeg_job)
        self.assertIn("outputs/mne_signal_blocks_ci_report.json", eeg_job)
        self.assertIn("--only-component mne_csd_adapter", eeg_job)
        self.assertIn("--external-test-job optional-eeg-suite", eeg_job)
        self.assertIn("outputs/mne_csd_adapter_eeg_report.json", eeg_job)
        self.assertIn('"mne==1.13.2"', eeg_job)
        self.assertIn("steps.mne_csd_reference_scope.outputs.changed == 'true'", eeg_job)
        self.assertIn("tools/mne_csd_reference_audit/(kkt|legendre|montages|pin)", eeg_job)
        self.assertIn("--only-component mne_csd_reference_audit", eeg_job)
        self.assertIn("outputs/mne_csd_reference_audit_eeg_report.json", eeg_job)
        self.assertIn("diff_base_sha:", workflow)
        self.assertIn("diff_head_sha:", workflow)
        self.assertIn("inputs.diff_base_sha", eeg_job)
        self.assertIn("inputs.diff_head_sha", eeg_job)
        self.assertEqual(
            _helper().COMPONENTS["mne_signal_blocks"]["external_test_paths"][
                "tests/adapters/mne_signal_blocks/test_mne_signal_blocks.py"
            ],
            "optional-eeg-suite",
        )

    def test_focused_mne_profile_runs_exact_marked_test_without_other_components(self):
        helper = _helper()
        implementation = "adapters/mne_signal_blocks/converter.py"
        test_file = "tests/adapters/mne_signal_blocks/test_mne_signal_blocks.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _repo(root, with_candidate=False)
            _write(root, implementation, "def convert():\n    return 'base'\n")
            _write(root, test_file, "def test_contract_fixture():\n    assert True\n")
            base = _commit(root, "MNE profile fixture")
            _write(root, implementation, "def convert():\n    return 'candidate'\n")
            head = _commit(root, "MNE candidate implementation change")
            report_path = root / "outputs/report.json"
            with patch.object(
                helper.subprocess, "run",
                side_effect=lambda command, **kwargs: _fake_runner(command, **kwargs),
            ):
                result = helper.run(
                    root, base, head, report_path,
                    only_components=["mne_signal_blocks"],
                    pytest_marker="requires_mne",
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["selected_components"], ["mne_signal_blocks"])
        execution = report["components"][0]["executions"][0]
        self.assertEqual(execution["test_file"], test_file)
        self.assertEqual(execution["pytest_marker"], "requires_mne")
        self.assertEqual(execution["result_counts"], {
            "collected": 1, "passed": 1, "skipped": 0, "failed": 0, "errors": 0, "timeouts": 0,
        })
        command = report["executed_commands"][0]
        self.assertEqual(command[command.index("--marker") + 1], "requires_mne")

    def test_external_job_executes_only_its_exact_changed_test(self):
        helper = _helper()
        implementation_paths = (
            "adapters/mne_csd/__init__.py",
            "adapters/mne_csd/transform.py",
        )
        optional_test = "tests/adapters/mne_csd/test_optional_mne_integration.py"
        pure_test = "tests/adapters/mne_csd/test_governance_and_availability.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _repo(root, with_candidate=False)
            spec = _helper().COMPONENTS["mne_csd_adapter"]
            for pair in spec["candidate_pairs"]:
                _write(root, pair["implementation"], "# deterministic adapter fixture\n")
            for test_file in spec["tests"]:
                _write(
                    root,
                    test_file,
                    "def test_fixture(): assert True\n",
                )
            _write(root, "tests/adapters/mne_csd/conftest.py", "# deterministic fixture support\n")
            base = _commit(root, "MNE adapter candidate fixture")
            _write(root, optional_test, "def test_fixture(): assert True  # changed\n")
            head = _commit(root, "change delegated MNE integration case")
            report_path = root / "outputs/report.json"
            with patch.object(
                helper.subprocess, "run",
                side_effect=lambda command, **kwargs: _fake_runner(command, **kwargs),
            ):
                result = helper.run(
                    root, base, head, report_path,
                    tested_checkout_sha=head,
                    workflow_sha=base,
                    event_name="pull_request",
                    require_checkout_match=True,
                    only_components=["mne_csd_adapter"],
                    external_test_job="optional-eeg-suite",
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["external_test_job"], "optional-eeg-suite")
        component = report["components"][0]
        self.assertEqual(component["external_tests_selected_for_job"], [optional_test])
        self.assertEqual(component["delegated_tests"], [optional_test])
        self.assertEqual([item["test_file"] for item in component["executions"]], [optional_test])
        self.assertEqual(component["executions"][0]["result_counts"], {
            "collected": 1, "passed": 1, "skipped": 0, "failed": 0, "errors": 0, "timeouts": 0,
        })

    def test_external_job_is_not_applicable_for_changed_pure_pair(self):
        helper = _helper()
        implementation = "adapters/mne_csd/transform.py"
        pure_test = "tests/adapters/mne_csd/test_parameter_forwarding.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _repo(root, with_candidate=False)
            spec = helper.COMPONENTS["mne_csd_adapter"]
            for pair in spec["candidate_pairs"]:
                _write(root, pair["implementation"], "# deterministic adapter fixture\n")
            for test_file in spec["tests"]:
                _write(root, test_file, "def test_fixture(): assert True\n")
            _write(root, "tests/adapters/mne_csd/conftest.py", "# deterministic fixture support\n")
            base = _commit(root, "MNE pure candidate fixture")
            _write(root, pure_test, "def test_pure_fixture(): assert True  # changed\n")
            head = _commit(root, "change pure MNE adapter test")
            report_path = root / "outputs/report.json"
            real_subprocess_run = helper.subprocess.run
            def fail_on_isolated_execution(command, *args, **kwargs):
                if "scripts/run_tests_isolated.py" in command:
                    raise AssertionError("no external test belongs to this diff")
                return real_subprocess_run(command, *args, **kwargs)
            with patch.object(helper.subprocess, "run", side_effect=fail_on_isolated_execution):
                result = helper.run(
                    root, base, head, report_path,
                    only_components=["mne_csd_adapter"],
                    external_test_job="optional-eeg-suite",
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        self.assertEqual(report["status"], "NOT_APPLICABLE")
        self.assertEqual(report["components"][0]["status"], "NOT_APPLICABLE")
        self.assertEqual(report["components"][0]["executions"], [])

    def test_mne_csd_live_parity_runs_in_the_pinned_eeg_job(self):
        helper = _helper()
        component = "mne_csd_reference_audit"
        live_test = "tests/optional_live_mne/test_mne_csd_live_parity.py"
        spec = helper.COMPONENTS[component]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _repo(root, with_candidate=False)
            for pair in spec["candidate_pairs"]:
                _write(root, pair["implementation"], "# deterministic audit fixture\n")
            for test_file in spec["tests"]:
                _write(root, test_file, "def test_fixture(): assert True\n")
            for support_file, mapped_tests in spec["support_files"].items():
                _write(root, support_file, "# deterministic support\n" if support_file.endswith("conftest.py") else "{}\n")
                for test_file in mapped_tests:
                    _write(root, test_file, "def test_fixture(): assert True\n")
            base = _commit(root, "MNE reference-audit fixture base")
            _write(root, live_test, "def test_fixture(): assert True  # changed\n")
            head = _commit(root, "change pinned live-MNE parity test")
            report_path = root / "outputs/report.json"
            with patch.object(
                helper.subprocess,
                "run",
                side_effect=lambda command, **kwargs: _fake_runner(command, **kwargs),
            ):
                result = helper.run(
                    root,
                    base,
                    head,
                    report_path,
                    tested_checkout_sha=head,
                    workflow_sha=base,
                    event_name="pull_request",
                    require_checkout_match=True,
                    only_components=[component],
                    external_test_job="optional-eeg-suite",
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        self.assertEqual(report["status"], "PASS")
        execution = report["components"][0]["executions"][0]
        self.assertEqual(execution["test_file"], live_test)
        self.assertEqual(execution["result_counts"], {
            "collected": 1, "passed": 1, "skipped": 0, "failed": 0, "errors": 0, "timeouts": 0,
        })

    def test_shared_csd_kkt_test_selects_one_source_aware_component(self):
        helper = _helper()
        shared_test = "tests/mne_csd_reference_audit/test_kkt_operator.py"
        shared_fixture = "tests/mne_csd_reference_audit/fixtures/mne_code_path_transcription.json"
        audit_source = "tools/mne_csd_reference_audit/kkt.py"

        # Historical CSD parity probes may change this exact test alone. When
        # the audit implementation is part of the diff, the independent audit
        # component owns the run and must not fan out to an absent sphere PR.
        self.assertEqual(helper.select_components({shared_test}), ["spherical_csd"])
        self.assertEqual(helper.select_components({shared_fixture}), ["spherical_csd"])
        self.assertEqual(
            helper.select_components({audit_source, shared_test}),
            ["mne_csd_reference_audit"],
        )
        self.assertEqual(
            helper.select_components({audit_source, shared_fixture}),
            ["mne_csd_reference_audit"],
        )
        self.assertEqual(helper._unmapped_candidate_paths({shared_test}), [])

    def test_unrelated_file_in_shared_experimental_namespace_is_not_candidate(self):
        helper = _helper()
        unrelated = "tests/experimental/test_unrelated_suite.py"
        self.assertEqual(helper.select_components({unrelated}), [])
        self.assertEqual(helper._unmapped_candidate_paths({unrelated}), [])

    def test_focused_mne_profile_reports_not_applicable_for_unrelated_candidate_changes(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report_path = root / "outputs/report.json"
            unrelated = "tools/surrogate_nulls/nulls.py"
            with patch.object(helper, "collect_changed_paths", return_value={unrelated}), patch.object(
                helper.subprocess, "run", side_effect=AssertionError("NOT_APPLICABLE must not launch pytest")
            ):
                result = helper.run(
                    root, "0" * 40, "1" * 40, report_path,
                    only_components=["mne_signal_blocks"],
                    pytest_marker="requires_mne",
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        self.assertEqual(report["status"], "NOT_APPLICABLE")
        self.assertEqual(report["selected_components"], [])
        self.assertEqual(report["executed_commands"], [])

    def test_focused_profile_rejects_unknown_component_or_marker(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaisesRegex(ValueError, "unknown component filters"):
                helper.run(root, "0" * 40, "1" * 40, root / "outputs/a.json", only_components=["unknown"])
            with self.assertRaisesRegex(ValueError, "unsupported pytest marker"):
                helper.run(root, "0" * 40, "1" * 40, root / "outputs/b.json", pytest_marker="optional")

    def test_workflow_dispatch_without_explicit_diff_shas_fails_closed(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _repo(root)
            with self.assertRaisesRegex(ValueError, "workflow_dispatch requires an explicit"):
                helper.run(
                    root, "", "", root / "outputs/report.json",
                    tested_checkout_sha="1" * 40,
                    workflow_sha="2" * 40,
                    event_name="workflow_dispatch",
                )

    def test_ci_manual_dispatch_requires_explicit_candidate_diff_shas(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        dispatch = re.search(r"(?ms)^  workflow_dispatch:\n    inputs:\n(.*?)(?=^\S|\Z)", workflow)
        self.assertIsNotNone(dispatch)
        inputs = dispatch.group(1)
        for name in ("diff_base_sha", "diff_head_sha"):
            with self.subTest(input=name):
                block = re.search(
                    rf"(?ms)^      {re.escape(name)}:\n(.*?)(?=^      [^ ]|\Z)", inputs
                )
                self.assertIsNotNone(block)
                self.assertRegex(block.group(1), r"(?m)^        required: true$")
        self.assertIn(
            "DIFF_BASE_SHA: ${{ github.event_name == 'workflow_dispatch' && inputs.diff_base_sha",
            workflow,
        )
        self.assertIn(
            "DIFF_HEAD_SHA: ${{ github.event_name == 'workflow_dispatch' && inputs.diff_head_sha",
            workflow,
        )

    def test_candidate_head_not_in_tested_checkout_is_blocked_before_execution(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate_base = _repo(root)
            _git(root, "switch", "-c", "candidate")
            _write(root, TEST, "def test_plan_fixture():\n    assert True  # candidate only\n")
            candidate_head = _commit(root, "candidate test change")
            _git(root, "switch", "main")
            tested_checkout = _git(root, "rev-parse", "HEAD")
            report_path = root / "outputs/report.json"

            result = helper.run(
                root, candidate_base, candidate_head, report_path,
                tested_checkout_sha=tested_checkout,
                workflow_sha=candidate_base,
                event_name="workflow_dispatch",
                require_checkout_match=True,
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(result, 1)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["candidate_head_in_tested_checkout"])
        self.assertIn("not an ancestor", report["selection_error"])
        self.assertEqual(report["executed_commands"], [])

    def test_docker_engine_suite_is_owned_by_a_dedicated_docker_job(self):
        workflow = (ROOT / ".github/workflows/required-checks.yml").read_text(encoding="utf-8")
        docker_job = re.search(
            r"(?ms)^  docker-context-engine:\n(.*?)^  awareness-tests:", workflow
        )
        self.assertIsNotNone(docker_job)
        job = docker_job.group(1)
        self.assertIn("runs-on: ubuntu-latest", job)
        self.assertIn("timeout-minutes: 20", job)
        self.assertIn("docker info --format", job)
        self.assertIn("tests/docker_context/test_docker_engine_build_context.py", job)
        self.assertIn("scripts/run_tests_isolated.py", job)
        self.assertIn("Write Docker candidate evidence", job)
        for field in (
            "diff_base_sha", "diff_head_sha", "tested_checkout_sha", "workflow_sha",
            "selected_component", "implementation_paths", "test_paths", "counts", "status",
        ):
            self.assertIn(f'"{field}"', (ROOT / ".github/workflows/round6_experimental_tests.py").read_text(encoding="utf-8"))
        self.assertIn("DIFF_BASE_SHA", job)
        self.assertIn("DIFF_HEAD_SHA", job)
        self.assertIn("git merge-base --is-ancestor", job)
        self.assertIn('git diff --name-only "$DIFF_BASE_SHA...$DIFF_HEAD_SHA"', job)
        self.assertIn("registered engine test is absent", job)
        self.assertIn("if: steps.candidate_scope.outputs.docker_context_changed == 'true'", job)
        self.assertIn(
            "--pytest-arg=--junitxml=outputs/docker_context_engine_test_report.junit.xml",
            job,
        )
        self.assertIn('helper["validate_docker_engine_test_artifacts"]', job)
        self.assertIn("Upload Docker-context diagnostics", job)
        self.assertLess(
            job.index("git diff --name-only"),
            job.index("git merge-base --is-ancestor"),
        )

    def test_docker_candidate_evidence_is_finite_identity_bound_and_fails_on_skip(self):
        helper = _helper()
        test_file = "tests/docker_context/test_docker_engine_build_context.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            telemetry_path = root / "outputs/runner.json"
            junit_path = root / "outputs/runner.junit.xml"
            telemetry_path.parent.mkdir(parents=True)
            telemetry_path.write_text(_valid_telemetry(test_file), encoding="utf-8")
            junit_path.write_text(
                '<testsuite tests="1" skipped="0" failures="0" errors="0">'
                '<testcase classname="docker" name="test_context"/></testsuite>',
                encoding="utf-8",
            )
            metadata = {
                "diff_base_sha": "1" * 40,
                "diff_head_sha": "2" * 40,
                "tested_checkout_sha": "3" * 40,
                "workflow_sha": "4" * 40,
                "event_name": "workflow_dispatch",
                "candidate_changed": True,
                "execution_outcome": "success",
            }
            evidence = helper.docker_engine_candidate_evidence(
                root, telemetry_path, junit_path, **metadata
            )
            self.assertEqual(evidence["status"], "PASS")
            self.assertEqual(evidence["selected_component"], "docker_context_policy")
            self.assertEqual(evidence["implementation_paths"], [".dockerignore"])
            self.assertEqual(evidence["test_paths"], [test_file])
            self.assertEqual(evidence["tested_checkout_sha"], "3" * 40)
            self.assertEqual(evidence["counts"], {
                "collected": 1, "passed": 1, "skipped": 0,
                "failures": 0, "errors": 0, "timeouts": 0,
            })
            json.dumps(evidence, sort_keys=True, allow_nan=False)

            junit_path.write_text(
                '<testsuite tests="1" skipped="1" failures="0" errors="0">'
                '<testcase classname="docker" name="test_context">'
                '<skipped message="optional unavailable"/></testcase></testsuite>',
                encoding="utf-8",
            )
            skipped = helper.docker_engine_candidate_evidence(
                root, telemetry_path, junit_path, **metadata
            )
            self.assertEqual(skipped["status"], "FAIL")
            self.assertEqual(skipped["counts"]["skipped"], 1)

            not_applicable = helper.docker_engine_candidate_evidence(
                root,
                root / "missing.json",
                root / "missing.xml",
                **{**metadata, "candidate_changed": False, "execution_outcome": "skipped"},
            )
            self.assertEqual(not_applicable["status"], "NOT_APPLICABLE")
            self.assertIsNone(not_applicable["selected_component"])
            json.dumps(not_applicable, sort_keys=True, allow_nan=False)

    def test_docker_engine_artifact_validator_reconciles_junit_and_runner_totals(self):
        helper = _helper()
        test_file = "tests/docker_context/test_docker_engine_build_context.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            telemetry_path = root / "runner.json"
            junit_path = root / "runner.junit.xml"
            telemetry_path.write_text(_valid_telemetry(test_file), encoding="utf-8")
            junit_path.write_text(
                '<testsuite tests="1" skipped="0" failures="0" errors="0">'
                "<testcase /></testsuite>",
                encoding="utf-8",
            )

            valid, error, total = helper.validate_docker_engine_test_artifacts(
                root, telemetry_path, junit_path, test_file
            )
            self.assertTrue(valid, error)
            self.assertEqual(total, 1)

            quiet_telemetry = json.loads(_valid_telemetry(test_file))
            quiet_telemetry["batches"][0]["stdout_tail"] = "captured by test runner\n"
            telemetry_path.write_text(json.dumps(quiet_telemetry), encoding="utf-8")
            valid, error, total = helper.validate_docker_engine_test_artifacts(
                root, telemetry_path, junit_path, test_file
            )
            self.assertTrue(valid, error)
            self.assertEqual(total, 1)

            junit_path.write_text(
                '<testsuite tests="2" skipped="0" failures="0" errors="0">'
                "<testcase /></testsuite>",
                encoding="utf-8",
            )
            valid, error, total = helper.validate_docker_engine_test_artifacts(
                root, telemetry_path, junit_path, test_file
            )
            self.assertFalse(valid)
            self.assertIn("without a registered subtest contract", error)
            self.assertEqual(total, 0)

            telemetry_path.write_text(_valid_telemetry(test_file), encoding="utf-8")
            junit_path.write_text(
                '<testsuite tests="2" skipped="0" failures="0" errors="0">'
                "<testcase /></testsuite>",
                encoding="utf-8",
            )
            valid, error, total = helper.validate_docker_engine_test_artifacts(
                root, telemetry_path, junit_path, test_file
            )

        self.assertFalse(valid)
        self.assertIn("JUnit test total does not match", error)
        self.assertEqual(total, 0)

    def test_docker_engine_artifacts_reject_duplicate_json_keys(self):
        helper = _helper()
        test_file = "tests/docker_context/test_docker_engine_build_context.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            telemetry_path = root / "runner.json"
            junit_path = root / "runner.junit.xml"
            telemetry_path.write_text(
                '{"completed":true,"completed":false}', encoding="utf-8"
            )
            junit_path.write_text(
                '<testsuite tests="1"><testcase/></testsuite>', encoding="utf-8"
            )
            valid, error, total = helper.validate_docker_engine_test_artifacts(
                root, telemetry_path, junit_path, test_file
            )
        self.assertFalse(valid)
        self.assertIn("duplicate JSON object key", error)
        self.assertEqual(total, 0)

    def test_docker_engine_artifacts_reject_exponent_overflow(self):
        helper = _helper()
        test_file = "tests/docker_context/test_docker_engine_build_context.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            telemetry_path = root / "runner.json"
            junit_path = root / "runner.junit.xml"
            telemetry = _valid_telemetry(test_file).rstrip("\n")
            telemetry = telemetry[:-1] + ',"ignored_extra":1e999}'
            telemetry_path.write_text(telemetry, encoding="utf-8")
            junit_path.write_text(
                '<testsuite tests="1"><testcase/></testsuite>', encoding="utf-8"
            )
            valid, error, total = helper.validate_docker_engine_test_artifacts(
                root, telemetry_path, junit_path, test_file
            )
        self.assertFalse(valid)
        self.assertIn("non-finite JSON number", error)
        self.assertEqual(total, 0)

    def test_docker_engine_artifacts_reject_paths_outside_checkout(self):
        helper = _helper()
        test_file = "tests/docker_context/test_docker_engine_build_context.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            outside = Path(td) / "outside.json"
            root.mkdir()
            outside.write_text(_valid_telemetry(test_file), encoding="utf-8")
            valid, error, total = helper.validate_docker_engine_test_artifacts(
                root,
                outside,
                root / "runner.junit.xml",
                test_file,
            )
        self.assertFalse(valid)
        self.assertIn("must remain inside", error)
        self.assertEqual(total, 0)

    def test_docker_engine_artifacts_reject_oversized_telemetry(self):
        helper = _helper()
        test_file = "tests/docker_context/test_docker_engine_build_context.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            telemetry_path = root / "runner.json"
            junit_path = root / "runner.junit.xml"
            telemetry_path.write_bytes(
                b" " * (helper.MAX_RUNNER_TELEMETRY_BYTES + 1)
            )
            junit_path.write_text(
                '<testsuite tests="1"><testcase/></testsuite>', encoding="utf-8"
            )
            valid, error, total = helper.validate_docker_engine_test_artifacts(
                root, telemetry_path, junit_path, test_file
            )
        self.assertFalse(valid)
        self.assertIn("read limit", error)
        self.assertEqual(total, 0)

    def test_contained_artifact_reads_are_size_bounded(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "diagnostics.bin"
            artifact.write_bytes(b"x" * 33)
            with self.assertRaisesRegex(ValueError, "exceeds the 32-byte read limit"):
                helper._read_contained_bytes(root, artifact, "fixture artifact", max_bytes=32)
            artifact.write_bytes(b"0123456789")
            self.assertEqual(
                helper._read_contained_tail_text(root, artifact, "fixture log", tail_bytes=4),
                "6789",
            )

    def test_contained_artifact_open_survives_parent_symlink_swap(self):
        helper = _helper()
        if (
            helper.os.name == "nt"
            or helper.os.open not in getattr(helper.os, "supports_dir_fd", set())
            or not getattr(helper.os, "O_NOFOLLOW", 0)
            or not getattr(helper.os, "O_DIRECTORY", 0)
        ):
            self.skipTest("openat-style no-follow directory descriptors are unavailable")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            original_parent = root / "logs"
            outside_parent = Path(td) / "outside"
            original_parent.mkdir(parents=True)
            outside_parent.mkdir()
            (original_parent / "junit.xml").write_text("trusted-tree", encoding="utf-8")
            (outside_parent / "junit.xml").write_text("outside-tree", encoding="utf-8")
            real_open = helper.os.open
            swapped = False

            def open_and_swap(file, flags, *args, **kwargs):
                nonlocal swapped
                fd = real_open(file, flags, *args, **kwargs)
                if file == "logs" and kwargs.get("dir_fd") is not None and not swapped:
                    swapped = True
                    original_parent.rename(root / "logs-held")
                    (root / "logs").symlink_to(outside_parent, target_is_directory=True)
                return fd

            with patch.object(helper.os, "open", open_and_swap):
                # The helper checks whether the active os.open callable supports
                # dir_fd. Keep the replacement callable in that capability set
                # so this test exercises the POSIX descriptor-relative branch.
                supported_dir_fd = set(helper.os.supports_dir_fd)
                supported_dir_fd.add(open_and_swap)
                with patch.object(helper.os, "supports_dir_fd", supported_dir_fd):
                    observed = helper._read_contained_bytes(
                        root, root / "logs" / "junit.xml", "JUnit path", max_bytes=64
                    )
        self.assertTrue(swapped)
        self.assertEqual(observed, b"trusted-tree")

    def test_pinned_report_descriptors_prevent_symlink_redirected_writes(self):
        helper = _helper()
        if not helper._supports_pinned_output_transport():
            self.skipTest("Linux procfs descriptor transport is unavailable")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            temp = root / "private"
            temp.mkdir()
            telemetry = temp / "telemetry.json"
            junit = temp / "junit.xml"
            outside_telemetry = Path(td) / "outside-telemetry.json"
            outside_junit = Path(td) / "outside-junit.xml"
            outside_telemetry.write_text("preserve telemetry\n", encoding="utf-8")
            outside_junit.write_text("preserve junit\n", encoding="utf-8")
            telemetry_fd = helper._open_contained_file(
                root, telemetry, helper.os.O_RDWR | helper.os.O_CREAT | helper.os.O_TRUNC,
                "runner telemetry path",
            )
            junit_fd = helper._open_contained_file(
                root, junit, helper.os.O_RDWR | helper.os.O_CREAT | helper.os.O_TRUNC,
                "JUnit report path",
            )
            try:
                telemetry_proc_path = helper._proc_fd_path(telemetry_fd)
                junit_proc_path = helper._proc_fd_path(junit_fd, pid=helper.os.getpid())
                code = (
                    "from pathlib import Path; import sys; "
                    "Path(sys.argv[1]).unlink(); Path(sys.argv[1]).symlink_to(sys.argv[3]); "
                    "Path(sys.argv[2]).unlink(); Path(sys.argv[2]).symlink_to(sys.argv[4]); "
                    "Path(sys.argv[5]).write_text('{\\\"completed\\\":true}', encoding='utf-8'); "
                    "Path(sys.argv[6]).write_text('<testsuite/>', encoding='utf-8')"
                )
                subprocess.run(
                    [
                        helper.sys.executable, "-c", code, str(telemetry), str(junit),
                        str(outside_telemetry), str(outside_junit),
                        telemetry_proc_path, junit_proc_path,
                    ],
                    check=True,
                    pass_fds=(telemetry_fd,),
                )
                telemetry_bytes = helper._read_pinned_output_bytes(
                    telemetry_fd, "runner telemetry path", max_bytes=1024
                )
                junit_bytes = helper._read_pinned_output_bytes(
                    junit_fd, "JUnit report path", max_bytes=1024
                )
                self.assertEqual(
                    outside_telemetry.read_text(encoding="utf-8"), "preserve telemetry\n"
                )
                self.assertEqual(
                    outside_junit.read_text(encoding="utf-8"), "preserve junit\n"
                )
            finally:
                os.close(telemetry_fd)
                os.close(junit_fd)
        self.assertEqual(telemetry_bytes, b'{"completed":true}')
        self.assertEqual(junit_bytes, b"<testsuite/>")

    def test_real_isolated_runner_and_pytest_writers_do_not_follow_swapped_outputs(self):
        helper = _helper()
        if not helper._supports_pinned_output_transport():
            self.skipTest("Linux procfs descriptor transport is unavailable")
        pair = helper.COMPONENTS["simulation_grid_planner"]["candidate_pairs"][0]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            _write(root, pair["implementation"], "# local synthetic candidate fixture\n")
            runner = ROOT / "scripts/run_tests_isolated.py"
            _write(root, "scripts/run_tests_isolated.py", runner.read_text(encoding="utf-8"))
            outside = Path(td) / "outside"
            outside.mkdir()
            outside_telemetry = outside / "telemetry.txt"
            outside_junit = outside / "junit.txt"
            outside_telemetry.write_text("preserve telemetry\n", encoding="utf-8")
            outside_junit.write_text("preserve junit\n", encoding="utf-8")
            _write(
                root,
                pair["test"],
                """import os
from pathlib import Path

runner_pid = os.getppid()
status = Path(f"/proc/{runner_pid}/status").read_text(encoding="utf-8")
helper_pid = int(next(line.split()[1] for line in status.splitlines() if line.startswith("PPid:")))
fd_dir = Path(f"/proc/{helper_pid}/fd")
outside = Path(os.environ["ROUND6_OUTPUT_RACE_DIR"])
found = set()
for descriptor in fd_dir.iterdir():
    try:
        target = Path(os.readlink(descriptor))
    except OSError:
        continue
    if target.name.endswith(".junit.xml"):
        kind = "junit"
    elif target.parent.name.startswith("round6-ci-") and target.suffix == ".json":
        kind = "telemetry"
    else:
        continue
    if kind not in found:
        target.unlink()
        target.symlink_to(outside / f"{kind}.txt")
        found.add(kind)
assert found == {"telemetry", "junit"}, found

def test_fixture():
    Path(os.environ["ROUND6_OUTPUT_RACE_MARKER"]).write_text("candidate ran\\n", encoding="utf-8")
    assert True
""",
            )
            report_path = root / "outputs/report.json"
            candidate_marker = root / "candidate-ran.txt"
            with patch.dict(os.environ, {
                "ROUND6_OUTPUT_RACE_DIR": str(outside),
                "ROUND6_OUTPUT_RACE_MARKER": str(candidate_marker),
            }), patch.object(
                helper, "collect_changed_paths", return_value={pair["implementation"]}
            ):
                exit_code = helper.run(root, "0" * 40, "1" * 40, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            candidate_marker_text = candidate_marker.read_text(encoding="utf-8")
            telemetry_text = outside_telemetry.read_text(encoding="utf-8")
            junit_text = outside_junit.read_text(encoding="utf-8")
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "BLOCKED")
        execution = report["components"][0]["executions"][0]
        self.assertEqual(execution["runner_exit_code"], 0)
        self.assertEqual(candidate_marker_text, "candidate ran\n")
        self.assertEqual(telemetry_text, "preserve telemetry\n")
        self.assertEqual(junit_text, "preserve junit\n")

    def test_candidate_implementation_and_test_change_runs_the_explicit_pair(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = _repo(root, with_candidate=False)
            _write(root, IMPLEMENTATION, "def plan():\n    return ('changed',)\n")
            _write(root, TEST, "def test_plan_fixture():\n    assert plan() == ('changed',)\n")
            head = _commit(root, "candidate source and test")
            report_path = root / "outputs/report.json"
            runner = lambda command, **kwargs: _fake_runner(command, **kwargs)
            with patch.object(helper.subprocess, "run", side_effect=runner):
                exit_code = helper.run(
                    root, base, head, report_path,
                    tested_checkout_sha=head, workflow_sha=base,
                    event_name="pull_request", require_checkout_match=True,
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["selected_components"], ["simulation_grid_planner"])
        execution = report["components"][0]["executions"][0]
        self.assertEqual(execution["test_file"], TEST)
        self.assertEqual(execution["implementation_paths"], [IMPLEMENTATION])
        self.assertEqual(execution["diff_base_sha"], base)
        self.assertEqual(execution["diff_head_sha"], head)
        executed_command = report["executed_commands"][0]
        self.assertNotIn("--report-dir", executed_command)
        junit_arg = next(arg for arg in executed_command if arg.startswith("--pytest-arg=--junitxml="))
        junit_path = Path(junit_arg.removeprefix("--pytest-arg=--junitxml="))
        with self.assertRaises(ValueError):
            junit_path.relative_to(root)
        self.assertEqual(execution["tested_checkout_sha"], head)
        self.assertEqual(execution["workflow_sha"], base)
        self.assertEqual(execution["result_counts"], {
            "collected": 1, "passed": 1, "skipped": 0, "failed": 0, "errors": 0, "timeouts": 0,
        })

    def test_test_only_change_selects_the_registered_implementation_pair(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = _repo(root)
            _write(root, TEST, "def test_plan_fixture():\n    assert True  # test-only revision\n")
            head = _commit(root, "adversarial test only")
            report_path = root / "outputs/report.json"
            with patch.object(helper.subprocess, "run", side_effect=lambda command, **kwargs: _fake_runner(command, **kwargs)):
                exit_code = helper.run(root, base, head, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["selected_components"], ["simulation_grid_planner"])
        self.assertEqual(report["components"][0]["required_pairs"], [
            {"implementation": IMPLEMENTATION, "test": TEST},
        ])
        self.assertEqual(report["components"][0]["executions"][0]["test_file"], TEST)

    def test_metadata_only_change_is_json_not_applicable_and_executes_nothing(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = _repo(root)
            _write(root, "docs/fixture-note.md", "metadata-only synthetic fixture\n")
            head = _commit(root, "metadata only")
            report_path = root / "outputs/report.json"
            def no_candidate_runner(command, **kwargs):
                if "scripts/run_tests_isolated.py" in command:
                    raise AssertionError("metadata-only changes must not execute candidate tests")
                return _REAL_SUBPROCESS_RUN(command, **kwargs)
            with patch.object(helper.subprocess, "run", side_effect=no_candidate_runner):
                exit_code = helper.run(
                    root, base, head, report_path,
                    tested_checkout_sha=head, workflow_sha=base,
                    event_name="pull_request", require_checkout_match=True,
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "NOT_APPLICABLE")
        self.assertEqual(report["executed_commands"], [])
        self.assertEqual(report["selected_components"], [])
        self.assertIn("does not certify", report["statement"])

    def test_workflow_owned_changes_do_not_self_select_candidate_suites(self):
        helper = _helper()
        workflow_owned_changes = {
            ".github/workflows/round6_experimental_tests.py",
            "tests/ci/test_round6_experimental_discovery.py",
        }
        self.assertEqual(helper.select_components(workflow_owned_changes), [])
        self.assertEqual(helper._unmapped_candidate_paths(workflow_owned_changes), [])

    def test_dmd_oracle_is_reference_support_for_the_production_bridge(self):
        helper = _helper()
        implementation = "neurotopology_sim/experimental/dynamics/dmd_crouzeix.py"
        oracle_test = "tests/dmd_ep2_oracle/test_oracle.py"
        bridge_test = "tests/dmd_ep2_oracle/test_production_bridge.py"
        spec = helper.COMPONENTS["dmd_crouzeix"]
        self.assertNotIn(
            oracle_test,
            {pair["test"] for pair in spec["candidate_pairs"]},
        )
        self.assertIn(oracle_test, spec["tests"])
        self.assertNotIn(oracle_test, spec["triggers"])
        self.assertIn(oracle_test, spec["independent_reference_tests"])
        self.assertEqual(spec["support_files"][oracle_test], (bridge_test,))
        self.assertEqual(spec["support_file_requires_changed"][oracle_test], (bridge_test,))
        self.assertEqual(
            {pair["test"] for pair in spec["candidate_pairs"]},
            {
                "tests/dmd_crouzeix_contract/test_production_contract.py",
                "tests/experimental/test_dmd_crouzeix.py",
                bridge_test,
            },
        )
        self.assertEqual(
            spec["environment_overrides"],
            {"DMD_EP2_REQUIRE_PRODUCTION": "1"},
        )
        self.assertEqual(helper.select_components({oracle_test}), [])
        self.assertEqual(helper._unmapped_candidate_paths({oracle_test}), [oracle_test])
        self.assertEqual(helper.select_components({bridge_test}), ["dmd_crouzeix"])
        self.assertEqual(helper._unmapped_candidate_paths({bridge_test}), [])
        paired_changes = {oracle_test, bridge_test}
        self.assertEqual(helper.select_components(paired_changes), ["dmd_crouzeix"])
        self.assertEqual(helper._unmapped_candidate_paths(paired_changes), [])
        self.assertEqual(
            helper._unmapped_candidate_paths({"tests/dmd_ep2_oracle/test_unregistered_extra.py"}),
            ["tests/dmd_ep2_oracle/test_unregistered_extra.py"],
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _repo(root, with_candidate=False)
            _write(root, implementation, "def marker(): return 'fixture'\n")
            base = _commit(root, "DMD implementation before oracle-only change")
            _write(root, oracle_test, "def test_oracle_fixture(): assert True\n")
            head = _commit(root, "unpaired oracle-only change")
            report_path = root / "outputs/report.json"
            exit_code = helper.run(root, base, head, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["selected_components"], [])
        self.assertEqual(report["unmapped_candidate_paths"], [oracle_test])
        self.assertEqual(report["executed_commands"], [])

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _repo(root, with_candidate=False)
            _write(root, implementation, "def marker(): return 'fixture'\n")
            base = _commit(root, "DMD production implementation without oracle-only candidate")
            _write(root, oracle_test, "def test_oracle_fixture(): assert True\n")
            _write(root, bridge_test, "def test_bridge_fixture(): assert True\n")
            head = _commit(root, "DMD paired production bridge and reference tests")
            changed_paths = helper.collect_changed_paths(base, head, root)
            self.assertEqual(changed_paths, {oracle_test, bridge_test})
            self.assertIn(oracle_test, helper._active_support_paths(spec, changed_paths))
            inspection = helper.inspect_component("dmd_crouzeix", root, changed_paths)
            self.assertEqual(inspection["tests_to_run"], [bridge_test, oracle_test])
            report_path = root / "outputs/report.json"
            observed_environments = []

            def capture_environment(command, **kwargs):
                if "scripts/run_tests_isolated.py" in command:
                    observed_environments.append(kwargs["env"].get("DMD_EP2_REQUIRE_PRODUCTION"))
                return _fake_runner(command, **kwargs)

            with patch.object(helper.subprocess, "run", side_effect=capture_environment):
                exit_code = helper.run(root, base, head, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["selected_components"], ["dmd_crouzeix"])
        component = report["components"][0]
        self.assertEqual(report["changed_paths"], sorted({bridge_test, oracle_test}))
        self.assertEqual(component["tests_to_run"], [bridge_test, oracle_test])
        self.assertEqual(observed_environments, ["1", "1"])
        self.assertTrue(all(item["environment_overrides"] == {"DMD_EP2_REQUIRE_PRODUCTION": "1"}
                            for item in component["executions"]))

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _repo(root, with_candidate=False)
            _write(root, implementation, "def marker(): return 'fixture'\n")
            _write(root, oracle_test, "def test_oracle_fixture(): assert True\n")
            _write(root, bridge_test, "def test_bridge_fixture(): assert True\n")
            inspection = helper.inspect_component("dmd_crouzeix", root, {oracle_test})
        self.assertEqual(inspection["status"], "BLOCKED")
        self.assertEqual(inspection["unmapped_candidate_paths"], [oracle_test])
        self.assertNotIn(oracle_test, inspection["tests_to_run"])

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, implementation, "def marker(): return 'fixture'\n")
            _write(root, oracle_test, "def test_oracle_fixture(): assert True\n")
            _write(root, bridge_test, "def test_bridge_fixture(): assert True\n")
            with patch.dict(
                helper.COMPONENTS["dmd_crouzeix"],
                {"support_file_requires_changed": {oracle_test: ("tests/not_registered.py",)}},
            ):
                inspection = helper.inspect_component(
                    "dmd_crouzeix", root, {oracle_test, bridge_test}
                )
        self.assertEqual(inspection["status"], "BLOCKED")
        self.assertIn(
            "support-file changed-path prerequisite mapping is invalid",
            inspection["blockers"],
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, oracle_test, "def oracle_fixture(): return 1\n")
            _write(root, bridge_test, "def test_bridge_fixture(): assert True\n")
            inspection = helper.inspect_component("dmd_crouzeix", root, {oracle_test})
        self.assertEqual(inspection["status"], "BLOCKED")
        self.assertEqual(inspection["missing_implementations"], [implementation])

    def test_candidate_environment_overrides_are_allowlisted_and_do_not_echo_secrets(self):
        helper = _helper()
        implementation = "neurotopology_sim/experimental/dynamics/dmd_crouzeix.py"
        oracle_test = "tests/dmd_ep2_oracle/test_oracle.py"
        bridge_test = "tests/dmd_ep2_oracle/test_production_bridge.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, implementation, "def marker(): return 'fixture'\n")
            _write(root, oracle_test, "def test_oracle_fixture(): assert True\n")
            _write(root, bridge_test, "def test_bridge_fixture(): assert True\n")
            with patch.dict(
                helper.COMPONENTS["dmd_crouzeix"],
                {"environment_overrides": {"GH_TOKEN": "do-not-log"}},
            ):
                result = helper.inspect_component("dmd_crouzeix", root, {bridge_test})

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["invalid_environment_overrides"], ["GH_TOKEN"])
        self.assertEqual(result["environment_overrides"], {})
        self.assertNotIn("do-not-log", json.dumps(result))

    def test_yaml_candidate_configs_are_registered_or_fail_closed(self):
        helper = _helper()
        guarded_configs = {
            "configs/scientific_falsification/batch3_falsification_matrix.yaml",
            "configs/research/batch3_source_registry.yaml",
        }
        for path in sorted(guarded_configs):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                with patch.object(helper, "collect_changed_paths", return_value={path}):
                    result = helper.run(root, "0" * 40, "1" * 40, root / "report.json")
                report = json.loads((root / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(result, 1)
            self.assertEqual(report["status"], "BLOCKED")
            if path == "configs/research/batch3_source_registry.yaml":
                self.assertEqual(report["selected_components"], ["batch3_source_registry"])
                self.assertEqual(report["unmapped_candidate_paths"], [])
                self.assertEqual(
                    report["components"][0]["component"], "batch3_source_registry"
                )
                self.assertEqual(
                    report["components"][0]["status"], "BLOCKED"
                )
            elif path == "configs/scientific_falsification/batch3_falsification_matrix.yaml":
                self.assertEqual(
                    report["selected_components"],
                    ["batch3_falsification_matrix_artifact"],
                )
                self.assertEqual(report["unmapped_candidate_paths"], [])
                self.assertEqual(
                    report["components"][0]["missing_required_tests"],
                    ["tests/scientific_falsification/test_batch3_falsification_matrix.py"],
                )
            else:
                self.assertEqual(report["unmapped_candidate_paths"], [path])
            self.assertNotEqual(report["status"], "NOT_APPLICABLE")

    def test_junit_root_and_summary_must_match_testcase_outcomes(self):
        helper = _helper()
        malformed_reports = (
            '<testsuite tests="2" failures="1"><testcase/></testsuite>',
            '<testsuite tests="1" skipped="1"><testcase/></testsuite>',
            '<testsuite tests="1"><testcase><failure/><skipped/></testcase></testsuite>',
            '<testsuite tests="4"><testcase/><testcase/></testsuite>',
            '<testsuite tests="4" skipped="1" failures="0" errors="0"><testcase/><testcase/></testsuite>',
            '<junit tests="1"><testcase/></junit>',
            '<testsuites tests="2"><testsuite tests="1"><testcase/></testsuite><testcase/></testsuites>',
        )
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "junit.xml"
            for xml in malformed_reports:
                with self.subTest(xml=xml):
                    report.write_text(xml, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        helper.junit_details(report)

            report.write_text(
                '<testsuites tests="2" failures="1" skipped="0" errors="0">'
                '<testsuite tests="2" failures="1" skipped="0" errors="0">'
                '<testcase/><testcase><failure/></testcase></testsuite></testsuites>',
                encoding="utf-8",
            )
            counts, _ = helper.junit_details(report)
        self.assertEqual(counts, (2, 0, 1, 0))

    def test_junit_accepts_pytest_unittest_subtest_total(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "junit.xml"
            xml = (
                '<testsuite tests="4" skipped="0" failures="0" errors="0">'
                '<testcase/><testcase/></testsuite>'
            )
            counts, cases, total = helper._junit_details_from_bytes(
                xml.encode("utf-8"), allow_subtest_totals=True
            )
        self.assertEqual(counts, (2, 0, 0, 0))
        self.assertEqual(len(cases), 2)
        self.assertEqual(total, 4)

    def test_registered_subtest_allowance_is_bound_to_exact_git_blob(self):
        helper = _helper()
        expected_blob = helper.REGISTERED_JUNIT_SUBTEST_DELTAS[MNE_SIGNAL_TEST]["blob_sha"]
        with patch.object(helper, "_git_tree_blob_sha", return_value=expected_blob):
            contract = helper._registered_junit_subtest_contract(
                Path.cwd(), "1" * 40, MNE_SIGNAL_TEST
            )
            self.assertEqual(contract["tested_tree_blob_sha"], expected_blob)
            self.assertEqual(contract["expected_delta"], 12)
            self.assertEqual(contract["source_head_sha"], "ab9090bb023695e32915a8f0302f086dc92fa780")
            self.assertEqual(contract["verification_run_id"], 39382340982)
            self.assertEqual(
                contract["verification_run_url"],
                "https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39382340982",
            )
            self.assertEqual(
                contract["tested_checkout_sha"],
                "224a92303b08277ea0885d54be68b82e475f951f",
            )
            self.assertEqual(contract["workflow_conclusion"], "failure")
            self.assertEqual(contract["candidate_status"], "FAIL")
            self.assertEqual(contract["failure_classification"], "missing_or_invalid_junit")
            self.assertEqual(contract["junit_reconciliation"], "mismatch")
            self.assertEqual(contract["test_process_outcome"], "passed")
            self.assertEqual(contract["verified_junit_total"], 53)
            self.assertEqual(contract["verified_junit_testcase_records"], 41)
            self.assertEqual(contract["component"], "mne_signal_blocks")
            self.assertEqual(contract["owner_pr"], 438)
            self.assertIn(438, helper.COMPONENT_OWNER_PRS[contract["component"]])
            self.assertEqual(
                helper._registered_junit_subtest_contract(
                    Path.cwd(), "1" * 40, "tests/elsewhere/test_changed.py"
                ),
                None,
            )
        with patch.object(helper, "_git_tree_blob_sha", return_value="a" * 40):
            self.assertEqual(
                helper._registered_junit_subtest_contract(Path.cwd(), "1" * 40, MNE_SIGNAL_TEST),
                None,
            )

        original = helper.REGISTERED_JUNIT_SUBTEST_DELTAS[MNE_SIGNAL_TEST]
        invalid_evidence = {
            **original,
            "verification": {
                **original["verification"],
                "junit_reported_total": 54,
            },
        }
        with (
            patch.object(
                helper, "REGISTERED_JUNIT_SUBTEST_DELTAS",
                {MNE_SIGNAL_TEST: invalid_evidence},
            ),
            patch.object(helper, "_git_tree_blob_sha", return_value=expected_blob),
        ):
            self.assertIsNone(
                helper._registered_junit_subtest_contract(
                    Path.cwd(), "1" * 40, MNE_SIGNAL_TEST
                )
            )

        for key, value in (("runner_telemetry_valid", False), ("skipped", 1)):
            invalid_verification = {
                **original,
                "verification": {**original["verification"], key: value},
            }
            with (
                patch.object(
                    helper, "REGISTERED_JUNIT_SUBTEST_DELTAS",
                    {MNE_SIGNAL_TEST: invalid_verification},
                ),
                patch.object(helper, "_git_tree_blob_sha", return_value=expected_blob),
            ):
                self.assertIsNone(
                    helper._registered_junit_subtest_contract(
                        Path.cwd(), "1" * 40, MNE_SIGNAL_TEST
                    )
                )

        for key, value in (
            ("tested_checkout_sha", "not-a-commit"),
            ("workflow_conclusion", "success"),
            ("candidate_status", "PASS"),
            ("failure_classification", "test_failure"),
            ("junit_reconciliation", "matched"),
            ("test_process_outcome", "failed"),
        ):
            invalid_verification = {
                **original,
                "verification": {**original["verification"], key: value},
            }
            with (
                patch.object(
                    helper,
                    "REGISTERED_JUNIT_SUBTEST_DELTAS",
                    {MNE_SIGNAL_TEST: invalid_verification},
                ),
                patch.object(helper, "_git_tree_blob_sha", return_value=expected_blob),
            ):
                with self.subTest(invalid_verification_field=key):
                    self.assertIsNone(
                        helper._registered_junit_subtest_contract(
                            Path.cwd(), "1" * 40, MNE_SIGNAL_TEST
                        )
                    )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            commit = _repo(root, with_candidate=False)
            _write(root, MNE_SIGNAL_TEST, "def test_fixture():\n    assert True\n")
            commit = _commit(root, "offline test-blob lookup fixture")
            actual_blob = helper._git_tree_blob_sha(root, commit, MNE_SIGNAL_TEST)
            expected_actual_blob = _git(root, "rev-parse", f"{commit}:{MNE_SIGNAL_TEST}")
            self.assertEqual(actual_blob, expected_actual_blob)
            self.assertNotEqual(actual_blob, expected_blob)

    def test_updated_438_test_blob_does_not_inherit_historical_subtest_allowance(self):
        helper = _helper()
        # PR #438's merged test file no longer has the historical six two-case
        # unittest.subTest loops represented by the older b37cc... blob.
        merged_438_blob = "6efe159f38e2ee4f5c662f0a63d32e9b0952751b"
        self.assertNotEqual(
            merged_438_blob,
            helper.REGISTERED_JUNIT_SUBTEST_DELTAS[MNE_SIGNAL_TEST]["blob_sha"],
        )
        with patch.object(helper, "_git_tree_blob_sha", return_value=merged_438_blob):
            self.assertIsNone(
                helper._registered_junit_subtest_contract(
                    Path.cwd(), "1" * 40, MNE_SIGNAL_TEST
                )
            )

    def test_failed_pytest_retains_bounded_junit_diagnostics(self):
        helper = _helper()
        pair = helper.COMPONENTS["simulation_grid_planner"]["candidate_pairs"][0]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = _repo(root)
            _write(root, pair["implementation"], "# fixture implementation\n")
            _write(root, pair["test"], "def test_fixture():\n    assert False\n")
            head = _commit(root, "failed pytest diagnostic fixture")
            report_path = root / "outputs/report.json"

            def failed_runner(command, **kwargs):
                if "scripts/run_tests_isolated.py" not in command:
                    return _REAL_SUBPROCESS_RUN(command, **kwargs)
                test_file = command[-1]
                testcase_xml = "".join(
                    f'<testcase classname="fixture" name="test_{index}"><failure '
                    'type="AssertionError" message="fixture failure detail"/>'
                    '</testcase>'
                    for index in range(helper.MAX_JUNIT_FAILURE_CASES + 1)
                )
                telemetry = json.loads(_valid_telemetry(test_file))
                telemetry["exit_code"] = 1
                telemetry["summary"].update({
                    "passed_batches": 0,
                    "failed_batches": 1,
                    "overall_exit_code": 1,
                })
                batch = telemetry["batches"][0]
                batch.update({
                    "status": "failed",
                    "exit_code": 1,
                    "failures": [f"FAILED {test_file}::test_fixture - AssertionError"],
                    "stdout_tail": "1 failed in 0.01s\n",
                })
                return _fake_runner(
                    command,
                    telemetry=json.dumps(telemetry),
                    junit_xml=(
                        f'<testsuite tests="{helper.MAX_JUNIT_FAILURE_CASES + 1}" '
                        f'skipped="0" failures="{helper.MAX_JUNIT_FAILURE_CASES + 1}" errors="0">'
                        f'{testcase_xml}</testsuite>'
                    ),
                    **kwargs,
                ).__class__(returncode=1, stdout="", stderr="")

            with patch.object(helper.subprocess, "run", side_effect=failed_runner):
                result = helper.run(root, base, head, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))

        execution = report["components"][0]["executions"][0]
        self.assertEqual(result, 1)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(execution["failure_classification"], "test_or_collection_failure")
        self.assertEqual(
            execution["junit_reconciliation"],
            "not_attempted_runner_telemetry_invalid",
        )
        self.assertNotIn("junit_error", execution)
        self.assertEqual(execution["result_counts"], {
            "collected": helper.MAX_JUNIT_FAILURE_CASES + 1,
            "passed": 0,
            "skipped": 0,
            "failed": helper.MAX_JUNIT_FAILURE_CASES + 1,
            "errors": 0,
            "timeouts": 0,
        })
        self.assertEqual(len(execution["junit_case_failures"]), helper.MAX_JUNIT_FAILURE_CASES)
        self.assertTrue(execution["junit_case_failures_truncated"])
        self.assertEqual(execution["junit_case_failures"][0], {
            "name": "fixture.test_0", "status": "failed"
        })
        self.assertNotIn("fixture failure detail", json.dumps(execution))

    def test_isolated_pass_reconciles_pytest_subtest_total_with_junit_summary(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = _repo(root)
            _write(root, TEST, "def test_plan_fixture():\n    assert True  # unittest subtest fixture\n")
            head = _commit(root, "unittest subtest fixture")
            report_path = root / "outputs/report.json"

            def subtest_runner(command, **kwargs):
                if "scripts/run_tests_isolated.py" not in command:
                    return _REAL_SUBPROCESS_RUN(command, **kwargs)
                test_file = command[-1]
                telemetry_path = Path(command[command.index("--report") + 1])
                telemetry = json.loads(_valid_telemetry(test_file))
                telemetry["batches"][0]["stdout_tail"] = "2 passed, 2 subtests passed in 0.01s\n"
                telemetry_path.write_text(json.dumps(telemetry), encoding="utf-8")
                junit_arg = next(arg for arg in command if arg.startswith("--pytest-arg=--junitxml="))
                junit = _workspace_path_for_output_arg(
                    junit_arg.removeprefix("--pytest-arg=--junitxml=")
                )
                junit.write_text(
                    '<testsuite tests="4" skipped="0" failures="0" errors="0">'
                    '<testcase/><testcase/></testsuite>',
                    encoding="utf-8",
                )
                return SimpleNamespace(returncode=0)

            with patch.object(helper.subprocess, "run", side_effect=subtest_runner):
                result = helper.run(root, base, head, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))
        execution = report["components"][0]["executions"][0]
        self.assertEqual(result, 0)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(execution["tests_collected"], 4)
        self.assertEqual(execution["runner_passed_tests"], 2)
        self.assertEqual(execution["runner_passed_subtests"], 2)
        self.assertEqual(execution["junit_reported_test_outcomes"], 4)
        self.assertEqual(execution["junit_reconciliation"], "matched")
        self.assertEqual(len(execution["test_cases"]), 2)
        self.assertEqual(execution["result_counts"]["passed"], 4)

    def test_isolated_pass_uses_valid_junit_when_stdout_has_no_pytest_summary(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = _repo(root)
            _write(root, TEST, "def test_plan_fixture():\n    assert True  # captured stdout case\n")
            head = _commit(root, "captured pytest output fixture")
            report_path = root / "outputs/report.json"
            junit_total = 2

            def quiet_runner(command, **kwargs):
                if "scripts/run_tests_isolated.py" not in command:
                    return _REAL_SUBPROCESS_RUN(command, **kwargs)
                test_file = command[-1]
                telemetry = json.loads(_valid_telemetry(test_file))
                telemetry["batches"][0]["stdout_tail"] = "captured by test runner\n"
                return _fake_runner(
                    command,
                    telemetry=json.dumps(telemetry),
                    junit_xml=(
                        f'<testsuite tests="{junit_total}" skipped="0" failures="0" errors="0">'
                        '<testcase/><testcase/></testsuite>'
                    ),
                    **kwargs,
                )

            with patch.object(helper.subprocess, "run", side_effect=quiet_runner):
                result = helper.run(root, base, head, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            execution = report["components"][0]["executions"][0]
            self.assertEqual(result, 0)
            self.assertEqual(report["status"], "PASS")
            self.assertTrue(execution["isolated_runner_telemetry_valid"])
            self.assertEqual(execution["junit_reconciliation"], "matched_junit_authoritative_no_summary")
            self.assertEqual(execution["result_counts"], {
                "collected": 2,
                "passed": 2,
                "skipped": 0,
                "failed": 0,
                "errors": 0,
                "timeouts": 0,
            })

            junit_total = 3
            with patch.object(helper.subprocess, "run", side_effect=quiet_runner):
                result = helper.run(root, base, head, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            execution = report["components"][0]["executions"][0]
            self.assertEqual(result, 1)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(execution["failure_classification"], "missing_or_invalid_junit")
            self.assertIn("without a registered subtest contract", execution["junit_error"])

    def test_registered_mne_subtest_delta_reconciles_without_pytest_stdout(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _repo(root, with_candidate=False)
            for implementation in MNE_SIGNAL_IMPLEMENTATIONS:
                _write(root, implementation, "# synthetic MNE signal-block module fixture\n")
            _write(root, MNE_SIGNAL_TEST, "def test_signal_block_contract():\n    assert True\n")
            base = _commit(root, "registered MNE signal-block candidate fixture")
            _write(root, MNE_SIGNAL_TEST, "def test_signal_block_contract():\n    assert True  # candidate change\n")
            head = _commit(root, "registered MNE unittest subtest delta fixture")
            report_path = root / "outputs/report.json"
            testcase_xml = "<testcase/>" * 41
            junit_delta = 12

            def subtest_runner(command, **kwargs):
                if "scripts/run_tests_isolated.py" not in command:
                    return _REAL_SUBPROCESS_RUN(command, **kwargs)
                telemetry = json.loads(_valid_telemetry(command[-1]))
                telemetry["batches"][0]["stdout_tail"] = "pytest output captured by isolated runner\n"
                return _fake_runner(
                    command,
                    telemetry=json.dumps(telemetry),
                    junit_xml=(
                        f'<testsuite tests="{41 + junit_delta}" skipped="0" failures="0" errors="0">'
                        f"{testcase_xml}</testsuite>"
                    ),
                    **kwargs,
                )

            with (
                patch.object(
                    helper, "_git_tree_blob_sha",
                    return_value=helper.REGISTERED_JUNIT_SUBTEST_DELTAS[MNE_SIGNAL_TEST]["blob_sha"],
                ),
                patch.object(helper.subprocess, "run", side_effect=subtest_runner),
                redirect_stdout(io.StringIO()) as log_output,
            ):
                result = helper.run(root, base, head, report_path, tested_checkout_sha=head)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            log_evidence = next(
                json.loads(line) for line in log_output.getvalue().splitlines()
                if line.startswith("{") and '"selected_component"' in line
            )

        execution = report["components"][0]["executions"][0]
        self.assertEqual(result, 0)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(execution["selected_component"], "mne_signal_blocks")
        self.assertEqual(execution["test_file"], MNE_SIGNAL_TEST)
        self.assertEqual(execution["registered_subtest_delta"], 12)
        self.assertEqual(execution["registered_subtest_contract"], {
            "test_path": MNE_SIGNAL_TEST,
            "tested_tree_blob_sha": helper.REGISTERED_JUNIT_SUBTEST_DELTAS[MNE_SIGNAL_TEST]["blob_sha"],
            "source_head_sha": "ab9090bb023695e32915a8f0302f086dc92fa780",
            "verification_run_id": 39382340982,
            "verification_run_url": "https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39382340982",
            "tested_checkout_sha": "224a92303b08277ea0885d54be68b82e475f951f",
            "workflow_conclusion": "failure",
            "candidate_status": "FAIL",
            "failure_classification": "missing_or_invalid_junit",
            "junit_reconciliation": "mismatch",
            "test_process_outcome": "passed",
            "expected_delta": 12,
            "observed_delta": 12,
            "verified_junit_total": 53,
            "verified_junit_testcase_records": 41,
            "component": "mne_signal_blocks",
            "owner_pr": 438,
            "applied_without_pytest_summary": True,
        })
        self.assertEqual(log_evidence["registered_subtest_contract"], execution["registered_subtest_contract"])
        self.assertEqual(log_evidence["junit_reconciliation"], execution["junit_reconciliation"])
        self.assertEqual(execution["junit_testcase_records"], 41)
        self.assertEqual(execution["tests_collected"], 53)
        self.assertEqual(
            execution["junit_reconciliation"],
            "matched_junit_declared_subtest_total_no_summary",
        )
        self.assertEqual(execution["result_counts"], {
            "collected": 53,
            "passed": 53,
            "skipped": 0,
            "failed": 0,
            "errors": 0,
            "timeouts": 0,
        })

        # A count mismatch beyond the exact reviewed subtest contract is not pass evidence.
        junit_delta = 13
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _repo(root, with_candidate=False)
            for implementation in MNE_SIGNAL_IMPLEMENTATIONS:
                _write(root, implementation, "# synthetic MNE signal-block module fixture\n")
            _write(root, MNE_SIGNAL_TEST, "def test_signal_block_contract():\n    assert True\n")
            base = _commit(root, "registered MNE signal-block candidate fixture")
            _write(root, MNE_SIGNAL_TEST, "def test_signal_block_contract():\n    assert True  # candidate change\n")
            head = _commit(root, "unregistered MNE subtest delta fixture")
            report_path = root / "outputs/report.json"
            with (
                patch.object(
                    helper, "_git_tree_blob_sha",
                    return_value=helper.REGISTERED_JUNIT_SUBTEST_DELTAS[MNE_SIGNAL_TEST]["blob_sha"],
                ),
                patch.object(helper.subprocess, "run", side_effect=subtest_runner),
            ):
                result = helper.run(root, base, head, report_path, tested_checkout_sha=head)
            report = json.loads(report_path.read_text(encoding="utf-8"))
        execution = report["components"][0]["executions"][0]
        self.assertEqual(result, 1)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(execution["failure_classification"], "missing_or_invalid_junit")
        self.assertIn("does not match registered delta 12", execution["junit_error"])
        self.assertEqual(execution["registered_subtest_contract"]["observed_delta"], 13)

    def test_subtest_junit_total_without_outcome_summaries_fails_closed(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = _repo(root)
            _write(root, TEST, "def test_plan_fixture():\n    assert True  # unverified subtest fixture\n")
            head = _commit(root, "JUnit subtest total without outcome summary")
            report_path = root / "outputs/report.json"

            def unverified_runner(command, **kwargs):
                if "scripts/run_tests_isolated.py" not in command:
                    return _REAL_SUBPROCESS_RUN(command, **kwargs)
                telemetry = json.loads(_valid_telemetry(command[-1]))
                telemetry["batches"][0]["stdout_tail"] = "pytest output captured by isolated runner\n"
                return _fake_runner(
                    command,
                    telemetry=json.dumps(telemetry),
                    junit_xml='<testsuite tests="53"><testcase/><testcase/></testsuite>',
                    **kwargs,
                )

            with patch.object(helper.subprocess, "run", side_effect=unverified_runner):
                result = helper.run(root, base, head, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))

        execution = report["components"][0]["executions"][0]
        self.assertEqual(result, 1)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(execution["failure_classification"], "missing_or_invalid_junit")
        self.assertIn("requires explicit outcome summaries", execution["junit_error"])
        self.assertEqual(execution["junit_reconciliation"], "invalid_junit")

    def test_runner_rejects_inflated_stdout_pass_count(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = _repo(root)
            _write(root, TEST, "def test_plan_fixture():\n    assert True  # inflated summary probe\n")
            head = _commit(root, "inflated pytest summary probe")
            report_path = root / "outputs/report.json"

            def inflated_runner(command, **kwargs):
                if "scripts/run_tests_isolated.py" not in command:
                    return _REAL_SUBPROCESS_RUN(command, **kwargs)
                test_file = command[-1]
                telemetry_path = Path(command[command.index("--report") + 1])
                telemetry = json.loads(_valid_telemetry(test_file))
                telemetry["batches"][0]["stdout_tail"] = "4 passed in 0.01s\n"
                telemetry_path.write_text(json.dumps(telemetry), encoding="utf-8")
                junit_arg = next(arg for arg in command if arg.startswith("--pytest-arg=--junitxml="))
                junit = _workspace_path_for_output_arg(
                    junit_arg.removeprefix("--pytest-arg=--junitxml=")
                )
                junit.write_text(
                    '<testsuite tests="4" skipped="0" failures="0" errors="0">'
                    '<testcase/><testcase/></testsuite>',
                    encoding="utf-8",
                )
                return SimpleNamespace(returncode=0)

            with patch.object(helper.subprocess, "run", side_effect=inflated_runner):
                result = helper.run(root, base, head, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))
        execution = report["components"][0]["executions"][0]
        self.assertEqual(result, 1)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(execution["failure_classification"], "missing_or_invalid_junit")
        self.assertIn("testcase records", execution["junit_error"])

    def test_unknown_data_suffixes_under_candidate_roots_fail_closed(self):
        helper = _helper()
        for path in (
            "tools/surrogate_nulls/new_fixture.h5",
            "tests/surrogate_nulls/new_fixture.fif",
            "tools/surrogate_nulls/new_fixture",
        ):
            with self.subTest(path=path):
                self.assertIn(path, helper._unmapped_candidate_paths({path}))
        self.assertEqual(
            helper._unmapped_candidate_paths({"tests/surrogate_nulls/notes.md"}),
            [],
        )

    def test_documentation_only_change_under_candidate_root_is_not_applicable(self):
        helper = _helper()
        documentation = "tests/surrogate_nulls/notes.md"
        self.assertEqual(helper.select_components({documentation}), [])
        self.assertEqual(helper._unmapped_candidate_paths({documentation}), [])

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = _repo(root)
            _write(root, documentation, "Documentation-only change.\n")
            head = _commit(root, "candidate documentation only")
            report_path = root / "outputs/report.json"

            def no_candidate_runner(command, **kwargs):
                if "scripts/run_tests_isolated.py" in command:
                    raise AssertionError("documentation-only changes must not execute candidate tests")
                return _REAL_SUBPROCESS_RUN(command, **kwargs)

            with patch.object(helper.subprocess, "run", side_effect=no_candidate_runner):
                exit_code = helper.run(
                    root, base, head, report_path,
                    tested_checkout_sha=head, workflow_sha=base,
                    event_name="pull_request", require_checkout_match=True,
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "NOT_APPLICABLE")
        self.assertEqual(report["selected_components"], [])
        self.assertEqual(report["executed_commands"], [])

    def test_unregistered_test_in_shared_experimental_root_blocks_not_applicable(self):
        helper = _helper()
        new_test = "tests/experimental/test_planar_triangulation_extra.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = _repo(root)
            _write(root, new_test, "def test_unregistered_candidate():\n    assert True\n")
            head = _commit(root, "unregistered shared experimental test")
            report_path = root / "outputs/report.json"

            def no_candidate_runner(command, **kwargs):
                if "scripts/run_tests_isolated.py" in command:
                    raise AssertionError("unmapped tests must not launch a candidate suite")
                return _REAL_SUBPROCESS_RUN(command, **kwargs)

            with patch.object(helper.subprocess, "run", side_effect=no_candidate_runner):
                exit_code = helper.run(
                    root, base, head, report_path,
                    tested_checkout_sha=head, workflow_sha=base,
                    event_name="pull_request", require_checkout_match=True,
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["selected_components"], [])
        self.assertEqual(report["unmapped_candidate_paths"], [new_test])
        self.assertEqual(report["executed_commands"], [])

    def test_case_mismatched_registered_paths_fail_closed(self):
        helper = _helper()
        wrong_case = "Tools/surrogate_nulls/nulls.py"
        self.assertEqual(helper.select_components({wrong_case}), ["surrogate_nulls"])
        self.assertEqual(helper._unmapped_candidate_paths({wrong_case}), [wrong_case])
        self.assertEqual(
            helper._changed_candidate_paths(helper.COMPONENTS["surrogate_nulls"], {wrong_case}),
            [wrong_case],
        )

    def test_isolated_runner_telemetry_requires_duration_and_batch_identity(self):
        helper = _helper()
        baseline = json.loads(_valid_telemetry(TEST))
        mutations = (
            ("summary", "duration_s"),
            ("batch", "duration_s"),
            ("batch", "batch_index"),
            ("batch", "batch_number"),
        )
        for target, field in mutations:
            with self.subTest(target=target, field=field):
                telemetry = json.loads(json.dumps(baseline))
                container = telemetry["summary"] if target == "summary" else telemetry["batches"][0]
                del container[field]
                valid, error, _ = helper._isolated_runner_report_is_valid(telemetry, TEST)
                self.assertFalse(valid)
                self.assertIn("missing or malformed", error)

    def test_runner_cannot_pass_with_inconsistent_junit_summary(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = _repo(root)
            _write(root, TEST, "def test_plan_fixture():\n    assert True  # changed test fixture\n")
            head = _commit(root, "candidate with inconsistent junit summary fixture")
            report_path = root / "outputs/report.json"
            runner = lambda command, **kwargs: _fake_runner(
                command,
                junit_xml='<testsuite tests="2" failures="1"><testcase/></testsuite>',
                **kwargs,
            )
            with patch.object(helper.subprocess, "run", side_effect=runner):
                result = helper.run(root, base, head, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))
        execution = report["components"][0]["executions"][0]
        self.assertEqual(result, 1)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(execution["failure_classification"], "missing_or_invalid_junit")
        self.assertIn("requires explicit outcome summaries", execution["junit_error"])

    def test_log_directory_symlink_escape_is_blocked_before_runner_launch(self):
        helper = _helper()
        pair = helper.COMPONENTS["simulation_grid_planner"]["candidate_pairs"][0]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            outside = Path(td) / "outside"
            outside.mkdir()
            for relative in (pair["implementation"], pair["test"]):
                _write(root, relative, "# deterministic fixture\n")
            log_parent = root / "outputs"
            log_parent.mkdir()
            log_link = log_parent / "round6-experimental-logs"
            try:
                log_link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                with self.assertRaises(ValueError):
                    helper._contained_path(root, outside / "logs", "test log directory")
                return

            report_path = log_parent / "report.json"
            with patch.object(helper, "collect_changed_paths", return_value={pair["implementation"]}), patch.object(
                helper.subprocess, "run", side_effect=AssertionError("escaped log path must block before launch")
            ):
                result = helper.run(root, "0" * 40, "1" * 40, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(result, 1)
            self.assertEqual(report["status"], "BLOCKED")
            execution = report["components"][0]["executions"][0]
            self.assertEqual(execution["failure_classification"], "unsafe_or_unavailable_log_path")
            self.assertFalse(any(outside.iterdir()))

    def test_log_file_symlink_escape_is_blocked_before_runner_launch(self):
        helper = _helper()
        pair = helper.COMPONENTS["simulation_grid_planner"]["candidate_pairs"][0]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            outside = Path(td) / "outside"
            outside.mkdir()
            for relative in (pair["implementation"], pair["test"]):
                _write(root, relative, "# deterministic fixture\n")
            log_dir = root / "outputs/round6-experimental-logs/01-simulation_grid_planner-01"
            log_dir.mkdir(parents=True)
            try:
                (log_dir / "runner.stdout.log").symlink_to(outside / "stdout.log")
            except (OSError, NotImplementedError):
                with self.assertRaises(ValueError):
                    helper._contained_path(root, outside / "stdout.log", "runner stdout path")
                return

            report_path = root / "outputs/report.json"
            with patch.object(helper, "collect_changed_paths", return_value={pair["implementation"]}), patch.object(
                helper.subprocess, "run", side_effect=AssertionError("escaped log path must block before launch")
            ):
                result = helper.run(root, "0" * 40, "1" * 40, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(result, 1)
            execution = report["components"][0]["executions"][0]
            self.assertEqual(execution["failure_classification"], "unsafe_or_unavailable_log_path")
            self.assertFalse((outside / "stdout.log").exists())

    def test_junit_symlink_escape_created_by_candidate_is_blocked_after_runner(self):
        helper = _helper()
        pair = helper.COMPONENTS["simulation_grid_planner"]["candidate_pairs"][0]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            outside = Path(td) / "outside-junit.xml"
            outside.write_text('<testsuite tests="1"><testcase/></testsuite>', encoding="utf-8")
            for relative in (pair["implementation"], pair["test"]):
                _write(root, relative, "# deterministic fixture\n")
            report_path = root / "outputs/report.json"

            def replace_junit_after_launch(command, **kwargs):
                if "scripts/run_tests_isolated.py" not in command:
                    return _REAL_SUBPROCESS_RUN(command, **kwargs)
                telemetry = Path(command[command.index("--report") + 1])
                telemetry.write_text(_valid_telemetry(command[-1]), encoding="utf-8")
                junit_arg = next(arg for arg in command if arg.startswith("--pytest-arg=--junitxml="))
                junit = Path(junit_arg.removeprefix("--pytest-arg=--junitxml="))
                try:
                    junit.unlink()
                    junit.symlink_to(outside)
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(f"symlink creation unavailable: {exc}")
                return SimpleNamespace(returncode=0)

            with patch.object(helper, "collect_changed_paths", return_value={pair["implementation"]}), patch.object(
                helper.subprocess, "run", side_effect=replace_junit_after_launch
            ):
                result = helper.run(root, "0" * 40, "1" * 40, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(result, 1)
        self.assertEqual(report["status"], "BLOCKED")
        execution = report["components"][0]["executions"][0]
        self.assertEqual(execution["failure_classification"], "unsafe_or_unavailable_log_path")
        self.assertNotIn("tests_collected", execution)

    def test_junit_symlink_to_in_repo_report_is_not_followed_after_runner(self):
        helper = _helper()
        pair = helper.COMPONENTS["simulation_grid_planner"]["candidate_pairs"][0]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            for relative in (pair["implementation"], pair["test"]):
                _write(root, relative, "# deterministic fixture\n")
            preserved = root / "preserved.xml"
            preserved.write_text(
                '<testsuite tests="1" skipped="0" failures="0" errors="0">'
                "<testcase/></testsuite>",
                encoding="utf-8",
            )
            report_path = root / "outputs/report.json"

            def replace_junit_with_in_repo_symlink(command, **kwargs):
                if "scripts/run_tests_isolated.py" not in command:
                    return _REAL_SUBPROCESS_RUN(command, **kwargs)
                telemetry = Path(command[command.index("--report") + 1])
                telemetry.write_text(_valid_telemetry(command[-1]), encoding="utf-8")
                junit_arg = next(arg for arg in command if arg.startswith("--pytest-arg=--junitxml="))
                junit = Path(junit_arg.removeprefix("--pytest-arg=--junitxml="))
                try:
                    junit.unlink()
                    junit.symlink_to(preserved)
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(f"symlink creation unavailable: {exc}")
                return SimpleNamespace(returncode=0)

            with patch.object(
                helper, "collect_changed_paths", return_value={pair["implementation"]}
            ), patch.object(
                helper.subprocess, "run", side_effect=replace_junit_with_in_repo_symlink
            ):
                result = helper.run(root, "0" * 40, "1" * 40, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(result, 1)
        self.assertEqual(report["status"], "BLOCKED")
        execution = report["components"][0]["executions"][0]
        self.assertEqual(execution["failure_classification"], "unsafe_or_unavailable_log_path")
        self.assertNotIn("tests_collected", execution)

    def test_preexisting_log_directory_symlink_to_in_repo_path_is_blocked(self):
        helper = _helper()
        pair = helper.COMPONENTS["simulation_grid_planner"]["candidate_pairs"][0]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            for relative in (pair["implementation"], pair["test"]):
                _write(root, relative, "# deterministic fixture\n")
            report_parent = root / "outputs"
            report_parent.mkdir()
            linked_parent = report_parent / "round6-experimental-logs"
            target_parent = root / "preserved-logs"
            target_parent.mkdir()
            target = target_parent / "runner.stdout.log"
            target.write_text("preserve this file\n", encoding="utf-8")
            try:
                linked_parent.symlink_to(target_parent, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")

            with patch.object(
                helper, "collect_changed_paths", return_value={pair["implementation"]}
            ):
                result = helper.run(root, "0" * 40, "1" * 40, report_parent / "report.json")
            report = json.loads((report_parent / "report.json").read_text(encoding="utf-8"))
            captured = target.read_text(encoding="utf-8")

        self.assertEqual(result, 1)
        self.assertEqual(report["status"], "BLOCKED")
        execution = report["components"][0]["executions"][0]
        self.assertEqual(execution["failure_classification"], "unsafe_or_unavailable_log_path")
        self.assertEqual(captured, "preserve this file\n")

    def test_report_symlink_escape_created_by_candidate_is_not_written(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            outside = Path(td) / "outside-report.json"
            outside.write_text("preserve this file\n", encoding="utf-8")
            base = _repo(root)
            _write(root, TEST, "def test_plan_fixture():\n    assert True  # report symlink probe\n")
            head = _commit(root, "report symlink probe")
            report_path = root / "outputs/report.json"

            def replace_report_after_launch(command, **kwargs):
                if "scripts/run_tests_isolated.py" not in command:
                    return _REAL_SUBPROCESS_RUN(command, **kwargs)
                telemetry = Path(command[command.index("--report") + 1])
                telemetry.write_text(_valid_telemetry(command[-1]), encoding="utf-8")
                junit_arg = next(arg for arg in command if arg.startswith("--pytest-arg=--junitxml="))
                junit = Path(junit_arg.removeprefix("--pytest-arg=--junitxml="))
                junit.write_text('<testsuite tests="1"><testcase/></testsuite>', encoding="utf-8")
                try:
                    report_path.unlink()
                    report_path.symlink_to(outside)
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(f"symlink creation unavailable: {exc}")
                return SimpleNamespace(returncode=0)

            with patch.object(helper.subprocess, "run", side_effect=replace_report_after_launch):
                result = helper.run(root, base, head, report_path)
            captured = outside.read_text(encoding="utf-8")
        self.assertEqual(result, 1)
        self.assertEqual(captured, "preserve this file\n")

    def test_preexisting_report_symlink_to_in_repo_file_is_not_followed(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            base = _repo(root)
            report_parent = root / "outputs"
            report_parent.mkdir()
            preserved = report_parent / "preserved.json"
            preserved.write_text("preserve this file\n", encoding="utf-8")
            report_path = report_parent / "round6-experimental-report.json"
            try:
                report_path.symlink_to(preserved)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")

            result = helper.run(root, base, base, report_path)
            captured = preserved.read_text(encoding="utf-8")

        self.assertEqual(result, 1)
        self.assertEqual(captured, "preserve this file\n")

    def test_stale_base_uses_pr_base_and_pr_head_while_testing_merge_checkout(self):
        helper = _helper()
        roc_implementation = "neurotopology_sim/experimental/benchmarks/synthetic_forward_roc.py"
        roc_test = "tests/neurotopology_sim/experimental/benchmarks/test_synthetic_forward_roc.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original_base = _repo(root)
            _git(root, "switch", "-c", "candidate")
            _write(root, TEST, "def test_plan_fixture():\n    assert True  # PR head\n")
            pr_head = _commit(root, "PR test-only change")
            _git(root, "switch", "main")
            _write(root, "tools/surrogate_nulls/nulls.py", "def unrelated_main_update():\n    return None\n")
            _write(root, roc_implementation, "def unrelated_merged_roc_update():\n    return None\n")
            _write(root, roc_test, "def test_unrelated_merged_roc_update():\n    assert True\n")
            pr_base = _commit(root, "main advances in unrelated candidate")
            _git(root, "switch", "candidate")
            _git(root, "merge", "--no-ff", "main", "-m", "synthetic tested merge checkout")
            merge_checkout = _git(root, "rev-parse", "HEAD")

            changed = helper.collect_changed_paths(pr_base, pr_head, root)
            wrong_merge_diff = helper.collect_changed_paths(original_base, merge_checkout, root)
            self.assertEqual(changed, {TEST})
            self.assertIn("tools/surrogate_nulls/nulls.py", wrong_merge_diff)
            self.assertIn(roc_implementation, wrong_merge_diff)
            self.assertIn(roc_test, wrong_merge_diff)
            self.assertEqual(helper.select_components(changed), ["simulation_grid_planner"])

            report_path = root / "outputs/report.json"
            with patch.object(helper.subprocess, "run", side_effect=lambda command, **kwargs: _fake_runner(command, **kwargs)):
                exit_code = helper.run(
                    root, pr_base, pr_head, report_path,
                    tested_checkout_sha=merge_checkout,
                    workflow_sha=original_base,
                    event_name="pull_request",
                    require_checkout_match=True,
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["changed_paths"], [TEST])
        self.assertEqual(report["diff_base_sha"], pr_base)
        self.assertEqual(report["diff_head_sha"], pr_head)
        self.assertEqual(report["tested_checkout_sha"], merge_checkout)
        self.assertEqual(report["workflow_sha"], original_base)
        self.assertNotEqual(report["tested_checkout_sha"], report["diff_head_sha"])
        self.assertEqual(report["selected_components"], ["simulation_grid_planner"])
        self.assertNotIn("synthetic_roc", report["selected_components"])
        self.assertEqual(report["components"][0]["executions"][0]["test_file"], TEST)

    def test_changed_candidate_without_required_test_is_blocked(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = _repo(root, with_candidate=False)
            _write(root, IMPLEMENTATION, "def plan():\n    return ()\n")
            head = _commit(root, "implementation with missing mapped test")
            report_path = root / "outputs/report.json"
            with patch.object(helper.subprocess, "run", side_effect=lambda command, **kwargs: _REAL_SUBPROCESS_RUN(command, **kwargs)):
                exit_code = helper.run(
                    root, base, head, report_path,
                    tested_checkout_sha=head, workflow_sha=base,
                    event_name="pull_request", require_checkout_match=True,
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn(TEST, report["components"][0]["missing_required_tests"])
        self.assertEqual(report["executed_commands"], [])

    def test_source_change_blocks_when_registered_companion_test_is_missing(self):
        helper = _helper()
        original = helper.COMPONENTS["simulation_grid_planner"]
        companion = "tests/simulation_runtime/test_grid_plan_adversarial.py"
        helper.COMPONENTS["simulation_grid_planner"] = {
            **original,
            "tests": (*original["tests"], companion),
            "candidate_pairs": (
                *original["candidate_pairs"],
                {"implementation": IMPLEMENTATION, "test": companion},
            ),
        }
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                base = _repo(root)
                _write(root, IMPLEMENTATION, "def plan():\n    return ('source revision',)\n")
                head = _commit(root, "source PR before companion test PR")
                report_path = root / "outputs/report.json"
                with patch.object(helper.subprocess, "run", side_effect=lambda command, **kwargs: _fake_runner(command, **kwargs)) as runner:
                    exit_code = helper.run(root, base, head, report_path)
                report = json.loads(report_path.read_text(encoding="utf-8"))
        finally:
            helper.COMPONENTS["simulation_grid_planner"] = original
        self.assertEqual(exit_code, 1)
        component = report["components"][0]
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(component["status"], "BLOCKED")
        self.assertEqual(component["missing_required_tests"], [companion])
        self.assertIn("required candidate test is absent", component["blockers"])
        self.assertEqual(
            [item["test"] for item in component["unavailable_companion_pairs"]],
            [companion],
        )
        self.assertEqual(component["executions"], [])
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(runner.call_args.args[0][:3], ["git", "diff", "--name-only"])

    def test_skipped_candidate_test_is_failure_not_pass(self):
        helper = _helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = _repo(root)
            _write(root, TEST, "def test_plan_fixture():\n    assert True  # changed\n")
            head = _commit(root, "test-only change with injected skip")
            report_path = root / "outputs/report.json"
            with patch.object(helper.subprocess, "run", side_effect=lambda command, **kwargs: _fake_runner(command, junit_status="skipped", **kwargs)):
                exit_code = helper.run(root, base, head, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 1)
        execution = report["components"][0]["executions"][0]
        self.assertEqual(execution["status"], "FAIL")
        self.assertEqual(execution["failure_classification"], "candidate_tests_skipped")
        self.assertEqual(execution["result_counts"]["skipped"], 1)

    def test_malformed_telemetry_and_boolean_counts_are_rejected(self):
        helper = _helper()
        valid = json.loads(_valid_telemetry(TEST))
        valid["summary"]["passed_batches"] = True
        ok, error, _ = helper._isolated_runner_report_is_valid(valid, TEST)
        self.assertFalse(ok)
        self.assertIn("malformed", error)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = _repo(root)
            _write(root, TEST, "def test_plan_fixture():\n    assert True  # malformed telemetry probe\n")
            head = _commit(root, "test-only malformed telemetry probe")
            report_path = root / "outputs/report.json"
            with patch.object(helper.subprocess, "run", side_effect=lambda command, **kwargs: _fake_runner(command, telemetry="NaN", **kwargs)):
                exit_code = helper.run(root, base, head, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 1)
        execution = report["components"][0]["executions"][0]
        self.assertEqual(execution["status"], "FAIL")
        self.assertFalse(execution["isolated_runner_telemetry_valid"])
        self.assertIn("non-finite", execution["runner_telemetry_error"])

    def test_required_active_candidate_paths_are_not_silently_unmapped_or_not_applicable(self):
        helper = _helper()
        expected = {
            "release_readiness_security": (
                370,
                "tools/release_readiness/batch2_security/artifact_states.py",
                "tests/release_readiness/batch2_security/test_artifact_states.py",
            ),
            "higher_order_runtime": (
                377,
                "tools/higher_order_runtime/stream_contract.py",
                "tests/higher_order_runtime_contract/test_chunk_boundaries.py",
            ),
            "synthetic_pipeline_replay": (
                387,
                "tools/synthetic_pipeline_replay/runner.py",
                "tests/integration/synthetic_pipeline_replay/test_replay_harness.py",
            ),
            "planar_geometry": (
                416,
                "neurotopology_sim/experimental/geometry/planar_triangulation.py",
                "tests/experimental/test_planar_triangulation.py",
            ),
            "finite_jitter_production_bridge": (
                410,
                "tools/audit_finite_jitter_triangulation.py",
                "tests/test_finite_jitter_production_import.py",
            ),
            "hodge_2d": (
                423,
                "neurotopology_sim/experimental/topology/hodge_2d.py",
                "tests/neurotopology_sim/experimental/topology/test_hodge_2d.py",
            ),
            "phase_cochain_reference": (
                385,
                "experimental/phase_cochain_reference/hodge.py",
                "tests/experimental/phase_cochain_reference/test_weighted_hodge_decomposition.py",
            ),
            "hodge_decomposition_audit": (
                396,
                "tools/hodge_decomposition_audit/audit.py",
                "tests/tools/hodge_decomposition_audit/test_hodge_audit.py",
            ),
            "spherical_csd": (
                402, 414, 419,
                "neurotopology_sim/experimental/preprocessing/spherical_csd.py",
                "tests/experimental/test_spherical_csd_parity.py",
            ),
            "mne_csd_reference_audit": (
                402,
                "tools/mne_csd_reference_audit/legendre.py",
                "tests/mne_csd_reference_audit/test_legendre_constants.py",
            ),
            "mne_csd_adapter": (
                378,
                "adapters/mne_csd/transform.py",
                "tests/adapters/mne_csd/test_parameter_forwarding.py",
            ),
            "source_mining_evidence_boundary": (
                382,
                "tools/evidence_promotion_gate/evaluator.py",
                "tests/source_mining_integration/test_source_mining_evidence_boundary.py",
            ),
            "measurement_hypothesis_contract": (
                384, 357,
                "shared/measurement_hypothesis/validate.py",
                "tests/measurement_hypothesis/test_gate_reference_and_promotion.py",
            ),
            "batch2_pipeline_benchmark": (
                371, 445,
                "tools/benchmarks/batch2_pipeline/harness.py",
                "tests/benchmarks/batch2_pipeline/test_harness_and_targets.py",
            ),
            "four_sphere": (
                418, 409,
                "physics/eeg_forward/four_sphere.py",
                "tests/physics/test_four_sphere_oracle.py",
            ),
            "phase_winding": (
                413,
                "neurotopology_sim/experimental/topology/winding.py",
                "tests/neurotopology_sim/experimental/topology/test_phase_winding.py",
            ),
            "surrogate_nulls": (
                417, 430,
                "tools/surrogate_nulls/nulls.py",
                "tests/surrogate_nulls/test_adversarial_contracts.py",
            ),
            "dmd_crouzeix": (
                415, 420, 400,
                "neurotopology_sim/experimental/dynamics/dmd_crouzeix.py",
                "tests/dmd_ep2_oracle/test_production_bridge.py",
            ),
            "synthetic_roc": (
                426, 427,
                "neurotopology_sim/experimental/benchmarks/synthetic_forward_roc.py",
                "tests/neurotopology_sim/experimental/benchmarks/test_synthetic_forward_roc.py",
            ),
            "simulation_grid_planner": (
                424,
                "tools/simulation_runtime/grid_plan.py",
                "tests/simulation_runtime/test_grid_plan.py",
            ),
            "fusion_validation_null_models": (
                374,
                "dual_engine/fusion_validation.py",
                "tests/test_fusion_null_models.py",
            ),
            "docker_context_policy": (
                431, 434,
                ".dockerignore",
                "tests/docker_context/test_build_context_policy.py",
            ),
            "public_repo_source_pack": (
                391,
                "tools/public_repo_harvest/source_pack.py",
                "tests/tools/test_public_repo_harvest_source_pack.py",
            ),
            "dandi_nwb_bounded": (
                437,
                "data/dandi_nwb_ingest.py",
                "tests/data_access/dandi_nwb_bounded/test_dandi_nwb_bounded_contract.py",
            ),
            "streaming_s3_transfer": (
                437,
                "tools/streaming/base_runner.py",
                "tests/streaming/test_sync_s3_subject_fail_closed.py",
            ),
            "ds005620_cohort_stream": (
                437,
                "tools/stream_pitnn_cohort_ds005620.py",
                "tests/test_pitnn_cohort_ds005620.py",
            ),
            "moabb_protocol_conformance": (
                379,
                "tools/moabb_protocol_conformance/validation.py",
                "tests/tools/moabb_protocol_conformance/test_manifest_and_validation.py",
            ),
            "mne_signal_blocks": (
                380, 438,
                "adapters/mne_signal_blocks/converter.py",
                "tests/adapters/mne_signal_blocks/test_mne_signal_blocks.py",
            ),
        }
        for component, record in expected.items():
            *owner_prs, implementation, test_file = record
            spec = helper.COMPONENTS[component]
            self.assertEqual(helper.COMPONENT_OWNER_PRS[component], tuple(owner_prs))
            self.assertIn(
                {"implementation": implementation, "test": test_file},
                spec["candidate_pairs"],
            )
            self.assertEqual(helper.select_components({test_file}), [component])

        security = helper.COMPONENTS["release_readiness_security"]
        self.assertEqual(
            {pair["implementation"] for pair in security["candidate_pairs"]},
            {
                "tools/release_readiness/batch2_security/artifact_states.py",
                "tools/release_readiness/batch2_security/evidence_boundary.py",
                "tools/release_readiness/batch2_security/finite_json.py",
                "tools/release_readiness/batch2_security/fixtures.py",
                "tools/release_readiness/batch2_security/network_policy.py",
                "tools/release_readiness/batch2_security/path_containment.py",
                "tools/release_readiness/batch2_security/report.py",
                "tools/release_readiness/batch2_security/runner.py",
                "tools/release_readiness/batch2_security/schema.py",
                "tools/release_readiness/batch2_security/static_scan.py",
                "tools/release_readiness/batch2_security/subprocess_guard.py",
                "scripts/run_batch2_security_audit.py",
            },
        )
        self.assertEqual(
            {pair["test"] for pair in security["candidate_pairs"]},
            set(security["tests"]),
        )
        self.assertEqual(
            set(security["support_files"]),
            {"tests/release_readiness/batch2_security/conftest.py"},
        )

        source_mining = helper.COMPONENTS["source_mining_evidence_boundary"]
        self.assertEqual(
            {(pair["implementation"], pair["test"]) for pair in source_mining["candidate_pairs"]},
            {
                (
                    "tools/evidence_promotion_gate/adapters.py",
                    "tests/source_mining_integration/test_source_mining_evidence_boundary.py",
                ),
                (
                    "tools/evidence_promotion_gate/evaluator.py",
                    "tests/source_mining_integration/test_source_mining_evidence_boundary.py",
                ),
                (
                    "tools/public_repo_harvest/schema.py",
                    "tests/source_mining_integration/test_source_mining_evidence_boundary.py",
                ),
            },
        )

        measurement = helper.COMPONENTS["measurement_hypothesis_contract"]
        self.assertEqual(
            {pair["implementation"] for pair in measurement["candidate_pairs"]},
            {
                "shared/measurement_hypothesis/validate.py",
                "shared/measurement_hypothesis/schema.py",
                "shared/measurement_hypothesis/resolve.py",
                "shared/measurement_hypothesis/language.py",
                "shared/measurement_hypothesis/__main__.py",
                "tools/research_claim_gate/gate.py",
            },
        )
        self.assertEqual(
            {pair["test"] for pair in measurement["candidate_pairs"]},
            set(measurement["tests"]),
        )
        self.assertEqual(
            measurement["package_initializers"]["shared/measurement_hypothesis/__init__.py"],
            tuple(measurement["tests"]),
        )

        self.assertIn(
            {"implementation": "tools/surrogate_nulls/nulls.py", "test": "tests/surrogate_nulls/test_adversarial_contracts.py"},
            helper.COMPONENTS["surrogate_nulls"]["candidate_pairs"],
        )
        self.assertIn(
            {"implementation": "tools/surrogate_audit/metrics.py", "test": "tests/surrogate_audit/test_metrics_scale_invariance.py"},
            helper.COMPONENTS["surrogate_audit"]["candidate_pairs"],
        )
        self.assertIn(
            {"implementation": "neurotopology_sim/experimental/topology/winding.py", "test": "tests/experimental_audits/test_winding_charge_production_import.py"},
            helper.COMPONENTS["winding_charge_audit"]["candidate_pairs"],
        )
        self.assertIn(
            {"implementation": "tools/experimental_audits/winding_charge_round6/oracle.py", "test": "tests/experimental_audits/test_winding_charge_production_import.py"},
            helper.COMPONENTS["winding_charge_audit"]["candidate_pairs"],
        )
        finite_bridge = helper.COMPONENTS["finite_jitter_production_bridge"]
        bridge_test = "tests/test_finite_jitter_production_import.py"
        self.assertIn(
            {
                "implementation": "tools/audit_finite_jitter_triangulation.py",
                "test": bridge_test,
            },
            finite_bridge["candidate_pairs"],
        )
        self.assertNotIn(
            bridge_test,
            helper.COMPONENTS["planar_geometry"]["tests"],
        )
        self.assertEqual(
            helper.select_components({bridge_test}),
            ["finite_jitter_production_bridge"],
        )
        geometry_source = "neurotopology_sim/experimental/geometry/planar_triangulation.py"
        self.assertEqual(helper.select_components({geometry_source}), ["planar_geometry"])
        self.assertEqual(helper._unmapped_candidate_paths({bridge_test}), [])

        csd_adapter = helper.COMPONENTS["mne_csd_adapter"]
        csd_live_test = "tests/adapters/mne_csd/test_optional_mne_integration.py"
        for implementation in (
            "adapters/mne_csd/__init__.py",
            "adapters/mne_csd/constants.py",
            "adapters/mne_csd/errors.py",
            "adapters/mne_csd/preconditions.py",
            "adapters/mne_csd/provenance.py",
            "adapters/mne_csd/transform.py",
        ):
            self.assertIn(
                {"implementation": implementation, "test": csd_live_test},
                csd_adapter["candidate_pairs"],
            )
        audit = helper.COMPONENTS["mne_csd_reference_audit"]
        audit_live_test = "tests/optional_live_mne/test_mne_csd_live_parity.py"
        for implementation in (
            "tools/mne_csd_reference_audit/kkt.py",
            "tools/mne_csd_reference_audit/legendre.py",
            "tools/mne_csd_reference_audit/montages.py",
            "tools/mne_csd_reference_audit/pin.py",
        ):
            self.assertIn(
                {"implementation": implementation, "test": audit_live_test},
                audit["candidate_pairs"],
            )

        benchmark = helper.COMPONENTS["batch2_pipeline_benchmark"]
        self.assertIn(
            {
                "implementation": "tools/benchmarks/batch2_pipeline/reporting.py",
                "test": "tests/benchmarks/batch2_pipeline/test_cli_and_reporting.py",
            },
            benchmark["candidate_pairs"],
        )
        self.assertNotIn(
            {
                "implementation": "tools/benchmarks/batch2_pipeline/reporting.py",
                "test": "tests/benchmarks/batch2_pipeline/test_failure_modes.py",
            },
            benchmark["candidate_pairs"],
        )
        makefile = "tools/benchmarks/batch2_pipeline/Makefile"
        makefile_test = "tests/ci/test_round6_benchmark_makefile.py"
        # A workflow-owned test change must not select the candidate component
        # whose implementation is not part of this workflow PR.
        self.assertEqual(helper.select_components({makefile_test}), [])
        self.assertEqual(helper._unmapped_candidate_paths({makefile_test}), [])
        self.assertIn(
            {"implementation": makefile, "test": makefile_test},
            helper.COMPONENTS["batch2_pipeline_benchmark"]["candidate_pairs"],
        )
        self.assertEqual(helper._unmapped_candidate_paths({makefile}), [])
        self.assertEqual(
            helper.select_components({makefile}),
            ["batch2_pipeline_benchmark"],
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, makefile, "generate:\n\ttrue\n")
            _write(root, makefile_test, "def test_makefile_contract(): pass\n")
            inspection = helper.inspect_component(
                "batch2_pipeline_benchmark", root, {makefile}
            )
        self.assertEqual(inspection["status"], "READY_TO_RUN")
        self.assertEqual(inspection["tests_to_run"], [makefile_test])
        self.assertEqual(
            helper.select_components({"tools/benchmarks/batch2_pipeline/reporting.py"}),
            ["batch2_pipeline_benchmark"],
        )
        docker_tests = {
            pair["test"] for pair in helper.COMPONENTS["docker_context_policy"]["candidate_pairs"]
        }
        engine_test = "tests/docker_context/test_docker_engine_build_context.py"
        self.assertEqual(docker_tests, {
            "tests/docker_context/test_build_context_policy.py",
            engine_test,
        })
        self.assertEqual(
            helper.COMPONENTS["docker_context_policy"]["external_test_paths"],
            {engine_test: "docker-context-engine"},
        )
        self.assertEqual(helper.select_components({engine_test}), ["docker_context_policy"])
        self.assertEqual(helper._unmapped_candidate_paths({engine_test}), [])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, ".dockerignore", "# synthetic policy\n")
            _write(root, "tests/docker_context/test_build_context_policy.py", "def test_static(): pass\n")
            inspection = helper.inspect_component(
                "docker_context_policy", root, {engine_test}
            )
        self.assertEqual(
            inspection["tests_to_run"],
            ["tests/docker_context/test_build_context_policy.py"],
        )
        self.assertEqual(inspection["delegated_tests"], [engine_test])
        mne_test = "tests/adapters/mne_signal_blocks/test_mne_signal_blocks.py"
        mne_inspection = helper.COMPONENTS["mne_signal_blocks"]
        self.assertEqual(mne_inspection["test_markers"][mne_test], "not requires_mne")
        self.assertEqual(
            mne_inspection["external_test_paths"],
            {mne_test: "optional-eeg-suite"},
        )
        csd_adapter_test = "tests/adapters/mne_csd/test_optional_mne_integration.py"
        csd_adapter = helper.COMPONENTS["mne_csd_adapter"]
        self.assertEqual(
            csd_adapter["external_test_paths"],
            {csd_adapter_test: "optional-eeg-suite"},
        )
        self.assertEqual(helper.select_components({csd_adapter_test}), ["mne_csd_adapter"])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for pair in csd_adapter["candidate_pairs"]:
                _write(root, pair["implementation"], "# adapter implementation fixture\n")
            for test_file in csd_adapter["tests"]:
                _write(root, test_file, "def test_fixture(): pass\n")
            for support_file in csd_adapter["support_files"]:
                _write(root, support_file, "# fixture support\n")
            inspection = helper.inspect_component("mne_csd_adapter", root, {csd_adapter_test})
        self.assertEqual(inspection["status"], "READY_TO_RUN")
        self.assertNotIn(csd_adapter_test, inspection["tests_to_run"])
        self.assertIn(csd_adapter_test, inspection["delegated_tests"])
        csd_live_test = "tests/optional_live_mne/test_mne_csd_live_parity.py"
        self.assertEqual(
            helper.select_components({csd_live_test}),
            ["mne_csd_reference_audit"],
        )
        self.assertEqual(
            helper.COMPONENTS["mne_csd_reference_audit"]["external_test_paths"][csd_live_test],
            "optional-eeg-suite",
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            audit_spec = helper.COMPONENTS["mne_csd_reference_audit"]
            pure_test = "tests/mne_csd_reference_audit/test_kkt_operator.py"
            for pair in audit_spec["candidate_pairs"]:
                _write(root, pair["implementation"], "# deterministic audit implementation fixture\n")
            for test_file in audit_spec["tests"]:
                _write(root, test_file, "def test_fixture(): assert True\n")
            for support_file in audit_spec["support_files"]:
                _write(root, support_file, "# deterministic test support\n")
            for support_test in audit_spec["support_files"][
                "tests/mne_csd_reference_audit/conftest.py"
            ]:
                _write(root, support_test, "def test_support(): assert True\n")
            for support_file, mapped_tests in audit_spec["support_files"].items():
                if support_file != "tests/mne_csd_reference_audit/conftest.py":
                    _write(root, support_file, "{}\n")
                    for support_test in mapped_tests:
                        _write(root, support_test, "def test_support(): assert True\n")
            _write(root, csd_live_test, "def test_live(): pass\n")
            inspection = helper.inspect_component(
                "mne_csd_reference_audit", root, {csd_live_test}
            )
        self.assertEqual(inspection["status"], "READY_TO_RUN")
        self.assertEqual(inspection["tests_to_run"], [pure_test])
        self.assertEqual(inspection["delegated_tests"], [csd_live_test])
        self.assertEqual(
            inspection["implementations"],
            [
                "tools/mne_csd_reference_audit/kkt.py",
                "tools/mne_csd_reference_audit/legendre.py",
                "tools/mne_csd_reference_audit/montages.py",
                "tools/mne_csd_reference_audit/pin.py",
            ],
        )
        preprocessing_init = "neurotopology_sim/experimental/preprocessing/__init__.py"
        self.assertEqual(helper.select_components({preprocessing_init}), ["spherical_csd"])
        self.assertNotIn("mne_csd_reference_audit", helper.select_components({preprocessing_init}))
        self.assertEqual(
            helper.select_components({"tests/tools/moabb_protocol_conformance/test_manifest_and_validation.py"}),
            ["moabb_protocol_conformance"],
        )
        self.assertEqual(
            helper.COMPONENTS["dandi_nwb_bounded"]["implementation_roots"],
            ("data/dandi_nwb_ingest.py", "tools/stream_process_dandi000458.py"),
        )
        self.assertNotIn(
            "tools/stream_pitnn_cohort_ds005620.py",
            helper.COMPONENTS["dandi_nwb_bounded"]["implementation_roots"],
        )

    def test_replication_artifact_contracts_are_mapped_without_report_only_fanout(self):
        helper = _helper()
        paths = {
            "reports/batch3/grok_chat_b/dataset_candidates.json",
            "tests/research/batch3/test_replication_dataset_feasibility.py",
            "reports/batch3/grok_chat_b/dataset_candidates_metadata_audit.json",
            "tests/research/batch3/test_dataset_metadata_audit.py",
        }
        self.assertEqual(
            helper.select_components(paths),
            ["batch3_dataset_feasibility_artifact", "batch3_metadata_audit_artifact"],
        )
        self.assertEqual(helper._unmapped_candidate_paths(paths), [])
        for component, support_path in (
            (
                "batch3_dataset_feasibility_artifact",
                "docs/research/batch3/replication_dataset_feasibility.md",
            ),
            (
                "batch3_metadata_audit_artifact",
                "docs/research/batch3/grok_chat_b_dataset_feasibility.md",
            ),
            ("whitening_audit", "tools/whitening_audit/__init__.py"),
            ("whitening_audit", "tests/whitening_audit/__init__.py"),
        ):
            spec = helper.COMPONENTS[component]
            self.assertIn(support_path, spec["support_files"])
            self.assertEqual(helper.select_components({support_path}), [component])
            self.assertEqual(helper._unmapped_candidate_paths({support_path}), [])
        sibling = "tests/research/batch3/test_claim_matrix_supplement.py"
        self.assertEqual(helper.select_components({sibling}), [])
        self.assertEqual(helper._unmapped_candidate_paths({sibling}), [sibling])

    def test_artifact_contract_pairs_require_the_real_artifact_and_exact_test(self):
        helper = _helper()
        cases = (
            (
                "oss_compatibility_inventory_artifact",
                "docs/oss_compat/compatibility_inventory_20261017.json",
                "tests/oss_compat/test_compatibility_inventory.py",
                None,
            ),
            (
                "batch3_dataset_feasibility_artifact",
                "reports/batch3/grok_chat_b/dataset_candidates.json",
                "tests/research/batch3/test_replication_dataset_feasibility.py",
                "docs/research/batch3/replication_dataset_feasibility.md",
            ),
            (
                "batch3_metadata_audit_artifact",
                "reports/batch3/grok_chat_b/dataset_candidates_metadata_audit.json",
                "tests/research/batch3/test_dataset_metadata_audit.py",
                "docs/research/batch3/grok_chat_b_dataset_feasibility.md",
            ),
        )
        for component, artifact, test_path, support_path in cases:
            with self.subTest(component=component):
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    _write(root, artifact, "{}\n")
                    _write(root, test_path, "def test_artifact_contract(): pass\n")
                    changed = {artifact, test_path}
                    if support_path:
                        _write(root, support_path, "# documented artifact contract\n")
                        changed.add(support_path)
                    ready = helper.inspect_component(component, root, changed)
                    self.assertEqual(ready["status"], "READY_TO_RUN")
                    self.assertEqual(ready["tests_to_run"], [test_path])

                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    _write(root, artifact, "{}\n")
                    changed = {artifact}
                    if support_path:
                        _write(root, support_path, "# documented artifact contract\n")
                        changed.add(support_path)
                    blocked = helper.inspect_component(component, root, changed)
                    self.assertEqual(blocked["status"], "BLOCKED")
                    self.assertEqual(blocked["missing_required_tests"], [test_path])

    def test_workflow_benchmark_contract_runs_in_core_without_self_selecting(self):
        helper = _helper()
        test_path = "tests/ci/test_round6_benchmark_makefile.py"
        self.assertEqual(helper.select_components({test_path}), [])
        self.assertEqual(helper._unmapped_candidate_paths({test_path}), [])

        required_checks = (ROOT / ".github/workflows/required-checks.yml").read_text(
            encoding="utf-8"
        )
        self.assertRegex(
            required_checks,
            r"(?m)^\s+tests/ci/test_round6_benchmark_makefile\.py\s*$",
        )

    def test_docker_engine_test_change_runs_static_policy_and_is_reported_as_delegated(self):
        helper = _helper()
        engine_test = "tests/docker_context/test_docker_engine_build_context.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _repo(root, with_candidate=False)
            _write(root, ".dockerignore", "# synthetic policy\n")
            _write(root, "tests/docker_context/test_build_context_policy.py", "def test_policy(): pass\n")
            _write(root, engine_test, "def test_docker_engine_fixture(): pass\n")
            base = _commit(root, "docker candidate fixtures")
            _write(root, engine_test, "def test_docker_engine_fixture(): assert True\n")
            head = _commit(root, "docker engine test-only change")
            report_path = root / "outputs/report.json"
            with patch.object(
                helper.subprocess, "run", side_effect=lambda command, **kwargs: _fake_runner(command, **kwargs)
            ):
                result = helper.run(
                    root, base, head, report_path,
                    tested_checkout_sha=head, workflow_sha=base,
                    event_name="pull_request", require_checkout_match=True,
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(result, 0)
        self.assertEqual(report["delegated_test_owners"], {engine_test: "docker-context-engine"})
        component = report["components"][0]
        self.assertEqual(component["delegated_tests"], [engine_test])
        self.assertEqual(
            [item["test_file"] for item in component["executions"]],
            ["tests/docker_context/test_build_context_policy.py"],
        )
        # The selector's research artifact contracts are narrow; unrelated
        # sibling reports do not inherit those mappings.
        self.assertEqual(
            helper.select_components({"docs/oss_compat/compatibility_inventory_20261017.json"}),
            ["oss_compatibility_inventory_artifact"],
        )
        self.assertEqual(
            helper.select_components({"docs/research/batch3/replication_dataset_feasibility.md"}),
            ["batch3_dataset_feasibility_artifact"],
        )
        self.assertEqual(
            helper.select_components({"docs/research/batch3/grok_chat_b_dataset_feasibility.md"}),
            ["batch3_metadata_audit_artifact"],
        )
        self.assertEqual(
            helper.select_components({"tests/research/batch3/test_claim_matrix_supplement.py"}),
            [],
        )
        source_mining_path = (
            "tests/source_mining_integration/test_source_mining_evidence_boundary.py"
        )
        self.assertEqual(
            helper.select_components({source_mining_path}),
            ["source_mining_evidence_boundary"],
        )
        self.assertEqual(helper._unmapped_candidate_paths({source_mining_path}), [])

        # The BIDS audit is now explicitly mapped despite its historical guard
        # root; registered mappings take precedence over the fail-closed list.
        bids_path = "tests/bids_inventory_audit/test_privacy_boundary.py"
        self.assertEqual(helper.select_components({bids_path}), ["bids_inventory_audit"])
        self.assertEqual(helper._unmapped_candidate_paths({bids_path}), [])
        self.assertIn(
            "tests/experimental/planar_mesh_test_helpers.py",
            helper.COMPONENTS["planar_geometry"]["support_files"],
        )
        self.assertIn(
            "tests/experimental/fixtures/spherical_csd_mne_1_13_2_reference.json",
            helper.COMPONENTS["spherical_csd"]["support_files"],
        )
        for fixture in (
            "tests/neurotopology_sim/experimental/preprocessing/fixtures/tetrahedron_csd_matrix_mne_1_13_2.json",
            "tests/neurotopology_sim/experimental/preprocessing/fixtures/tetrahedron_csd_matrix_mne_1_13_2.npy",
        ):
            self.assertEqual(helper.select_components({fixture}), ["spherical_csd"])
            self.assertEqual(
                helper.COMPONENTS["spherical_csd"]["support_files"][fixture],
                ("tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py",),
            )
            self.assertEqual(helper._unmapped_candidate_paths({fixture}), [])
        falsification_matrix = "configs/scientific_falsification/batch3_falsification_matrix.yaml"
        self.assertEqual(
            helper._unmapped_candidate_paths({falsification_matrix}),
            [],
        )
        self.assertEqual(
            helper.select_components({falsification_matrix}),
            ["batch3_falsification_matrix_artifact"],
        )
        self.assertEqual(
            helper._unmapped_candidate_paths({"configs/research/batch3_source_registry.yaml"}),
            [],
        )
        claim_matrix = "reports/batch3/grok_chat_a/claim_matrix.json"
        self.assertEqual(
            helper.select_components({claim_matrix}),
            ["batch3_claim_matrix_artifact"],
        )
        self.assertEqual(helper._unmapped_candidate_paths({claim_matrix}), [])
        # A newly registered candidate package initializer selects only its
        # mapped test suite; unrelated unregistered initializers still block.
        nuisance_initializer = "tests/nuisance_scenarios/__init__.py"
        self.assertEqual(helper._unmapped_candidate_paths({nuisance_initializer}), [])
        self.assertEqual(helper.select_components({nuisance_initializer}), ["nuisance_scenarios"])
        self.assertNotIn("tests/surrogate_nulls/__init__.py", helper._unmapped_candidate_paths({"tests/surrogate_nulls/__init__.py"}))

    def test_package_initializers_require_exact_test_support_mappings(self):
        helper = _helper()
        for component, initializer_paths in helper.PACKAGE_INITIALIZER_SUPPORT_PATHS.items():
            spec = helper.COMPONENTS[component]
            for initializer in initializer_paths:
                with self.subTest(component=component, initializer=initializer):
                    expected_tests = spec["package_initializers"][initializer]
                    self.assertTrue(expected_tests, component)
                    self.assertTrue(set(expected_tests).issubset(set(spec["tests"])))
                    self.assertTrue(
                        set(expected_tests).issubset(
                            {pair["test"] for pair in spec["candidate_pairs"]}
                        )
                    )
                    self.assertEqual(spec["package_initializers"][initializer], expected_tests)
                    self.assertIn(component, helper.select_components({initializer}))
                    self.assertEqual(helper._changed_candidate_paths(spec, {initializer}), [])
                    self.assertEqual(helper._unmapped_candidate_paths({initializer}), [])
                    with tempfile.TemporaryDirectory() as td:
                        root = Path(td)
                        init_path = root / initializer
                        init_path.parent.mkdir(parents=True, exist_ok=True)
                        init_path.write_text("# package initializer fixture\n", encoding="utf-8")
                        for pair in spec["candidate_pairs"]:
                            for relative in (pair["implementation"], pair["test"]):
                                candidate = root / relative
                                candidate.parent.mkdir(parents=True, exist_ok=True)
                                candidate.write_text("# deterministic candidate fixture\n", encoding="utf-8")
                        for support_path in spec.get("support_files", {}):
                            support_file = root / support_path
                            support_file.parent.mkdir(parents=True, exist_ok=True)
                            support_file.write_text("# deterministic support fixture\n", encoding="utf-8")
                        result = helper.inspect_component(component, root, {initializer})
                    self.assertEqual(result["status"], "READY_TO_RUN", result["blockers"])
                    self.assertEqual(result["tests_to_run"], list(expected_tests))
                    self.assertEqual(result["selected_package_initializers"], [initializer])

        for unregistered_initializer in (
            "tools/surrogate_nulls/unregistered/__init__.py",
            "tests/surrogate_nulls/unregistered/__init__.py",
        ):
            with self.subTest(initializer=unregistered_initializer):
                self.assertIn(
                    unregistered_initializer,
                    helper._unmapped_candidate_paths({unregistered_initializer}),
                )

        geometry_pair = helper.COMPONENTS["planar_geometry"]["candidate_pairs"][0]
        self.assertEqual(
            helper.select_components({"tests/experimental/__init__.py"}),
            ["planar_geometry"],
        )
        self.assertEqual(
            helper.select_components({
                "neurotopology_sim/__init__.py",
                geometry_pair["implementation"],
                geometry_pair["test"],
            }),
            ["planar_geometry", "phase_winding", "synthetic_roc"],
        )
        roc_pair = helper.COMPONENTS["synthetic_roc"]["candidate_pairs"][0]
        self.assertEqual(
            helper.select_components({
                "neurotopology_sim/__init__.py",
                roc_pair["implementation"],
                roc_pair["test"],
            }),
            ["phase_winding", "synthetic_roc"],
        )
        dmd_pair = helper.COMPONENTS["dmd_crouzeix"]["candidate_pairs"][0]
        self.assertEqual(
            helper.select_components({
                "tests/experimental/__init__.py",
                dmd_pair["implementation"],
                dmd_pair["test"],
            }),
            ["planar_geometry", "dmd_crouzeix"],
        )

    def test_mixed_direct_candidate_and_initializer_change_keeps_all_owners(self):
        helper = _helper()
        initializer = "neurotopology_sim/__init__.py"
        selected = helper.select_components({initializer, "tools/surrogate_nulls/nulls.py"})
        self.assertEqual(selected, ["phase_winding", "surrogate_nulls", "synthetic_roc"])

    def test_shared_initializer_owner_with_absent_candidate_implementation_blocks(self):
        helper = _helper()
        component = "synthetic_roc"
        initializer = "neurotopology_sim/__init__.py"
        spec = helper.COMPONENTS[component]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_path = root / initializer
            init_path.parent.mkdir(parents=True, exist_ok=True)
            init_path.write_text("# shared package initializer fixture\n", encoding="utf-8")
            for test_path in spec["tests"]:
                test_file = root / test_path
                test_file.parent.mkdir(parents=True, exist_ok=True)
                test_file.write_text("# paired test fixture\n", encoding="utf-8")

            result = helper.inspect_component(component, root, {initializer})

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(
            result["missing_implementations"],
            ["neurotopology_sim/experimental/benchmarks/synthetic_forward_roc.py"],
        )
        self.assertIn("required candidate implementation is absent", result["blockers"])
        self.assertTrue(result["tests_to_run"])

    def test_candidate_support_only_changes_select_their_declared_tests(self):
        helper = _helper()
        cases = (
            (
                "planar_geometry",
                "tests/experimental/planar_mesh_test_helpers.py",
                "tests/experimental/test_planar_triangulation.py",
            ),
            (
                "spherical_csd",
                "tests/experimental/fixtures/spherical_csd_mne_1_13_2_reference.json",
                "tests/experimental/test_spherical_csd_parity.py",
            ),
            (
                "spherical_csd",
                "tests/neurotopology_sim/experimental/preprocessing/fixtures/tetrahedron_csd_matrix_mne_1_13_2.json",
                "tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py",
            ),
            (
                "spherical_csd",
                "tests/neurotopology_sim/experimental/preprocessing/fixtures/tetrahedron_csd_matrix_mne_1_13_2.npy",
                "tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py",
            ),
        )
        for component, support_path, test_file in cases:
            with self.subTest(component=component):
                spec = helper.COMPONENTS[component]
                self.assertEqual(helper.select_components({support_path}), [component])
                self.assertIn(test_file, spec["support_files"][support_path])
                self.assertIn(test_file, spec["tests"])

    def test_fusion_validation_mapping_requires_exact_companion_tests(self):
        helper = _helper()
        component = "fusion_validation_null_models"
        implementation = "dual_engine/fusion_validation.py"
        test_paths = (
            "tests/test_fusion_null_models.py",
            "tests/test_fusion_validation.py",
        )
        spec = helper.COMPONENTS[component]
        self.assertEqual(helper.COMPONENT_OWNER_PRS[component], (374,))
        self.assertEqual(
            spec["candidate_pairs"],
            tuple(
                {"implementation": implementation, "test": test_path}
                for test_path in test_paths
            ),
        )
        for test_path in test_paths:
            self.assertEqual(helper.select_components({test_path}), [component])
            self.assertEqual(helper._unmapped_candidate_paths({test_path}), [])

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, implementation, "# candidate implementation fixture\n")
            for test_path in test_paths:
                _write(root, test_path, "def test_candidate_contract(): pass\n")
            inspection = helper.inspect_component(component, root, {implementation})
        self.assertEqual(inspection["status"], "READY_TO_RUN")
        self.assertEqual(inspection["tests_to_run"], list(test_paths))

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, implementation, "# candidate implementation fixture\n")
            _write(root, test_paths[0], "def test_candidate_contract(): pass\n")
            inspection = helper.inspect_component(component, root, {implementation})
        self.assertEqual(inspection["status"], "BLOCKED")
        self.assertEqual(inspection["missing_required_tests"], [test_paths[1]])

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, implementation, "# candidate implementation fixture\n")
            _write(root, test_paths[1], "def test_candidate_contract(): pass\n")
            inspection = helper.inspect_component(component, root, {test_paths[1]})
        self.assertEqual(inspection["status"], "READY_TO_RUN")
        self.assertEqual(inspection["tests_to_run"], [test_paths[1]])

    def test_unmapped_open_pr_candidate_gaps_are_fail_closed(self):
        helper = _helper()
        current_open_pr_gaps = (
            (400, "tests/dmd_ep2_oracle/test_unregistered_extra.py"),
        )
        for pr_number, path in current_open_pr_gaps:
            with self.subTest(pr=pr_number, path=path):
                self.assertIn(path, helper._unmapped_candidate_paths({path}))
                self.assertEqual(helper.select_components({path}), [])

    def test_report_only_candidate_tests_remain_unmapped(self):
        helper = _helper()
        report_only_paths = (
            "tests/research/batch3/test_claim_matrix_supplement.py",  # unregistered sibling
        )
        for path in report_only_paths:
            with self.subTest(path=path):
                self.assertIn(path, helper._unmapped_candidate_paths({path}))
                self.assertEqual(helper.select_components({path}), [])

    def test_research_plan_line_endings_regression_is_a_registered_pair(self):
        helper = _helper()
        implementation = "tools/research_plan_quality_eval/manifest.py"
        test_path = "tests/research_plan_quality_eval/test_line_endings.py"
        spec = helper.COMPONENTS["research_plan_quality_eval"]
        self.assertIn(test_path, spec["tests"])
        self.assertIn(
            {"implementation": implementation, "test": test_path},
            spec["candidate_pairs"],
        )
        self.assertEqual(helper.select_components({implementation, test_path}), ["research_plan_quality_eval"])
        self.assertEqual(helper._unmapped_candidate_paths({implementation, test_path}), [])

    def test_registered_uppercase_support_path_is_not_a_case_mismatch(self):
        helper = _helper()
        readme = "tests/data_access/bids_adapter/fixtures/invalid_bids/README"
        spec = helper.COMPONENTS["bids_adapter"]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for path in (
                *(pair["implementation"] for pair in spec["candidate_pairs"]),
                *spec["tests"],
                *spec["support_files"],
            ):
                _write(root, path, "fixture placeholder\n")
            result = helper.inspect_component("bids_adapter", root, {readme})
        self.assertEqual(result["status"], "READY_TO_RUN")
        self.assertEqual(result["unmapped_candidate_paths"], [])
        self.assertEqual(
            result["tests_to_run"],
            ["tests/data_access/bids_adapter/test_bids_adapter.py"],
        )

    def test_live_batch_candidate_pairs_have_explicit_owners_and_no_fanout(self):
        helper = _helper()
        expected_pairs = {
            "bids_adapter": (
                369,
                {
                    ("data/bids_ingest.py", "tests/data_access/bids_adapter/test_bids_adapter.py"),
                    ("data/openneuro_loader.py", "tests/data_access/bids_adapter/test_bids_adapter.py"),
                },
            ),
            "level_t_missingness": (
                373,
                {
                    ("sciencer_d/btc_icft/level_t/base_real_topology.py", "tests/test_base_real_topology_missingness.py"),
                    ("sciencer_d/btc_icft/level_t/base_real_topology.py", "tests/test_cohort_missingness.py"),
                },
            ),
            "batch3_source_registry": (
                375,
                {
                    ("configs/research/batch3_source_registry.yaml", "tests/research/test_batch3_source_registry.py"),
                },
            ),
            "oss_adoption_gates": (
                386,
                {
                    ("oss_opportunities/opportunity_batch.py", "tests/test_oss_adoption_gates.py"),
                    ("oss_opportunities/repository_candidate.py", "tests/test_oss_adoption_gates.py"),
                    ("oss_opportunities/repository_candidate.py", "tests/test_oss_repository_candidate.py"),
                    ("oss_opportunities/scoring.py", "tests/test_oss_adoption_gates.py"),
                    ("oss_opportunities/scoring.py", "tests/test_oss_opportunity_scoring.py"),
                    ("oss_opportunities/validation.py", "tests/test_oss_adoption_gates.py"),
                    ("oss_opportunities/validation.py", "tests/test_oss_opportunity_scoring.py"),
                    ("oss_opportunities/validation.py", "tests/test_oss_integration_opportunity.py"),
                    ("oss_opportunities/license_review.py", "tests/test_oss_license_review.py"),
                },
            ),
            "oss_compatibility_inventory_artifact": (
                406,
                {
                    (
                        "docs/oss_compat/compatibility_inventory_20261017.json",
                        "tests/oss_compat/test_compatibility_inventory.py",
                    ),
                },
            ),
            "batch3_dataset_feasibility_artifact": (
                394,
                {
                    (
                        "reports/batch3/grok_chat_b/dataset_candidates.json",
                        "tests/research/batch3/test_replication_dataset_feasibility.py",
                    ),
                },
            ),
            "batch3_metadata_audit_artifact": (
                411,
                {
                    (
                        "reports/batch3/grok_chat_b/dataset_candidates_metadata_audit.json",
                        "tests/research/batch3/test_dataset_metadata_audit.py",
                    ),
                },
            ),
            "whitening_audit": (
                407,
                {
                    ("scripts/audit_round6_whitening.py", "tests/whitening_audit/test_whitening_audit.py"),
                    ("tools/whitening_audit/audit_reporter.py", "tests/whitening_audit/test_whitening_audit.py"),
                    ("tools/whitening_audit/leakage_detector.py", "tests/whitening_audit/test_whitening_audit.py"),
                    ("tools/whitening_audit/matrix_ops.py", "tests/whitening_audit/test_whitening_audit.py"),
                    ("tools/whitening_audit/synthetic_data.py", "tests/whitening_audit/test_whitening_audit.py"),
                    ("tools/whitening_audit/types.py", "tests/whitening_audit/test_whitening_audit.py"),
                    ("tools/whitening_audit/whitening_verifier.py", "tests/whitening_audit/test_whitening_audit.py"),
                },
            ),
            "research_plan_quality_eval": (
                383,
                {
                    ("tools/research_plan_quality_eval/harness.py", "tests/research_plan_quality_eval/test_manifest.py"),
                    ("tools/research_plan_quality_eval/isolation.py", "tests/research_plan_quality_eval/test_isolation.py"),
                    ("tools/research_plan_quality_eval/records.py", "tests/research_plan_quality_eval/test_records.py"),
                    ("tools/research_plan_quality_eval/splits.py", "tests/research_plan_quality_eval/test_splits.py"),
                    ("tools/research_plan_quality_eval/errors.py", "tests/research_plan_quality_eval/test_line_endings.py"),
                    ("tools/research_plan_quality_eval/manifest.py", "tests/research_plan_quality_eval/test_line_endings.py"),
                    ("tools/research_plan_quality_eval/records.py", "tests/research_plan_quality_eval/test_line_endings.py"),
                },
            ),
            "forward_model_contract": (
                388,
                {
                    ("dual_engine/forward_model_contract.py", "tests/forward_model_contract/test_forward_model_contract.py"),
                },
            ),
            "batch3_offline_integration": (
                381,
                {
                    (implementation, "tests/tools/batch3_offline_integration/test_offline_integration.py")
                    for implementation in (
                        "scripts/run_batch3_offline_integration.py",
                        "tools/batch3_offline_integration/__init__.py",
                        "tools/batch3_offline_integration/__main__.py",
                        "tools/batch3_offline_integration/allowlist.py",
                        "tools/batch3_offline_integration/fixture_producers.py",
                        "tools/batch3_offline_integration/guards.py",
                        "tools/batch3_offline_integration/runner.py",
                        "tools/batch3_offline_integration/schema.py",
                        "tools/batch3_offline_integration/serialization.py",
                        "tools/batch3_offline_integration/stages.py",
                    )
                },
            ),
            "batch3_claim_matrix_artifact": (
                393,
                {
                    (
                        "reports/batch3/grok_chat_a/claim_matrix.json",
                        "tests/research/batch3/test_claim_matrix.py",
                    ),
                },
            ),
            "batch3_falsification_matrix_artifact": (
                376,
                {
                    (
                        "configs/scientific_falsification/batch3_falsification_matrix.yaml",
                        "tests/scientific_falsification/test_batch3_falsification_matrix.py",
                    ),
                },
            ),
            "nuisance_scenarios": (
                408,
                {
                    ("sim/nuisance_scenarios/factory.py", "tests/nuisance_scenarios/test_factory_and_grid.py"),
                    ("sim/nuisance_scenarios/snr_mixer.py", "tests/nuisance_scenarios/test_target_snr.py"),
                },
            ),
        }
        for component, (owner_pr, expected) in expected_pairs.items():
            with self.subTest(component=component):
                spec = helper.COMPONENTS[component]
                pairs = {
                    (pair["implementation"], pair["test"])
                    for pair in spec["candidate_pairs"]
                }
                self.assertTrue(expected.issubset(pairs))
                self.assertIn(owner_pr, helper.COMPONENT_OWNER_PRS[component])
                for implementation, test_path in expected:
                    self.assertEqual(helper.select_components({implementation}), [component])
                    self.assertEqual(helper.select_components({test_path}), [component])
                    self.assertEqual(helper._unmapped_candidate_paths({implementation}), [])
                    self.assertEqual(helper._unmapped_candidate_paths({test_path}), [])

        self.assertEqual(
            helper.COMPONENT_OWNER_PRS["batch3_falsification_matrix_artifact"],
            (376, 444),
        )
        self.assertEqual(
            helper.COMPONENT_OWNER_PRS["batch2_pipeline_benchmark"],
            (371, 445),
        )
        self.assertEqual(
            helper.COMPONENT_OWNER_PRS["measurement_hypothesis_contract"],
            (384, 357),
        )
        falsification_followup = {
            "docs/scientific_falsification/batch3_adversarial_review.md",
            "tests/scientific_falsification/test_batch3_falsification_matrix.py",
        }
        self.assertEqual(
            helper.select_components(falsification_followup),
            ["batch3_falsification_matrix_artifact"],
        )
        self.assertEqual(helper._unmapped_candidate_paths(falsification_followup), [])
        benchmark_followup = {
            "scripts/benchmark_batch2_pipeline.py",
            "tests/benchmarks/batch2_pipeline/test_cli_and_reporting.py",
            "tests/benchmarks/batch2_pipeline/test_harness_and_targets.py",
            "tests/benchmarks/batch2_pipeline/test_isolation_and_network.py",
            "tools/benchmarks/batch2_pipeline/budgets.py",
            "tools/benchmarks/batch2_pipeline/harness.py",
            "tools/benchmarks/batch2_pipeline/validator.py",
        }
        self.assertEqual(
            helper.select_components(benchmark_followup),
            ["batch2_pipeline_benchmark"],
        )
        self.assertEqual(helper._unmapped_candidate_paths(benchmark_followup), [])

        exact_candidate_diffs = {
            "bids_adapter": {
                "data/bids_ingest.py",
                "data/openneuro_loader.py",
                "tests/data_access/bids_adapter/__init__.py",
                "tests/data_access/bids_adapter/test_bids_adapter.py",
                "tests/data_access/bids_adapter/fixtures/condition_manifest_ambiguous.json",
                "tests/data_access/bids_adapter/fixtures/condition_manifest_ok.json",
                "tests/data_access/bids_adapter/fixtures/invalid_bids/README",
                "tests/data_access/bids_adapter/fixtures/missing_entities/dataset_description.json",
                "tests/data_access/bids_adapter/fixtures/missing_entities/sub-01/eeg/sub-01_task-rest_eeg.edf",
                "tests/data_access/bids_adapter/fixtures/valid_bids/dataset_description.json",
                "tests/data_access/bids_adapter/fixtures/valid_bids/participants.tsv",
                "tests/data_access/bids_adapter/fixtures/valid_bids/sub-01/eeg/sub-01_task-rest_run-01_channels.tsv",
                "tests/data_access/bids_adapter/fixtures/valid_bids/sub-01/eeg/sub-01_task-rest_run-01_eeg.edf",
                "tests/data_access/bids_adapter/fixtures/valid_bids/sub-01/eeg/sub-01_task-rest_run-01_eeg.json",
            },
            "level_t_missingness": {
                "sciencer_d/btc_icft/level_t/base_real_topology.py",
                "tests/test_base_real_topology_missingness.py",
                "tests/test_cohort_missingness.py",
            },
            "batch3_source_registry": {
                "configs/research/batch3_source_registry.yaml",
                "tests/research/test_batch3_source_registry.py",
            },
            "research_plan_quality_eval": {
                "tests/research_plan_quality_eval/__init__.py",
                "tests/research_plan_quality_eval/conftest.py",
                "tests/research_plan_quality_eval/test_cli.py",
                "tests/research_plan_quality_eval/test_held_out_boundary.py",
                "tests/research_plan_quality_eval/test_isolation.py",
                "tests/research_plan_quality_eval/test_leakage.py",
                "tests/research_plan_quality_eval/test_line_endings.py",
                "tests/research_plan_quality_eval/test_manifest.py",
                "tests/research_plan_quality_eval/test_records.py",
                "tests/research_plan_quality_eval/test_report.py",
                "tests/research_plan_quality_eval/test_splits.py",
                "tools/research_plan_quality_eval/__init__.py",
                "tools/research_plan_quality_eval/__main__.py",
                "tools/research_plan_quality_eval/errors.py",
                "tools/research_plan_quality_eval/harness.py",
                "tools/research_plan_quality_eval/isolation.py",
                "tools/research_plan_quality_eval/leakage.py",
                "tools/research_plan_quality_eval/manifest.py",
                "tools/research_plan_quality_eval/records.py",
                "tools/research_plan_quality_eval/splits.py",
                "tools/research_plan_quality_eval/fixtures/v1/labels.json",
                "tools/research_plan_quality_eval/fixtures/v1/manifest.json",
                *(
                    f"tools/research_plan_quality_eval/fixtures/v1/plans/P{index:02}.json"
                    for index in range(1, 11)
                ),
            },
            "forward_model_contract": {
                "dual_engine/forward_model_contract.py",
                "tests/forward_model_contract/__init__.py",
                "tests/forward_model_contract/test_forward_model_contract.py",
            },
            "nuisance_scenarios": {
                "sim/nuisance_scenarios/__init__.py",
                "sim/nuisance_scenarios/colored_noise.py",
                "sim/nuisance_scenarios/config.py",
                "sim/nuisance_scenarios/factory.py",
                "sim/nuisance_scenarios/jitter.py",
                "sim/nuisance_scenarios/models.py",
                "sim/nuisance_scenarios/snr_mixer.py",
                "tests/nuisance_scenarios/__init__.py",
                "tests/nuisance_scenarios/test_colored_noise.py",
                "tests/nuisance_scenarios/test_config_serialization.py",
                "tests/nuisance_scenarios/test_coordinate_jitter.py",
                "tests/nuisance_scenarios/test_factory_and_grid.py",
                "tests/nuisance_scenarios/test_fail_closed_and_labels.py",
                "tests/nuisance_scenarios/test_seed_reproducibility.py",
                "tests/nuisance_scenarios/test_target_snr.py",
            },
            "batch3_offline_integration": {
                "docs/tools/batch3_offline_integration.md",
                "scripts/run_batch3_offline_integration.py",
                "tests/tools/batch3_offline_integration/__init__.py",
                "tests/tools/batch3_offline_integration/test_offline_integration.py",
                "tools/batch3_offline_integration/__init__.py",
                "tools/batch3_offline_integration/__main__.py",
                "tools/batch3_offline_integration/allowlist.py",
                "tools/batch3_offline_integration/fixture_producers.py",
                "tools/batch3_offline_integration/fixtures/complete_plan_request.json",
                "tools/batch3_offline_integration/fixtures/incomplete_plan_request.json",
                "tools/batch3_offline_integration/fixtures/nonfinite_probe.json",
                "tools/batch3_offline_integration/fixtures/release_bundle_synthetic.json",
                "tools/batch3_offline_integration/fixtures/workflow_request.json",
                "tools/batch3_offline_integration/guards.py",
                "tools/batch3_offline_integration/runner.py",
                "tools/batch3_offline_integration/schema.py",
                "tools/batch3_offline_integration/serialization.py",
                "tools/batch3_offline_integration/stages.py",
            },
            "batch3_claim_matrix_artifact": {
                "docs/research/batch3/theory_to_measurement_review.md",
                "reports/batch3/grok_chat_a/claim_matrix.json",
                "tests/research/batch3/test_claim_matrix.py",
            },
            "oss_adoption_gates": {
                "docs/oss_opportunity_candidate_review_20261016.md",
                "docs/oss_opportunity_pipeline.md",
                "oss_opportunities/opportunity_batch.py",
                "oss_opportunities/repository_candidate.py",
                "oss_opportunities/scoring.py",
                "oss_opportunities/validation.py",
                "tests/test_oss_adoption_gates.py",
            },
            "oss_compatibility_inventory_artifact": {
                "docs/oss_compat/batch1_compatibility_audit_20261017.md",
                "docs/oss_compat/compatibility_inventory_20261017.json",
                "tests/oss_compat/test_compatibility_inventory.py",
            },
            "batch3_dataset_feasibility_artifact": {
                "docs/research/batch3/replication_dataset_feasibility.md",
                "reports/batch3/grok_chat_b/dataset_candidates.json",
                "tests/research/batch3/test_replication_dataset_feasibility.py",
            },
            "batch3_metadata_audit_artifact": {
                "docs/research/batch3/grok_chat_b_dataset_feasibility.md",
                "reports/batch3/grok_chat_b/dataset_candidates_metadata_audit.json",
                "tests/research/batch3/test_dataset_metadata_audit.py",
            },
            "whitening_audit": {
                "docs/statistics/round6_whitening_audit.md",
                "scripts/audit_round6_whitening.py",
                "tests/whitening_audit/__init__.py",
                "tests/whitening_audit/test_whitening_audit.py",
                "tools/whitening_audit/__init__.py",
                "tools/whitening_audit/audit_reporter.py",
                "tools/whitening_audit/leakage_detector.py",
                "tools/whitening_audit/matrix_ops.py",
                "tools/whitening_audit/synthetic_data.py",
                "tools/whitening_audit/types.py",
                "tools/whitening_audit/whitening_verifier.py",
            },
            "batch3_falsification_matrix_artifact": {
                "configs/scientific_falsification/batch3_falsification_matrix.yaml",
                "docs/scientific_falsification/batch3_adversarial_review.md",
                "tests/scientific_falsification/test_batch3_falsification_matrix.py",
            },
            "batch2_pipeline_benchmark": {
                "scripts/benchmark_batch2_pipeline.py",
                "tests/benchmarks/batch2_pipeline/test_cli_and_reporting.py",
                "tests/benchmarks/batch2_pipeline/test_harness_and_targets.py",
                "tests/benchmarks/batch2_pipeline/test_isolation_and_network.py",
                "tools/benchmarks/batch2_pipeline/budgets.py",
                "tools/benchmarks/batch2_pipeline/harness.py",
                "tools/benchmarks/batch2_pipeline/validator.py",
            },
        }
        for component, paths in exact_candidate_diffs.items():
            with self.subTest(exact_candidate_diff=component):
                self.assertEqual(helper.select_components(paths), [component])
                self.assertEqual(helper._unmapped_candidate_paths(paths), [])

    def test_oss_adoption_mapping_runs_the_verified_owner_suite(self):
        helper = _helper()
        component = "oss_adoption_gates"
        spec = helper.COMPONENTS[component]
        tests = (
            "tests/test_oss_adoption_gates.py",
            "tests/test_oss_license_review.py",
            "tests/test_oss_opportunity_scoring.py",
            "tests/test_oss_repository_candidate.py",
            "tests/test_oss_integration_opportunity.py",
        )
        self.assertEqual(spec["tests"], tests)
        self.assertEqual(spec["suite_companion_tests"], ("tests/test_oss_license_review.py",))
        expected_pairs = {
            ("oss_opportunities/opportunity_batch.py", "tests/test_oss_adoption_gates.py"),
            ("oss_opportunities/repository_candidate.py", "tests/test_oss_adoption_gates.py"),
            ("oss_opportunities/repository_candidate.py", "tests/test_oss_repository_candidate.py"),
            ("oss_opportunities/scoring.py", "tests/test_oss_adoption_gates.py"),
            ("oss_opportunities/scoring.py", "tests/test_oss_opportunity_scoring.py"),
            ("oss_opportunities/validation.py", "tests/test_oss_adoption_gates.py"),
            ("oss_opportunities/validation.py", "tests/test_oss_opportunity_scoring.py"),
            ("oss_opportunities/validation.py", "tests/test_oss_integration_opportunity.py"),
            ("oss_opportunities/license_review.py", "tests/test_oss_license_review.py"),
        }
        pairs = {(item["implementation"], item["test"]) for item in spec["candidate_pairs"]}
        self.assertEqual(pairs, expected_pairs)

        changed = {
            "oss_opportunities/opportunity_batch.py",
            "oss_opportunities/repository_candidate.py",
            "oss_opportunities/scoring.py",
            "oss_opportunities/validation.py",
            "tests/test_oss_adoption_gates.py",
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for path in (*changed, *tests, "oss_opportunities/license_review.py"):
                _write(root, path, "# offline fixture\n")
            result = helper.inspect_component(component, root, changed)
        self.assertEqual(result["status"], "READY_TO_RUN")
        self.assertCountEqual(result["tests_to_run"], tests)
        self.assertEqual(len(result["tests_to_run"]), len(tests))
        self.assertEqual(result["missing_required_tests"], [])

    def test_oss_adoption_mapping_blocks_when_suite_companion_is_missing(self):
        helper = _helper()
        spec = helper.COMPONENTS["oss_adoption_gates"]
        changed = {
            "oss_opportunities/opportunity_batch.py",
            "oss_opportunities/repository_candidate.py",
            "oss_opportunities/scoring.py",
            "oss_opportunities/validation.py",
            "tests/test_oss_adoption_gates.py",
        }
        companion = "tests/test_oss_license_review.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for path in changed:
                _write(root, path, "# offline fixture\n")
            for path in spec["tests"]:
                if path != companion:
                    _write(root, path, "# offline fixture\n")
            _write(root, "oss_opportunities/license_review.py", "# offline fixture\n")
            result = helper.inspect_component("oss_adoption_gates", root, changed)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn(companion, result["missing_required_tests"])

    def test_oss_adoption_mapping_rejects_unregistered_suite_companion(self):
        helper = _helper()
        component = "oss_adoption_gates"
        spec = helper.COMPONENTS[component]
        invalid_spec = dict(spec)
        invalid_spec["suite_companion_tests"] = ("tests/not_registered.py",)
        changed = {
            "oss_opportunities/opportunity_batch.py",
            "oss_opportunities/repository_candidate.py",
            "oss_opportunities/scoring.py",
            "oss_opportunities/validation.py",
            "tests/test_oss_adoption_gates.py",
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for path in changed:
                _write(root, path, "# offline fixture\n")
            for path in spec["tests"]:
                _write(root, path, "# offline fixture\n")
            _write(root, "oss_opportunities/license_review.py", "# offline fixture\n")
            with patch.dict(helper.COMPONENTS, {component: invalid_spec}):
                result = helper.inspect_component(component, root, changed)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(
            result["invalid_suite_companion_tests"],
            ["tests/not_registered.py"],
        )

    def test_oss_adoption_suite_companion_requires_its_paired_implementation(self):
        helper = _helper()
        spec = helper.COMPONENTS["oss_adoption_gates"]
        changed = {
            "oss_opportunities/opportunity_batch.py",
            "oss_opportunities/repository_candidate.py",
            "oss_opportunities/scoring.py",
            "oss_opportunities/validation.py",
            "tests/test_oss_adoption_gates.py",
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for path in changed:
                _write(root, path, "# offline fixture\n")
            for path in spec["tests"]:
                _write(root, path, "# offline fixture\n")
            _write(root, "oss_opportunities/repository_candidate.py", "# offline fixture\n")
            _write(root, "oss_opportunities/scoring.py", "# offline fixture\n")
            _write(root, "oss_opportunities/validation.py", "# offline fixture\n")
            result = helper.inspect_component("oss_adoption_gates", root, changed)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn(
            "oss_opportunities/license_review.py",
            result["missing_implementations"],
        )

    def test_pr357_claim_gate_pair_does_not_hide_unmapped_candidate_paths(self):
        helper = _helper()
        implementation = "tools/research_claim_gate/gate.py"
        test_path = "tests/research_claim_gate/test_claim_gate.py"
        unmapped_implementation = "analysis/empirical_higher_order/runner.py"
        changed = {implementation, test_path, unmapped_implementation}
        self.assertEqual(
            helper.COMPONENT_OWNER_PRS["measurement_hypothesis_contract"],
            (384, 357),
        )
        self.assertEqual(helper.select_components(changed), ["measurement_hypothesis_contract"])
        unmapped = helper._unmapped_candidate_paths(changed)
        self.assertIn(unmapped_implementation, unmapped)
        self.assertNotIn(implementation, unmapped)
        self.assertNotIn(test_path, unmapped)

        # A changed source that declares multiple required tests is blocked
        # when its candidate checkout contains only one companion test.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            implementation = "sciencer_d/btc_icft/level_t/base_real_topology.py"
            first_test = "tests/test_base_real_topology_missingness.py"
            missing_test = "tests/test_cohort_missingness.py"
            _write(root, implementation, "# source fixture\n")
            _write(root, first_test, "def test_fixture(): pass\n")
            result = helper.inspect_component(
                "level_t_missingness", root, {implementation}
            )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["missing_required_tests"], [missing_test])

        # A fresh Hodge-reference candidate must not select or require the
        # independent numerical-audit PR, and vice versa.
        self.assertEqual(
            helper.select_components({"experimental/phase_cochain_reference/hodge.py"}),
            ["phase_cochain_reference"],
        )
        self.assertEqual(
            helper.select_components({"tools/hodge_decomposition_audit/audit.py"}),
            ["hodge_decomposition_audit"],
        )

        # The #402 audit pair is distinct from #414/#419 spherical parity.
        csd_audit_paths = {
            "tools/mne_csd_reference_audit/kkt.py",
            "tests/mne_csd_reference_audit/test_kkt_operator.py",
        }
        self.assertEqual(helper.select_components(csd_audit_paths), ["mne_csd_reference_audit"])
        self.assertEqual(
            helper.select_components({"tests/experimental/test_spherical_csd_parity.py"}),
            ["spherical_csd"],
        )

        # The #399 production bridge is not conflated with the merged #410
        # finite-jitter bridge, despite both living in experimental audits.
        self.assertEqual(
            helper.select_components({"tests/experimental_audits/test_winding_charge_production_import.py"}),
            ["winding_charge_audit"],
        )
        pr399_paths = {
            "docs/research/batch2/winding_charge_round6_conformance_audit.md",
            "tests/experimental_audits/__init__.py",
            "tests/experimental_audits/test_winding_charge_production_import.py",
            "tests/experimental_audits/test_winding_charge_round6_oracle.py",
            "tools/experimental_audits/__init__.py",
            "tools/experimental_audits/winding_charge_round6/__init__.py",
            "tools/experimental_audits/winding_charge_round6/__main__.py",
            "tools/experimental_audits/winding_charge_round6/audit.py",
            "tools/experimental_audits/winding_charge_round6/conventions.py",
            "tools/experimental_audits/winding_charge_round6/fixtures.py",
            "tools/experimental_audits/winding_charge_round6/oracle.py",
        }
        self.assertEqual(helper.select_components(pr399_paths), ["winding_charge_audit"])
        self.assertEqual(helper._unmapped_candidate_paths(pr399_paths), [])
        self.assertEqual(
            helper.select_components({"tests/test_finite_jitter_production_import.py"}),
            ["finite_jitter_production_bridge"],
        )


if __name__ == "__main__":
    unittest.main()
