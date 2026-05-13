# DS005620 Artifact Contracts

## Purpose
Define stable, machine-readable contract files for P18.1 DS005620 artifacts and enforce them with a stdlib validator.

## Why artifact contracts matter
Contracts prevent silent shape drift in JSON outputs used by CI and downstream automation.

## Contract files
Located in `contracts/btc_icft/ds005620/p18_1/`:
- `ds005620_real_benchmark_execution.contract.json`
- `stage_execution_plan.contract.json`
- `stage_results.contract.json`
- `execution_blockers.contract.json`
- `omega_event.contract.json`
- `validation_summary.contract.json`

## Validator command
```bash
python tools/validate_ds005620_contracts.py \
  --root outputs/btc_icft/ds005620_real_benchmark_execution_mock \
  --contracts contracts/btc_icft/ds005620/p18_1
```

## What is checked
- Required keys and value types.
- Allowed stage IDs (`P12`, `P13`, `P11`).
- Stage command constraints for P12/P13/P11 wiring.
- Omega false invariants.
- Validation summary consistency.

## What is intentionally not checked
- Runtime performance claims.
- Real-data scientific interpretation.

## Relationship to P18.1
P18.1 remains execution-focused; this layer hardens artifact compatibility.

## Relationship to future P18.2 runtime autonomy kernel
This contract layer provides replay-safe interfaces for later autonomy logic.

## CI integration
`make ds005620-e2e-ci` and workflow now call both JSON summary validation and contract validation.

## Guardrails
Allowed safe claim:

> DS005620 P18.1 artifacts are now contract-validated for stable automation and replay-safe downstream tooling.
