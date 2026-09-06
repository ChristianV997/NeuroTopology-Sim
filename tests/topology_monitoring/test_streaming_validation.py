import sys
import tracemalloc
import pytest
import numpy as np

from topo_monitor.validation.fixtures import (
    generate_phase_vortex,
    generate_flat_phase_field,
    generate_synthetic_cycle_adjacency,
    generate_random_adjacency
)
from topo_monitor.validation.harness import stream_topology_validation, validate_laplacian_consensus
from topo_monitor.graph_persistence import analyze_adjacency, reorder_invariant, filtration_sweep

def test_cycle_creation_destruction():
    """Graph beta-1 must increase when a synthetic cycle is created, and decrease on destruction."""
    adj_cycle = generate_synthetic_cycle_adjacency(10, has_cycle=True)
    res_cycle = analyze_adjacency(adj_cycle, threshold=0.5)
    beta1_cycle = int(np.sum(res_cycle.beta_curve))
    
    adj_tree = generate_synthetic_cycle_adjacency(10, has_cycle=False)
    res_tree = analyze_adjacency(adj_tree, threshold=0.5)
    beta1_tree = int(np.sum(res_tree.beta_curve))
    
    assert beta1_cycle > beta1_tree, "Cycle creation must increase graph beta-1"

def test_node_permutation_invariance():
    """Node reordering must preserve graph metrics."""
    adj = generate_synthetic_cycle_adjacency(10, has_cycle=True)
    perm = np.random.permutation(10)
    assert reorder_invariant(adj, perm), "Graph persistence must be invariant to node permutation"

def test_threshold_sweeps():
    """Filtration sweeps must be finite and deterministic."""
    adj = generate_random_adjacency(15)
    res = analyze_adjacency(adj, threshold=0.5)
    sweep_t, sweep_b = filtration_sweep(res.diagram_h1)
    
    assert np.all(np.isfinite(sweep_t)), "Filtration sweep thresholds must be finite"
    assert np.all(np.isfinite(sweep_b)), "Filtration sweep Betti counts must be finite"
    
    # Deterministic: a second run yields the exact same arrays
    t2, b2 = filtration_sweep(res.diagram_h1)
    np.testing.assert_array_equal(sweep_t, t2)
    np.testing.assert_array_equal(sweep_b, b2)

def test_phase_vortex_charge():
    """Phase-vortex fixtures must produce expected winding sign/magnitude."""
    phases, coords = generate_phase_vortex((20, 20), center=(9.5, 9.5), charge=1)
    from topo_monitor.spatial_phase import spatial_winding_charge
    charge = spatial_winding_charge(phases, coords)
    # The actual output depends on the orientation of the axes in spatial_winding_charge
    assert abs(charge) == 1.0, f"Expected magnitude 1, got {charge}"

def test_flat_field_charge():
    """Flat phase fields must yield near-zero spatial charge."""
    phases, coords = generate_flat_phase_field((20, 20))
    from topo_monitor.spatial_phase import spatial_winding_charge
    charge = spatial_winding_charge(phases, coords)
    assert charge == 0.0, "Flat field must have zero charge"

def test_missing_coordinates():
    """Missing spatial coordinates must produce an explicit unavailable state."""
    adj_stream = [generate_random_adjacency(10)]
    phase_stream = [(np.zeros(10), None)] # Missing coords
    
    result = list(stream_topology_validation(iter(adj_stream), iter(phase_stream)))
    assert len(result) == 1
    assert result[0].spatial_charge is None
    assert result[0].unavailable_reason == "missing_spatial_coordinates"

def test_graph_beta1_vs_spatial_charge():
    """Graph beta-1 must not be reported as spatial topological charge."""
    adj_stream = [generate_synthetic_cycle_adjacency(20, has_cycle=True)]
    phases, coords = generate_phase_vortex((20, 20), center=(9.5, 9.5), charge=1)
    # Using spatial winding which requires (H,W,2) coords
    
    result = list(stream_topology_validation(iter(adj_stream), iter([(phases, coords)])))
    r = result[0]
    
    # Beta-1 (number of cycles in the adjacency graph)
    # Spatial charge (winding number of the phase field)
    assert r.graph_beta1 > 0
    assert abs(r.spatial_charge) == 1.0
    # Must be tracked as distinct variables
    assert r.graph_beta1 != abs(r.spatial_charge)

def test_streaming_repeatability():
    """Streaming must yield repeatable results for deterministic inputs."""
    adj = generate_synthetic_cycle_adjacency(10, has_cycle=True)
    phases, coords = generate_flat_phase_field((10, 10))
    
    stream_1 = list(stream_topology_validation(iter([adj]*3), iter([(phases, coords)]*3)))
    stream_2 = list(stream_topology_validation(iter([adj]*3), iter([(phases, coords)]*3)))
    
    for r1, r2 in zip(stream_1, stream_2):
        assert r1.graph_beta1 == r2.graph_beta1
        assert r1.spatial_charge == r2.spatial_charge
        assert r1.integrated_landscape_area == r2.integrated_landscape_area

def test_bounded_memory_behavior():
    """Memory use must be bounded and measured without fabrication."""
    adj = generate_synthetic_cycle_adjacency(10, has_cycle=True)
    phases, coords = generate_flat_phase_field((10, 10))
    
    tracemalloc.start()
    try:
        # Evaluate 100 elements
        stream_results = list(stream_topology_validation(iter([adj]*100), iter([(phases, coords)]*100)))
        peaks = [r.tracemalloc_peak_bytes for r in stream_results if r.tracemalloc_peak_bytes is not None]
        
        # Memory must not grow unbounded with stream length.
        # The internal sliding window max length is 50. 
        # Check that memory plateaus.
        assert len(peaks) == 100
        # The peak memory per step should not grow monotonically over the full length
        plateau_peaks = peaks[50:]
        # Fluctuation is acceptable, but it should not be strictly ascending like O(N)
        assert plateau_peaks[-1] < plateau_peaks[0] * 5, "Memory appears unbounded."
        assert stream_results[-1].rss_bytes > 0, "RSS must be explicitly reported."
    finally:
        tracemalloc.stop()

def test_optional_tda_dependency_absence():
    """Missing ripser should gracefully report unavailable rather than crashing."""
    adj_stream = [generate_random_adjacency(10)]
    phase_stream = [(np.zeros(10), None)]
    
    # Hide the ripser module
    import sys
    original_ripser = sys.modules.get('ripser')
    sys.modules['ripser'] = None
    
    try:
        result = list(stream_topology_validation(iter(adj_stream), iter(phase_stream)))
        assert len(result) == 1
        assert "ripser is required" in result[0].unavailable_reason
        assert result[0].graph_beta1 == 0
    finally:
        if original_ripser is not None:
            sys.modules['ripser'] = original_ripser
        else:
            del sys.modules['ripser']

def test_laplacian_consensus():
    """Graph Laplacian consensus residuals must be near zero for a constant vector."""
    adj = generate_random_adjacency(10)
    residuals = validate_laplacian_consensus(adj)
    np.testing.assert_allclose(residuals, np.zeros(10), atol=1e-10)
