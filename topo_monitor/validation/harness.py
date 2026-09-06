"""
Validation harness for streaming topology metrics.
Executes bounding, measurement, and metric separation logic.
"""
from __future__ import annotations
import tracemalloc
import os
import psutil
from collections.abc import Iterator
import numpy as np
from dataclasses import dataclass

from topo_monitor.graph_persistence import analyze_adjacency, reorder_invariant, persistence_diagram
from topo_monitor.spatial_phase import spatial_winding_charge, sensor_spatial_charge

@dataclass
class StreamValidationResult:
    window_index: int
    graph_beta1: int
    integrated_landscape_area: float
    spatial_charge: float | None
    is_anomaly: bool
    rss_bytes: int
    tracemalloc_peak_bytes: int | None
    unavailable_reason: str | None = None

def get_current_rss() -> int:
    process = psutil.Process(os.getpid())
    return process.memory_info().rss

def stream_topology_validation(
    adjacency_stream: Iterator[np.ndarray],
    phase_stream: Iterator[tuple[np.ndarray, np.ndarray | None]],
    threshold: float = 0.5,
    detect_anomalies: bool = True
) -> Iterator[StreamValidationResult]:
    """
    Process streaming data in bounded windows.
    - Graph beta-1 vs spatial charge separation.
    - Missing coordinates yield explicit unavailable state.
    - Returns physical RSS and tracemalloc peaks.
    """
    baseline_beta1 = []
    
    for i, (adj, (phases, coords)) in enumerate(zip(adjacency_stream, phase_stream)):
        if tracemalloc.is_tracing():
            tracemalloc.clear_traces()
            
        unavailable_reason = None
        spatial_charge = None
        
        # 1. Spatial Charge Validation
        if coords is None:
            unavailable_reason = "missing_spatial_coordinates"
        else:
            try:
                if phases.ndim == 2:
                    spatial_charge = spatial_winding_charge(phases, coords)
                elif phases.ndim == 1:
                    spatial_charge = sensor_spatial_charge(phases, coords)
            except ValueError as e:
                unavailable_reason = str(e)
                
        # 2. Graph Persistence Validation
        try:
            res = analyze_adjacency(adj, threshold=threshold)
            
            # Explicitly separate graph beta-1 from spatial topological charge
            # by storing beta-1 and making sure they are semantically distinct
            beta1_count = int(np.sum(res.beta_curve)) if res.beta_curve.size > 0 else 0
            
            # Rolling anomaly detection (simple change-point logic)
            is_anomaly = False
            if detect_anomalies and baseline_beta1:
                mean_b1 = np.mean(baseline_beta1[-10:])
                std_b1 = np.std(baseline_beta1[-10:])
                if std_b1 > 0 and abs(beta1_count - mean_b1) > 3 * std_b1:
                    is_anomaly = True
            
            baseline_beta1.append(beta1_count)
            if len(baseline_beta1) > 50:
                baseline_beta1.pop(0)  # Bounded window for memory safety
                
            peak_tracemalloc = tracemalloc.get_traced_memory()[1] if tracemalloc.is_tracing() else None
            
            yield StreamValidationResult(
                window_index=i,
                graph_beta1=beta1_count,
                integrated_landscape_area=res.integrated_landscape_area,
                spatial_charge=spatial_charge,
                is_anomaly=is_anomaly,
                rss_bytes=get_current_rss(),
                tracemalloc_peak_bytes=peak_tracemalloc,
                unavailable_reason=unavailable_reason
            )
        except Exception as e:
            # Yield gracefully on computation failure instead of crashing the stream
            yield StreamValidationResult(
                window_index=i,
                graph_beta1=0,
                integrated_landscape_area=0.0,
                spatial_charge=spatial_charge,
                is_anomaly=False,
                rss_bytes=get_current_rss(),
                tracemalloc_peak_bytes=None,
                unavailable_reason=f"computation_error: {str(e)}"
            )

def validate_laplacian_consensus(adjacency: np.ndarray) -> np.ndarray:
    """
    Computes graph Laplacian and returns consensus residuals.
    L = D - W
    """
    degrees = np.sum(adjacency, axis=1)
    laplacian = np.diag(degrees) - adjacency
    # The consensus residuals for a constant vector should be zero
    constant_vec = np.ones(adjacency.shape[0])
    residuals = laplacian @ constant_vec
    return residuals
