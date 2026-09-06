#!/usr/bin/env python3
"""
Validation CLI for Topology Streaming.
Produces JSON and Markdown summaries of validation fixtures.
"""
import argparse
import json
import sys
import math
from pathlib import Path
import tracemalloc

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from topo_monitor.validation.fixtures import (
    generate_synthetic_cycle_adjacency,
    generate_phase_vortex,
    generate_flat_phase_field
)
from topo_monitor.validation.harness import stream_topology_validation

def sanitize_json(val):
    """Ensure no NaN or Infinity is emitted to JSON."""
    if val is None:
        return None
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
    return val

def run_validation(n_steps: int = 10):
    """Run a small bounded simulation of streaming topology."""
    tracemalloc.start()
    
    # 1. Setup a fixture sequence
    # 5 steps of tree, 5 steps of cycle
    def generate_adj():
        for i in range(n_steps):
            yield generate_synthetic_cycle_adjacency(15, has_cycle=(i >= 5))
            
    # 5 steps flat phase, 5 steps vortex
    def generate_phases():
        for i in range(n_steps):
            if i < 5:
                yield generate_flat_phase_field((10, 10))
            else:
                yield generate_phase_vortex((10, 10), center=(4.5, 4.5), charge=1)
                
    results = list(stream_topology_validation(
        generate_adj(),
        generate_phases(),
        threshold=0.5,
        detect_anomalies=True
    ))
    
    tracemalloc.stop()
    
    # Format JSON
    json_results = []
    for r in results:
        json_results.append({
            "window_index": r.window_index,
            "graph_beta1": sanitize_json(r.graph_beta1),
            "integrated_landscape_area": sanitize_json(r.integrated_landscape_area),
            "spatial_charge": sanitize_json(r.spatial_charge),
            "is_anomaly": r.is_anomaly,
            "rss_bytes": r.rss_bytes,
            "tracemalloc_peak_bytes": sanitize_json(r.tracemalloc_peak_bytes),
            "unavailable_reason": r.unavailable_reason
        })
        
    return json_results

def print_markdown(json_results, out_file=sys.stdout):
    print("# Streaming Topology Validation Report\n", file=out_file)
    print("## Validation Summary\n", file=out_file)
    print("| Step | Graph Beta-1 | Spatial Charge | Landscape Area | Anomaly | RSS (MB) |", file=out_file)
    print("|------|--------------|----------------|----------------|---------|----------|", file=out_file)
    for r in json_results:
        b1 = r['graph_beta1']
        sc = r['spatial_charge']
        sc_str = f"{sc:.1f}" if sc is not None else "null"
        la = r['integrated_landscape_area']
        la_str = f"{la:.3f}" if la is not None else "null"
        an = "Yes" if r['is_anomaly'] else "No"
        rss_mb = r['rss_bytes'] / 1e6 if r['rss_bytes'] else 0.0
        
        print(f"| {r['window_index']} | {b1} | {sc_str} | {la_str} | {an} | {rss_mb:.2f} |", file=out_file)
        
    print("\n*Note: All values NaN or Infinity are strictly reported as `null`.*", file=out_file)

def main():
    parser = argparse.ArgumentParser(description="Validate streaming topology components.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--steps", type=int, default=10, help="Bounded sequence length")
    parser.add_argument("--out", type=Path, default=None, help="Output file path")
    args = parser.parse_args()
    
    results = run_validation(args.steps)
    
    out_file = args.out.open("w", encoding="utf-8") if args.out else sys.stdout
    try:
        if args.format == "json":
            json.dump(results, out_file, indent=2)
            if out_file is not sys.stdout:
                print(f"Validation JSON written to {args.out}")
        else:
            print_markdown(results, out_file=out_file)
            if out_file is not sys.stdout:
                print(f"Validation Markdown written to {args.out}")
    finally:
        if args.out:
            out_file.close()

if __name__ == "__main__":
    sys.exit(main())
