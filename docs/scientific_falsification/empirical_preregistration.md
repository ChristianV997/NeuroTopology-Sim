# Empirical-source preregistration

Operator-supplied freeze of dataset identity, condition labels, exclusions,
and planned statistical outcomes. This is a preregistration and readiness
artifact. It is not empirical evidence.

Owned files:

- `configs/empirical_sources/**`
- `scripts/validate_empirical_source_manifest.py`
- `tests/empirical_sources/**`
- `docs/scientific_falsification/empirical_preregistration.md`

Condition labels are preserved exactly. The validator never infers
`awake`, `sedated`, `meditation`, or any other condition from filenames.

## Schema

`NeuroTopologySim.EmpiricalSourceManifest.v1`

## States

- `VALID_PREREGISTRATION` — internally complete plan; not a data result
- `INCOMPLETE_PREREGISTRATION`
- `AMBIGUOUS_CONDITIONS`
- `INVALID_PROVENANCE`
- `SYNTHETIC_DEMO_ONLY`
- `UNAVAILABLE_SOURCE`

The template at `configs/empirical_sources/preregistration.template.yaml`
is `UNAVAILABLE_SOURCE` until an operator supplies identity and labels.
No dataset is reported as validated by this layer.
