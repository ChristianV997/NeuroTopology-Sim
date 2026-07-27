from pathlib import Path
from scripts.run_eeg_topology_analysis import parser, run


def test_synthetic_eeg_stream_produces_strict_artifacts(tmp_path: Path) -> None:
    args = parser().parse_args(["--synthetic-samples", "1000", "--chunk-samples", "250", "--output-dir", str(tmp_path)])
    payload = run(args)
    assert payload["source"] == "synthetic_eeg_demo"
    assert len(payload["metrics"]) == 4
    assert all(record["beta1"] >= 0 for record in payload["metrics"])
    assert (tmp_path / "eeg_topology_results.json").is_file()
