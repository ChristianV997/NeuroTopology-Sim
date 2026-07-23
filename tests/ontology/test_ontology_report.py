from __future__ import annotations

import json
import subprocess
import sys

from sciencer_d.ontology.firewall import scan_text
from sciencer_d.ontology.reports import REPORT_TITLE, build_ontology_report


def test_report_builder_writes_required_artifacts_and_sections(tmp_path):
    paths = build_ontology_report(tmp_path)
    assert set(paths) == {"report", "claims", "scores", "events"}
    assert all(path.is_file() for path in paths.values())

    report = paths["report"].read_text(encoding="utf-8")
    assert report.startswith(f"# {REPORT_TITLE}")
    for section in range(1, 11):
        assert f"## {section}." in report
    assert scan_text(report).allowed is True


def test_report_outputs_keep_sensitive_claims_speculative(tmp_path):
    paths = build_ontology_report(tmp_path)
    scores = {
        row["claim_id"]: row
        for row in json.loads(paths["scores"].read_text(encoding="utf-8"))
    }
    assert scores["O5_SOUL_IDENTITY_INVARIANT"]["status"] == "O-C"
    assert scores["O6_SURVIVAL_AFTER_DEATH"]["status"] == "O-C"
    assert scores["O8_PANPSYCHISM_NEUTRAL_MONISM"]["status"] == "O-C"
    assert scores["O7_FIELD_CONSCIOUSNESS"]["status"] in {"O-B", "O-C"}


def test_report_cli_succeeds(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "sciencer_d.ontology.pipelines.build_ontology_report",
            "--out",
            str(tmp_path),
        ],
        check=False,
    )
    assert completed.returncode == 0
    assert (tmp_path / "level_o_ontology_report.md").is_file()


def test_evidence_events_include_curated_sources_without_status_promotion(tmp_path):
    paths = build_ontology_report(tmp_path)
    events = json.loads(paths["events"].read_text(encoding="utf-8"))
    assert all(event["event_type"] == "curated_seed_review" for event in events)
    assert all(event["source_ids"] for event in events)
    assert next(
        event
        for event in events
        if event["claim_id"] == "O6_SURVIVAL_AFTER_DEATH"
    )["resulting_status"] == "O-C"
