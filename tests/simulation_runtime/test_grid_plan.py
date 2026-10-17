"""Fail-closed tests for the synthetic benchmark grid plan.

These tests do not launch a simulation, download data, or install packages.
"""

from __future__ import annotations

import copy
import json
import math
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from analysis.binomial_planning.planner import plan_sample_size
from tools.evidence_promotion_gate.schema import (
    PROMOTION_DECISIONS,
    PromotionResult,
)
from tools.simulation_runtime.atomic_io import compute_config_hash
from tools.simulation_runtime.grid_plan import (
    ADMISSIBLE_GATE_DECISIONS,
    REQUIRED_GATE_IDS,
    RUN_STATES,
    GridPlan,
    GridPlanError,
    dry_run,
    execute,
)
from tools.simulation_runtime.types import CampaignManifest, Outcome


CHECKED_AT = "2026-01-02T00:00:00+00:00"
VERIFIED_AT = "2026-01-01T00:00:00+00:00"


def _spy_calls():
    calls = []

    def spy(*args, **kwargs):
        calls.append((args, kwargs))

    return calls, spy


def _base_config(**overrides):
    config = {
        "schema_version": "grid_plan_v1",
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
        "calibration_samples": 12,
        "evaluation_samples": 12,
        "wilson_confidence_level": 0.95,
        "wilson_target_full_width": 0.5,
        "wilson_design_p": None,
        "max_cells": 16,
        "max_trials": 1000,
        "max_compute_units": 10000.0,
        "compute_units_per_trial": 1.0,
        "max_evidence_age_s": 86400.0,
    }
    config.update(overrides)
    return config


