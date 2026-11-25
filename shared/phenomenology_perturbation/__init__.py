"""Additive phenomenology / perturbation domain record.

This package does **not** replace ``runs.RunRecordV1`` or C5 provenance sidecars.
It records practice context, perturbation timing, behavior, delayed reports,
signal-quality metadata, optional physiology/neural *features*, and optional
*explicitly labeled* model-inferred latents with uncertainty.

Conceptual distinctions enforced in field naming and validation:
- latent state ``x_t`` is not treated as directly observed;
- practice-control skill ``k_s`` is not practice dose;
- slow transition parameters ``theta_w`` are not attainment / liberation;
- a delayed report is an observation about a target interval, not ``x_t``;
- EEG / physiology features are not consciousness or attainment labels;
- digests support integrity checking only, not authenticity or scientific validity.

No attainment, jhāna, liberation, diagnosis, or consciousness classifier.
"""

from .record import (
    SCHEMA,
    PhenomenologyPerturbationRecord,
    PhenomenologyValidationError,
    dumps_record,
    loads_record,
    validate_record_dict,
)
from .paths import safe_relative_path
from .run_link import (
    RUN_ARTIFACT_KEY,
    TRANSITION_ARTIFACT_KEY,
    assert_parent_run_id_matches,
    merge_run_artifact_pointer,
    pointer_for_run_artifacts,
    provenance_layer_map,
)
from .integration_path import run_integration_path, write_bundle_with_byte_check

__all__ = [
    "SCHEMA",
    "PhenomenologyPerturbationRecord",
    "PhenomenologyValidationError",
    "dumps_record",
    "loads_record",
    "validate_record_dict",
    "safe_relative_path",
    "RUN_ARTIFACT_KEY",
    "TRANSITION_ARTIFACT_KEY",
    "assert_parent_run_id_matches",
    "merge_run_artifact_pointer",
    "pointer_for_run_artifacts",
    "provenance_layer_map",
    "run_integration_path",
    "write_bundle_with_byte_check",
]
