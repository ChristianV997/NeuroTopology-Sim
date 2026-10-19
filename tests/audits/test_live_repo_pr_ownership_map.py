"""Offline structural checks for the dated PR ownership/status snapshot."""

from __future__ import annotations

import importlib.util
import ast
import json
import re
import subprocess
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
        self.assertIn(425, numbers)
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
        allowed_check_states = {"pass", "fail", "pending", "unknown", "not_applicable"}
        self.assertIn(doc["required_check_configuration"]["state"], allowed_check_states)
        if doc["required_check_configuration"]["state"] == "unknown":
            self.assertTrue(doc["required_check_configuration"].get("reason"))
        readiness_counts = {state: 0 for state in ("ready", "draft", "blocked", "conflicted", "unknown")}
        ready_numbers = []
        for pr in doc["pull_requests"]:
            self.assertIn(pr["ci"]["required_check_state"], allowed_check_states)
            readiness_counts[pr["readiness"]["state"]] += 1
            if pr["readiness"]["state"] == "ready":
                ready_numbers.append(pr["number"])
                self.assertFalse(pr["draft"])
                self.assertEqual(pr["review"]["approval_count"], 1)
                self.assertEqual(pr["ci"]["required_check_state"], "pass")
                self.assertEqual(pr["ci"]["observed_state"], "pass")
                self.assertIsNot(pr["mergeability"]["github_mergeable"], False)
        self.assertEqual(sorted(ready_numbers), doc["readiness_summary"]["ready_pr_numbers"])
        self.assertEqual(doc["readiness_summary"]["merge_ready_count"], len(ready_numbers))
        self.assertEqual(doc["readiness_summary"]["counts"], readiness_counts)
        if doc["required_check_configuration"]["state"] == "unknown":
            self.assertEqual(ready_numbers, [])
        if all(pr["review"]["approval_count"] == 0 for pr in doc["pull_requests"]):
            self.assertEqual(ready_numbers, [])

    def test_candidate_discovery_snapshot_is_complete_and_reports_local_limitations(self):
        doc = _load(AUDIT)
        helper = _helper()
        discovery = doc["main_ci"]["round6_candidate_discovery"]
        self.assertEqual(discovery["helper_path"], ".github/workflows/round6_experimental_tests.py")
        self.assertEqual(discovery["component_count"], len(helper.COMPONENTS))
        self.assertEqual(
            discovery["candidate_pair_count"],
            sum(len(spec["candidate_pairs"]) for spec in helper.COMPONENTS.values()),
        )
        recorded = {item["name"]: item for item in discovery["components"]}
        self.assertEqual(set(recorded), set(helper.COMPONENTS))
        for name, spec in helper.COMPONENTS.items():
            self.assertEqual(recorded[name]["candidate_pairs"], list(spec["candidate_pairs"]))
            self.assertEqual(recorded[name]["test_files"], list(spec["tests"]))
        self.assertEqual(discovery["coverage_audit"]["unmapped_candidate_paths"], [])
        contract = discovery["execution_contract"]
        self.assertEqual(contract["empty_collection"], "fail")
        self.assertEqual(contract["skipped_tests"], "fail")
        self.assertEqual(contract["missing_implementation_or_test"], "blocked")
        self.assertEqual(contract["no_candidate_change"], "NOT_APPLICABLE_not_a_pass")
        self.assertTrue(contract["per_file_singleton_process"])
        local = discovery["local_candidate_probe"]
        self.assertIn(local["status"], {"complete", "partial", "blocked", "inconclusive", "unknown"})
        self.assertRegex(local["retrieved_at_utc"], r"^\d{4}-\d{2}-\d{2}T.*Z$")
        self.assertIsInstance(local["candidate_probes"], list)
        for probe in local["candidate_probes"]:
            self.assertIn(probe["result_status"], {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "MERGE_CONFLICT"})
            self.assertIsInstance(probe["candidate_tests_executed"], bool)
        self.assertIn(discovery["hosted_candidate_execution"], {"not_observed", "observed", "unknown"})
        schema = _load(SCHEMA)["properties"]["main_ci"]["properties"]["round6_candidate_discovery"]["properties"]
        self.assertEqual(
            set(schema["local_candidate_probe"]["required"]),
            {"retrieved_at_utc", "status", "environment", "candidate_probes", "summary"},
        )
        for run in discovery.get("hosted_candidate_runs", []):
            self.assertRegex(run["head_sha"], r"^[0-9a-f]{40}$")
            self.assertGreater(run["run_id"], 0)
            self.assertGreater(run["isolated_batches_total"], 0)
            self.assertGreaterEqual(run["isolated_batches_failed"], 0)
            self.assertGreaterEqual(run["isolated_batches_skipped"], 0)
            self.assertTrue(run["candidate_test_paths"])

    def test_unknown_branch_gate_and_candidate_blockage_are_not_reported_as_pass(self):
        doc = _load(AUDIT)
        self.assertEqual(doc["required_check_configuration"]["state"], "unknown")
        discovery = doc["main_ci"]["round6_candidate_discovery"]
        self.assertEqual(discovery["local_candidate_probe"]["status"], "blocked")
        self.assertTrue(all(not p["candidate_tests_executed"] for p in discovery["local_candidate_probe"]["candidate_probes"]))
        for probe in discovery["local_candidate_probe"]["candidate_probes"]:
            self.assertEqual(probe["collected_test_count"], 0)
            self.assertEqual(probe["result_status"], "BLOCKED")
            self.assertEqual(probe["runner_status"], "FAIL")
        self.assertEqual(doc["readiness_summary"]["ready_pr_numbers"], [])
        self.assertGreaterEqual(doc["readiness_summary"]["counts"]["unknown"], 0)

    def test_collision_summary_and_round6_pr_405_fact_are_consistent(self):
        doc = _load(AUDIT)
        self.assertEqual(doc["ownership_summary"]["path_collision_path_count"], len(doc["path_collisions"]))
        self.assertTrue(doc["pr_405"]["merged"])
        self.assertRegex(doc["pr_405"]["merge_commit_sha"], r"^[0-9a-f]{40}$")
        self.assertEqual(doc["pr_405"]["interface"]["package"], "analysis.binomial_planning")
        self.assertIn("wilson_score_interval", doc["pr_405"]["interface"]["exports"])

    def test_integration_lane_main_presence_is_explicit_not_inferred(self):
        doc = _load(AUDIT)
        for lane in doc["integration_lanes"]:
            present = lane["candidate_paths_present_on_main"]
            missing = lane["candidate_paths_missing_from_main"]
            self.assertEqual(present, sorted(set(present)))
            self.assertEqual(missing, sorted(set(missing)))
            self.assertFalse(set(present) & set(missing))
            self.assertEqual(lane["main_candidate_files_present"], not missing)
            self.assertRegex(lane["note"], r"\d+/\d+ candidate source/test files exist")

    def test_workflow_runs_mapped_candidate_tests_and_does_not_call_absence_a_pass(self):
        workflow = (ROOT / ".github/workflows/required-checks.yml").read_text(encoding="utf-8")
        self.assertIn("round6_experimental_tests.py", workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("outputs/round6_experimental_ci_report.json", workflow)
        helper = _helper()
        expected = {
            "planar_geometry", "hodge_2d", "spherical_csd", "four_sphere",
            "phase_winding", "surrogate_nulls", "phase_uncertainty",
            "surrogate_audit", "synthetic_roc", "dmd_crouzeix",
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
        self.assertEqual(helper.select_components({"tests/physics/test_four_sphere_oracle.py"}), ["four_sphere"])
        self.assertEqual(helper.select_components({"tests/surrogate_nulls/test_phase_nulls.py"}), ["surrogate_nulls"])
        self.assertEqual(helper.select_components({"tests/phase_uncertainty/test_candidate_contract.py"}), ["phase_uncertainty"])
        self.assertEqual(helper.select_components({"tests/surrogate_audit/test_mv_fpr.py"}), ["surrogate_audit"])
        self.assertEqual(helper.select_components({"neurotopology_sim/experimental/dynamics/dmd_crouzeix.py"}), ["dmd_crouzeix"])
        self.assertEqual(helper.select_components({"tests/dmd_crouzeix_contract/test_production_contract.py"}), ["dmd_crouzeix"])
        self.assertEqual(helper.select_components({"tests/experimental/test_dmd_crouzeix.py"}), ["dmd_crouzeix"])
        self.assertEqual(helper.select_components({"docs/unrelated.md"}), [])
        with TemporaryDirectory() as td:
            root = Path(td)
            verdict = helper.inspect_component("synthetic_roc", root)
            self.assertEqual(verdict["status"], "BLOCKED")
            self.assertIn("required candidate implementation is absent", verdict["blockers"])

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
            "simulation_grid_planner": ("tools/simulation_runtime/grid_plan.py", "tests/simulation_runtime/test_grid_plan.py"),
            "report_firewall": ("tools/batch3_report_firewall/checker.py", "tests/tools/batch3_report_firewall/test_checker.py"),
            "provenance_join": ("tools/batch3_provenance_join/auditor.py", "tests/tools/batch3_provenance_join/test_audit.py"),
            "topology_backend_conformance": ("tools/topology_backend_conformance/comparator.py", "tests/topology_backend_conformance/test_comparability_gates.py"),
            "finite_chain_audit": ("tools/batch2_chain_complex_audit/complex.py", "tests/batch2_chain_complex_audit/test_boundary_composition.py"),
            "winding_charge_audit": ("tools/experimental_audits/winding_charge_round6/__main__.py", "tests/experimental_audits/test_winding_charge_round6_oracle.py"),
            "dmd_crouzeix": ("neurotopology_sim/experimental/dynamics/dmd_crouzeix.py", "tests/dmd_crouzeix_contract/test_production_contract.py"),
        }
        for name, (implementation, test_file) in expected_pairs.items():
            spec = helper.COMPONENTS[name]
            implementations = spec.get("implementation_any", (spec.get("implementation"),))
            self.assertIn(implementation, implementations, name)
            self.assertIn(test_file, spec["tests"], name)
            self.assertIn(
                {"implementation": implementation, "test": test_file},
                spec["candidate_pairs"],
                name,
            )
        self.assertIn(
            {"implementation": "tools/batch3_provenance_join/models.py", "test": "tests/tools/batch3_provenance_join/test_safety_and_cycles.py"},
            helper.COMPONENTS["provenance_join"]["candidate_pairs"],
        )
        self.assertEqual(helper.select_components({"tools/simulation_runtime/grid_plan.py"}), ["simulation_grid_planner"])
        self.assertEqual(helper.select_components({"scripts/check_batch3_report_language.py"}), ["report_firewall"])
        self.assertEqual(helper.select_components({"scripts/run_batch3_provenance_join.py"}), ["provenance_join"])
        self.assertEqual(helper.select_components({"tools/topology_backend_conformance/comparator.py"}), ["topology_backend_conformance"])
        self.assertEqual(helper.select_components({"tests/batch2_chain_complex_audit/test_boundary_composition.py"}), ["finite_chain_audit"])
        self.assertEqual(helper.select_components({"tests/experimental_audits/test_winding_charge_round6_oracle.py"}), ["winding_charge_audit"])
        self.assertIn(
            {"implementation": "neurotopology_sim/experimental/dynamics/dmd_crouzeix.py", "test": "tests/experimental/test_dmd_crouzeix.py"},
            helper.COMPONENTS["dmd_crouzeix"]["candidate_pairs"],
        )
        self.assertIn(
            {"implementation": "physics/eeg_forward/four_sphere.py", "test": "tests/physics/test_four_sphere_oracle.py"},
            helper.COMPONENTS["four_sphere"]["candidate_pairs"],
        )
        self.assertIn("tests/mne_csd_reference_audit/test_mne_integration_optional.py", helper.COMPONENTS["spherical_csd"]["tests"])
        self.assertIn("tests/surrogate_nulls/test_hardening_diagnostics.py", helper.COMPONENTS["surrogate_nulls"]["tests"])
        self.assertIn("tests/surrogate_nulls/test_real_part_and_validity.py", helper.COMPONENTS["surrogate_nulls"]["tests"])
        for source in (
            "tools/surrogate_nulls/csd.py",
            "tools/surrogate_nulls/nulls.py",
            "tools/surrogate_nulls/spectral.py",
        ):
            self.assertIn(
                {"implementation": source, "test": "tests/surrogate_nulls/test_real_part_and_validity.py"},
                helper.COMPONENTS["surrogate_nulls"]["candidate_pairs"],
            )
        for name, spec in helper.COMPONENTS.items():
            for pair in spec["candidate_pairs"]:
                self.assertIn(pair["test"], spec["tests"], f"unlisted test mapping in {name}")

        snapshot = _load(AUDIT)
        for pr in snapshot["pull_requests"]:
            changed = set(pr["changed_paths"])
            for name in helper.select_components(changed):
                self.assertEqual(
                    helper._changed_candidate_paths(helper.COMPONENTS[name], changed),
                    [],
                    f"PR #{pr['number']} has an unmapped candidate path in {name}",
                )

    def test_windows_separators_select_the_same_candidate_lane(self):
        helper = _helper()
        self.assertEqual(
            helper.select_components({r"tools\batch3_report_firewall\checker.py"}),
            ["report_firewall"],
        )

    def test_inspection_blocks_missing_implementation_or_required_test(self):
        helper = _helper()
        spec = helper.COMPONENTS["simulation_grid_planner"]
        pair = spec["candidate_pairs"][0]
        with TemporaryDirectory() as td:
            root = Path(td)
            test_path = root / pair["test"]
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.write_text("# candidate test fixture\n", encoding="utf-8")
            verdict = helper.inspect_component(
                "simulation_grid_planner", root, {pair["test"]}
            )
            self.assertEqual(verdict["status"], "BLOCKED")
            self.assertEqual(verdict["missing_implementations"], [pair["implementation"]])

            source_path = root / pair["implementation"]
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text("# candidate implementation fixture\n", encoding="utf-8")
            test_path.unlink()
            verdict = helper.inspect_component(
                "simulation_grid_planner", root, {pair["implementation"]}
            )
            self.assertEqual(verdict["status"], "BLOCKED")
            self.assertEqual(verdict["missing_required_tests"], [pair["test"]])

    def test_unmapped_candidate_test_path_is_blocked_instead_of_ignored(self):
        helper = _helper()
        with TemporaryDirectory() as td:
            root = Path(td)
            verdict = helper.inspect_component(
                "report_firewall",
                root,
                {"tests/tools/batch3_report_firewall/test_unregistered_contract.py"},
            )
        self.assertEqual(verdict["status"], "BLOCKED")
        self.assertIn(
            "tests/tools/batch3_report_firewall/test_unregistered_contract.py",
            verdict["unmapped_candidate_paths"],
        )
        dmd_verdict = helper.inspect_component(
            "dmd_crouzeix",
            Path(td),
            {"neurotopology_sim/experimental/dynamics/unregistered_model.py"},
        )
        self.assertEqual(dmd_verdict["status"], "BLOCKED")
        self.assertIn(
            "neurotopology_sim/experimental/dynamics/unregistered_model.py",
            dmd_verdict["unmapped_candidate_paths"],
        )

    def test_no_candidate_changes_are_not_applicable_and_do_not_execute(self):
        helper = _helper()
        with TemporaryDirectory() as td:
            root = Path(td)
            report_path = root / "report.json"
            with patch.object(helper, "collect_changed_paths", return_value={"docs/unrelated.md"}), patch.object(
                helper.subprocess, "run", side_effect=AssertionError("no-lane runs must not spawn tests")
            ):
                result = helper.run(root, "0" * 40, "1" * 40, report_path)
            report = _load(report_path)
        self.assertEqual(result, 0)
        self.assertEqual(report["status"], "NOT_APPLICABLE")
        self.assertEqual(report["selected_components"], [])
        self.assertEqual(report["executed_commands"], [])

    def test_malformed_runner_telemetry_and_junit_fail_closed(self):
        helper = _helper()
        pair = helper.COMPONENTS["simulation_grid_planner"]["candidate_pairs"][0]
        with TemporaryDirectory() as td:
            root = Path(td)
            for relative in (pair["implementation"], pair["test"]):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# deterministic placeholder fixture\n", encoding="utf-8")

            def invalid_telemetry(command, **kwargs):
                telemetry = Path(command[command.index("--report") + 1])
                telemetry.write_text("{malformed", encoding="utf-8")
                junit_arg = next(arg for arg in command if arg.startswith("--pytest-arg=--junitxml="))
                Path(junit_arg.removeprefix("--pytest-arg=--junitxml=")).write_text(
                    '<testsuite tests="1"><testcase/></testsuite>', encoding="utf-8"
                )
                return SimpleNamespace(returncode=0)

            report_path = root / "bad-telemetry.json"
            with patch.object(helper, "collect_changed_paths", return_value={pair["implementation"]}), patch.object(
                helper.subprocess, "run", side_effect=invalid_telemetry
            ):
                result = helper.run(root, "0" * 40, "1" * 40, report_path)
            report = _load(report_path)
            self.assertEqual(result, 1)
            self.assertEqual(report["components"][0]["executions"][0]["failure_classification"], "missing_or_failed_runner_telemetry")
            self.assertIn("runner_telemetry_error", report["components"][0]["executions"][0])

            def invalid_junit(command, **kwargs):
                telemetry = Path(command[command.index("--report") + 1])
                telemetry.write_text(json.dumps({
                    "exit_code": 0,
                    "batches": [{"status": "passed"}],
                    "summary": {"skipped_batches": 0, "failed_batches": 0, "timeout_batches": 0},
                }), encoding="utf-8")
                junit_arg = next(arg for arg in command if arg.startswith("--pytest-arg=--junitxml="))
                Path(junit_arg.removeprefix("--pytest-arg=--junitxml=")).write_text("<testsuite", encoding="utf-8")
                return SimpleNamespace(returncode=0)

            report_path = root / "bad-junit.json"
            with patch.object(helper, "collect_changed_paths", return_value={pair["implementation"]}), patch.object(
                helper.subprocess, "run", side_effect=invalid_junit
            ):
                result = helper.run(root, "0" * 40, "1" * 40, report_path)
            report = _load(report_path)
        self.assertEqual(result, 1)
        execution = report["components"][0]["executions"][0]
        self.assertEqual(execution["failure_classification"], "missing_or_invalid_junit")
        self.assertIn("junit_error", execution)

    def test_relevant_change_with_empty_component_selection_fails_closed(self):
        helper = _helper()
        with TemporaryDirectory() as td:
            root = Path(td)
            report_path = root / "report.json"
            with patch.object(
                helper,
                "collect_changed_paths",
                return_value={"tools/simulation_runtime/grid_plan.py"},
            ), patch.object(helper, "select_components", return_value=[]):
                result = helper.run(root, "0" * 40, "1" * 40, report_path)
            report = _load(report_path)
        self.assertNotEqual(result, 0)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["selected_components"], [])
        self.assertIn("empty component selection", report["selection_error"])

    def test_timeout_is_explicit_and_contains_the_exact_command(self):
        helper = _helper()
        pair = helper.COMPONENTS["simulation_grid_planner"]["candidate_pairs"][0]
        with TemporaryDirectory() as td:
            root = Path(td)
            for relative in (pair["implementation"], pair["test"]):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# local fixture\n", encoding="utf-8")
            report_path = root / "report.json"
            with patch.object(
                helper,
                "collect_changed_paths",
                return_value={pair["implementation"]},
            ), patch.object(
                helper.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(["python", "pytest"], 130),
            ):
                result = helper.run(root, "0" * 40, "1" * 40, report_path)
            report = _load(report_path)
        self.assertNotEqual(result, 0)
        execution = report["components"][0]["executions"][0]
        self.assertEqual(execution["status"], "TIMEOUT")
        self.assertTrue(execution["timeout"])
        self.assertIn("scripts/run_tests_isolated.py", execution["command"])
        self.assertEqual(report["executed_commands"], [execution["command"]])

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
            report.write_text(
                '<testsuite tests="2"><testcase classname="candidate" name="assertion"><failure message="bad result"/></testcase><testcase classname="candidate" name="import"><error message="import error"/></testcase></testsuite>',
                encoding="utf-8",
            )
            counts, cases = helper.junit_details(report)
            self.assertEqual(counts, (2, 0, 1, 1))
            self.assertEqual([case["status"] for case in cases], ["failed", "error"])
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
            self.assertEqual(len(report["executed_commands"]), len(spec["tests"]))
            self.assertEqual(report["selected_components"], ["surrogate_nulls"])
            self.assertIn("tools/surrogate_nulls/nulls.py", report["selected_paths"]["surrogate_nulls"])
            for command in calls:
                self.assertIn("scripts/run_tests_isolated.py", command)
                self.assertEqual(command[command.index("--batch-size") + 1], "1")
                self.assertEqual(command[command.index("--timeout-s") + 1], "120")
            execution = report["components"][0]["executions"][0]
            self.assertEqual(execution["status"], "FAIL")
            self.assertEqual(execution["failure_classification"], "candidate_tests_skipped")
            self.assertEqual(execution["test_cases"], [{"name": "", "status": "skipped"}])

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
