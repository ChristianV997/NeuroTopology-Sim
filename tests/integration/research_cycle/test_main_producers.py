"""Black-box probes of origin/main producers; pending Batch 1 modules stay fixtures."""
from __future__ import annotations

import json
from pathlib import Path

from tests.integration.research_cycle.contracts import MISSING_PREREQUISITES, ON_MAIN, STAGE_CONTRACTS
from tests.integration.research_cycle.fixtures import happy_chain, write_happy_chain
from tests.integration.research_cycle.inspector import inspect_directory
from tests.integration.research_cycle.producers import (
    available_main_producers,
    pending_producers,
    probe_artifact_manifest,
    probe_empirical_source,
    probe_release_evidence,
    probe_research_cycle,
    probe_run_record,
    module_available,
)


def test_pending_batch1_modules_are_listed_not_invented() -> None:
    pending = pending_producers()
    for item in MISSING_PREREQUISITES:
        component = item["component"]
        if component.startswith("tools.") or component.startswith("awareness_studio."):
            assert component in pending or component == "research-cycle evidence graph producer"
    assert ("awareness_studio.research_cycle" in pending) is (
        not module_available("awareness_studio.research_cycle")
    )


def test_stage_contract_status_matches_main_availability() -> None:
    available = set(available_main_producers())
    assert "configs.empirical_sources.manifest" in available
    assert "tools.research_cycle" in available
    assert "runs.run_record" in available
    assert "tools.integration_bridge.artifact_manifest" in available
    assert "tools.performance.release_evidence_gate" in available
    assert STAGE_CONTRACTS["literature_source_manifest"]["status"] == ON_MAIN
    assert STAGE_CONTRACTS["research_plan_audit"]["status"] != ON_MAIN
    assert STAGE_CONTRACTS["evidence_graph"]["status"] != ON_MAIN


def test_empirical_source_manifest_consumer_preserves_synthetic_origin() -> None:
    payload = happy_chain()[0]["payload"]
    report = probe_empirical_source(payload)
    assert report["schema"] == "NeuroTopologySim.EmpiricalSourceManifest.v1"
    assert report["origin"] == "synthetic_demo"
    assert report["status"] == "SYNTHETIC_DEMO_ONLY"
    assert report["evidence_claim_allowed"] is False
    assert report["scientific_status"] == "preregistration_only"
    assert report["data_downloaded"] is False


def test_run_record_round_trip_preserves_id_and_data_mode() -> None:
    payload = happy_chain()[3]["payload"]
    encoded = probe_run_record(payload)
    assert encoded["run_id"] == payload["run_id"]
    assert encoded["data_mode"] == "synthetic"
    assert encoded["schema_version"] == "0.1"
    assert encoded["verdict"] is None


def test_artifact_manifest_builder_is_deterministic(tmp_path: Path) -> None:
    (tmp_path / "summary.json").write_text('{"ok": true}\n', encoding="utf-8")
    (tmp_path / "metrics.json").write_text('{"loss": 0.25}\n', encoding="utf-8")
    first = probe_artifact_manifest(tmp_path, ["metrics.json", "summary.json"], "run_synthetic_001")
    second = probe_artifact_manifest(tmp_path, ["summary.json", "metrics.json"], "run_synthetic_001")
    assert first == second
    assert first["schema"] == "NTS.IntegrationArtifactManifest.v1"
    paths = [entry["relative_path"] for entry in first["artifacts"]]
    assert paths == sorted(paths)
    serialized = json.dumps(first, sort_keys=True)
    assert serialized == json.dumps(second, sort_keys=True)


def test_release_evidence_is_performance_only_and_not_scientific_pass() -> None:
    payload = happy_chain()[-1]["payload"]
    report = probe_release_evidence(payload["baseline"], payload["candidate"])
    assert report["schema_version"] == "1.0"
    assert report["evidence_class"] == "performance_only"
    assert report["synthetic"] is True
    assert report["decision"] != "PASS"
    text = json.dumps(report)
    assert "NaN" not in text
    assert "Infinity" not in text


def test_research_cycle_registry_keeps_synthetic_flag() -> None:
    payload = happy_chain()[2]["payload"]
    exported = probe_research_cycle(payload)
    plan = next(iter(exported["plans"].values()))
    assert plan["is_synthetic"] is True
    assert plan["schema_version"] == "ExperimentPlan.v1"
    hypothesis = next(iter(exported["hypotheses"].values()))
    assert hypothesis["provenance"]["source_checksum"]


def test_file_chain_and_main_producers_agree_on_synthetic_labels(tmp_path: Path) -> None:
    write_happy_chain(tmp_path)
    report = inspect_directory(tmp_path)
    assert report.status == "COMPLETE"
    lit = probe_empirical_source(json.loads((tmp_path / "01_literature_source_manifest.json").read_text())["payload"])
    assert lit["origin"] == "synthetic_demo"
    for doc in report.documents:
        assert doc.data_mode in {"synthetic", "proxy"}
        assert doc.scientific_verdict not in {"PASS", "SUPPORTED", "CONFIRMED"}
