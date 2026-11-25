#!/usr/bin/env python3
"""Run the offline BB84 write-wait-read memory benchmark as finite JSON."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from physics.quantum_memory_benchmark import (
    ClassicalOUConfig,
    PseudomodeConfig,
    classical_bound_one_bit,
    classical_ou_expected_score,
    classical_ou_trial_scores,
    quantum_write_wait_read,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait-s", type=float, default=2.0e-13)
    parser.add_argument("--temperature-k", type=float, default=310.0)
    parser.add_argument("--mode-frequency-rad-s", type=float, default=1.644e13)
    parser.add_argument("--coupling-rad-s", type=float, default=5.0e11)
    parser.add_argument("--mode-damping-rate-s", type=float, default=2.0e12)
    parser.add_argument("--mode-drive-rad-s", type=float, default=0.0)
    parser.add_argument("--qubit-dephasing-rate-s", type=float, default=3.0e12)
    parser.add_argument("--qubit-relaxation-rate-s", type=float, default=0.0)
    parser.add_argument("--max-step-s", type=float, default=5.0e-15)
    parser.add_argument("--fock-cutoff", type=int, default=10)
    parser.add_argument("--classical-tau-s", type=float, default=1.0e-12)
    parser.add_argument("--classical-stationary-std", type=float, default=0.2)
    parser.add_argument("--trials", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=20261124)
    args = parser.parse_args()

    quantum_config = PseudomodeConfig(
        temperature_K=args.temperature_k,
        mode_frequency_rad_s=args.mode_frequency_rad_s,
        coupling_rad_s=args.coupling_rad_s,
        mode_damping_rate_s=args.mode_damping_rate_s,
        mode_drive_rad_s=args.mode_drive_rad_s,
        qubit_dephasing_rate_s=args.qubit_dephasing_rate_s,
        qubit_relaxation_rate_s=args.qubit_relaxation_rate_s,
        wait_s=args.wait_s,
        max_step_s=args.max_step_s,
        fock_cutoff=args.fock_cutoff,
    )
    classical_config = ClassicalOUConfig(
        wait_s=args.wait_s,
        tau_s=args.classical_tau_s,
        stationary_std=args.classical_stationary_std,
    )
    quantum_result = quantum_write_wait_read(quantum_config)
    classical_exact = classical_ou_expected_score(classical_config)
    classical_sampled = classical_ou_trial_scores(
        classical_config, n_trials=args.trials, seed=args.seed
    )
    payload = {
        "schema_version": "quantum-memory-benchmark-v1",
        "status": "SYNTHETIC_MODEL_ONLY",
        "task": {
            "alphabet": ["Z0", "Z1", "X+", "X-"],
            "receiver_basis_announced_after_wait": True,
            "receiver_gets_input_labels": False,
            "receiver_gets_seed_or_hidden_state": False,
            "postselection": False,
            "memory_capacity": "one qubit versus one classical bit",
        },
        "quantum_config": asdict(quantum_config),
        "classical_config": asdict(classical_config),
        "classical_one_bit_upper_bound": classical_bound_one_bit,
        "quantum": asdict(quantum_result),
        "classical_ou_exact_expectation": asdict(classical_exact),
        "classical_ou_seeded_trials": {
            **asdict(classical_sampled),
            "seed_used_by_evaluator_only": args.seed,
        },
        "limitations": [
            "The pseudomode and OU process are synthetic models, not biological sources.",
            "One qubit and one classical bit have equal nominal alphabet capacity, not equal hardware cost.",
            "The quantum path has an unobserved oscillator during storage; the one-bit bound is not a matched total internal-resource bound.",
            "The one-bit bound is specific to this four-state delayed-basis task.",
        ],
    }
    print(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