def _evidence(decision="ADMISSIBLE_FOR_ENGINEERING_REPORT", **per_gate):
    records = []
    for index, gate_id in enumerate(REQUIRED_GATE_IDS):
        record = {
            "gate_id": gate_id,
            "promotion_decision": decision,
            "artifact_sha256": f"{index + 1:064x}",
            "log_pointer": f"log:{gate_id}",
            "verifier": "unit-test-verifier",
            "verified_at": VERIFIED_AT,
        }
        record.update(per_gate.get(gate_id, {}))
        records.append(record)
    return records


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
        self.assertIn("scientific_pass", promotion_fields)
        for missing in ("artifact_sha256", "log_pointer", "verifier", "verified_at", "freshness"):
            self.assertNotIn(missing, promotion_fields)

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

        forward = dry_run(_base_config())
        reversed_keys = {}
        source = _base_config()
        for key in reversed(list(source)):
            reversed_keys[key] = source[key]
        backward = dry_run(reversed_keys)
        self.assertEqual(forward.config_hash, backward.config_hash)
        self.assertEqual(forward.config_hash, compute_config_hash(forward.hash_payload))
        reshuffled = {key: forward.hash_payload[key] for key in reversed(forward.hash_payload)}
        self.assertEqual(compute_config_hash(forward.hash_payload), compute_config_hash(reshuffled))

        swapped_axes = _base_config(
            axes=[
                {
                    "name": "jitter_mm",
                    "unit": "mm",
                    "values": [0, 2.5],
                    "minimum": 0,
                    "maximum": 5,
                },
                {
                    "name": "snr_db",
                    "unit": "dB",
                    "values": [-6, 0, 6],
                    "minimum": -6,
                    "maximum": 6,
                },
            ]
        )
        axes = swapped_axes["axes"]
        other = _base_config(axes=[axes[1], axes[0]])
        self.assertEqual(dry_run(swapped_axes).config_hash, dry_run(other).config_hash)

    def test_hash_changes_on_parameter_seed_and_gate_policy(self):
        original = dry_run(_base_config())
        changed_axis = _base_config()
        changed_axis["axes"][0]["values"] = [-6, 0, 3]
        changed_seed = _base_config(master_seed=101)
        changed_gate = _base_config(max_evidence_age_s=86399.0)
        self.assertNotEqual(original.config_hash, dry_run(changed_axis).config_hash)
        self.assertNotEqual(original.config_hash, dry_run(changed_seed).config_hash)
        self.assertNotEqual(original.config_hash, dry_run(changed_gate).config_hash)
        payload = dict(original.hash_payload)
        payload["required_gate_ids"] = list(payload["required_gate_ids"][:-1])
        self.assertNotEqual(original.config_hash, compute_config_hash(payload))
        self.assertIn("four_sphere_forward_model", original.hash_payload["required_gate_ids"])

    def test_dry_run_lists_cells_and_never_calls_the_simulation(self):
        calls, spy = _spy_calls()
        plan = dry_run(_base_config(), simulation=spy)
        self.assertEqual(calls, [])
        self.assertEqual(plan.run_state, "planned")
        self.assertNotEqual(plan.run_state, "completed")
        self.assertFalse(plan.execution["simulation_invoked"])
        self.assertFalse(plan.execution["launched"])
        self.assertFalse(plan.execution["completed"])
        self.assertFalse(plan.gate_check["opened"])
        self.assertEqual(plan.status_label, "HOLD_SYNTHETIC_ONLY")
        self.assertEqual(plan.cell_count, 3)
        self.assertEqual(len(plan.cells), 3)
        self.assertEqual(plan.trial_count, 3 * 24)
        self.assertEqual(
            [cell["cell_id"] for cell in plan.cells],
            ["cell-0000", "cell-0001", "cell-0002"],
        )
        self.assertEqual(plan.cells[0]["parameter_case"]["axes"], {"snr_db": -6})
        self.assertEqual(plan.cells[0]["null_model_id"], "synthetic_iaaft")
        self.assertEqual(plan.cells[0]["source_model_id"], "synthetic_single_dipole")
        self.assertEqual(plan.cells[0]["calibration_seed"], 11)
        self.assertEqual(plan.cells[0]["evaluation_seed"], 29)
        self.assertTrue(plan.cells[0]["split"]["roles_are_disjoint"])
        manifest = plan.campaign_manifest
        self.assertEqual(manifest.schema_version, "simulation_campaign_manifest_v1")
        self.assertEqual(manifest.configuration_hash, plan.config_hash)
        self.assertEqual(manifest.seed, 100)
        self.assertEqual(len(manifest.units), 3)
        self.assertEqual(manifest.units[0].command, [])
        self.assertFalse(manifest.units[0].retryable)
        self.assertEqual(manifest.environment["data_mode"], "synthetic")
        self.assertFalse(manifest.environment["launches_simulation"])
        self.assertEqual(plan.wilson.required_n, 12)
        self.assertEqual(plan.wilson.status, "found")
        self.assertNotIn("sim.nuisance_scenarios", sys.modules)

    def test_two_axis_enumeration_is_name_sorted_and_budget_matches(self):
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
        self.assertEqual(
            plan.cells[1]["null_model_id"],
            "synthetic_iaaft",
        )

    def test_serialization_roundtrip_ignores_tampered_cells(self):
        plan = dry_run(_base_config())
        encoded = json.dumps(plan.to_dict(), sort_keys=True)
        self.assertEqual(encoded, json.dumps(json.loads(encoded), sort_keys=True))
        document = json.loads(encoded)
        document["cells"][0]["parameter_case"]["axes"]["snr_db"] = 99
        restored = GridPlan.from_dict(document)
        self.assertEqual(restored.config_hash, plan.config_hash)
        self.assertEqual(restored.run_state, "planned")
        self.assertEqual(restored.cells[0]["parameter_case"]["axes"]["snr_db"], -6)
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
            ("non_finite_value", {"wilson_target_full_width": float("nan")}),
            ("empty_axes", {"axes": []}),
            ("empty_axes", {"axes": [{
                "name": "snr_db",
                "unit": "dB",
                "values": [],
                "minimum": -6,
                "maximum": 6,
            }]}),
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
            ("duplicate_axis", {"axes": [{
                "name": "snr_db",
                "unit": "dB",
                "values": [1, 1.0],
                "minimum": 0,
                "maximum": 2,
            }]}),
            ("invalid_range", {"axes": [{
                "name": "snr_db",
                "unit": "dB",
                "values": [0],
                "minimum": 5,
                "maximum": -5,
            }]}),
            ("invalid_range", {"axes": [{
                "name": "snr_db",
                "unit": "dB",
                "values": [7],
                "minimum": -6,
                "maximum": 6,
            }]}),
            ("invalid_range", {"axes": [{
                "name": "snr_db",
                "unit": "  ",
                "values": [0],
                "minimum": -6,
                "maximum": 6,
            }]}),
            ("invalid_range", {"wilson_design_p": 1.5}),
            ("unknown_null_model", {"null_model_ids": ["empirical_surrogate"]}),
            ("unknown_null_model", {"null_model_ids": []}),
            ("unknown_source_model", {"source_model_ids": ["synthetic_iaaft"]}),
            ("duplicate_identifier", {"null_model_ids": ["synthetic_iaaft", "synthetic_iaaft"]}),
            ("invalid_sample_count", {"calibration_samples": 11}),
            ("invalid_sample_count", {"evaluation_samples": 0}),
            ("invalid_sample_count", {"calibration_samples": True}),
            ("invalid_sample_count", {"evaluation_samples": 12.0}),
            ("invalid_sample_count", {"calibration_samples": -4}),
            ("invalid_seed", {"calibration_seed": 29}),
            ("invalid_seed", {"master_seed": True}),
            ("invalid_seed", {"evaluation_seed": -1}),
            ("unsupported_schema_version", {"schema_version": "grid_plan_v2"}),
            ("unsupported_schema_version", {"schema_version": "simulation_campaign_manifest_v1"}),
            ("unknown_field", {"hidden_scientific_parameter": 1}),
            ("over_budget", {"max_cells": 2}),
            ("over_budget", {"max_trials": 70}),
            ("over_budget", {"max_compute_units": 71}),
            ("over_budget", {"max_trials": 5, "calibration_samples": 12, "evaluation_samples": 12}),
            ("invalid_nuisance_scenario_id", {"nuisance_scenario_id": "https://example.invalid/scenario"}),
        ]
        for code, updates in cases:
            with self.subTest(code=code, updates=sorted(updates)):
                calls, spy = _spy_calls()
                with self.assertRaises(GridPlanError) as caught:
                    dry_run(_base_config(**updates), simulation=spy)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(calls, [])

    def test_absolute_cell_ceiling_rejects_before_launch(self):
        values = list(range(64))
        config = _base_config(
            axes=[
                {
                    "name": "left_index",
                    "unit": "1",
                    "values": values,
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
        bare = dry_run(_base_config())
        self.assertNotEqual(plan.config_hash, bare.config_hash)

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

    def test_gate_failures_are_closed_and_do_not_call_the_simulation(self):
        fresh = _evidence()
        stale = _base_config(max_evidence_age_s=10.0)
        missing = fresh[:-1]
        hold = _evidence(decision="HOLD_SYNTHETIC_ONLY")
        blocked = _evidence(decision="BLOCK_PROMOTION")
        unverified = _evidence()
        unverified[0]["artifact_sha256"] = "ABC"
        unlabeled = _evidence()
        unlabeled[2]["promotion_decision"] = "VERIFIED"
        passed = _evidence()
        passed[1]["promotion_decision"] = Outcome.PASS.value
        future = _evidence()
        future[0]["verified_at"] = "2026-01-03T00:00:00+00:00"
        naive = _evidence()
        naive[0]["verified_at"] = "2026-01-01T00:00:00"
        empty_verifier = _evidence()
        empty_verifier[0]["verifier"] = "  "
        cases = [
            ("invalid_evidence", _base_config(), True, CHECKED_AT),
            ("invalid_evidence", _base_config(), {gate: True for gate in REQUIRED_GATE_IDS}, CHECKED_AT),
            ("missing_gate", _base_config(), missing, CHECKED_AT),
            ("gate_not_admissible", _base_config(), hold, CHECKED_AT),
            ("gate_not_admissible", _base_config(), blocked, CHECKED_AT),
            ("gate_not_admissible", _base_config(), unlabeled, CHECKED_AT),
            ("gate_not_admissible", _base_config(), passed, CHECKED_AT),
            ("unverified_gate", _base_config(), unverified, CHECKED_AT),
            ("unverified_gate", _base_config(), future, CHECKED_AT),
            ("unverified_gate", _base_config(), naive, CHECKED_AT),
            ("unverified_gate", _base_config(), empty_verifier, CHECKED_AT),
            ("unverified_gate", _base_config(), fresh, None),
            ("stale_gate", stale, fresh, CHECKED_AT),
        ]
        for code, config, evidence, checked_at in cases:
            with self.subTest(code=code):
                calls, spy = _spy_calls()
                plan = execute(config, evidence, simulation=spy, checked_at=checked_at)
                self.assertEqual(calls, [])
                self.assertEqual(plan.run_state, "blocked")
                self.assertNotEqual(plan.run_state, "completed")
                self.assertFalse(plan.gate_check["opened"])
                self.assertTrue(plan.execution["refused"])
                self.assertFalse(plan.execution["simulation_invoked"])
                self.assertFalse(plan.execution["launched"])
                self.assertFalse(plan.execution["completed"])
                self.assertIn(code, {item["code"] for item in plan.gate_check["blockers"]})
                self.assertEqual(plan.status_label, "HOLD_SYNTHETIC_ONLY")

    def test_non_record_objects_and_duplicate_gates_fail_closed(self):
        calls, spy = _spy_calls()

        class Declared:
            promotion_decision = "ADMISSIBLE_FOR_ENGINEERING_REPORT"
            scientific_pass = True

        plan = execute(_base_config(), Declared(), simulation=spy, checked_at=CHECKED_AT)
        self.assertEqual(calls, [])
        self.assertEqual(plan.run_state, "blocked")
        self.assertIn("invalid_evidence", {item["code"] for item in plan.gate_check["blockers"]})

        duplicated = _evidence()
        duplicated.append(dict(duplicated[0]))
        plan = execute(_base_config(), duplicated, simulation=spy, checked_at=CHECKED_AT)
        self.assertEqual(calls, [])
        self.assertIn("invalid_evidence", {item["code"] for item in plan.gate_check["blockers"]})

        smuggled = _evidence()
        smuggled[0]["scientific_pass"] = True
        plan = execute(_base_config(), smuggled, simulation=spy, checked_at=CHECKED_AT)
        self.assertFalse(plan.gate_check["opened"])
        self.assertIn("invalid_evidence", {item["code"] for item in plan.gate_check["blockers"]})

    def test_admissible_records_do_not_launch_or_complete(self):
        calls, spy = _spy_calls()
        evidence = _evidence()
        plan = execute(_base_config(), evidence, simulation=spy, checked_at=CHECKED_AT)
        self.assertEqual(calls, [])
        self.assertTrue(plan.gate_check["opened"])
        self.assertEqual(plan.gate_check["blockers"], [])
        self.assertEqual(plan.run_state, "planned")
        self.assertNotEqual(plan.run_state, "completed")
        self.assertFalse(plan.execution["refused"])
        self.assertFalse(plan.execution["launched"])
        self.assertFalse(plan.execution["simulation_invoked"])
        self.assertFalse(plan.execution["completed"])
        self.assertEqual(plan.status_label, "HOLD_SYNTHETIC_ONLY")
        self.assertIsNotNone(plan.evidence_hash)
        reversed_evidence = list(reversed(evidence))
        again = execute(
            _base_config(), reversed_evidence, simulation=spy, checked_at=CHECKED_AT
        )
        self.assertEqual(calls, [])
        self.assertEqual(plan.evidence_hash, again.evidence_hash)
        self.assertEqual(plan.config_hash, again.config_hash)
        changed = _evidence()
        changed[0]["artifact_sha256"] = f"{9:064x}"
        changed_plan = execute(_base_config(), changed, simulation=spy, checked_at=CHECKED_AT)
        self.assertEqual(plan.config_hash, changed_plan.config_hash)
        self.assertNotEqual(plan.evidence_hash, changed_plan.evidence_hash)

        descriptive = execute(
            _base_config(),
            _evidence(decision="ADMISSIBLE_FOR_DESCRIPTIVE_REVIEW"),
            simulation=spy,
            checked_at=CHECKED_AT,
        )
        self.assertTrue(descriptive.gate_check["opened"])
        self.assertEqual(descriptive.run_state, "planned")
        self.assertFalse(descriptive.execution["launched"])
        self.assertEqual(calls, [])

    def test_exact_freshness_boundary(self):
        calls, spy = _spy_calls()
        fresh = execute(
            _base_config(max_evidence_age_s=86400),
            _evidence(),
            simulation=spy,
            checked_at=CHECKED_AT,
        )
        stale = execute(
            _base_config(max_evidence_age_s=86399),
            _evidence(),
            simulation=spy,
            checked_at=CHECKED_AT,
        )
        self.assertTrue(fresh.gate_check["opened"])
        self.assertEqual(stale.run_state, "blocked")
        self.assertIn("stale_gate", {item["code"] for item in stale.gate_check["blockers"]})
        self.assertEqual(calls, [])

    def test_mapping_evidence_is_accepted_only_as_records(self):
        calls, spy = _spy_calls()
        mapping = {record["gate_id"]: dict(record) for record in _evidence()}
        for record in mapping.values():
            record.pop("gate_id")
        plan = execute(_base_config(), mapping, simulation=spy, checked_at=CHECKED_AT)
        self.assertTrue(plan.gate_check["opened"])
        self.assertEqual(calls, [])
        self.assertEqual(plan.run_state, "planned")

    def test_blocked_document_roundtrip_stays_blocked(self):
        plan = execute(
            _base_config(),
            _evidence(decision="HOLD_SYNTHETIC_ONLY"),
            checked_at=CHECKED_AT,
        )
        self.assertEqual(plan.run_state, "blocked")
        restored = GridPlan.from_dict(plan.to_dict())
        self.assertEqual(restored.run_state, "blocked")
        self.assertEqual(restored.config_hash, plan.config_hash)
        forged = plan.to_dict()
        forged["run_state"] = "planned"
        rebuilt = GridPlan.from_dict(forged)
        self.assertEqual(rebuilt.run_state, "blocked")

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
        self.assertTrue(math.isnan(float("nan")))


if __name__ == "__main__":
    unittest.main()
