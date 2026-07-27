from tools.benchmark_topology_kernel import run_benchmark


def test_topology_benchmark_returns_explicit_measurement_contract():
    result = run_benchmark(channels=4, samples=32, iterations=2, seed=1)
    assert result["kernel"] == "compute_topology_from_channels"
    assert result["iterations"] == 2
    assert result["elapsed_seconds"] >= 0.0
    assert result["milliseconds_per_window"] >= 0.0
    assert result["windows_per_second"] is not None
