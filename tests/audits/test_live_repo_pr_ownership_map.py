"""Offline structural checks for the dated PR ownership/status snapshot."""

from __future__ import annotations

import importlib.util
import ast
import copy
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


def _write_valid_runner_telemetry(command):
    report_path = Path(command[command.index("--report") + 1])
    test_file = command[-1]
    report_path.write_text(json.dumps({
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
    }), encoding="utf-8")


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

    def test_snapshot_explicitly_separates_facts_inferences_and_unknowns(self):
        doc = _load(AUDIT)
        boundaries = doc["assessment_boundaries"]
        self.assertEqual(set(boundaries), {"facts", "inferences", "unknowns"})
        for category in boundaries.values():
            self.assertTrue(category)
            self.assertTrue(all(isinstance(item, str) and item.strip() for item in category))
        self.assertTrue(any("required" in item.lower() and "unknown" in item.lower() for item in boundaries["unknowns"]))
        schema = _load(SCHEMA)
        self.assertEqual(set(schema["properties"]["assessment_boundaries"]["required"]), set(boundaries))

    def test_open_inventory_ids_shas_and_relative_paths_are_valid(self):
        doc = _load(AUDIT)
        prs = doc["pull_requests"]
        numbers = [pr["number"] for pr in prs]
        self.assertEqual(numbers, sorted(set(numbers)))
        self.assertEqual(numbers, doc["scope"]["open_pr_numbers"])
        self.assertEqual(len(numbers), doc["scope"]["open_pr_count"])
        self.assertIn(425, numbers)
        for pr in prs:
            self.assertEqual(set(pr["writer"]), {"login", "identity_state"})
            self.assertIn(pr["writer"]["identity_state"], {"known", "unknown"})
            self.assertEqual(pr["writer"]["identity_state"] == "known", bool(pr["writer"]["login"]))
            for key in ("base_sha", "head_sha"):
                self.assertRegex(pr["base"]["sha"] if key == "base_sha" else pr["head"]["sha"], r"^[0-9a-f]{40}$")
            for path in pr["changed_paths"]:
                self.assertNotIn("\x00", path)
                self.assertFalse(PurePosixPath(path).is_absolute())
                self.assertFalse(PureWindowsPath(path).is_absolute())
                self.assertFalse(PureWindowsPath(path).drive)
                self.assertNotIn("..", PurePosixPath(path).parts)

    def test_candidate_test_ownership_is_derived_from_exact_pr_changed_paths(self):
        doc = _load(AUDIT)
        by_number = {pr["number"]: pr for pr in doc["pull_requests"]}
        pair_records = doc["candidate_pair_ownership"]
        snapshot_components = doc["main_ci"]["round6_candidate_discovery"]["components"]
        snapshot_component_names = {component["name"] for component in snapshot_components}
        self.assertEqual(
            len(pair_records),
            sum(len(component.get("candidate_pairs", ())) for component in snapshot_components),
        )
        self.assertTrue(any(owner["pr_number"] == 427 and owner["pr_state"] == "merged"
                            for pair in pair_records for owner in pair["test_owners"]))
        for record in pair_records:
            self.assertIn(record["component"], snapshot_component_names)
            for path_key, owners_key in (("implementation_path", "implementation_owners"), ("test_path", "test_owners")):
                path = record[path_key]
                self.assertFalse(PurePosixPath(path).is_absolute())
                self.assertFalse(PureWindowsPath(path).drive)
                self.assertNotIn("..", PurePosixPath(path).parts)
                seen = set()
                for owner in record[owners_key]:
                    self.assertNotIn(owner["pr_number"], seen)
                    seen.add(owner["pr_number"])
                    self.assertRegex(owner["head_sha"], r"^[0-9a-f]{40}$")
                    self.assertIn(owner["writer"]["identity_state"], {"known", "unknown"})
                    if owner["pr_state"] == "open":
                        pr = by_number[owner["pr_number"]]
                        self.assertIn(path, pr["changed_paths"])
                        self.assertEqual(owner["head_sha"], pr["head"]["sha"])
                        self.assertEqual(owner["writer"], pr["writer"])
                    else:
                        self.assertEqual((owner["pr_number"], owner["pr_state"]), (427, "merged"))
        schema = _load(SCHEMA)
        self.assertIn("candidate_pair_ownership", schema["required"])
        self.assertIn("writer", schema["$defs"]["pull_request"]["required"])
        self.assertEqual(
            set(schema["properties"]["candidate_pair_ownership"]["items"]["required"]),
            {"component", "implementation_path", "implementation_owners", "test_path", "test_owners"},
        )

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

    def test_pr_failure_groups_are_classified_against_main_without_root_cause_inference(self):
        doc = _load(AUDIT)
        awareness = next(item for item in doc["ci_failure_groups"] if item["id"] == "check_awareness_tests")
        self.assertIn(429, awareness["pr_numbers"])
        self.assertEqual(awareness["main_equivalent_status"], "success")
        self.assertEqual(awareness["classification"], "confirmed_only_on_PR_heads")
        self.assertIn("3 failures", awareness["notes"])
        self.assertIn("ENGINEERING_EXECUTION_COMPLETE", awareness["notes"])
        self.assertIn("EXECUTION_FAILED", awareness["notes"])

    def test_candidate_discovery_snapshot_is_complete_and_reports_local_limitations(self):
        doc = _load(AUDIT)
        by_number = {pr["number"]: pr for pr in doc["pull_requests"]}
        discovery = doc["main_ci"]["round6_candidate_discovery"]
        self.assertEqual(discovery["helper_path"], ".github/workflows/round6_experimental_tests.py")
        # The checked-in ownership map is a timestamped historical snapshot,
        # not a live mirror of the current helper registry. Validate its own
        # declared inventory here; live mappings are tested separately below.
        self.assertEqual(discovery["component_count"], len(discovery["components"]))
        self.assertEqual(
            discovery["candidate_pair_count"],
            sum(len(component["candidate_pairs"]) for component in discovery["components"]),
        )
        recorded = {item["name"]: item for item in discovery["components"]}
        self.assertEqual(len(recorded), len(discovery["components"]))
        for name, component in recorded.items():
            test_files = set(component["test_files"])
            self.assertTrue(component["candidate_pairs"])
            self.assertTrue(test_files)
            self.assertTrue(all(pair["test"] in test_files for pair in component["candidate_pairs"]))
            support_records = component["support_files"]
            for support in support_records:
                self.assertTrue(support["test_files"])
                self.assertTrue(set(support["test_files"]).issubset(test_files))
                for owner in support["owners"]:
                    if owner["pr_state"] == "open":
                        self.assertIn(support["path"], by_number[owner["pr_number"]]["changed_paths"])
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
            self.assertRegex(run["tested_checkout_sha"], r"^[0-9a-f]{40}$")
            self.assertGreater(run["run_id"], 0)
            self.assertGreater(run["isolated_batches_total"], 0)
            self.assertGreaterEqual(run["isolated_batches_failed"], 0)
            self.assertGreaterEqual(run["isolated_batches_skipped"], 0)
            self.assertTrue(run["candidate_test_paths"])
            self.assertTrue(run["candidate_tests_executed"])
            self.assertGreater(run["test_case_count"], 0)
            self.assertTrue(run["workflow_run_url"].startswith("https://github.com/"))
            self.assertTrue(run["artifact_url"].startswith("https://github.com/"))
            if run["conclusion"] == "success":
                self.assertEqual(run["component_status"], "PASS")
                self.assertEqual(run["isolated_batches_failed"], 0)
                self.assertEqual(run["isolated_batches_skipped"], 0)

    def test_unknown_branch_gate_and_candidate_blockage_are_not_reported_as_pass(self):
        doc = _load(AUDIT)
        self.assertEqual(doc["required_check_configuration"]["state"], "unknown")
        discovery = doc["main_ci"]["round6_candidate_discovery"]
        self.assertEqual(discovery["local_candidate_probe"]["status"], "blocked")
        self.assertTrue(all(not p["candidate_tests_executed"] for p in discovery["local_candidate_probe"]["candidate_probes"]))
        for probe in discovery["local_candidate_probe"]["candidate_probes"]:
            self.assertEqual(probe["collected_test_count"], 0)
            self.assertEqual(probe["result_status"], "BLOCKED")
            self.assertEqual(probe["runner_status"], "BLOCKED")
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
            self.assertRegex(lane["note"], r"\d+/\d+ mapped candidate source/test files exist")

    def test_workflow_runs_mapped_candidate_tests_and_does_not_call_absence_a_pass(self):
        workflow = (ROOT / ".github/workflows/required-checks.yml").read_text(encoding="utf-8")
        self.assertIn("round6_experimental_tests.py", workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("DIFF_BASE_SHA:", workflow)
        self.assertIn("DIFF_HEAD_SHA:", workflow)
        self.assertIn("TESTED_CHECKOUT_SHA:", workflow)
        self.assertIn("WORKFLOW_SHA:", workflow)
        self.assertIn("--diff-base", workflow)
        self.assertIn("--diff-head", workflow)
        self.assertIn("--tested-checkout", workflow)
        self.assertNotIn("--always-component surrogate_nulls", workflow)
        self.assertIn("outputs/round6_experimental_ci_report.json", workflow)
        self.assertIn("outputs/round6-experimental-logs/**", workflow)
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
            "docker_context_policy": (".dockerignore", "tests/docker_context/test_docker_engine_build_context.py"),
            "finite_jitter_geometry_audit": ("tools/audit_finite_jitter_triangulation.py", "tests/test_finite_jitter_triangulation_audit.py"),
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
            {"implementation": "tools/surrogate_nulls/nulls.py", "test": "tests/surrogate_nulls/test_adversarial_contracts.py"},
            helper.COMPONENTS["surrogate_nulls"]["candidate_pairs"],
        )
        self.assertIn(
            {"implementation": "neurotopology_sim/experimental/preprocessing/spherical_csd.py", "test": "tests/experimental/test_spherical_csd_parity.py"},
            helper.COMPONENTS["spherical_csd"]["candidate_pairs"],
        )
        self.assertIn(
            {"implementation": "shared/bids_inventory_audit/paths.py", "test": "tests/bids_inventory_audit/test_privacy_boundary.py"},
            helper.COMPONENTS["bids_inventory_audit"]["candidate_pairs"],
        )
        self.assertEqual(helper.COMPONENT_OWNER_PRS["surrogate_nulls"], (417, 430))
        self.assertEqual(helper.COMPONENT_OWNER_PRS["docker_context_policy"], (431, 434))
        self.assertEqual(helper.select_components({"tests/surrogate_nulls/test_adversarial_contracts.py"}), ["surrogate_nulls"])
        self.assertEqual(helper.select_components({"tests/docker_context/test_docker_engine_build_context.py"}), ["docker_context_policy"])
        self.assertIn("tests/dmd_ep2_oracle/test_oracle.py", helper._unmapped_candidate_paths({"tests/dmd_ep2_oracle/test_oracle.py"}))

    def test_unmapped_candidate_scan_ignores_shared_unrelated_test_roots(self):
        helper = _helper()
        self.assertEqual(
            helper._unmapped_candidate_paths({"tests/experimental/test_unrelated_suite.py"}),
            [],
        )
        self.assertEqual(
            helper._unmapped_candidate_paths({"tests/surrogate_nulls/test_unregistered.py"}),
            ["tests/surrogate_nulls/test_unregistered.py"],
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

    def test_test_support_files_map_to_real_test_pairs_and_fail_closed(self):
        helper = _helper()
        expected = {
            "spherical_csd": "tests/mne_csd_reference_audit/conftest.py",
            "surrogate_audit": "tests/surrogate_audit/fixtures.py",
            "provenance_join": "tests/tools/batch3_provenance_join/helpers.py",
        }
        for component, support_path in expected.items():
            with self.subTest(component=component):
                spec = helper.COMPONENTS[component]
                mapped_tests = spec["support_files"][support_path]
                self.assertTrue(mapped_tests)
                self.assertTrue(set(mapped_tests) <= set(spec["tests"]))
                self.assertEqual(helper._unmapped_candidate_paths({support_path}), [])
                with TemporaryDirectory() as td:
                    root = Path(td)
                    support = root / support_path
                    support.parent.mkdir(parents=True, exist_ok=True)
                    support.write_text("# test support fixture\n", encoding="utf-8")
                    relevant_pairs = [pair for pair in spec["candidate_pairs"] if pair["test"] in mapped_tests]
                    for pair in relevant_pairs:
                        for relative in (pair["implementation"], pair["test"]):
                            target = root / relative
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_text("# mapped candidate fixture\n", encoding="utf-8")
                    result = helper.inspect_component(component, root, {support_path})
                    self.assertEqual(result["status"], "READY_TO_RUN", result["blockers"])
                    self.assertEqual(result["tests_to_run"], list(dict.fromkeys(pair["test"] for pair in relevant_pairs)))
                    self.assertEqual(result["selected_support_files"], [support_path])
                    self.assertIn(support_path, result["selected_paths"])

                    support.unlink()
                    missing = helper.inspect_component(component, root, {support_path})
                    self.assertEqual(missing["status"], "BLOCKED")
                    self.assertEqual(missing["missing_support_files"], [support_path])

    def test_support_mapping_to_unpaired_test_is_blocked(self):
        helper = _helper()
        component_spec = copy.deepcopy(helper.COMPONENTS["spherical_csd"])
        support_path = "tests/mne_csd_reference_audit/conftest.py"
        unpaired_test = "tests/mne_csd_reference_audit/test_unpaired_candidate.py"
        component_spec["tests"] = (*component_spec["tests"], unpaired_test)
        component_spec["support_files"][support_path] = (
            *component_spec["support_files"][support_path],
            unpaired_test,
        )
        with patch.dict(helper.COMPONENTS, {"spherical_csd": component_spec}):
            with TemporaryDirectory() as td:
                root = Path(td)
                support = root / support_path
                support.parent.mkdir(parents=True, exist_ok=True)
                support.write_text("# support fixture\n", encoding="utf-8")
                for pair in component_spec["candidate_pairs"]:
                    if pair["test"] not in component_spec["support_files"][support_path]:
                        continue
                    for relative in (pair["implementation"], pair["test"]):
                        target = root / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text("# candidate fixture\n", encoding="utf-8")

                result = helper.inspect_component("spherical_csd", root, {support_path})

        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn(unpaired_test, result["invalid_support_test_mappings"])

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
                _write_valid_runner_telemetry(command)
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

    def test_missing_bounded_runner_dependency_is_explicit_and_not_a_skip_or_pass(self):
        helper = _helper()
        pair = helper.COMPONENTS["simulation_grid_planner"]["candidate_pairs"][0]
        with TemporaryDirectory() as td:
            root = Path(td)
            for relative in (pair["implementation"], pair["test"]):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("# fixture\n", encoding="utf-8")

            def missing_timeout_plugin(command, **kwargs):
                kwargs["stderr"].write(b"RuntimeError: pytest-timeout is required for bounded isolated execution\n")
                return SimpleNamespace(returncode=1)

            report_path = root / "report.json"
            with patch.object(helper, "collect_changed_paths", return_value={pair["implementation"]}), patch.object(
                helper.subprocess, "run", side_effect=missing_timeout_plugin
            ):
                result = helper.run(root, "0" * 40, "1" * 40, report_path)
            report = _load(report_path)
        execution = report["components"][0]["executions"][0]
        self.assertEqual(result, 1)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(execution["status"], "BLOCKED")
        self.assertEqual(execution["failure_classification"], "runner_dependency_unavailable")
        self.assertEqual(execution["result_counts"]["collected"], 0)
        self.assertFalse(execution["isolated_runner_telemetry_valid"])
        self.assertIn("pytest-timeout is required", execution["runner_stderr_tail"])

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
                _write_valid_runner_telemetry(command)
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
                result = helper.run(
                    root, "0" * 40, "1" * 40, report_path,
                    always_components=["surrogate_nulls"],
                )

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
            self.assertEqual(execution["artifact_path"], "round6-experimental-logs/01-surrogate_nulls-01")

    def test_always_component_is_not_applicable_only_when_its_inventory_is_absent(self):
        helper = _helper()
        with TemporaryDirectory() as td:
            root = Path(td)
            report_path = root / "report.json"
            with patch.object(helper, "collect_changed_paths", return_value={"docs/unrelated.md"}), patch.object(
                helper.subprocess, "run", side_effect=AssertionError("absent optional lane must not execute")
            ):
                result = helper.run(
                    root, "0" * 40, "1" * 40, report_path,
                    always_components=["surrogate_nulls"],
                )
            report = _load(report_path)
        self.assertEqual(result, 0)
        self.assertEqual(report["status"], "NOT_APPLICABLE")
        self.assertEqual(report["not_applicable_components"], ["surrogate_nulls"])
        self.assertEqual(report["components"][0]["status"], "NOT_APPLICABLE")
        self.assertNotEqual(report["components"][0]["status"], "PASS")

    def test_always_component_blocks_partial_inventory_and_requires_every_pair(self):
        helper = _helper()
        spec = helper.COMPONENTS["surrogate_nulls"]
        with TemporaryDirectory() as td:
            root = Path(td)
            partial_source = root / spec["implementation_any"][0]
            partial_source.parent.mkdir(parents=True)
            partial_source.write_text("# present but incomplete\n", encoding="utf-8")
            report_path = root / "report.json"
            with patch.object(helper, "collect_changed_paths", return_value={"docs/unrelated.md"}), patch.object(
                helper.subprocess, "run", side_effect=AssertionError("incomplete inventory must not execute")
            ):
                result = helper.run(
                    root, "0" * 40, "1" * 40, report_path,
                    always_components=["surrogate_nulls"],
                )
            report = _load(report_path)
        self.assertEqual(result, 1)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["components"][0]["require_all_pairs"], True)
        self.assertTrue(report["components"][0]["missing_required_tests"])

    def test_source_identity_binds_git_blob_and_direct_import_paths(self):
        helper = _helper()
        with TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            module_paths = list(helper.COMPONENTS["surrogate_nulls"]["module_imports"].values())
            for relative in ("tools/surrogate_nulls/__init__.py", *module_paths):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("VALUE = 1\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
            subprocess.run([
                "git", "-C", str(root), "-c", "user.name=Fixture", "-c",
                "user.email=fixture@example.invalid", "commit", "-qm", "fixture",
            ], check=True, capture_output=True)
            commit = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            result = helper.verify_candidate_source_identity(root, "surrogate_nulls", module_paths, commit)
            self.assertEqual(result["status"], "PASS", result["errors"])
            self.assertTrue(all(item["matches_tested_commit"] for item in result["implementation_files"]))
            self.assertTrue(all(item["matches_expected_source"] for item in result["module_imports"]))
            self.assertTrue(all(not Path(item["resolved_path"]).is_absolute() for item in result["module_imports"]))

            (root / module_paths[0]).write_text("VALUE = 2\n", encoding="utf-8")
            changed = helper.verify_candidate_source_identity(root, "surrogate_nulls", module_paths, commit)
            self.assertEqual(changed["status"], "FAIL")
            self.assertIn("working source does not match tested commit", changed["errors"][0])

    def test_runner_telemetry_requires_exact_file_singleton_and_zero_skips_failures_and_timeouts(self):
        helper = _helper()
        expected = "tests/example/test_contract.py"
        valid = {
            "completed": True,
            "exit_code": 0,
            "summary": {
                "total_files": 1, "total_batches": 1, "passed_batches": 1,
                "skipped_batches": 0, "failed_batches": 0, "timeout_batches": 0,
                "duration_s": 0.1,
                "overall_exit_code": 0,
            },
            "batches": [{
                "batch_index": 1, "batch_number": 1,
                "status": "passed", "exit_code": 0, "test_files": [expected],
                "duration_s": 0.1, "peak_memory_mb": None, "failures": [],
                "stdout_tail": "1 passed in 0.01s\n", "stderr_tail": "", "files": [expected],
                "timed_out": False, "timeout_status": "completed",
            }],
        }
        ok, error, _ = helper._isolated_runner_report_is_valid(valid, expected)
        self.assertTrue(ok, error)
        for mutation in (
            {"completed": False},
            {"exit_code": 1},
            {"summary": {**valid["summary"], "skipped_batches": 1}},
            {"summary": {**valid["summary"], "timeout_batches": 1}},
            {"summary": {key: value for key, value in valid["summary"].items() if key != "duration_s"}},
            {"batches": [{**valid["batches"][0], "test_files": ["tests/other.py"]}]},
            {"batches": [{**valid["batches"][0], "timed_out": True}]},
            {"batches": [{key: value for key, value in valid["batches"][0].items() if key != "batch_number"}]},
            {"batches": [{**valid["batches"][0], "duration_s": float("nan")}]},
        ):
            candidate = {**valid, **mutation}
            ok, error, _ = helper._isolated_runner_report_is_valid(candidate, expected)
            self.assertFalse(ok, mutation)
            self.assertTrue(error)
        with self.assertRaises(ValueError):
            helper._strict_json_loads('{"memory_mb":NaN}')

    def test_actual_checkout_run_records_exact_sha_source_test_and_counts(self):
        helper = _helper()
        with TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            subprocess.run([
                "git", "-C", str(root), "-c", "user.name=Fixture", "-c",
                "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "base",
            ], check=True, capture_output=True)
            base = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            pair = helper.COMPONENTS["simulation_grid_planner"]["candidate_pairs"][0]
            for relative, content in (
                (pair["implementation"], "VALUE = 1\n"),
                (pair["test"], "# deterministic fixture test\n"),
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
            subprocess.run([
                "git", "-C", str(root), "-c", "user.name=Fixture", "-c",
                "user.email=fixture@example.invalid", "commit", "-qm", "candidate",
            ], check=True, capture_output=True)
            head = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            report_path = root / "report.json"
            real_run = subprocess.run

            def candidate_runner(command, **kwargs):
                if "scripts/run_tests_isolated.py" not in command:
                    return real_run(command, **kwargs)
                _write_valid_runner_telemetry(command)
                junit_arg = next(arg for arg in command if arg.startswith("--pytest-arg=--junitxml="))
                Path(junit_arg.removeprefix("--pytest-arg=--junitxml=")).write_text(
                    '<testsuite tests="1"><testcase classname="fixture" name="passes"/></testsuite>',
                    encoding="utf-8",
                )
                return SimpleNamespace(returncode=0)

            with patch.object(helper.subprocess, "run", side_effect=candidate_runner):
                result = helper.run(
                    root, base, head, report_path,
                    tested_checkout_sha=head, workflow_sha=base, event_name="pull_request",
                    require_checkout_match=True,
                )
            report = _load(report_path)
        self.assertEqual(result, 0)
        self.assertEqual(report["status"], "PASS")
        execution = report["components"][0]["executions"][0]
        self.assertEqual(execution["tested_checkout_sha"], head)
        self.assertEqual(execution["workflow_sha"], base)
        self.assertEqual(execution["test_file"], pair["test"])
        self.assertEqual(execution["implementation_paths"], [pair["implementation"]])
        self.assertEqual(execution["result_counts"], {
            "collected": 1, "passed": 1, "skipped": 0, "failed": 0, "errors": 0, "timeouts": 0,
        })
        self.assertEqual(execution["artifact_path"], "round6-experimental-logs/01-simulation_grid_planner-01")

    def test_stale_checkout_is_blocked_before_any_test_execution(self):
        helper = _helper()
        with TemporaryDirectory() as td:
            root = Path(td)
            report_path = root / "report.json"
            with patch.object(helper, "collect_changed_paths", return_value={"docs/unrelated.md"}), patch.object(
                helper.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="1" * 40 + "\n")
            ):
                result = helper.run(
                    root, "0" * 40, "2" * 40, report_path,
                    tested_checkout_sha="2" * 40, workflow_sha="3" * 40,
                    event_name="pull_request", require_checkout_match=True,
                )
            report = _load(report_path)
        self.assertEqual(result, 1)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("does not match", report["selection_error"])
        self.assertEqual(report["executed_commands"], [])

    def test_report_and_artifact_paths_cannot_escape_checkout_root(self):
        helper = _helper()
        with TemporaryDirectory() as td:
            parent = Path(td)
            root = parent / "checkout"
            root.mkdir()
            outside_report = parent / "escaped-report.json"
            with patch.object(
                helper, "collect_changed_paths",
                side_effect=AssertionError("path containment must be checked before git/test execution"),
            ):
                with self.assertRaisesRegex(ValueError, "inside the checked-out repository"):
                    helper.run(root, "0" * 40, "1" * 40, outside_report)

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
