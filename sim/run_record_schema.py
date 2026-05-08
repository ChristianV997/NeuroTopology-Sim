"""Compatibility shim — canonical implementation lives in runs.run_record.

All symbols re-exported here for backwards compatibility with existing imports.
New code should import directly from runs.run_record.
"""
from runs.run_record import (
    RunRecordV1 as RunRecord,
    CONFOUNDS_CHECKLIST,
    build_run_id,
    canonicalize_paths,
    validate_run_record_dict,
    RUN_RECORD_SCHEMA,
)

__all__ = [
    "RunRecord",
    "CONFOUNDS_CHECKLIST",
    "build_run_id",
    "canonicalize_paths",
    "validate_run_record_dict",
    "RUN_RECORD_SCHEMA",
]
