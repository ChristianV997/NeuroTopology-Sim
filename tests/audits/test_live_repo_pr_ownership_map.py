"""Offline structural checks for the dated PR ownership/status snapshot."""

from __future__ import annotations

import importlib.util
import ast
import json
import re
import unittest
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "docs/audits/live_repo_pr_ownership_map.json"
SCHEMA = ROOT / "docs/audits/live_repo_pr_ownership_map.schema.json"
HELPER = ROOT / ".github/workflows/round6_experimental_tests.py"


def _load(path: Path):
    def reject_constant(value: str):
        raise ValueError(f"non-finite JSON constant: {value}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def _helper():
    spec = importlib.util.spec_from_file_location("round6_experimental_tests", HELPER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OwnershipSnapshotTests(unittest.TestCase):
    def test_snapshot_is_canonical_finite_json_and_schema_versioned(self):
        raw = AUDIT.read_text(encoding="utf-8")
        doc = _load(AUDIT)
        self.assertEqual(raw, json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")
        schema = _load(SCHEMA)
        self.assertEqual(doc["schema_version"], schema["properties"]["schema_version"]["const"])
        self.assertEqual(doc["snapshot_kind"], "timestamped_read_only_repository_and_pull_request_audit")
        self.assertEqual(doc["repository"]["posture"], "HOLD / SYNTHETIC_ONLY")
        self.assertRegex(doc["captured_at_utc"], r"^\d{4}-\d{2}-\d{2}T.*Z$")
        self.assertIsNotNone(datetime.fromisoformat(doc["captured_at_utc"].replace("Z", "+00:00")).tzinfo)
        self.assertRegex(doc["repository"]["main_sha"], r"^[0-9a-f]{40}$")

    def test_open_inventory_ids_shas_and_relative_paths_are_valid(self):
        doc = _load(AUDIT)
        prs = doc["pull_requests"]
        numbers = [pr["number"] for pr in prs]
        self.assertEqual(numbers, sorted(set(numbers)))
        self.assertEqual(numbers, doc["scope"]["open_pr_numbers"])
        self.assertEqual(len(numbers), doc["scope"]["open_pr_count"])
        self.assertTrue({390, 392, 409, 413, 421, 425, 428} <= set(numbers))
        for pr in prs:
            for key in ("base_sha", "head_sha"):
                self.assertRegex(pr["base"]["sha"] if key == "base_sha" else pr["head"]["sha"], r"^[0-9a-f]{40}$")
            for path in pr["changed_paths"]:
                self.assertNotIn("\x00", path)
                self.assertFalse(PurePosixPath(path).is_absolute())
                self.assertFalse(PureWindowsPath(path).is_absolute())
                self.assertFalse(PureWindowsPath(path).drive)
                self.assertNotIn("..", PurePosixPath(path).parts)

    def test_path_overlaps_are_exact_ownership_collisions_not_git_conflicts(self):
        doc = _load(AUDIT)
        by_number = {pr["number"]: pr for pr in doc["pull_requests"]}
        seen = set()
        for collision in doc["path_collisions"]:
            self.assertNotIn(collision["path"], seen)
            seen.add(collision["path"])
            self.assertEqual(collision["classification"], "exact_changed_path_overlap")
            self.assertIsNone(collision["git_conflict"])
            self.assertGreaterEqual(len(collision["pr_numbers"]), 2)
            for number in collision["pr_numbers"]:
                self.assertIn(collision["path"], by_number[number]["changed_paths"])

    def test_unknown_required_checks_cannot_make_a_pr_ready(self):
        doc = _load(AUDIT)
        self.assertEqual(doc["required_check_configuration"]["state"], "unknown")
        self.assertTrue(doc["required_check_configuration"]["reason"])
        for pr in doc["pull_requests"]:
            self.assertEqual(pr["ci"]["required_check_state"], "unknown")
            if pr["readiness"]["state"] == "ready":
                self.assertEqual(pr["review"]["approval_count"], 1)
                self.assertEqual(pr["ci"]["required_check_state"], "pass")
        self.assertEqual(doc["readiness_summary"]["merge_ready_count"], 0)
        self.assertEqual(doc["readiness_summary"]["ready_pr_numbers"], [])
        self.assertEqual(doc["readiness_summary"]["counts"]["ready"], 0)

    def test_collision_summary_and_round6_pr_405_fact_are_consistent(self):
        doc = _load(AUDIT)
        self.assertEqual(doc["ownership_summary"]["path_collision_path_count"], len(doc["path_collisions"]))
        self.assertTrue(doc["pr_405"]["merged"])
        self.assertRegex(doc["pr_405"]["merge_commit_sha"], r"^[0-9a-f]{40}$")
        self.assertEqual(doc["pr_405"]["interface"]["package"], "analysis.binomial_planning")
        self.assertIn("wilson_score_interval", doc["pr_405"]["interface"]["exports"])

    def test_workflow_runs_mapped_candidate_tests_and_does_not_call_absence_a_pass(self):
        workflow = (ROOT / ".github/workflows/required-checks.yml").read_text(encoding="utf-8")
        self.assertIn("round6_experimental_tests.py", workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("outputs/round6_experimental_ci_report.json", workflow)
        helper = _helper()
        expected = {
            "planar_geometry", "hodge_2d", "spherical_csd", "four_sphere",
            "phase_winding", "surrogate_nulls", "phase_uncertainty",
            "surrogate_audit", "synthetic_roc",
        }
        for name, spec in helper.COMPONENTS.items():
            self.assertTrue(spec.get("tests"))
            self.assertTrue(spec.get("triggers"))
        self.assertTrue(expected <= set(helper.COMPONENTS))
        self.assertEqual(helper.select_components({"tests/experimental/test_synthetic_roc_calibration_split.py"}), ["synthetic_roc"])
        self.assertEqual(helper.select_components({"tests/neurotopology_sim/experimental/geometry/test_planar_triangulation.py"}), ["planar_geometry"])
        self.assertEqual(helper.select_components({"tests/neurotopology_sim/experimental/topology/test_hodge_2d.py"}), ["hodge_2d"])
        self.assertEqual(helper.select_components({"tests/mne_csd_reference_audit/test_kkt_operator.py"}), ["spherical_csd"])
        self.assertEqual(helper.select_components({"tests/experimental_audits/test_four_shell_bvp_oracle.py"}), ["four_sphere"])
        self.assertEqual(helper.select_components({"tests/surrogate_nulls/test_phase_nulls.py"}), ["surrogate_nulls"])
        self.assertEqual(helper.select_components({"tests/phase_uncertainty/test_candidate_contract.py"}), ["phase_uncertainty"])
        self.assertEqual(helper.select_components({"tests/surrogate_audit/test_mv_fpr.py"}), ["surrogate_audit"])
        self.assertEqual(helper.select_components({"docs/unrelated.md"}), [])
        with TemporaryDirectory() as td:
            root = Path(td)
            verdict = helper.inspect_component("synthetic_roc", root)
            self.assertEqual(verdict["status"], "BLOCKED")
            self.assertIn("absent", verdict["reason"])

    def test_candidate_mapping_covers_direct_implementation_and_adversarial_test_pairs(self):
        helper = _helper()
        expected_pairs = {
            "planar_geometry": ("neurotopology_sim/experimental/geometry/planar_triangulation.py", "tests/neurotopology_sim/experimental/geometry/test_planar_triangulation.py"),
            "hodge_2d": ("neurotopology_sim/experimental/topology/hodge_2d.py", "tests/neurotopology_sim/experimental/topology/test_hodge_2d.py"),
            "spherical_csd": ("neurotopology_sim/experimental/preprocessing/spherical_csd.py", "tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py"),
            "four_sphere": ("physics/eeg_forward/four_sphere.py", "tests/physics/eeg_forward/test_four_sphere.py"),
            "phase_winding": ("neurotopology_sim/experimental/topology/winding.py", "tests/neurotopology_sim/experimental/topology/test_phase_winding.py"),
            "surrogate_nulls": ("tools/surrogate_nulls/nulls.py", "tests/surrogate_nulls/test_phase_nulls.py"),
            "phase_uncertainty": ("tools/phase_uncertainty/candidate_estimator.py", "tests/phase_uncertainty/test_candidate_contract.py"),
            "surrogate_audit": ("tools/surrogate_audit/mv_fpr.py", "tests/surrogate_audit/test_mv_fpr.py"),
            "synthetic_roc": ("neurotopology_sim/experimental/benchmarks/synthetic_forward_roc.py", "tests/neurotopology_sim/experimental/benchmarks/test_synthetic_forward_roc.py"),
        }
        for name, (implementation, test_file) in expected_pairs.items():
            spec = helper.COMPONENTS[name]
            implementations = spec.get("implementation_any", (spec.get("implementation"),))
            self.assertIn(implementation, implementations, name)
            self.assertIn(test_file, spec["tests"], name)

    def test_junit_skip_and_empty_collection_are_visible_to_ci_gate(self):
        helper = _helper()
        with TemporaryDirectory() as td:
            report = Path(td) / "report.xml"
            report.write_text('<testsuite tests="2" skipped="1"><testcase/><testcase><skipped/></testcase></testsuite>', encoding="utf-8")
            counts = helper.junit_counts(report)
            self.assertEqual(counts, (2, 1, 0, 0))
            self.assertEqual(helper.junit_status(counts), "FAIL")
            report.write_text('<testsuite tests="0"/>', encoding="utf-8")
            counts = helper.junit_counts(report)
            self.assertEqual(counts, (0, 0, 0, 0))
            self.assertEqual(helper.junit_status(counts), "FAIL")
            report.write_text('<testsuite tests="1"><testcase/></testsuite>', encoding="utf-8")
            self.assertEqual(helper.junit_status(helper.junit_counts(report)), "PASS")

    def test_every_mapped_file_runs_even_after_a_skip_and_skip_fails_lane(self):
        helper = _helper()
        spec = helper.COMPONENTS["surrogate_nulls"]
        with TemporaryDirectory() as td:
            root = Path(td)
            for source in spec["implementation_any"]:
                path = root / source
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# fixture implementation path\n", encoding="utf-8")
            for test_file in spec["tests"]:
                path = root / test_file
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# fixture candidate test path\n", encoding="utf-8")

            calls = []

            def fake_runner(command, **kwargs):
                calls.append(command)
                report_path = Path(command[command.index("--report") + 1])
                report_path.write_text(json.dumps({
                    "exit_code": 0,
                    "batches": [{"status": "passed"}],
                    "summary": {"skipped_batches": 0, "failed_batches": 0, "timeout_batches": 0},
                }), encoding="utf-8")
                junit_arg = next(arg for arg in command if arg.startswith("--pytest-arg=--junitxml="))
                junit_path = Path(junit_arg.removeprefix("--pytest-arg=--junitxml="))
                junit_path.write_text(
                    '<testsuite tests="1"><testcase><skipped/></testcase></testsuite>'
                    if len(calls) == 1 else
                    '<testsuite tests="1"><testcase/></testsuite>',
                    encoding="utf-8",
                )
                return SimpleNamespace(returncode=0)

            report_path = root / "report.json"
            with patch.object(helper, "collect_changed_paths", return_value={"tools/surrogate_nulls/nulls.py"}), patch.object(helper.subprocess, "run", side_effect=fake_runner):
                result = helper.run(root, "0" * 40, "1" * 40, report_path)

            report = _load(report_path)
            self.assertEqual(result, 1)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(len(calls), len(spec["tests"]))
            for command in calls:
                self.assertIn("scripts/run_tests_isolated.py", command)
                self.assertEqual(command[command.index("--batch-size") + 1], "1")
                self.assertEqual(command[command.index("--timeout-s") + 1], "120")

    def test_discovery_helper_has_no_dataset_or_network_client_imports(self):
        tree = ast.parse(HELPER.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        self.assertTrue({"socket", "requests", "urllib", "boto3", "mne"}.isdisjoint(imports))


if __name__ == "__main__":
    unittest.main()
