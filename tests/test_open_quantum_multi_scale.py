from pathlib import Path
from scripts.run_decoherence_sweep import make_parser, run_sweep
from scripts.run_matrix_free_scaling import parser, run


def test_missing_pdb_uses_explicit_deterministic_disorder(tmp_path: Path) -> None:
    args = make_parser().parse_args(["--temperatures", "310", "--pdb", str(tmp_path / "missing_1jff.pdb"), "--output-dir", str(tmp_path / "pdb")])
    payload = run_sweep(args)
    assert payload["source"] == "pdb_synthetic_disorder"
    assert (tmp_path / "pdb" / "decoherence_sweep.json").is_file()


def test_two_layer_routes_to_exact_dense_solver(tmp_path: Path) -> None:
    args = parser().parse_args(["--n-layers", "2", "--output-dir", str(tmp_path)])
    record = run(args)["records"][0]
    assert record["method"] == "exact_dense"
    assert record["converged"] is True
    assert record["trace_preservation_residual_s"] >= 0.0
