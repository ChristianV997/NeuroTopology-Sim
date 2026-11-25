# Triadic feature contract

This document defines the additive adapter contract for converting a bounded
triadic-functional-connectivity result into a canonical feature/provenance
record. The adapter creates interoperable records; it does not create
scientific evidence, causal claims, biological mechanisms, or a Bayesian PASS.

## Versioned input envelope

The input object must have `schema_version` equal to
`triadic-functional-connectivity-input-v1` and must explicitly contain:

- `channels`: unique channel names;
- `window`: `window_id`, `start_s`, `end_s`, positive `sample_count`, positive
  `sampling_rate_hz`, non-empty `units`, and explicit `condition_labels`;
- `method`: a declared estimator, surrogate method, and deterministic integer
  seed;
- `resources`: bounded `candidate_count`, `max_triads`, and finite memory
  telemetry;
- `provenance`: source ID, SHA-256 source checksum, provenance checksum,
  `data_mode`, `synthetic_demo`, and evidence class;
- `result`: ordered triadic interactions, optional top-triad IDs, complexity
  telemetry, and separately named control results.

Every interaction has a canonical identity of the form
`triad:i,j,k`, where `i < j < k` are distinct channel indices. Scores are
finite, and interactions are ordered by descending `combined_score` followed by
triad ID. The adapter never silently transposes arrays or infers labels.

## Canonical output

The output schema is `triadic-feature-contract-v1`. It contains a source
checksum, deterministic adapter checksum, evidence class, synthetic-demo flag,
window and method metadata, resource telemetry, validation findings, and a
`features` object with independent namespaces:

| Namespace | Meaning |
| --- | --- |
| `triadic_statistical_dependence` | Bounded statistical dependence among three channels. |
| `pairwise_connectivity` | Pairwise control or feature, if supplied. |
| `psd_control` | Power-spectral-density control, if supplied. |
| `common_driver_control` | Common-driver control, if supplied. |
| `graph_beta_1` | Separate graph-persistence feature; never inferred from triadic scores. |
| `spatial_phase_charge` | Separate spatial phase/topological feature; never inferred from triadic scores. |
| `causal_influence` | Separate directed causal analysis; never inferred from triadic scores. |

Unavailable values are represented as JSON `null`, never as NaN or Infinity.
The Markdown and JSON serializers are deterministic and use the same canonical
payload checksum.

## Provenance and evidence semantics

Synthetic demonstrations are marked `synthetic_demo` and are engineering
validation only. They cannot be treated as empirical evidence. Empirical data
must declare empirical mode and complete source provenance. Missing source
checksums, units, sampling rates, condition labels, bounds, or provenance are
contract errors rather than implicit defaults.

The adapter accepts condition labels only when explicitly declared. It rejects
inferred behavioral labels and topology labels attached to triadic statistical
scores. No metadata-only input can establish a biological interpretation.

## RunRecordV1 relationship

`RunRecordV1` in `runs/run_record.py` remains the canonical run record. This
adapter does not create a competing run-record schema. A caller may store the
serialized feature record as a referenced artifact or metric in a
`RunRecordV1`, preserving the run record's existing schema and provenance
rules.

## No network and optional capabilities

The adapter has no network code, performs no downloads, and does not require
MNE, SciPy, PyTorch, or any other optional package. Optional upstream solver
capabilities are represented in their own result metadata; an unavailable
capability must not be converted into a passing feature. The adapter validates
the contract only and does not execute a solver.
