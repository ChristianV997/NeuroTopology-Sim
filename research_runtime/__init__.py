"""Governed research-run primitives for state-transition campaigns."""

from .envelope import RunEnvelope, build_code_manifest, build_input_manifest, canonical_json, sha256_text
from .protocol import ProtocolSpec, deterministic_subject_split
from .stage_policy import StageLock, StagePolicyError

__all__ = [
    "RunEnvelope",
    "ProtocolSpec",
    "StageLock",
    "StagePolicyError",
    "build_input_manifest",
    "build_code_manifest",
    "canonical_json",
    "deterministic_subject_split",
    "sha256_text",
]
