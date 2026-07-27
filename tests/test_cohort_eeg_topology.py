from pathlib import Path

from scripts.run_cohort_eeg_topology import parser, run


def test_empty_local_cohort_is_explicitly_descriptive(tmp_path: Path) -> None:
    args = parser().parse_args(["--data-dir", str(tmp_path / "empty"), "--output-dir", str(tmp_path / "out")])
    result = run(args)
    assert result["discovered_subjects"] == 0
    assert result["wilcoxon_signed_rank"]["mean_beta1"]["status"] == "insufficient_paired_subjects"
    assert (tmp_path / "out" / "cohort_topology_summary.json").is_file()
