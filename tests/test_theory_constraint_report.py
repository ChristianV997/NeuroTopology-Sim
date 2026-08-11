import json

from tools.build_theory_constraint_report import build


def test_constraint_report_marks_empirical_data_as_soft_only(tmp_path):
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    (campaign / "phase_diagram_summary.json").write_text(json.dumps({"n_successful": 1}), encoding="utf-8")
    output = tmp_path / "constraints.json"
    payload = build(campaign, output)
    assert payload["interpretation"]["role"] == "soft_constraint_only"
    ds005620 = payload["empirical_constraints"]["ds005620"]
    assert ds005620.get("status", "loaded") in {"loaded", "missing"}
    assert output.is_file()
