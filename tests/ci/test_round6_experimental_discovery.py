"""Offline regression tests for required-check candidate discovery and identity binding."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = ROOT / ".github/workflows/round6_experimental_tests.py"
_REAL_SUBPROCESS_RUN = subprocess.run
IMPLEMENTATION = "tools/simulation_runtime/grid_plan.py"
TEST = "tests/simulation_runtime/test_grid_plan.py"


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
            finally:
                os.close(telemetry_fd)
                os.close(junit_fd)
        self.assertEqual(outside_telemetry.read_text(encoding="utf-8"), "preserve telemetry\n")
        self.assertEqual(outside_junit.read_text(encoding="utf-8"), "preserve junit\n")
        self.assertEqual(telemetry_bytes, b'{"completed":true}')
        self.assertEqual(junit_bytes, b"<testsuite/>")

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
            "collected": 1, "skipped": 0, "failed": 0, "errors": 0, "timeouts": 0,
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

    def test_unmapped_yaml_candidate_configs_block_instead_of_becoming_not_applicable(self):
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
            self.assertEqual(report["unmapped_candidate_paths"], [path])
            self.assertNotEqual(report["status"], "NOT_APPLICABLE")

    def test_junit_root_and_summary_must_match_testcase_outcomes(self):
        helper = _helper()
        malformed_reports = (
            '<testsuite tests="2" failures="1"><testcase/></testsuite>',
            '<testsuite tests="1" skipped="1"><testcase/></testsuite>',
            '<testsuite tests="1"><testcase><failure/><skipped/></testcase></testsuite>',
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
            report.write_text(
                '<testsuite tests="4" skipped="0" failures="0" errors="0">'
                '<testcase/><testcase/></testsuite>',
                encoding="utf-8",
            )
            counts, cases = helper.junit_details(report)
        self.assertEqual(counts, (2, 0, 0, 0))
        self.assertEqual(len(cases), 2)

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
        self.assertEqual(execution["tests_collected"], 2)
        self.assertEqual(execution["runner_passed_tests"], 2)
        self.assertEqual(execution["runner_passed_subtests"], 2)
        self.assertEqual(execution["junit_reported_test_outcomes"], 4)
        self.assertEqual(len(execution["test_cases"]), 2)

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
        self.assertIn("does not match", execution["junit_error"])

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
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original_base = _repo(root)
            _git(root, "switch", "-c", "candidate")
            _write(root, TEST, "def test_plan_fixture():\n    assert True  # PR head\n")
            pr_head = _commit(root, "PR test-only change")
            _git(root, "switch", "main")
            _write(root, "tools/surrogate_nulls/nulls.py", "def unrelated_main_update():\n    return None\n")
            pr_base = _commit(root, "main advances in unrelated candidate")
            _git(root, "switch", "candidate")
            _git(root, "merge", "--no-ff", "main", "-m", "synthetic tested merge checkout")
            merge_checkout = _git(root, "rev-parse", "HEAD")

            changed = helper.collect_changed_paths(pr_base, pr_head, root)
            wrong_merge_diff = helper.collect_changed_paths(original_base, merge_checkout, root)
            self.assertEqual(changed, {TEST})
            self.assertIn("tools/surrogate_nulls/nulls.py", wrong_merge_diff)

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
            "planar_geometry": (
                416, 421,
                "neurotopology_sim/experimental/geometry/planar_triangulation.py",
                "tests/experimental/test_planar_triangulation.py",
            ),
            "hodge_2d": (
                423, 396, 385,
                "neurotopology_sim/experimental/topology/hodge_2d.py",
                "tests/neurotopology_sim/experimental/topology/test_hodge_2d.py",
            ),
            "spherical_csd": (
                414, 419, 402,
                "neurotopology_sim/experimental/preprocessing/spherical_csd.py",
                "tests/experimental/test_spherical_csd_parity.py",
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
                415, 420,
                "neurotopology_sim/experimental/dynamics/dmd_crouzeix.py",
                "tests/dmd_crouzeix_contract/test_production_contract.py",
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
            "docker_context_policy": (
                431, 434,
                ".dockerignore",
                "tests/docker_context/test_build_context_policy.py",
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

        self.assertIn(
            {"implementation": "tools/surrogate_nulls/nulls.py", "test": "tests/surrogate_nulls/test_adversarial_contracts.py"},
            helper.COMPONENTS["surrogate_nulls"]["candidate_pairs"],
        )
        docker_tests = {
            pair["test"] for pair in helper.COMPONENTS["docker_context_policy"]["candidate_pairs"]
        }
        self.assertEqual(docker_tests, {
            "tests/docker_context/test_build_context_policy.py",
            "tests/docker_context/test_docker_engine_build_context.py",
        })
        for test_path in (
            "tests/dmd_ep2_oracle/test_oracle.py",  # PR #400 is an independent oracle, not a DMD pair.
            "tests/research/batch3/test_dataset_metadata_audit.py",  # PR #411
            "tests/oss_compat/test_compatibility_inventory.py",  # PR #406
            "tests/research/batch3/test_replication_dataset_feasibility.py",  # PR #394
            "tests/research/batch3/test_claim_matrix.py",  # PR #393
            "tests/source_mining_integration/test_source_mining_evidence_boundary.py",  # PR #382
        ):
            self.assertIn(test_path, helper._unmapped_candidate_paths({test_path}))

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
        for config_path in (
            "configs/scientific_falsification/batch3_falsification_matrix.yaml",
            "configs/research/batch3_source_registry.yaml",
        ):
            self.assertEqual(helper._unmapped_candidate_paths({config_path}), [config_path])
        # Unregistered candidate roots remain fail-closed even when the only
        # changed Python file is a package initializer.
        self.assertIn("tests/nuisance_scenarios/__init__.py", helper._unmapped_candidate_paths({"tests/nuisance_scenarios/__init__.py"}))
        self.assertNotIn("tests/surrogate_nulls/__init__.py", helper._unmapped_candidate_paths({"tests/surrogate_nulls/__init__.py"}))

    def test_package_initializers_require_exact_test_support_mappings(self):
        helper = _helper()
        for component, initializer_paths in helper.PACKAGE_INITIALIZER_SUPPORT_PATHS.items():
            spec = helper.COMPONENTS[component]
            expected_tests = tuple(dict.fromkeys(
                pair["test"] for pair in spec["candidate_pairs"]
            ))
            self.assertTrue(expected_tests, component)
            for initializer in initializer_paths:
                with self.subTest(component=component, initializer=initializer):
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
            helper.select_components({
                "neurotopology_sim/__init__.py",
                geometry_pair["implementation"],
                geometry_pair["test"],
            }),
            ["planar_geometry"],
        )
        roc_pair = helper.COMPONENTS["synthetic_roc"]["candidate_pairs"][0]
        self.assertEqual(
            helper.select_components({
                "neurotopology_sim/__init__.py",
                roc_pair["implementation"],
                roc_pair["test"],
            }),
            ["synthetic_roc"],
        )
        dmd_pair = helper.COMPONENTS["dmd_crouzeix"]["candidate_pairs"][0]
        self.assertEqual(
            helper.select_components({
                "tests/experimental/__init__.py",
                dmd_pair["implementation"],
                dmd_pair["test"],
            }),
            ["dmd_crouzeix"],
        )

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

    def test_unmapped_open_pr_candidate_gaps_are_fail_closed(self):
        helper = _helper()
        current_open_pr_gaps = {
            411: "tests/research/batch3/test_dataset_metadata_audit.py",
            406: "tests/oss_compat/test_compatibility_inventory.py",
            394: "tests/research/batch3/test_replication_dataset_feasibility.py",
            393: "tests/research/batch3/test_claim_matrix.py",
            391: "tools/public_repo_harvest/source_pack.py",
            386: "oss_opportunities/opportunity_batch.py",
            384: "shared/measurement_hypothesis/validate.py",
            383: "tools/research_plan_quality_eval/harness.py",
            382: "tests/source_mining_integration/test_source_mining_evidence_boundary.py",
            376: "tests/scientific_falsification/test_batch3_falsification_matrix.py",
            375: "tests/research/test_batch3_source_registry.py",
            374: "dual_engine/fusion_validation.py",
            373: "sciencer_d/btc_icft/level_t/base_real_topology.py",
            388: "dual_engine/forward_model_contract.py",
            387: "tools/synthetic_pipeline_replay/runner.py",
        }
        for pr_number, path in current_open_pr_gaps.items():
            with self.subTest(pr=pr_number, path=path):
                self.assertIn(path, helper._unmapped_candidate_paths({path}))
                self.assertEqual(helper.select_components({path}), [])


if __name__ == "__main__":
    unittest.main()
