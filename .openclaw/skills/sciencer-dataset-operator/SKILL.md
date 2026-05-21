# OpenClaw Skill: sciencer-dataset-operator

## Purpose

Inspects per-dataset readiness across all 6 registered datasets and emits
the next required artifact preparation action.

## Supported datasets

| Dataset ID | Executor available |
|---|---|
| DS005620 | yes (P18.1) |
| DS002094 | no (blocked_dataset_specific_support_required) |
| ds001787 | no (blocked_dataset_specific_support_required) |
| ds003969 | no (blocked_dataset_specific_support_required) |
| ds003816 | no (blocked_dataset_specific_support_required) |
| PhysioNet_GABA | no (blocked_dataset_specific_support_required) |

## Safe commands

- `make real-data-source-matrix`
- `make ds005620-real-artifact-plan`
- `make multi-dataset-real-readiness`
- `make validate-real-data-source-matrix`

## Boundaries

- Never runs real MNE extraction automatically.
- Never runs real Level M / Level T extraction.
- Never runs real benchmark execution.
- Never downloads dataset files.
- For non-DS005620 datasets, real-data stages are always marked
  `blocked_dataset_specific_support_required`.

## Output reference

Multi-dataset matrix outputs: `outputs/btc_icft/multi_dataset_real_execution/`

Per-dataset artifact operator outputs (DS005620):
`outputs/btc_icft/ds005620_real_artifact_operator/`
