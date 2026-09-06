"""
Synthetic fixtures for validation of streaming topology metrics.
WARNING: All fixtures herein are for demonstration and validation only.
They do not constitute empirical evidence and must not be used to fabricate scientific claims.
"""
import numpy as np

def generate_phase_vortex(shape: tuple[int, int], center: tuple[float, float], charge: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate an analytic phase vortex fixture.
    WARNING: demonstration-only.
    """
    y, x = np.mgrid[0:shape[0], 0:shape[1]]
    coords = np.stack([y, x], axis=-1).astype(float)
    dy = y - center[0]
    dx = x - center[1]
    
    # Calculate phase with a given winding charge
    phases = float(charge) * np.arctan2(dy, dx)
    # Wrap to [-pi, pi]
    phases = (phases + np.pi) % (2 * np.pi) - np.pi
    
    return phases, coords

def generate_flat_phase_field(shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate a flat phase field (zero spatial charge).
    WARNING: demonstration-only.
    """
    y, x = np.mgrid[0:shape[0], 0:shape[1]]
    coords = np.stack([y, x], axis=-1).astype(float)
    phases = np.zeros(shape, dtype=float)
    return phases, coords

def generate_synthetic_cycle_adjacency(n_nodes: int, has_cycle: bool) -> np.ndarray:
    """
    Generate an adjacency matrix representing a graph.
    If has_cycle is True, creates a clear 1D cycle (ring) which increases graph beta-1.
    If has_cycle is False, creates a star graph or tree with zero beta-1.
    WARNING: demonstration-only.
    """
    adj = np.zeros((n_nodes, n_nodes), dtype=float)
    if has_cycle:
        for i in range(n_nodes):
            adj[i, (i + 1) % n_nodes] = 1.0
            adj[(i + 1) % n_nodes, i] = 1.0
    else:
        # Star graph: node 0 is connected to all other nodes, no cycles
        for i in range(1, n_nodes):
            adj[0, i] = 1.0
            adj[i, 0] = 1.0
    return adj

def generate_random_adjacency(n_nodes: int, seed: int = 42) -> np.ndarray:
    """Generate a random symmetric weighted adjacency matrix in [0, 1]."""
    rng = np.random.default_rng(seed)
    arr = rng.uniform(0, 1, size=(n_nodes, n_nodes))
    arr = (arr + arr.T) / 2
    np.fill_diagonal(arr, 0)
    return arr
