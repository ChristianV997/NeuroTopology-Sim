"""Authoritative data-access migration gate package."""

from .classifier import MigrationClassifier
from .gate import DataAccessMigrationGate
from .types import (
    MANIFEST_SCHEMA_VERSION,
    PERMANENT_EXPIRATION_TOKENS,
    PROHIBITED_EXCEPTION_CATEGORIES,
    PROHIBITED_EXCEPTION_RULES,
    REPORT_SCHEMA_VERSION,
    GateClassification,
    GateReport,
    MigrationEntry,
    MigrationManifest,
    MigrationStatus,
    json_safe,
)
from .validator import (
    EntryValidationResult,
    is_permanent_expiration,
    is_prohibited_exception_rule,
    is_stale_expiration,
    is_wildcard_string,
    parse_iso_date,
    validate_migration_entry,
)

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "PERMANENT_EXPIRATION_TOKENS",
    "PROHIBITED_EXCEPTION_CATEGORIES",
    "PROHIBITED_EXCEPTION_RULES",
    "REPORT_SCHEMA_VERSION",
    "DataAccessMigrationGate",
    "EntryValidationResult",
    "GateClassification",
    "GateReport",
    "MigrationClassifier",
    "MigrationEntry",
    "MigrationManifest",
    "MigrationStatus",
    "is_permanent_expiration",
    "is_prohibited_exception_rule",
    "is_stale_expiration",
    "is_wildcard_string",
    "json_safe",
    "parse_iso_date",
    "validate_migration_entry",
]
