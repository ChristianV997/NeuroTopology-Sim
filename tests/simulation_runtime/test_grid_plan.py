"""Fail-closed tests for the synthetic benchmark grid plan.

These tests do not launch a simulation, download data, or install packages.
Gate fixtures are temporary JSON files shaped like evidence-promotion reports.
They are not a gate registry.
"""

from __future__ import annotations

import copy
import inspect
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from analysis.binomial_planning.planner import plan_sample_size
from tools.evidence_promotion_gate.reporting import results_payload, write_report
from tools.evidence_promotion_gate.schema import (
    PROMOTION_DECISIONS,
    SCHEMA_VERSION as EVIDENCE_SCHEMA_VERSION,
    PromotionResult,
)
from tools.simulation_runtime.atomic_io import compute_config_hash
from tools.simulation_runtime import grid_plan as grid_plan_module
from tools.simulation_runtime.grid_plan import (
    ADMISSIBLE_GATE_DECISIONS,
    AUDITED_MAIN_SHA,
    BLOCKING_GATE_IDS,
    GATE_INTEGRATION_STATE,
    NONBLOCKING_GATE_IDS,
    NULL_MODEL_NOTE,
    REQUIRED_GATE_IDS,
    RUN_STATES,
    TEST_FIXTURE_NOT_EVIDENCE,
    TOY_FIXTURE_LABEL,
    GridPlan,
    GridPlanError,
    dry_run,
    execute,
)
from tools.simulation_runtime.types import CampaignManifest, Outcome


CHECKED_AT = "2026-01-02T00:00:00+00:00"


