# Compatibility map — phenomenology / perturbation vs generic provenance

**Schema:** `NeuroTopologySim.PhenomenologyPerturbationRecord.v1`  
**Role:** Additive domain trial record. Does **not** replace `RunRecordV1`, `TransitionRecordV1`, or research-cycle ledgers.

## Schema responsibilities

| Layer | Contract | Holds | Does not hold |
|-------|----------|-------|---------------|
| Generic run | `RunRecordV1` | `run_id`, git, argv, metrics, `artifacts` paths | Trial prompt/delay/sync/missingness |
| Transition | `TransitionRecordV1` | Identity, features, governance; general `time_axis` / `intervention` / `preprocessing_provenance` | Typed delayed-report / missingness / sync-uncertainty |
| Research cycle | `HypothesisRecord` / `ExperimentPlan` / … | Claim lifecycle | Trial phenomenology payload |
| **Domain payload** | **This package** | Practice (dose ≠ skill), perturbation+clock, behavior/missingness, delayed report, signal quality, optional physiology/neural features, optional model-inferred latent, origin/causal/evidence enums, privacy status, optional digests | Authenticity / authorship / scientific validity / attainment |

## Parent / child links

- `parent_run_id` → recorded equality to `RunRecordV1.run_id` (not byte verification of the parent file).
- `RunRecordV1.artifacts["phenomenology_perturbation_record"]` → safe relative path to this JSON (via `run_link.merge_run_artifact_pointer`).
- Optional `TransitionRecordV1.artifact_paths["phenomenology_perturbation"]` → same sibling JSON.
- `integrity.path_sha256`: `record_only` stores digests; `verify_paths` byte-checks under `verify_root`.

**Hashes support integrity of specified bytes only** — not authenticity, reproducibility of computation, scientific validity, or attainment.

## Claim limits (normalized on every record)

Dose ≠ skill; report ≠ latent; model estimate ≠ participant report; EEG/physiology feature ≠ consciousness/attainment; slow parameter ≠ liberation; digest ≠ authenticity/validity.

## Integration status

- Local validators + `run_integration_path` / `write_bundle_with_byte_check` helpers.
- Not a required field on every generic run.
- Production writers, TransitionStore persistence of domain JSON, and batch3 allowlisting remain optional follow-ups.
