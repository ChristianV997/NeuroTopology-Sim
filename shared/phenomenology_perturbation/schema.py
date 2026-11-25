"""Closed vocabularies for the phenomenology / perturbation domain record."""

from __future__ import annotations

SCHEMA = "NeuroTopologySim.PhenomenologyPerturbationRecord.v1"

# Empirical vs synthetic labeling — never inferred.
DATA_STATUSES = frozenset({
    "synthetic",
    "empirical_measured",
    "mixed_declared",
})

OBSERVATION_ORIGINS = frozenset({
    "synthetic",
    "measured",
})

CAUSAL_CLAIM_TYPES = frozenset({
    "none",
    "associational",
    "randomized_intervention_intent",
    "observational_timing_only",
})

# Epistemic status of *this trial record* — not scientific validity of a theory.
EVIDENCE_STATUSES = frozenset({
    "none",
    "exploratory_synthetic",
    "recorded_observation",
    "model_inferred_only",
    "inconclusive",
})

PERTURBATION_MODALITIES = frozenset({
    "sensory_probe",
    "task_cue",
    "instruction_change",
    "sham",
    "other_declared",
})

# Latent block must declare this label; never "observed" or "measured".
LATENT_PROFILE_LABEL = "model_inferred"

# Relative artifact path roles (optional pointers).
ARTIFACT_PATH_KEYS = frozenset({
    "eeg_path",
    "physiology_path",
    "behavior_log_path",
    "report_log_path",
    "parent_run_record_path",
})

# Integrity: recorded digests are not authenticity proofs.
INTEGRITY_MODES = frozenset({
    "record_only",   # store declared sha256 hex; do not open files
    "verify_paths",  # require files under a provided root and match bytes
})

TIME_REFERENCES = frozenset({
    "session_t0",
    "recording_clock",
    "ntp_synced_clock",
    "other_declared",
})

# Portable artifacts must not embed direct identifiers.
PROHIBITED_IDENTIFIER_KEYS: frozenset[str] = frozenset({
    "participant_name",
    "subject_full_name",
    "full_name",
    "email",
    "phone",
    "mrn",
    "national_id",
    "address",
    "ip_address",
})

# Soft cap on verbatim delayed-report text in portable JSON.
MAX_REPORT_TEXT_CHARS = 500

# Reject attainment / soteriological / diagnostic classifier language in free text
# and forbidden keys. Matching is case-insensitive substring on normalized text.
PROHIBITED_CLASSIFIER_PHRASES: tuple[str, ...] = (
    "jhana",
    "jhāna",
    "nibbana",
    "nibbāna",
    "nirvana",
    "liberation attained",
    "attainment score",
    "consciousness classifier",
    "diagnos",
    "clinical diagnosis",
    "stream-enterer",
    "arahant",
)

PROHIBITED_KEYS: frozenset[str] = frozenset({
    "jhana_level",
    "attainment",
    "liberation_score",
    "consciousness_class",
    "diagnosis",
    "theta_w_attainment",
})

TOP_LEVEL_REQUIRED = frozenset({
    "schema",
    "record_id",
    "data_status",
    "causal_claim_type",
    "evidence_status",
    "practice",
    "perturbation",
    "behavior",
    "delayed_report",
    "signal_quality",
})

# Privacy metadata — status fields only; schema compliance ≠ privacy pipeline.
CONSENT_STATUSES = frozenset({
    "synthetic_no_human_subjects",
    "not_recorded",
    "recorded_on_file_off_artifact",
    "unavailable",
})

ACCESS_STATUSES = frozenset({
    "public_synthetic",
    "restricted",
    "unavailable",
})