def _git(*args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise unittest.SkipTest("git binary not available")
    if completed.returncode != 0:
        raise AssertionError(completed.stderr.strip() or "git failed")
    return completed.stdout.strip()


def _git_cwd(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def _local_main_sha(test: unittest.TestCase) -> str:
    """Prefer origin/main, then main.

    ``skipTest`` only when the git binary is missing. An unresolvable ref
    or any other git error fails the test.
    """

    errors: list[str] = []
    try:
        for ref in ("origin/main", "main"):
            completed = _git_cwd("rev-parse", "--verify", ref)
            sha = completed.stdout.strip()
            if completed.returncode == 0 and len(sha) == 40:
                return sha
            detail = (completed.stderr or completed.stdout).strip() or "unresolved"
            errors.append(f"{ref}: {detail}")
    except FileNotFoundError:
        test.skipTest("git binary not available")
    test.fail(
        "unresolvable origin/main and main; a local main ref is required. "
        + "; ".join(errors)
    )
    return ""


def _require_audited_main_ancestor(test: unittest.TestCase) -> str:
    """Return local main when ``AUDITED_MAIN_SHA`` is an ancestor of it.

    ``skipTest`` only when the git binary is missing. A shallow clone, a
    non-repository, an unresolvable main ref, a missing object, a
    non-ancestor, or any other git error fails the test.
    """

    try:
        shallow = _git_cwd("rev-parse", "--is-shallow-repository")
    except FileNotFoundError:
        test.skipTest("git binary not available")
    if shallow.returncode != 0:
        detail = (shallow.stderr or shallow.stdout).strip() or "git rev-parse failed"
        test.fail(
            "git error: ancestry of AUDITED_MAIN_SHA cannot be verified "
            f"({detail})"
        )
    if shallow.stdout.strip() == "true":
        test.fail(
            "shallow clone: ancestry of AUDITED_MAIN_SHA cannot be verified; "
            "fetch full history"
        )
    main_sha = ""
    ref_errors: list[str] = []
    for ref in ("origin/main", "main"):
        completed = _git_cwd("rev-parse", "--verify", ref)
        sha = completed.stdout.strip()
        if completed.returncode == 0 and len(sha) == 40:
            main_sha = sha
            break
        detail = (completed.stderr or completed.stdout).strip() or "unresolved"
        ref_errors.append(f"{ref}: {detail}")
    if not main_sha:
        test.fail(
            "unresolvable origin/main and main: ancestry of AUDITED_MAIN_SHA "
            "cannot be verified. " + "; ".join(ref_errors)
        )
    present = _git_cwd("cat-file", "-e", AUDITED_MAIN_SHA)
    if present.returncode != 0:
        detail = (present.stderr or present.stdout).strip()
        test.fail(
            f"missing AUDITED_MAIN_SHA object {AUDITED_MAIN_SHA}; "
            "ancestry cannot be verified; fetch full history"
            + (f" ({detail})" if detail else "")
        )
    ancestor = _git_cwd("merge-base", "--is-ancestor", AUDITED_MAIN_SHA, main_sha)
    if ancestor.returncode != 0:
        detail = (ancestor.stderr or ancestor.stdout).strip()
        test.fail(
            f"AUDITED_MAIN_SHA {AUDITED_MAIN_SHA} is not an ancestor of main {main_sha}"
            + (f" ({detail})" if detail else "")
        )
    return main_sha


def _spy_calls():
    calls = []

    def spy(*args, **kwargs):
        calls.append((args, kwargs))

    return calls, spy


def _base_config(**overrides):
    config = {
        "schema_version": "grid_plan_v2",
        "axes": [
            {
                "name": "snr_db",
                "unit": "dB",
                "values": [-6, 0, 6],
                "minimum": -6,
                "maximum": 6,
            }
        ],
        "null_model_ids": ["synthetic_iaaft"],
        "source_model_ids": ["synthetic_single_dipole"],
        "master_seed": 100,
        "calibration_seed": 11,
        "evaluation_seed": 29,
        "independent_unit": "simulation_seed",
        "n_independent_calibration": 24,
        "n_positive_calibration": 12,
        "n_negative_calibration": 12,
        "n_independent_evaluation": 24,
        "n_positive_evaluation": 12,
        "n_negative_evaluation": 12,
        "nested_unit": "none",
        "nested_per_unit": 1,
        "interval_method": "wilson_on_independent_unit",
        "estimand": "score contrast between synthetic source and null labels",
        "power_claim": "none",
        "h0": "source and null labels share the same score distribution",
        "h1": "source and null labels differ in the score distribution",
        "score_definition_id": "score_ref_unspecified_v0",
        "threshold": {"kind": "fixed_reference", "cutoff": 0.5},
        "wilson_confidence_level": 0.95,
        "wilson_target_full_width": 0.5,
        "wilson_design_p": None,
        "max_cells": 16,
        "max_trials": 1000,
        "max_compute_units": 10000.0,
        "compute_units_per_trial": 1.0,
    }
    config.update(overrides)
    return config


def _promotion(case_id: str, decision: str = "ADMISSIBLE_FOR_ENGINEERING_REPORT") -> PromotionResult:
    return PromotionResult(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        case_id=case_id,
        promotion_decision=decision,
        reason_codes=(),
        reasons=(),
        declared_evidence_class="engineering_fact",
        allowed_evidence_class="engineering_fact",
        synthetic_demo=True,
        scientific_pass=False,
        scientific_eligibility=False,
        formal_bayes_factor=None,
        declared_formal_bayes_factor=None,
        claim_gate=None,
        input_fingerprints={},
    )


def _write_report(directory: Path, rows: list[dict], *, name: str = "report.json") -> Path:
    payload = results_payload([_promotion(row["case_id"], row.get("decision", "ADMISSIBLE_FOR_ENGINEERING_REPORT")) for row in rows])
    for item, row in zip(payload["results"], rows):
        if "verified_at_commit" in row:
            item["verified_at_commit"] = row["verified_at_commit"]
        if "scientific_pass" in row:
            item["scientific_pass"] = row["scientific_pass"]
        if "promotion_decision" in row:
            item["promotion_decision"] = row["promotion_decision"]
    if rows and rows[0].get("file_scientific_pass") is True:
        payload["scientific_pass"] = True
    path = directory / name
    write_report(payload, path)
    return path


def _statuses(plan):
    return {item["gate_id"]: item["status"] for item in plan.gate_resolution}


def _assert_all_cells_blocked(test: unittest.TestCase, plan) -> None:
    test.assertGreater(len(plan.cells), 0)
    for cell in plan.cells:
        test.assertTrue(cell["blocked"])
        test.assertFalse(cell["evaluation_eligible"])
        test.assertFalse(cell["parameter_case"]["executable"])
        test.assertEqual(cell["power_claim"], "none")
        test.assertEqual(cell["independent_unit"], "simulation_seed")


def _assert_seven_non_admissible(test: unittest.TestCase, plan) -> None:
    statuses = _statuses(plan)
    test.assertEqual(set(statuses), set(BLOCKING_GATE_IDS) | set(NONBLOCKING_GATE_IDS))
    for gate_id in BLOCKING_GATE_IDS:
        test.assertNotEqual(statuses[gate_id], "admissible_on_ancestor")
        test.assertFalse(plan.gate_resolution[list(BLOCKING_GATE_IDS).index(gate_id)]["integration_is_evidence"])
    test.assertFalse(plan.gate_check["opened"])
    test.assertEqual(plan.run_state, "blocked")
    test.assertFalse(plan.execution["simulation_invoked"])
    test.assertFalse(plan.execution["launched"])
    _assert_all_cells_blocked(test, plan)


def _write_forged_reports(directory: Path, commit: str) -> None:
    """One admissible case_id per file, so a directory scan could open each gate."""

    for gate_id in BLOCKING_GATE_IDS:
        _write_report(
            directory,
            [
                {
                    "case_id": gate_id,
                    "promotion_decision": "ADMISSIBLE_FOR_ENGINEERING_REPORT",
                    "verified_at_commit": commit,
                }
            ],
            name=f"_forged_{gate_id}.json",
        )


def _git_result(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr="")


@contextmanager
def _resolved_main():
    """Treat this checkout as non-shallow so report resolution can be asserted.

    The cloud checkout is shallow. Production fail-closes on that, which is
    covered separately. These tests need the branch that resolves local main
    and then refuses worktree files. Only the shallow probe is replaced.
    """

    real_git = grid_plan_module._git

    def wrapped(args):
        if list(args)[:2] == ["rev-parse", "--is-shallow-repository"]:
            return _git_result("false\n")
        return real_git(args)

    with patch.object(grid_plan_module, "_git", side_effect=wrapped):
        yield


class _Probe(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reads: list[str] = []

    def __getitem__(self, key):
        self.reads.append(key)
        return super().__getitem__(key)


class GridPlanTests(unittest.TestCase):
    def test_campaign_manifest_v1_gap_is_still_true(self):
        fields = set(CampaignManifest.__dataclass_fields__)
        self.assertIn("configuration_hash", fields)
        self.assertIn("seed", fields)
        self.assertIn("units", fields)
        self.assertNotIn("run_state", fields)
        self.assertNotIn("gate_evidence", fields)
        self.assertNotIn("planned", {item.value for item in Outcome})
        self.assertEqual(Outcome.PASS.value, "PASS")
        self.assertNotIn("PASS", RUN_STATES)
        promotion_fields = set(PromotionResult.__dataclass_fields__)
        self.assertIn("promotion_decision", promotion_fields)
        self.assertIn("case_id", promotion_fields)
        self.assertNotIn("verified_at_commit", promotion_fields)
        self.assertNotIn("artifact_sha256", promotion_fields)
        self.assertEqual(REQUIRED_GATE_IDS, BLOCKING_GATE_IDS)
        self.assertIn("ci_discovery", BLOCKING_GATE_IDS)
        self.assertEqual(NONBLOCKING_GATE_IDS, ("dmd_crouzeix",))
        self.assertEqual(GATE_INTEGRATION_STATE["ci_discovery"], "BLOCKED")
        self.assertEqual(GATE_INTEGRATION_STATE["dmd_crouzeix"], "NONBLOCKING")
        self.assertEqual(AUDITED_MAIN_SHA, "f6951115bcbf83b75bf20481085a5dad9c25c7e6")

    def test_admissible_decisions_are_read_from_evidence_schema(self):
        self.assertTrue(ADMISSIBLE_GATE_DECISIONS)
        self.assertTrue(all(item.startswith("ADMISSIBLE_") for item in ADMISSIBLE_GATE_DECISIONS))
        for decision in PROMOTION_DECISIONS:
            if decision.startswith("ADMISSIBLE_"):
                self.assertIn(decision, ADMISSIBLE_GATE_DECISIONS)
            else:
                self.assertNotIn(decision, ADMISSIBLE_GATE_DECISIONS)
        self.assertNotIn("PASS", ADMISSIBLE_GATE_DECISIONS)
        self.assertNotIn("VERIFIED", ADMISSIBLE_GATE_DECISIONS)

    def test_hash_is_the_shared_config_hash_and_is_key_order_invariant(self):
        import tools.simulation_runtime.grid_plan as grid_plan

        self.assertIs(grid_plan.compute_config_hash, compute_config_hash)
        self.assertNotIn("hashlib", grid_plan.__dict__)
        self.assertFalse(hasattr(grid_plan, "run_campaign_manifest"))
        self.assertFalse(hasattr(grid_plan, "SimulationCampaignRunner"))
        source = Path(grid_plan.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"roles_are_disjoint": True', source)
        self.assertNotIn("roles_are_disjoint = True", source)

        forward = dry_run(_base_config())
        reversed_keys = {}
        raw = _base_config()
        for key in reversed(list(raw)):
            reversed_keys[key] = raw[key]
        backward = dry_run(reversed_keys)
        self.assertEqual(forward.config_hash, backward.config_hash)
        self.assertEqual(forward.config_hash, compute_config_hash(forward.hash_payload))
        binding = {
            "h0": raw["h0"],
            "h1": raw["h1"],
            "score_definition_id": raw["score_definition_id"],
            "threshold": raw["threshold"],
            "calibration_unit_ids": list(forward.cells[0]["calibration_unit_ids"]),
            "calibration_seed": raw["calibration_seed"],
            "estimand": raw["estimand"],
            "interval_method": raw["interval_method"],
            "unit_aggregation": "not_required",
            "n_positive_calibration": raw["n_positive_calibration"],
            "n_negative_calibration": raw["n_negative_calibration"],
            "nested_per_unit": raw["nested_per_unit"],
            "unit_score_rule": "max_window_score",
            "calibration_positive_unit_ids": list(forward.cells[0]["calibration_positive_unit_ids"]),
            "calibration_negative_unit_ids": list(forward.cells[0]["calibration_negative_unit_ids"]),
        }
        self.assertEqual(forward.threshold_hash, compute_config_hash(binding))
        self.assertNotIn("evaluation_unit_ids", binding)
        self.assertNotIn("evaluation_seed", binding)
        self.assertNotIn("os.walk", source)
        self.assertEqual(grid_plan._writer_report_paths(), ())
        output = inspect.signature(write_report).parameters["output"]
        self.assertIs(output.default, inspect.Parameter.empty)

    def test_hash_changes_on_parameter_seed_threshold_and_gate_ids(self):
        original = dry_run(_base_config())
        changed_axis = _base_config()
        changed_axis["axes"][0]["values"] = [-6, 0, 3]
        changed_seed = _base_config(master_seed=101)
        changed_threshold = _base_config(threshold={"kind": "fixed_reference", "cutoff": 0.25})
        changed_estimand = _base_config(estimand="a different synthetic contrast")
        self.assertNotEqual(original.config_hash, dry_run(changed_axis).config_hash)
        self.assertNotEqual(original.config_hash, dry_run(changed_seed).config_hash)
        self.assertNotEqual(original.config_hash, dry_run(changed_threshold).config_hash)
        self.assertNotEqual(original.threshold_hash, dry_run(changed_threshold).threshold_hash)
        self.assertNotEqual(original.config_hash, dry_run(changed_estimand).config_hash)
        self.assertNotEqual(original.threshold_hash, dry_run(changed_estimand).threshold_hash)
        changed_interval = _base_config(interval_method="cluster_bootstrap_over_independent_unit")
        changed_calibration_seed = _base_config(calibration_seed=12)
        changed_evaluation_seed = _base_config(evaluation_seed=30)
        self.assertNotEqual(original.threshold_hash, dry_run(changed_interval).threshold_hash)
        self.assertNotEqual(original.threshold_hash, dry_run(changed_calibration_seed).threshold_hash)
        self.assertNotEqual(original.config_hash, dry_run(changed_evaluation_seed).config_hash)
        self.assertEqual(original.threshold_hash, dry_run(changed_evaluation_seed).threshold_hash)
        payload = dict(original.hash_payload)
        payload["blocking_gate_ids"] = list(payload["blocking_gate_ids"][:-1])
        self.assertNotEqual(original.config_hash, compute_config_hash(payload))
        self.assertIn("four_sphere_forward_model", original.hash_payload["blocking_gate_ids"])
        self.assertIn("planar_geometry", original.hash_payload["blocking_gate_ids"])
        self.assertIn("winding", original.hash_payload["blocking_gate_ids"])
        self.assertIn("hodge", original.hash_payload["blocking_gate_ids"])
        self.assertNotIn("winding_hodge", original.hash_payload["blocking_gate_ids"])
        self.assertNotIn("four_sphere_oracle", original.hash_payload["blocking_gate_ids"])
        self.assertNotIn("planar_embedding_winding_hodge", original.hash_payload["blocking_gate_ids"])
        leaked = _base_config(
            n_independent_evaluation=25,
            n_positive_evaluation=13,
            n_negative_evaluation=12,
        )
        self.assertEqual(original.threshold_hash, dry_run(leaked).threshold_hash)
        self.assertNotEqual(original.config_hash, dry_run(leaked).config_hash)
        changed_class = _base_config(
            n_independent_calibration=25,
            n_positive_calibration=13,
            n_negative_calibration=12,
        )
        self.assertNotEqual(original.threshold_hash, dry_run(changed_class).threshold_hash)

    def test_evaluation_ids_are_read_only_after_the_threshold_hash(self):
        probe = _Probe(_base_config())
        plan = dry_run(probe)
        eval_index = probe.reads.index("n_independent_evaluation")
        self.assertLess(probe.reads.index("threshold"), eval_index)
        self.assertLess(probe.reads.index("estimand"), eval_index)
        self.assertLess(probe.reads.index("interval_method"), eval_index)
        self.assertLess(probe.reads.index("calibration_seed"), eval_index)
        self.assertNotIn("evaluation_unit_ids", probe.reads)
        self.assertNotIn("calibration_unit_ids", probe.reads)
        self.assertEqual(plan.evaluation_manifest["threshold_hash"], plan.threshold_hash)
        self.assertTrue(plan.evaluation_manifest["built_after_threshold_hash"])
        self.assertEqual(plan.evaluation_manifest["threshold_order"], "in_process_only_not_preregistration")
        self.assertEqual(
            plan.evaluation_manifest["evaluation_unit_ids"][0],
            "evaluation-pos-seed29-u000000",
        )
        self.assertNotIn("calibration_unit_ids", plan.configuration)
        self.assertNotIn("evaluation_unit_ids", plan.configuration)

        missing = _Probe(_base_config())
        missing.pop("threshold")
        missing.reads.clear()
        with self.assertRaises(GridPlanError) as caught:
            dry_run(missing)
        self.assertEqual(caught.exception.code, "threshold_not_frozen")
        self.assertNotIn("evaluation_unit_ids", missing.reads)
        self.assertNotIn("n_independent_evaluation", missing.reads)

        prebuilt = _base_config(evaluation_manifest={"evaluation_unit_ids": ["evaluation-seed29-u000000"]})
        with self.assertRaises(GridPlanError) as caught:
            dry_run(prebuilt)
        self.assertEqual(caught.exception.code, "evaluation_manifest_before_threshold")

    def test_disjointness_is_computed_from_explicit_id_sets(self):
        plan = dry_run(_base_config())
        cal = plan.cells[0]["calibration_unit_ids"]
        ev = plan.cells[0]["evaluation_unit_ids"]
        self.assertEqual(plan.cells[0]["roles_are_disjoint"], set(cal).isdisjoint(ev))
        self.assertTrue(set(cal).isdisjoint(set(ev)))
        positive = plan.cells[0]["calibration_positive_unit_ids"]
        negative = plan.cells[0]["calibration_negative_unit_ids"]
        self.assertTrue(all(item.startswith("calibration-pos-seed11-u") for item in positive))
        self.assertTrue(all(item.startswith("calibration-neg-seed11-u") for item in negative))
        self.assertEqual(len(positive), 12)
        self.assertEqual(len(negative), 12)
        self.assertEqual(cal, positive + negative)
        self.assertTrue(all(item.startswith("evaluation-pos-seed29-u") for item in plan.cells[0]["evaluation_positive_unit_ids"]))
        self.assertTrue(all(item.startswith("evaluation-neg-seed29-u") for item in plan.cells[0]["evaluation_negative_unit_ids"]))
        groups = [
            set(positive),
            set(negative),
            set(plan.cells[0]["evaluation_positive_unit_ids"]),
            set(plan.cells[0]["evaluation_negative_unit_ids"]),
        ]
        for index, left in enumerate(groups):
            for right in groups[index + 1 :]:
                self.assertTrue(left.isdisjoint(right))
        self.assertEqual(plan.cells[0]["roles_are_disjoint"], True)
        self.assertEqual(len(cal), plan.cells[0]["n_independent_calibration"])
        self.assertNotIn("calibration_trial_index_start", plan.cells[0])
        self.assertNotIn("evaluation_trial_index_start", plan.cells[0])
        self.assertNotIn("calibration_trial_index_start", plan.cells[0]["parameter_case"])
        shared = _base_config(
            calibration_unit_ids=["shared-unit"],
            evaluation_unit_ids=["shared-unit"],
        )
        with self.assertRaises(GridPlanError) as caught:
            dry_run(shared)
        self.assertEqual(caught.exception.code, "caller_unit_ids_rejected")

    def test_windows_are_not_counted_in_n_or_toward_wilson_floors(self):
        nested = _base_config(
            nested_unit="window",
            nested_per_unit=10,
            unit_aggregation="cluster_any_event_rate",
        )
        plan = dry_run(nested)
        self.assertEqual(plan.trial_count, plan.cell_count * (24 + 24))
        self.assertNotEqual(plan.trial_count, plan.cell_count * (24 + 24) * 10)
        self.assertFalse(plan.cells[0]["nested_counted_in_n"])
        self.assertEqual(plan.wilson.required_n, 12)
        self.assertEqual(
            plan.to_dict()["wilson_bound"]["applied_to"],
            [
                "n_positive_calibration",
                "n_negative_calibration",
                "n_positive_evaluation",
                "n_negative_evaluation",
                "n_independent_calibration",
                "n_independent_evaluation",
            ],
        )
        self.assertTrue(plan.to_dict()["wilson_bound"]["nested_per_unit_ignored"])
        bare = dry_run(_base_config())
        self.assertEqual(plan.trial_count, bare.trial_count)
        self.assertNotEqual(plan.config_hash, bare.config_hash)

        window_ids = _base_config(
            calibration_unit_ids=["s1_w0", "s1_w1"],
            evaluation_unit_ids=["s1_w0", "s1_w1"],
            n_independent_calibration=2,
            n_independent_evaluation=2,
            nested_unit="window",
            nested_per_unit=2,
        )
        with self.assertRaises(GridPlanError) as caught:
            dry_run(window_ids)
        self.assertEqual(caught.exception.code, "caller_unit_ids_rejected")
        nested_ids = dry_run(
            _base_config(
                nested_unit="window",
                nested_per_unit=2,
                unit_aggregation="cluster_any_event_rate",
            )
        )
        self.assertEqual(nested_ids.cells[0]["n_independent_calibration"], 24)
        self.assertEqual(len(nested_ids.cells[0]["calibration_unit_ids"]), 24)
        self.assertEqual(len(nested_ids.cells[0]["calibration_positive_unit_ids"]), 12)
        self.assertEqual(nested_ids.trial_count, nested_ids.cell_count * (24 + 24))
        self.assertFalse(any("_w" in item for item in nested_ids.cells[0]["calibration_unit_ids"]))
        self.assertTrue(
            nested_ids.cells[0]["calibration_unit_ids"][0].startswith("calibration-pos-seed11-u")
        )
        self.assertTrue(
            nested_ids.cells[0]["evaluation_unit_ids"][0].startswith("evaluation-pos-seed29-u")
        )
        with self.assertRaises(GridPlanError) as caught:
            grid_plan_module._count_matches_ids(120, ["cal"] * 12, 10, "n_independent_calibration")
        self.assertEqual(caught.exception.code, "windows_counted_in_n")

        with self.assertRaises(GridPlanError) as caught:
            dry_run(_base_config(interval_method="wilson_on_window"))
        self.assertEqual(caught.exception.code, "window_level_interval")
        with self.assertRaises(GridPlanError) as caught:
            dry_run(_base_config(independent_unit="subject"))
        self.assertEqual(caught.exception.code, "synthetic_requires_simulation_seed")
        with self.assertRaises(GridPlanError) as caught:
            dry_run(_base_config(power_claim="adequate"))
        self.assertEqual(caught.exception.code, "power_claim")
        cluster = dry_run(_base_config(interval_method="cluster_bootstrap_over_independent_unit"))
        self.assertEqual(cluster.cells[0]["interval_method"], "cluster_bootstrap_over_independent_unit")
        self.assertEqual(cluster.cells[0]["power_claim"], "none")

    def test_dry_run_lists_blocked_cells_and_never_calls_the_simulation(self):
        calls, spy = _spy_calls()
        plan = dry_run(_base_config(), simulation=spy, toy_scores=[0.25, 0.5])
        self.assertEqual(calls, [])
        self.assertEqual(plan.run_state, "planned")
        self.assertNotEqual(plan.run_state, "completed")
        self.assertFalse(plan.execution["simulation_invoked"])
        self.assertFalse(plan.execution["launched"])
        self.assertFalse(plan.execution["completed"])
        self.assertFalse(plan.gate_check["opened"])
        self.assertEqual(plan.status_label, "HOLD_SYNTHETIC_ONLY")
        self.assertEqual(plan.cell_count, 3)
        self.assertEqual(plan.trial_count, 3 * 48)
        self.assertEqual(plan.cells[0]["parameter_case"]["axes"], {"snr_db": -6})
        self.assertEqual(plan.toy_fixture["label"], TOY_FIXTURE_LABEL)
        self.assertIsNone(plan.toy_fixture["detector_roc"])
        self.assertIsNone(plan.detector_roc)
        self.assertEqual(plan.limits["null_model_note"], NULL_MODEL_NOTE)
        self.assertFalse(plan.limits["spatial_winding_randomization_evidence"])
        self.assertIn("no evidence that phase shuffle", NULL_MODEL_NOTE)
        self.assertIn("IAAFT", NULL_MODEL_NOTE)
        _assert_all_cells_blocked(self, plan)
        manifest = plan.campaign_manifest
        self.assertEqual(manifest.schema_version, "simulation_campaign_manifest_v1")
        self.assertEqual(manifest.configuration_hash, plan.config_hash)
        self.assertEqual(manifest.code_commit, plan.code_version_id)
        self.assertNotEqual(manifest.code_commit, "not_recorded")
        self.assertNotIn("code_commit", plan.provenance)
        self.assertIn("worktree_dirty", plan.provenance)
        would = plan.would_execute()
        self.assertFalse(would["executed"])
        self.assertEqual(len(would["cells"]), plan.cell_count)
        self.assertEqual(would["seeds"]["calibration_seed"], 11)
        self.assertEqual(would["splits"]["n_positive_calibration"], 12)
        self.assertEqual(would["cost"]["label"], "DECLARED_ESTIMATE")
        self.assertEqual(manifest.units[0].command, [])
        self.assertFalse(manifest.environment["launches_simulation"])
        self.assertIsNone(manifest.environment["detector_roc"])
        self.assertEqual(plan.provenance["generator"], "tools.simulation_runtime.grid_plan")
        self.assertEqual(plan.provenance["schema_version"], "grid_plan_v2")
        self.assertEqual(plan.failure_policy, "fail_closed_block_grid")
        self.assertNotIn("sim.nuisance_scenarios", sys.modules)
        with self.assertRaises(GridPlanError) as caught:
            dry_run(_base_config(), simulation=spy, toy_scores={"auc": 0.99, "fpr": [0, 1]})
        self.assertEqual(caught.exception.code, "detector_roc_refused")
        self.assertEqual(calls, [])

    def test_two_axis_enumeration_is_name_sorted(self):
        config = _base_config(
            axes=[
                {
                    "name": "snr_db",
                    "unit": "dB",
                    "values": [-6, 6],
                    "minimum": -6,
                    "maximum": 6,
                },
                {
                    "name": "jitter_mm",
                    "unit": "mm",
                    "values": [0, 2.5],
                    "minimum": 0,
                    "maximum": 5,
                },
            ],
            null_model_ids=["synthetic_time_reverse", "synthetic_iaaft"],
            source_model_ids=["synthetic_patch"],
            max_cells=32,
            max_trials=5000,
        )
        plan = dry_run(config)
        self.assertEqual(plan.cell_count, 8)
        first = plan.cells[0]["parameter_case"]
        self.assertEqual(first["axes"], {"jitter_mm": 0, "snr_db": -6})
        self.assertEqual(first["null_model_id"], "synthetic_time_reverse")
        self.assertEqual(plan.cells[1]["null_model_id"], "synthetic_iaaft")

    def test_serialization_roundtrip_ignores_tampered_cells(self):
        plan = dry_run(_base_config())
        encoded = json.dumps(plan.to_dict(), sort_keys=True)
        self.assertEqual(encoded, json.dumps(json.loads(encoded), sort_keys=True))
        document = json.loads(encoded)
        document["cells"][0]["parameter_case"]["axes"]["snr_db"] = 99
        document["cells"][0]["blocked"] = False
        restored = GridPlan.from_dict(document)
        self.assertEqual(restored.config_hash, plan.config_hash)
        self.assertEqual(restored.run_state, "planned")
        self.assertEqual(restored.cells[0]["parameter_case"]["axes"]["snr_db"], -6)
        self.assertTrue(restored.cells[0]["blocked"])
        document["config_hash"] = "0" * 64
        with self.assertRaises(GridPlanError) as caught:
            GridPlan.from_dict(document)
        self.assertEqual(caught.exception.code, "hash_mismatch")

    def test_self_declared_terminal_states_are_rejected(self):
        document = dry_run(_base_config()).to_dict()
        for state in ("running", "completed", "failed", "PASS"):
            forged = copy.deepcopy(document)
            forged["run_state"] = state
            with self.assertRaises(GridPlanError) as caught:
                GridPlan.from_dict(forged)
            self.assertEqual(caught.exception.code, "self_declared_state")

    def test_input_bounds(self):
        cases = [
            ("non_finite_value", {"axes": [{
                "name": "snr_db",
                "unit": "dB",
                "values": [float("nan")],
                "minimum": -6,
                "maximum": 6,
            }]}),
            ("non_finite_value", {"max_compute_units": float("inf")}),
            ("non_finite_value", {"threshold": {"cutoff": float("nan")}}),
            ("empty_axes", {"axes": []}),
            ("duplicate_axis", {"axes": [
                {
                    "name": "snr_db",
                    "unit": "dB",
                    "values": [-6],
                    "minimum": -6,
                    "maximum": 6,
                },
                {
                    "name": "snr_db",
                    "unit": "dB",
                    "values": [0],
                    "minimum": -6,
                    "maximum": 6,
                },
            ]}),
            ("invalid_range", {"axes": [{
                "name": "snr_db",
                "unit": "dB",
                "values": [7],
                "minimum": -6,
                "maximum": 6,
            }]}),
            ("invalid_range", {"wilson_design_p": 1.5}),
            ("unknown_null_model", {"null_model_ids": ["not_a_null_model"]}),
            ("unknown_source_model", {"source_model_ids": ["synthetic_iaaft"]}),
            ("duplicate_identifier", {"null_model_ids": ["synthetic_iaaft", "synthetic_iaaft"]}),
            (
                "invalid_sample_count",
                {
                    "n_independent_calibration": 11,
                    "n_positive_calibration": 5,
                    "n_negative_calibration": 6,
                },
            ),
            (
                "n_class_mismatch",
                {
                    "n_positive_calibration": 5,
                    "n_negative_calibration": 6,
                },
            ),
            ("invalid_sample_count", {"n_independent_evaluation": True}),
            ("invalid_sample_count", {"n_independent_evaluation": 12.0}),
            ("invalid_seed", {"calibration_seed": 29}),
            ("invalid_seed", {"master_seed": True}),
            ("unsupported_schema_version", {"schema_version": "grid_plan_v1"}),
            ("unsupported_schema_version", {"schema_version": "simulation_campaign_manifest_v1"}),
            ("unknown_field", {"calibration_samples": 12}),
            ("unknown_field", {"max_evidence_age_s": 10}),
            ("unknown_field", {"hidden_scientific_parameter": 1}),
            ("over_budget", {"max_cells": 2}),
            ("over_budget", {"max_trials": 70}),
            ("missing_estimand", {"estimand": "  "}),
            ("missing_hypothesis", {"h0": ""}),
            ("missing_score_definition", {"score_definition_id": "has space"}),
            ("invalid_nested", {"nested_unit": "channel"}),
            ("invalid_nuisance_scenario_id", {"nuisance_scenario_id": "https://example.invalid/scenario"}),
        ]
        for code, updates in cases:
            with self.subTest(code=code, updates=sorted(updates)):
                calls, spy = _spy_calls()
                with self.assertRaises(GridPlanError) as caught:
                    dry_run(_base_config(**updates), simulation=spy)
                self.assertEqual(caught.exception.code, code, caught.exception)
                self.assertEqual(calls, [])

    def test_artifact_count_hard_cap_rejects_oversized_plans(self):
        normalized = grid_plan_module._normalize_config(_base_config())
        with self.assertRaises(GridPlanError) as caught:
            grid_plan_module._cost_estimate(
                normalized, grid_plan_module.ABSOLUTE_MAX_CELLS + 1
            )
        self.assertEqual(caught.exception.code, "over_budget")
        self.assertIn("artifact", str(caught.exception).lower())

    def test_absolute_cell_ceiling_rejects_before_launch(self):
        config = _base_config(
            axes=[
                {
                    "name": "left_index",
                    "unit": "1",
                    "values": list(range(64)),
                    "minimum": 0,
                    "maximum": 63,
                },
                {
                    "name": "right_index",
                    "unit": "1",
                    "values": list(range(65)),
                    "minimum": 0,
                    "maximum": 64,
                },
            ],
            max_cells=100000,
            max_trials=100000000,
            max_compute_units=1e12,
        )
        calls, spy = _spy_calls()
        with self.assertRaises(GridPlanError) as caught:
            dry_run(config, simulation=spy)
        self.assertEqual(caught.exception.code, "over_budget")
        self.assertEqual(calls, [])

    def test_nuisance_id_is_not_imported(self):
        scenario_id = "nuis_chi1.00_snr+0.0dB_jit0.00mm_rawcart_seed42"
        plan = dry_run(_base_config(nuisance_scenario_id=scenario_id))
        self.assertEqual(plan.cells[0]["nuisance_scenario_id"], scenario_id)
        self.assertNotIn("sim.nuisance_scenarios", sys.modules)
        self.assertNotEqual(plan.config_hash, dry_run(_base_config()).config_hash)

    def test_wilson_floor_matches_planner(self):
        required = plan_sample_size(
            0.5,
            design_p=None,
            is_half_width=False,
            confidence_level=0.95,
            max_n=1000,
        )
        self.assertEqual(required.required_n, 12)
        plan = dry_run(_base_config())
        self.assertEqual(plan.wilson.required_n, required.required_n)
        self.assertEqual(plan.wilson.status, "found")

    def test_fabricated_admissible_caller_record_blocks_every_cell(self):
        main_sha = _local_main_sha(self)
        fabricated = []
        for gate_id in BLOCKING_GATE_IDS:
            fabricated.append(
                {
                    "schema_version": EVIDENCE_SCHEMA_VERSION,
                    "case_id": gate_id,
                    "gate_id": gate_id,
                    "promotion_decision": "ADMISSIBLE_FOR_ENGINEERING_REPORT",
                    "scientific_pass": False,
                    "artifact_sha256": "ab" * 32,
                    "verified_at_commit": main_sha,
                    "log_pointer": f"log:{gate_id}",
                    "verifier": "caller",
                    "verified_at": CHECKED_AT,
                }
            )
        calls, spy = _spy_calls()
        with _resolved_main(), tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp)
            plan = execute(
                _base_config(),
                fabricated,
                simulation=spy,
                checked_at=CHECKED_AT,
                record_root=empty,
            )
            again = execute(
                _base_config(),
                [{**fabricated[0], "artifact_sha256": "cd" * 32}],
                simulation=spy,
                checked_at="not-a-timestamp",
                record_root=empty,
            )
        self.assertEqual(calls, [])
        self.assertEqual(plan.test_fixture_label, TEST_FIXTURE_NOT_EVIDENCE)
        self.assertIsNone(plan.gate_source_failure)
        self.assertTrue(plan.caller_gate_decision_rejected)
        self.assertTrue(plan.gate_check["caller_gate_decision_rejected"])
        self.assertFalse(plan.gate_check["opened"])
        self.assertEqual(plan.run_state, "blocked")
        self.assertNotEqual(plan.run_state, "completed")
        self.assertTrue(plan.execution["refused"])
        self.assertFalse(plan.execution["launched"])
        self.assertFalse(plan.execution["simulation_invoked"])
        self.assertIsNone(plan.gate_evidence)
        self.assertIsNone(plan.detector_roc)
        self.assertEqual(plan.checked_at, CHECKED_AT)
        self.assertTrue(plan.limits["checked_at_is_caller_set"])
        self.assertTrue(plan.limits["artifact_sha_is_format_only"])
        _assert_all_cells_blocked(self, plan)
        statuses = _statuses(plan)
        for gate_id in BLOCKING_GATE_IDS:
            if gate_id == "ci_discovery":
                self.assertEqual(statuses[gate_id], "ci_discovery_blocked")
            else:
                self.assertEqual(statuses[gate_id], "dependency_not_merged_on_main")
            self.assertNotEqual(statuses[gate_id], "admissible_on_ancestor")
        self.assertEqual(statuses["dmd_crouzeix"], "dependency_not_merged_on_main")
        self.assertEqual(plan.evidence_hash, again.evidence_hash)
        self.assertIn(
            "dependency_not_merged_on_main",
            {item["code"] for item in plan.gate_check["blockers"]},
        )
        self.assertIn("ci_discovery_blocked", {item["code"] for item in plan.gate_check["blockers"]})

    def test_stale_non_ancestor_report_blocks_every_cell(self):
        main_sha = _local_main_sha(self)
        head_sha = _git("rev-parse", "HEAD")
        self.assertNotEqual(head_sha, main_sha)
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", head_sha, main_sha],
            cwd=str(_REPO_ROOT),
            check=False,
        )
        self.assertNotEqual(ancestor.returncode, 0)
        calls, spy = _spy_calls()
        with _resolved_main(), tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_report(
                root,
                [
                    {
                        "case_id": "four_sphere_forward_model",
                        "promotion_decision": "ADMISSIBLE_FOR_ENGINEERING_REPORT",
                        "verified_at_commit": head_sha,
                    }
                ],
            )
            before = sorted(path.name for path in root.iterdir())
            plan = execute(_base_config(), simulation=spy, record_root=root)
            self.assertEqual(sorted(path.name for path in root.iterdir()), before)
        self.assertEqual(calls, [])
        self.assertEqual(plan.test_fixture_label, TEST_FIXTURE_NOT_EVIDENCE)
        self.assertFalse(plan.caller_gate_decision_rejected)
        self.assertFalse(plan.gate_check["opened"])
        self.assertEqual(plan.run_state, "blocked")
        self.assertEqual(
            _statuses(plan)["four_sphere_forward_model"],
            "dependency_not_merged_on_main",
        )
        self.assertNotEqual(_statuses(plan)["four_sphere_forward_model"], "admissible_on_ancestor")
        self.assertEqual(_statuses(plan)["planar_geometry"], "dependency_not_merged_on_main")
        self.assertEqual(_statuses(plan)["winding"], "dependency_not_merged_on_main")
        self.assertEqual(_statuses(plan)["hodge"], "dependency_not_merged_on_main")
        self.assertEqual(_statuses(plan)["ci_discovery"], "ci_discovery_blocked")
        self.assertNotIn("not_ancestor", {item["code"] for item in plan.gate_check["blockers"]})
        _assert_all_cells_blocked(self, plan)
        self.assertFalse(plan.execution["simulation_invoked"])
        self.assertIsNone(plan.detector_roc)

    def test_forged_report_in_untracked_tmp_dir_opens_no_gate(self):
        main_sha = _local_main_sha(self)
        calls, spy = _spy_calls()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_forged_reports(root, main_sha)
            (root / "command_center.json").write_text(
                json.dumps(
                    {
                        "schema_version": "command-center-evidence-promotion/v1",
                        "scientific_pass": False,
                        "cases": [
                            {
                                "case_id": "four_sphere_forward_model",
                                "promotion_decision": "ADMISSIBLE_FOR_ENGINEERING_REPORT",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with _resolved_main(), patch.object(grid_plan_module, "_ci_discovery_blocked", return_value=False):
                plan = execute(
                    _base_config(),
                    {"promotion_decision": "ADMISSIBLE_FOR_ENGINEERING_REPORT"},
                    simulation=spy,
                    record_root=root,
                )
        self.assertEqual(calls, [])
        self.assertEqual(plan.test_fixture_label, TEST_FIXTURE_NOT_EVIDENCE)
        self.assertTrue(plan.caller_gate_decision_rejected)
        _assert_seven_non_admissible(self, plan)
        self.assertTrue(
            all(item["status"] == "dependency_not_merged_on_main" for item in plan.gate_resolution)
        )

    def test_forged_report_in_tree_but_uncommitted_opens_no_gate(self):
        main_sha = _local_main_sha(self)
        directory = _REPO_ROOT / "tools" / "simulation_runtime"
        names = [f"_forged_{gate_id}.json" for gate_id in BLOCKING_GATE_IDS]
        for name in names:
            self.assertFalse((directory / name).exists())
        calls, spy = _spy_calls()
        try:
            _write_forged_reports(directory, main_sha)
            for name in names:
                relative = f"tools/simulation_runtime/{name}"
                self.assertTrue((directory / name).is_file())
                tracked = subprocess.run(
                    ["git", "ls-files", "--error-unmatch", "--", relative],
                    cwd=str(_REPO_ROOT),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(tracked.returncode, 0)
            with _resolved_main(), patch.object(grid_plan_module, "_ci_discovery_blocked", return_value=False):
                plan = execute(_base_config(), simulation=spy)
                labeled = execute(_base_config(), simulation=spy, record_root=directory)
        finally:
            for name in names:
                (directory / name).unlink(missing_ok=True)
        for name in names:
            self.assertFalse((directory / name).exists())
        self.assertEqual(calls, [])
        self.assertIsNone(plan.test_fixture_label)
        self.assertEqual(labeled.test_fixture_label, TEST_FIXTURE_NOT_EVIDENCE)
        _assert_seven_non_admissible(self, plan)
        _assert_seven_non_admissible(self, labeled)

    def test_tip_commit_claim_on_a_file_not_on_main_opens_no_gate(self):
        main_sha = _local_main_sha(self)
        calls, spy = _spy_calls()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_forged_reports(root, main_sha)
            on_main = subprocess.run(
                ["git", "cat-file", "-e", f"{main_sha}:_forged_four_sphere_forward_model.json"],
                cwd=str(_REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(on_main.returncode, 0)
            with _resolved_main(), patch.object(grid_plan_module, "_ci_discovery_blocked", return_value=False):
                plan = execute(_base_config(), simulation=spy, record_root=root)
        self.assertEqual(calls, [])
        _assert_seven_non_admissible(self, plan)
        self.assertTrue(
            all(item.get("verified_at_commit") is None for item in plan.gate_resolution)
        )

    def test_git_missing_shallow_and_unresolved_main_fail_closed(self):
        calls, spy = _spy_calls()

        def missing(_args):
            raise FileNotFoundError("git")

        def shallow(args):
            listed = list(args)
            if listed[:2] == ["rev-parse", "--is-shallow-repository"]:
                return _git_result("true\n")
            if listed[:3] == ["rev-parse", "--verify", "HEAD"]:
                return _git_result("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n")
            raise AssertionError(args)

        def unresolved(args):
            listed = list(args)
            if listed[:2] == ["rev-parse", "--is-shallow-repository"]:
                return _git_result("false\n")
            if listed[:3] == ["rev-parse", "--verify", "HEAD"]:
                return _git_result("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n")
            if listed[:2] == ["rev-parse", "--verify"]:
                return _git_result("", returncode=1)
            raise AssertionError(args)

        with patch.object(grid_plan_module, "_git", side_effect=missing):
            missing_plan = execute(_base_config(), simulation=spy)
        with patch.object(grid_plan_module, "_git", side_effect=shallow):
            shallow_plan = execute(_base_config(), simulation=spy)
        with patch.object(grid_plan_module, "_git", side_effect=unresolved):
            unresolved_plan = execute(_base_config(), simulation=spy)
        self.assertEqual(calls, [])
        expected = {
            missing_plan: "git_missing",
            shallow_plan: "shallow_clone",
            unresolved_plan: "main_unresolved",
        }
        for plan, code in expected.items():
            self.assertEqual(plan.gate_source_failure, code)
            self.assertFalse(plan.gate_check["opened"])
            self.assertEqual(plan.run_state, "blocked")
            self.assertTrue(plan.execution["refused"])
            _assert_seven_non_admissible(self, plan)
            self.assertTrue(all(item["status"] == "missing" for item in plan.gate_resolution))
            self.assertTrue(all(item["code"] == code for item in plan.gate_check["blockers"]))
            self.assertEqual(plan.provenance["base_sha"], "unresolved")
        self.assertEqual(missing_plan.code_version_id, "UNKNOWN")
        self.assertEqual(shallow_plan.code_version_id, "a" * 40)
        self.assertEqual(unresolved_plan.code_version_id, "b" * 40)

    def test_one_case_id_opens_one_gate_and_duplicates_block_that_gate(self):
        main_sha = _local_main_sha(self)
        admissible = {
            "promotion_decision": "ADMISSIBLE_FOR_ENGINEERING_REPORT",
            "scientific_pass": False,
            "verified_at_commit": main_sha,
            "_source": "git_blob",
        }
        duplicate_rows = [
            {**admissible, "case_id": "four_sphere_forward_model", "_path": "reports/a.json"},
            {**admissible, "case_id": "four_sphere_forward_model", "_path": "reports/b.json"},
        ]
        multi_rows = [
            {**admissible, "case_id": "four_sphere_forward_model", "_path": "reports/both.json"},
            {
                **admissible,
                "case_id": "planar_geometry",
                "_path": "reports/both.json",
            },
        ]
        single_rows = [
            {
                **admissible,
                "case_id": "four_sphere_forward_model",
                "_path": "not/on/main.json",
            },
        ]
        with patch.object(grid_plan_module, "_ci_discovery_blocked", return_value=False), patch.object(
            grid_plan_module, "_contract_reasons", return_value=[]
        ):
            duplicated, duplicate_blockers = grid_plan_module._resolve_gates_from_rows(
                duplicate_rows,
                main_sha=main_sha,
                git_failure=None,
            )
            multi, _multi_blockers = grid_plan_module._resolve_gates_from_rows(
                multi_rows,
                main_sha=main_sha,
                git_failure=None,
            )
            single, _single_blockers = grid_plan_module._resolve_gates_from_rows(
                single_rows,
                main_sha=main_sha,
                git_failure=None,
            )
        by_id = {item["gate_id"]: item for item in duplicated}
        self.assertEqual(by_id["four_sphere_forward_model"]["status"], "duplicate_record")
        self.assertNotEqual(by_id["four_sphere_forward_model"]["status"], "admissible_on_ancestor")
        self.assertEqual(by_id["planar_geometry"]["status"], "missing")
        self.assertIn("duplicate_gate_record", {item["code"] for item in duplicate_blockers})
        self.assertTrue(
            all(item["status"] != "admissible_on_ancestor" for item in duplicated)
        )
        multi_status = {item["gate_id"]: item["status"] for item in multi}
        self.assertEqual(multi_status["four_sphere_forward_model"], "missing")
        self.assertEqual(multi_status["planar_geometry"], "missing")
        self.assertTrue(all(item["status"] != "admissible_on_ancestor" for item in multi))
        single_status = {item["gate_id"]: item["status"] for item in single}
        self.assertEqual(single_status["four_sphere_forward_model"], "not_on_main")
        self.assertEqual(single_status["planar_geometry"], "missing")
        self.assertEqual(single_status["ci_discovery"], "missing")
        self.assertTrue(all(item["status"] != "admissible_on_ancestor" for item in single))

    def test_repo_without_promotion_reports_leaves_gates_missing(self):
        calls, spy = _spy_calls()
        with _resolved_main():
            plan = execute(_base_config(), simulation=spy)
        self.assertEqual(calls, [])
        self.assertFalse(plan.caller_gate_decision_rejected)
        self.assertFalse(plan.gate_check["opened"])
        self.assertEqual(plan.run_state, "blocked")
        statuses = _statuses(plan)
        for gate_id in BLOCKING_GATE_IDS:
            if gate_id == "ci_discovery":
                self.assertEqual(statuses[gate_id], "ci_discovery_blocked")
            else:
                self.assertEqual(statuses[gate_id], "dependency_not_merged_on_main")
                self.assertIsNone(plan.gate_resolution[
                    [item["gate_id"] for item in plan.gate_resolution].index(gate_id)
                ]["pinned_commit"])
        _assert_all_cells_blocked(self, plan)
        self.assertIsNone(plan.test_fixture_label)
        self.assertIsNone(plan.gate_source_failure)
        self.assertEqual(plan.limits["reports_read_from"], "git_blobs_at_writer_paths_on_main")
        self.assertFalse(plan.limits["record_root_is_evidence"])
        self.assertFalse(plan.limits["gate_integration_state_is_evidence"])
        self.assertFalse(plan.limits["ancestry_fetches"])
        self.assertEqual(plan.limits["writer_report_paths"], [])
        self.assertTrue(all(item["integration_is_evidence"] is False for item in plan.gate_resolution))
        self.assertEqual(plan.provenance["audited_main_sha"], AUDITED_MAIN_SHA)
        self.assertEqual(len(plan.provenance["base_sha"]), 40)

    def test_blocked_document_roundtrip_stays_blocked(self):
        with _resolved_main(), tempfile.TemporaryDirectory() as tmp:
            plan = execute(_base_config(), [{"promotion_decision": "ADMISSIBLE_FOR_ENGINEERING_REPORT"}], record_root=Path(tmp))
            self.assertEqual(plan.run_state, "blocked")
            restored = GridPlan.from_dict(plan.to_dict(), record_root=Path(tmp))
            self.assertEqual(restored.run_state, "blocked")
            self.assertEqual(restored.config_hash, plan.config_hash)
            self.assertEqual(restored.evidence_hash, plan.evidence_hash)
            self.assertNotIn("calibration_unit_ids", restored.configuration)
            self.assertNotIn("evaluation_unit_ids", restored.configuration)
            self.assertFalse(restored.gate_check["opened"])
            forged = plan.to_dict()
            forged["run_state"] = "planned"
            forged["gate_check"]["opened"] = True
            rebuilt = GridPlan.from_dict(forged, record_root=Path(tmp))
            self.assertEqual(rebuilt.run_state, "blocked")
            self.assertFalse(rebuilt.gate_check["opened"])
            _assert_all_cells_blocked(self, rebuilt)

    def test_non_finite_helper_rejects_bool_axis_values(self):
        with self.assertRaises(GridPlanError) as caught:
            dry_run(
                _base_config(
                    axes=[
                        {
                            "name": "snr_db",
                            "unit": "dB",
                            "values": [False],
                            "minimum": -1,
                            "maximum": 1,
                        }
                    ]
                )
            )
        self.assertEqual(caught.exception.code, "invalid_range")

    def test_planned_metrics_carry_not_integrated_status(self):
        spec = grid_plan_module._metric_spec({"value": "not_required"})
        self.assertEqual(spec["status"], "NOT_INTEGRATED")
        self.assertFalse(spec["computed"])
        self.assertTrue(spec["metrics"])
        for metric in spec["metrics"]:
            self.assertEqual(metric["status"], "NOT_INTEGRATED")
            self.assertFalse(metric["computed"])
            self.assertIsNone(metric["value"])

    def test_ci_discovery_stays_blocked_after_round6_selection(self):
        row = grid_plan_module._resolve_one(
            "ci_discovery",
            role="blocking",
            rows=[],
            main_sha="a" * 40,
            git_failure=None,
        )
        self.assertEqual(row["status"], "ci_discovery_blocked")
        self.assertNotIn("#425 owns that change", row["message"])
        self.assertIn("round6_experimental_tests.py", row["message"])
        self.assertIn("does not open this gate", row["message"])

    def test_declarations_cost_and_smoke_do_not_compute_or_sweep(self):
        import tools.simulation_runtime.grid_plan as grid_plan

        source = Path(grid_plan.__file__).read_text(encoding="utf-8")
        self.assertNotIn("import neurotopology_sim", source)
        self.assertNotIn("from neurotopology_sim", source)
        self.assertNotIn("import synthetic_forward_roc", source)
        self.assertIn("synthetic_forward_roc.py:194", source)
        self.assertNotIn("wilson_score_interval", source)
        self.assertNotIn("simulation(", source)
        self.assertNotIn("def sweep", source)
        self.assertNotIn("def run_grid", source)
        self.assertNotIn('"hash" in name', source)
        self.assertFalse(hasattr(grid_plan, "compute_auc"))
        self.assertFalse(hasattr(grid_plan, "compute_roc"))
        self.assertFalse(hasattr(grid_plan, "run_sweep"))
        calls, spy = _spy_calls()
        plan = dry_run(_base_config(), simulation=spy, toy_scores=[0.1, 0.2, 0.3])
        self.assertEqual(calls, [])
        self.assertEqual(plan.toy_fixture["label"], TOY_FIXTURE_LABEL)
        self.assertFalse(plan.execution["simulation_invoked"])
        self.assertFalse(plan.execution["sweep_reachable"])
        self.assertFalse(plan.limits["sweep_reachable"])
        self.assertFalse(plan.gate_check["opened"])
        self.assertEqual(plan.run_state, "planned")
        _assert_all_cells_blocked(self, plan)
        self.assertEqual(plan.sample_size_label, "UNDERPOWERED_DRY_RUN")
        self.assertEqual(plan.execution_mode, "smoke_only")
        self.assertEqual(plan.engineering_minimum_note, "engineering minimum, not a power guarantee")
        self.assertFalse(plan.would_execute()["executed"])
        self.assertEqual(plan.code_version_id, _git("rev-parse", "HEAD"))
        self.assertEqual(plan.to_dict()["config_digest"], plan.config_hash)
        self.assertEqual(plan.provenance["config_digest"], plan.config_hash)
        self.assertEqual(plan.to_dict()["audit"]["project_status"], "HOLD / SYNTHETIC_ONLY")
        audit = plan.to_dict()["audit"]
        self.assertEqual(audit["code_version_id"], plan.code_version_id)
        self.assertEqual(audit["config_digest"], plan.config_hash)
        self.assertEqual(
            audit["seeds"],
            {"master_seed": 100, "calibration_seed": 11, "evaluation_seed": 29},
        )
        self.assertEqual(audit["calibration_unit_ids"], plan.cells[0]["calibration_unit_ids"])
        self.assertEqual(audit["power_claim"], "none")
        self.assertFalse(audit["power_analysis_supplied"])
        self.assertFalse(audit["engineering_threshold_is_power_guarantee"])
        self.assertFalse(plan.cells[0]["roles_are_disjoint_is_statistical_independence"])
        self.assertIn("per-seed RNG", plan.cells[0]["roles_are_disjoint_note"])
        spec = plan.metric_spec
        self.assertFalse(spec["computed"])
        self.assertFalse(spec["imports_roc_api"])
        self.assertEqual(spec["integration"], "NOT_INTEGRATED")
        self.assertEqual(spec["source_pr"], 426)
        self.assertIsNone(spec["source_head"])
        self.assertFalse(spec["source_head_is_pin"])
        self.assertEqual(plan.hash_payload["metric_spec"], spec)
        by_id = {item["metric_id"]: item for item in spec["metrics"]}
        self.assertEqual(
            set(by_id),
            {"tpr", "fpr", "precision", "accuracy", "auc", "average_precision"},
        )
        for metric_id in ("tpr", "fpr", "precision", "accuracy"):
            metric = by_id[metric_id]
            self.assertFalse(metric["computed"])
            self.assertIsNone(metric["value"])
            self.assertEqual(metric["interval_method"], "wilson_on_independent_unit")
            self.assertEqual(metric["count_unit"], "independent_unit")
            self.assertFalse(metric["windows_counted"])
            self.assertEqual(metric["undefined_value"], "UNDEFINED")
            self.assertFalse(metric["silent_zero"])
            self.assertFalse(metric["silent_nan"])
        self.assertEqual(by_id["auc"]["unit_score_rule"], "max_window_score")
        self.assertEqual(by_id["average_precision"]["unit_score_rule"], "max_window_score")
        self.assertTrue(spec["fpr_depends_on_nested_per_unit"])
        self.assertIn("nested_per_unit", spec["fpr_dependence_note"])
        self.assertEqual(by_id["auc"]["tie_rule"], "ties_count_0.5")
        self.assertEqual(by_id["auc"]["undefined_reason"], "auc_undefined_empty_class")
        self.assertEqual(by_id["auc"]["interval_method"], "cluster_bootstrap_over_independent_unit")
        self.assertFalse(by_id["average_precision"]["interpolation"])
        self.assertEqual(by_id["average_precision"]["undefined_reason"], "ap_undefined_no_positives")
        self.assertEqual(
            by_id["precision"]["undefined_reason"],
            "precision_undefined_no_predicted_positives",
        )
        self.assertEqual(by_id["tpr"]["undefined_reason"], "tpr_undefined_zero_denominator")
        self.assertEqual(by_id["fpr"]["undefined_reason"], "fpr_undefined_zero_denominator")
        for metric in spec["metrics"]:
            self.assertEqual(metric["status"], "NOT_INTEGRATED")
            self.assertIsNone(metric["value"])
            self.assertNotEqual(metric["value"], 0)
            self.assertFalse(metric["computed"])
        cost = plan.cost_estimate
        self.assertTrue(cost["computed_without_running"])
        product = plan.cell_count * (24 + 24) * 1
        self.assertEqual(cost["cells_times_independent_units_times_nested"], product)
        self.assertEqual(cost["estimated_callback_invocations"], product)
        self.assertEqual(cost["output_records"], product)
        self.assertEqual(cost["declared_bytes_per_record"], 4096)
        self.assertEqual(
            cost["expected_artifact_count"],
            len(plan.planned_outputs) + plan.cell_count,
        )
        nested_plan = dry_run(
            _base_config(
                nested_unit="window",
                nested_per_unit=3,
                unit_aggregation="cluster_any_event_rate",
            ),
            simulation=spy,
        )
        self.assertEqual(
            nested_plan.cost_estimate["cells_times_independent_units_times_nested"],
            nested_plan.cell_count * (24 + 24) * 3,
        )
        self.assertEqual(nested_plan.cost_estimate["nested_per_unit"], 3)
        self.assertLessEqual(
            nested_plan.cost_estimate["expected_artifact_count"],
            grid_plan_module.ABSOLUTE_MAX_ARTIFACTS,
        )
        self.assertEqual(cost["label"], "DECLARED_ESTIMATE")
        self.assertNotIn("BOUND_NOT_A_MEASUREMENT", source)
        self.assertGreater(cost["estimated_disk_mb"], 0.0)
        self.assertGreater(cost["estimated_memory_mb"], 0.0)
        self.assertNotEqual(plan.campaign_manifest.units[0].estimated_disk_mb, 0.0)
        self.assertNotEqual(plan.campaign_manifest.units[0].estimated_memory_mb, 0.0)
        self.assertEqual(
            plan.campaign_manifest.units[0].estimated_disk_mb,
            cost["per_cell_disk_mb"],
        )
        self.assertEqual(
            plan.campaign_manifest.units[0].estimated_memory_mb,
            cost["per_cell_memory_mb"],
        )
        executed = execute(_base_config(), simulation=spy)
        self.assertEqual(calls, [])
        self.assertFalse(executed.gate_check["opened"])
        self.assertFalse(executed.execution["sweep_reachable"])
        self.assertEqual(executed.run_state, "blocked")
        _assert_all_cells_blocked(self, executed)

        met = dry_run(
            _base_config(
                n_independent_calibration=200,
                n_positive_calibration=100,
                n_negative_calibration=100,
                n_independent_evaluation=200,
                n_positive_evaluation=100,
                n_negative_evaluation=100,
                max_trials=5000,
                max_compute_units=100000.0,
            ),
            simulation=spy,
        )
        self.assertEqual(calls, [])
        self.assertEqual(met.sample_size_label, "ENGINEERING_THRESHOLD_MET")
        self.assertEqual(met.execution_mode, "held")
        self.assertEqual(met.engineering_minimum_note, "engineering minimum, not a power guarantee")
        self.assertEqual(met.cells[0]["power_claim"], "none")
        self.assertFalse(met.gate_check["opened"])
        self.assertFalse(met.execution["sweep_reachable"])
        _assert_all_cells_blocked(self, met)

    def test_reporting_hash_callable_uses_an_exact_name(self):
        import tools.evidence_promotion_gate.reporting as reporting

        def decoy(_body):
            raise AssertionError("substring hash name must not be called")

        def report_hash(body):
            return body

        with patch.object(reporting, "rehash_notes", decoy, create=True):
            self.assertIsNone(grid_plan_module._reporting_hash_callable())
        with patch.object(reporting, "report_hash", report_hash, create=True):
            self.assertIs(grid_plan_module._reporting_hash_callable(), report_hash)

    def test_record_root_must_be_a_path_and_is_not_evidence(self):
        with self.assertRaises(GridPlanError) as caught:
            execute(_base_config(), record_root=object())
        self.assertEqual(caught.exception.code, "invalid_record_root")

    def test_same_config_has_the_same_digest(self):
        first = dry_run(_base_config())
        second = dry_run(_base_config())
        self.assertEqual(first.config_hash, second.config_hash)
        self.assertEqual(first.threshold_hash, second.threshold_hash)
        self.assertEqual(first.to_dict()["config_digest"], first.config_hash)

    def test_missing_unit_aggregation_is_rejected_when_nested(self):
        with self.assertRaises(GridPlanError) as caught:
            dry_run(_base_config(nested_unit="window", nested_per_unit=2))
        self.assertEqual(caught.exception.code, "missing_unit_aggregation")
        with self.assertRaises(GridPlanError) as caught:
            dry_run(
                _base_config(
                    nested_unit="window",
                    nested_per_unit=2,
                    unit_aggregation="mean_of_windows",
                )
            )
        self.assertEqual(caught.exception.code, "invalid_unit_aggregation")
        named = dry_run(
            _base_config(
                nested_unit="window",
                nested_per_unit=2,
                unit_aggregation="cluster_any_event_rate",
            )
        )
        spec = named.metric_spec["unit_aggregation"]
        self.assertEqual(spec["value"], "cluster_any_event_rate")
        self.assertTrue(spec["named_on_pr_426"])
        self.assertEqual(spec["source_citation"], "synthetic_forward_roc.py:194")
        self.assertEqual(spec["cluster_ids_parameters"], ["operating_point", "compute_roc"])
        self.assertNotEqual(named.threshold_hash, dry_run(_base_config()).threshold_hash)
        bare = dry_run(_base_config())
        self.assertEqual(bare.metric_spec["unit_aggregation"]["value"], "not_required")
        self.assertFalse(bare.metric_spec["unit_aggregation"]["named_on_pr_426"])

    def test_wilson_reject_is_not_labeled_underpowered(self):
        with self.assertRaises(GridPlanError) as caught:
            dry_run(
                _base_config(
                    n_independent_calibration=11,
                    n_positive_calibration=5,
                    n_negative_calibration=6,
                )
            )
        self.assertEqual(caught.exception.code, "invalid_sample_count")
        message = str(caught.exception)
        self.assertNotIn("below either floor", message)
        self.assertIn("n_positive_calibration", message)
        self.assertIn("engineering minimum, not a power guarantee", message)

    def test_dependency_pins_staleness_and_abort(self):
        calls, spy = _spy_calls()
        wrong = "0" * 40
        stale_rows = [
            {
                "case_id": "roc_metrics",
                "_source": "git_blob",
                "_path": "absent.json",
                "source_sha": wrong,
                "promotion_decision": "ADMISSIBLE_FOR_ENGINEERING_REPORT",
                "scientific_pass": False,
            }
        ]
        missing_rows = [
            {
                "case_id": "roc_metrics",
                "_source": "git_blob",
                "_path": "absent.json",
                "promotion_decision": "ADMISSIBLE_FOR_ENGINEERING_REPORT",
                "scientific_pass": False,
            }
        ]
        phase_rows = [
            {
                "case_id": "phase_score_limitations_recorded",
                "_source": "git_blob",
                "_path": "absent.json",
                "limitations_recorded": False,
                "promotion_decision": "ADMISSIBLE_FOR_ENGINEERING_REPORT",
                "scientific_pass": False,
            }
        ]
        pinned_but_untracked = [
            {
                "case_id": "phase_dispersion_module",
                "_source": "git_blob",
                "_path": "absent.json",
                "source_sha": "b" * 40,
                "promotion_decision": "ADMISSIBLE_FOR_ENGINEERING_REPORT",
                "scientific_pass": False,
            }
        ]
        with patch.object(grid_plan_module, "_ci_discovery_blocked", return_value=False), patch.object(
            grid_plan_module, "_contract_reasons", return_value=[]
        ), patch.dict(
            grid_plan_module.GATE_CONTRACT["roc_metrics"],
            {"pinned_commit": "b" * 40},
        ):
            stale, stale_blockers = grid_plan_module._resolve_gates_from_rows(
                stale_rows,
                main_sha="a" * 40,
                git_failure=None,
            )
            missing, missing_blockers = grid_plan_module._resolve_gates_from_rows(
                missing_rows,
                main_sha="a" * 40,
                git_failure=None,
            )
            phase, phase_blockers = grid_plan_module._resolve_gates_from_rows(
                phase_rows,
                main_sha="a" * 40,
                git_failure=None,
            )
            untracked, _untracked_blockers = grid_plan_module._resolve_gates_from_rows(
                pinned_but_untracked,
                main_sha="a" * 40,
                git_failure=None,
            )
        stale_status = {item["gate_id"]: item for item in stale}
        self.assertEqual(stale_status["roc_metrics"]["status"], "stale_source")
        self.assertFalse(stale_status["roc_metrics"]["candidate_is_evidence"])
        self.assertIn("stale_source", {item["code"] for item in stale_blockers})
        self.assertTrue(all(item["status"] != "admissible_on_ancestor" for item in stale))
        missing_status = {item["gate_id"]: item["status"] for item in missing}
        self.assertEqual(missing_status["roc_metrics"], "missing_source_sha")
        self.assertIn("missing_dependency", {item["code"] for item in missing_blockers})
        phase_status = {item["gate_id"]: item["status"] for item in phase}
        self.assertEqual(phase_status["phase_score_limitations_recorded"], "limitations_missing")
        self.assertEqual(phase_status["phase_dispersion_module"], "missing")
        self.assertIn("limitations_missing", {item["code"] for item in phase_blockers})
        untracked_status = {item["gate_id"]: item["status"] for item in untracked}
        self.assertEqual(untracked_status["phase_dispersion_module"], "not_on_main")
        self.assertEqual(untracked_status["phase_score_limitations_recorded"], "missing")
        self.assertNotEqual(untracked_status["phase_dispersion_module"], "admissible_on_ancestor")
        self.assertIsNone(
            grid_plan_module.GATE_CONTRACT["phase_score_limitations_recorded"]["pinned_commit"]
        )
        self.assertIsNone(grid_plan_module.GATE_CONTRACT["phase_dispersion_module"]["pinned_commit"])

        plan = execute(_base_config(), simulation=spy)
        self.assertEqual(calls, [])
        self.assertTrue(plan.execution["aborted"])
        self.assertEqual(plan.execution["abort_gate"], BLOCKING_GATE_IDS[0])
        self.assertFalse(plan.execution["partial_launch"])
        self.assertFalse(plan.execution["executed"])
        self.assertFalse(plan.would_execute()["executed"])
        self.assertFalse(plan.gate_check["opened"])
        self.assertEqual(plan.run_state, "blocked")
        _assert_all_cells_blocked(self, plan)
        self.assertFalse(plan.limits["candidate_is_evidence"])
        self.assertFalse(plan.limits["open_pr_is_evidence"])
        roc_contract = next(
            item for item in plan.limits["gate_contract"] if item["gate_id"] == "roc_metrics"
        )
        self.assertIsNone(roc_contract["pinned_commit"])
        self.assertEqual(plan.grid_execution, "NOT_RUN")
        self.assertTrue(plan.limits["informational_candidates_are_not_pins"])

    def test_locked_dataset_arguments_are_rejected(self):
        locked = [
            {"h0": "scores from ds005620"},
            {"h1": "a BIDS subject contrast"},
            {"estimand": "participant level contrast"},
            {"estimand": "an empirical contrast"},
            {"score_definition_id": "participant-score"},
        ]
        for updates in locked:
            with self.subTest(updates=sorted(updates)):
                with self.assertRaises(GridPlanError) as caught:
                    dry_run(_base_config(**updates))
                self.assertEqual(caught.exception.code, "locked_input")
        for root in (
            "/tmp/ds005620/sub-01",
            "bids/sub-01",
            "study/participant/01",
            "empirical/input.npy",
        ):
            with self.subTest(record_root=root):
                with self.assertRaises(GridPlanError) as caught:
                    execute(_base_config(), record_root=root)
                self.assertEqual(caught.exception.code, "locked_input")

    def test_provenance_round_trip_rebuilds_code_version(self):
        plan = dry_run(_base_config())
        document = plan.to_dict()
        document["provenance"]["code_version_id"] = "c" * 40
        document["provenance"]["worktree_dirty"] = not plan.worktree_dirty
        document["provenance"]["code_commit"] = "not_recorded"
        restored = GridPlan.from_dict(document)
        self.assertEqual(restored.config_hash, plan.config_hash)
        self.assertEqual(restored.code_version_id, plan.code_version_id)
        self.assertEqual(restored.worktree_dirty, plan.worktree_dirty)
        self.assertNotEqual(restored.code_version_id, "c" * 40)
        self.assertIn("code_version_id", restored.provenance)
        self.assertIn("worktree_dirty", restored.provenance)
        self.assertNotIn("code_commit", restored.provenance)
        self.assertFalse(restored.would_execute()["executed"])
        self.assertEqual(restored.provenance["config_digest"], restored.config_hash)

    def test_dirty_or_unknown_head_blocks_execute_only(self):
        calls, spy = _spy_calls()
        with patch.object(grid_plan_module, "_worktree_dirty", return_value=True):
            listed = dry_run(_base_config(), simulation=spy)
        self.assertEqual(calls, [])
        self.assertEqual(listed.run_state, "planned")
        self.assertTrue(listed.worktree_dirty)
        self.assertFalse(listed.would_execute()["executed"])
        self.assertNotIn("dirty_worktree", {item["code"] for item in listed.gate_check["blockers"]})
        with _resolved_main(), patch.object(grid_plan_module, "_worktree_dirty", return_value=True):
            blocked = execute(_base_config(), simulation=spy)
        self.assertEqual(calls, [])
        self.assertTrue(blocked.worktree_dirty)
        self.assertIn("dirty_worktree", {item["code"] for item in blocked.gate_check["blockers"]})
        self.assertFalse(blocked.execution["executed"])
        self.assertFalse(blocked.execution["partial_launch"])
        self.assertEqual(blocked.run_state, "blocked")
        _assert_all_cells_blocked(self, blocked)

    def test_imbalanced_splits_stay_smoke_only_and_wilson_rejects_a_short_class(self):
        wide = {
            "wilson_target_full_width": 0.6,
            "max_trials": 5000,
            "max_compute_units": 100000.0,
            "max_cells": 16,
        }
        for positive, negative in ((150, 50), (190, 10)):
            plan = dry_run(
                _base_config(
                    n_independent_calibration=positive + negative,
                    n_positive_calibration=positive,
                    n_negative_calibration=negative,
                    n_independent_evaluation=positive + negative,
                    n_positive_evaluation=positive,
                    n_negative_evaluation=negative,
                    **wide,
                )
            )
            self.assertGreaterEqual(min(positive, negative), plan.wilson.required_n)
            self.assertEqual(plan.sample_size_label, "UNDERPOWERED_DRY_RUN")
            self.assertEqual(plan.execution_mode, "smoke_only")
            self.assertEqual(plan.engineering_minimum_note, "engineering minimum, not a power guarantee")
            self.assertFalse(plan.would_execute()["executed"])
        with self.assertRaises(GridPlanError) as caught:
            dry_run(
                _base_config(
                    n_independent_calibration=23,
                    n_positive_calibration=11,
                    n_negative_calibration=12,
                )
            )
        self.assertEqual(caught.exception.code, "invalid_sample_count")
        self.assertIn("n_positive_calibration", str(caught.exception))
        self.assertNotIn("below either floor", str(caught.exception))

    def test_phase_gates_block_independently_and_aborted_plan_cannot_reload_as_planned(self):
        ids = list(BLOCKING_GATE_IDS)
        self.assertLess(ids.index("phase_dispersion_module"), ids.index("phase_score_limitations_recorded"))
        self.assertEqual(GATE_INTEGRATION_STATE["phase_dispersion_module"], "NOT_INTEGRATED")
        self.assertEqual(GATE_INTEGRATION_STATE["phase_score_limitations_recorded"], "NOT_INTEGRATED")
        module_only = [
            {
                "case_id": "phase_dispersion_module",
                "_source": "git_blob",
                "_path": "absent.json",
                "promotion_decision": "ADMISSIBLE_FOR_ENGINEERING_REPORT",
                "scientific_pass": False,
            }
        ]
        limitations_only = [
            {
                "case_id": "phase_score_limitations_recorded",
                "_source": "git_blob",
                "_path": "absent.json",
                "limitations_recorded": True,
                "promotion_decision": "ADMISSIBLE_FOR_ENGINEERING_REPORT",
                "scientific_pass": False,
            }
        ]
        with patch.object(grid_plan_module, "_ci_discovery_blocked", return_value=False), patch.object(
            grid_plan_module, "_contract_reasons", return_value=[]
        ):
            module_resolved, _module_blockers = grid_plan_module._resolve_gates_from_rows(
                module_only,
                main_sha="a" * 40,
                git_failure=None,
            )
            limitations_resolved, _limitations_blockers = grid_plan_module._resolve_gates_from_rows(
                limitations_only,
                main_sha="a" * 40,
                git_failure=None,
            )
        module_status = {item["gate_id"]: item["status"] for item in module_resolved}
        limitations_status = {item["gate_id"]: item["status"] for item in limitations_resolved}
        self.assertEqual(module_status["phase_dispersion_module"], "not_on_main")
        self.assertEqual(module_status["phase_score_limitations_recorded"], "missing")
        self.assertEqual(limitations_status["phase_score_limitations_recorded"], "not_on_main")
        self.assertEqual(limitations_status["phase_dispersion_module"], "missing")
        self.assertNotEqual(module_status["phase_dispersion_module"], "admissible_on_ancestor")
        self.assertNotEqual(limitations_status["phase_score_limitations_recorded"], "admissible_on_ancestor")

        calls, spy = _spy_calls()
        plan = execute(_base_config(), simulation=spy)
        self.assertEqual(calls, [])
        self.assertTrue(plan.execution["aborted"])
        document = plan.to_dict()
        document["run_state"] = "planned"
        document["grid_execution"] = "RUN"
        document["execution"]["requested"] = False
        document["execution"]["partial_launch"] = True
        document["gate_resolution"] = []
        restored = GridPlan.from_dict(document)
        self.assertEqual(calls, [])
        self.assertNotEqual(restored.run_state, "planned")
        self.assertEqual(restored.run_state, "blocked")
        self.assertEqual(restored.grid_execution, "NOT_RUN")
        self.assertTrue(restored.execution["aborted"])
        self.assertFalse(restored.execution["partial_launch"])
        self.assertFalse(restored.execution["executed"])
        _assert_all_cells_blocked(self, restored)
        document["run_state"] = "running"
        with self.assertRaises(GridPlanError) as caught:
            GridPlan.from_dict(document)
        self.assertEqual(caught.exception.code, "self_declared_state")

    def test_null_pins_ignore_informational_heads_and_reject_substitutes(self):
        for gate_id, row in grid_plan_module.GATE_CONTRACT.items():
            pin = row["pinned_commit"]
            self.assertIsNone(pin, gate_id)
        source = (_REPO_ROOT / "tools" / "simulation_runtime" / "grid_plan.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("PINS_BEHIND_OPEN_PR_HEADS", source)
        self.assertNotIn("OPEN_PR_HEADS_NOT_EVIDENCE", source)
        self.assertNotIn("REQUIRED_SOURCE_SHA", source)
        phase_row = grid_plan_module.GATE_CONTRACT["phase_dispersion_module"]
        self.assertIsNone(phase_row["required_module_path"])
        self.assertEqual(phase_row["required_api_symbols"], ())
        self.assertEqual(phase_row["contract_source"], "contract_declared_unobserved")
        hodge_row = grid_plan_module.GATE_CONTRACT["hodge"]
        self.assertEqual(
            hodge_row["required_module_path"],
            "neurotopology_sim/experimental/topology/hodge_2d.py",
        )
        self.assertIn("hodge_decompose", hodge_row["required_api_symbols"])
        self.assertEqual(hodge_row["contract_source"], "candidate_head_observed")
        self.assertEqual(hodge_row["informational_candidate"]["candidate_pr"], 423)
        self.assertIsNone(hodge_row["pinned_commit"])
        hashed_rows = grid_plan_module._gate_contract_for_hash()
        self.assertTrue(all("candidate_head_observed" not in row for row in hashed_rows))
        self.assertNotIn(
            "1785a3a14e1cdf3c2f27924d64b88b9354cf427f",
            json.dumps(hashed_rows),
        )
        info = grid_plan_module.GATE_CONTRACT["roc_metrics"]["informational_candidate"]
        original_head = info["candidate_head_observed"]
        before_hash_rows = grid_plan_module._gate_contract_for_hash()
        info["candidate_head_observed"] = "not-a-pin"
        try:
            after_hash_rows = grid_plan_module._gate_contract_for_hash()
            reasons = grid_plan_module._contract_reasons(
                "phase_dispersion_module", "a" * 40
            )
        finally:
            info["candidate_head_observed"] = original_head
        self.assertEqual(after_hash_rows, before_hash_rows)
        self.assertNotIn("not-a-pin", json.dumps(after_hash_rows))
        self.assertNotIn("not-a-pin", reasons)
        with patch.dict(
            grid_plan_module.GATE_CONTRACT["phase_dispersion_module"],
            {"required_module_path": "tools/phase_uncertainty/estimator.py"},
        ):
            substitute_reasons = grid_plan_module._contract_reasons(
                "phase_dispersion_module", "a" * 40
            )
        self.assertIn("substitute_module_rejected", substitute_reasons)
        self.assertIn("dependency_not_merged_on_main", substitute_reasons)

    def test_audited_main_sha_is_an_ancestor_or_the_test_fails(self):
        main_sha = _require_audited_main_ancestor(self)
        info = grid_plan_module.GATE_CONTRACT["roc_metrics"]["informational_candidate"]
        original_head = info["candidate_head_observed"]
        info["candidate_head_observed"] = "not-a-pin"
        try:
            unchanged, _blockers = grid_plan_module._resolve_gates_from_rows(
                [],
                main_sha=main_sha,
                git_failure=None,
            )
        finally:
            info["candidate_head_observed"] = original_head
        unchanged_status = {item["gate_id"]: item["status"] for item in unchanged}
        self.assertEqual(unchanged_status["roc_metrics"], "dependency_not_merged_on_main")

        open_head = "55115149c7443ca8b325dc4dbf65d6900c9fdd79"
        not_ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", open_head, main_sha],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(not_ancestor.returncode, 0)
        with patch.dict(
            grid_plan_module.GATE_CONTRACT["four_sphere_forward_model"],
            {"pinned_commit": open_head},
        ):
            rejected, _rejected_blockers = grid_plan_module._resolve_gates_from_rows(
                [],
                main_sha=main_sha,
                git_failure=None,
            )
        rejected_status = {item["gate_id"]: item for item in rejected}
        self.assertEqual(
            rejected_status["four_sphere_forward_model"]["status"],
            "pin_not_ancestor_of_main",
        )
        self.assertNotEqual(
            rejected_status["four_sphere_forward_model"]["status"],
            "admissible_on_ancestor",
        )

        with patch.dict(
            grid_plan_module.GATE_CONTRACT["planar_geometry"],
            {"pinned_commit": main_sha},
        ):
            missing_module, _missing_blockers = grid_plan_module._resolve_gates_from_rows(
                [],
                main_sha=main_sha,
                git_failure=None,
            )
        self.assertEqual(
            {item["gate_id"]: item["status"] for item in missing_module}["planar_geometry"],
            "module_missing_on_main",
        )

        symbol_path = "runs/run_record.py"
        present = subprocess.run(
            ["git", "cat-file", "-e", f"{main_sha}:{symbol_path}"],
            cwd=str(_REPO_ROOT),
            check=False,
        )
        self.assertEqual(present.returncode, 0)
        with patch.dict(
            grid_plan_module.GATE_CONTRACT["winding"],
            {
                "pinned_commit": main_sha,
                "required_module_path": symbol_path,
                "required_api_symbols": ("symbol_absent_from_main_blob",),
            },
        ):
            missing_symbols, _symbol_blockers = grid_plan_module._resolve_gates_from_rows(
                [],
                main_sha=main_sha,
                git_failure=None,
            )
        self.assertEqual(
            {item["gate_id"]: item["status"] for item in missing_symbols}["winding"],
            "symbols_missing_on_main",
        )

        with patch.dict(
            grid_plan_module.GATE_CONTRACT["phase_dispersion_module"],
            {
                "pinned_commit": main_sha,
                "required_module_path": "tools/phase_uncertainty/estimator.py",
            },
        ):
            substitute, _substitute_blockers = grid_plan_module._resolve_gates_from_rows(
                [],
                main_sha=main_sha,
                git_failure=None,
            )
        self.assertEqual(
            {item["gate_id"]: item["status"] for item in substitute}["phase_dispersion_module"],
            "substitute_module_rejected",
        )

        calls, spy = _spy_calls()
        with _resolved_main():
            plan = execute(_base_config(), simulation=spy)
        self.assertEqual(calls, [])
        self.assertEqual(plan.grid_execution, "NOT_RUN")
        self.assertFalse(plan.gate_check["opened"])
        self.assertFalse(plan.execution["partial_launch"])
        blocker = next(
            item
            for item in plan.gate_check["blockers"]
            if item["gate_id"] == "four_sphere_forward_model"
            and item["code"] == "dependency_not_merged_on_main"
        )
        self.assertEqual(blocker["main_sha_checked"], main_sha)
        self.assertIsNone(blocker["pinned_commit"])
        self.assertEqual(blocker["required_module_path"], "physics/eeg_forward/four_sphere.py")
        self.assertIn("forward_potentials", blocker["required_api_symbols"])
        self.assertIn("FourSphereGeometry", blocker["required_api_symbols"])
        self.assertIn("FourSphereResult", blocker["required_api_symbols"])
        self.assertEqual(blocker["contract_source"], "candidate_head_observed")
        self.assertEqual(blocker["candidate_pr"], 418)
        self.assertEqual(
            blocker["candidate_head_observed"],
            "1630d62668422ac14a5eb69c22392540c25ec13d",
        )

    def test_observed_contracts_match_cited_paths_and_do_not_open_on_a_placeholder(self):
        cited_paths = {
            "four_sphere_forward_model": "physics/eeg_forward/four_sphere.py",
            "planar_geometry": "neurotopology_sim/experimental/geometry/planar_triangulation.py",
            "winding": "neurotopology_sim/experimental/topology/winding.py",
            "hodge": "neurotopology_sim/experimental/topology/hodge_2d.py",
            "csd_full_matrix_pinned_mne": "neurotopology_sim/experimental/preprocessing/spherical_csd.py",
            "surrogate_null": "tools/surrogate_nulls/nulls.py",
            "roc_metrics": "neurotopology_sim/experimental/benchmarks/synthetic_forward_roc.py",
        }
        observed = []
        for gate_id, row in grid_plan_module.GATE_CONTRACT.items():
            self.assertIn("contract_source", row)
            self.assertIn(row["contract_source"], {
                "candidate_head_observed",
                "contract_declared_unobserved",
                "limitations_record",
                "ci_collection",
                "nonblocking",
            })
            if row["contract_source"] != "candidate_head_observed":
                continue
            observed.append(gate_id)
            self.assertTrue(row["required_module_path"])
            self.assertTrue(row["required_api_symbols"])
            self.assertTrue(all(isinstance(name, str) and name for name in row["required_api_symbols"]))
            self.assertEqual(row["required_module_path"], cited_paths[gate_id])
        self.assertEqual(set(observed), set(cited_paths))
        roc_symbols = grid_plan_module.GATE_CONTRACT["roc_metrics"]["required_api_symbols"]
        named = grid_plan_module._UNIT_AGGREGATION_NAMED["cluster_any_event_rate"]
        self.assertIn(named["symbol"], roc_symbols)
        self.assertIn("operating_point", roc_symbols)
        self.assertIn("compute_roc", roc_symbols)
        self.assertEqual(named["symbol"], "cluster_any_event_rate")
        hodge = grid_plan_module.GATE_CONTRACT["hodge"]
        self.assertEqual(
            hodge["required_module_path"],
            "neurotopology_sim/experimental/topology/hodge_2d.py",
        )
        self.assertEqual(hodge["contract_source"], "candidate_head_observed")
        self.assertIsNone(hodge["pinned_commit"])
        self.assertEqual(hodge["informational_candidate"]["candidate_pr"], 423)
        self.assertEqual(
            hodge["informational_candidate"]["candidate_head_observed"],
            "1785a3a14e1cdf3c2f27924d64b88b9354cf427f",
        )
        self.assertFalse(hodge["informational_candidate"]["read_by_gate_evaluation"])
        for symbol in (
            "hodge_decompose",
            "HodgeResult",
            "validate_cochain_complex",
            "HodgeError",
        ):
            self.assertIn(symbol, hodge["required_api_symbols"])

        main_sha = _local_main_sha(self)
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", main_sha, main_sha],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(ancestor.returncode, 0)
        gate_id = "four_sphere_forward_model"
        declared = grid_plan_module.GATE_CONTRACT[gate_id]
        placeholder = "\n".join(f"{name} = None" for name in declared["required_api_symbols"]) + "\n"
        real_tracked = grid_plan_module._path_tracked
        real_show = grid_plan_module._git_show

        def tracked(sha, path):
            if path == declared["required_module_path"]:
                return True
            return real_tracked(sha, path)

        def show(sha, path):
            if path == declared["required_module_path"]:
                return placeholder
            return real_show(sha, path)

        calls, spy = _spy_calls()
        before = dry_run(_base_config()).config_hash
        info = grid_plan_module.GATE_CONTRACT["roc_metrics"]["informational_candidate"]
        saved_head = info["candidate_head_observed"]
        saved_pr = info["candidate_pr"]
        info["candidate_head_observed"] = "f" * 40
        info["candidate_pr"] = 999999
        try:
            self.assertEqual(dry_run(_base_config()).config_hash, before)
            with patch.dict(declared, {"pinned_commit": main_sha}), patch.object(
                grid_plan_module, "_path_tracked", side_effect=tracked
            ), patch.object(grid_plan_module, "_git_show", side_effect=show), _resolved_main():
                plan = execute(_base_config(), simulation=spy)
                mutated, _mutated_blockers = grid_plan_module._resolve_gates_from_rows(
                    [],
                    main_sha=main_sha,
                    git_failure=None,
                )
        finally:
            info["candidate_head_observed"] = saved_head
            info["candidate_pr"] = saved_pr
        self.assertEqual(calls, [])
        self.assertFalse(plan.gate_check["opened"])
        self.assertEqual(plan.grid_execution, "NOT_RUN")
        self.assertFalse(plan.execution["executed"])
        four = next(item for item in plan.gate_resolution if item["gate_id"] == gate_id)
        self.assertEqual(four["status"], "missing")
        self.assertNotEqual(four["status"], "admissible_on_ancestor")
        self.assertNotIn("module_missing_on_main", four["reason_codes"])
        self.assertNotIn("symbols_missing_on_main", four["reason_codes"])
        mutated_status = {item["gate_id"]: item["status"] for item in mutated}
        self.assertEqual(mutated_status["roc_metrics"], "dependency_not_merged_on_main")
        hodge_resolved = next(item for item in plan.gate_resolution if item["gate_id"] == "hodge")
        self.assertEqual(hodge_resolved["status"], "dependency_not_merged_on_main")
        self.assertIn("dependency_not_merged_on_main", hodge_resolved["reason_codes"])
        self.assertIsNone(hodge_resolved["pinned_commit"])
        self.assertNotEqual(hodge_resolved["status"], "admissible_on_ancestor")
        self.assertEqual(
            hodge_resolved["required_module_path"],
            "neurotopology_sim/experimental/topology/hodge_2d.py",
        )

        forged = {
            "case_id": "hodge",
            "_source": "git_blob",
            "_path": "reports/hodge.json",
            "promotion_decision": "ADMISSIBLE_FOR_ENGINEERING_REPORT",
            "scientific_pass": False,
            "verified_at_commit": main_sha,
            "source_sha": main_sha,
        }
        for unobserved in ("phase_dispersion_module",):
            with patch.dict(
                grid_plan_module.GATE_CONTRACT[unobserved],
                {
                    "pinned_commit": main_sha,
                    "required_module_path": "runs/run_record.py",
                    "required_api_symbols": (),
                },
            ):
                resolved, blockers = grid_plan_module._resolve_gates_from_rows(
                    [{**forged, "case_id": unobserved}],
                    main_sha=main_sha,
                    git_failure=None,
                )
            row = next(item for item in resolved if item["gate_id"] == unobserved)
            self.assertEqual(row["status"], "module_missing_on_main")
            self.assertIn("module_missing_on_main", row["reason_codes"])
            self.assertNotEqual(row["status"], "admissible_on_ancestor")
            self.assertIn(
                "module_missing_on_main",
                {item["code"] for item in blockers if item["gate_id"] == unobserved},
            )


if __name__ == "__main__":
    unittest.main()
