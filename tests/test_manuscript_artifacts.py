from scripts.build_manuscript_artifacts import build_manuscript_artifacts

def test_build_manuscript_assets_from_local_artifacts(tmp_path):
    root = tmp_path / "pitnn"
    (root / "research_campaign").mkdir(parents=True)
    (root / "dsim_export").mkdir()
    (root / "research_campaign" / "research_insights_summary.json").write_text('{"ep_boundary":{"pump_s":1.5,"loss_s":2.5}}')
    (root / "dsim_export" / "empirical_falsification_report.json").write_text('{"bayes_factor":1.0,"verdict":"NOT_SUPPORTED","comparison":{"pitnn":{"rss":1,"aicc":2},"classical_wilson_cowan":{"rss":2,"aicc":3}},"conditions":{}}')
    output = build_manuscript_artifacts(root, tmp_path / "manuscript")
    assert all(__import__("pathlib").Path(path).is_file() for path in output.values())
