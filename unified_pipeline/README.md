# Unified Quantum Lattice + EEG Topology Pipeline

This module integrates the full simulation stack developed for Irreversible Constraint Causality (ICC) research.

## Core Components

- **Nonlinear Fröhlich Pumping** (Kerr-like anharmonicity)
- **Diósi-Penrose Gravitational Dissipator**
- **Active Inference Controller** (dynamic pump rate tuning based on topological cost)
- **Dynamic Topological Data Analysis** (β₁ knots, Q_abs fragmentation)
- **Entropy Production Tracking** (˙Σ with von Neumann + heat currents)
- **Direct Coupling to EEG Mapper** (synthetic coherence signal → Mapper graph simplification)

## Key Results

- Clear Fröhlich threshold with sharp coherence jump and topological simplification.
- Active Inference successfully minimizes topological cost while maximizing coherence.
- Post-threshold states show low persistence entropy and compact Mapper graphs (fewer nodes, shorter paths).
- Strong multi-scale correspondence: Quantum lattice → TDA metrics → EEG-like topology.

## Usage

Run the main unified script:
```bash
python sim/quantum_lattice/unified_frohlich_dp_active_inference_tda_entropy.py
```

Or the coupled version:
```bash
python analysis/eeg_topology/unified_sim_to_eeg_mapper.py
```

## Integration with ds003969

The EEG Mapper component is designed to work with BIDS datasets such as ds003969 (Meditation vs Thinking). See `eeg_mapper_bids_ds003969.py` for the full BIDS loop.