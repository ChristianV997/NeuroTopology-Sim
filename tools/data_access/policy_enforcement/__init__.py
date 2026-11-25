"""Static, read-only enforcement for bounded data-access policy."""

from .paths import PathContainment, check_path_containment
from .policy import (
    APPROVED_ACQUISITION_ADAPTERS,
    APPROVED_LAZY_READERS,
    APPROVED_METADATA_OPERATIONS,
    DEFAULT_POLICY,
    DataAccessPolicy,
    POLICY_REGISTRATION_REQUIREMENTS,
    PR346_BOUNDED_ADAPTER_REGISTRATIONS,
)
from .scanner import (
    PolicyFinding,
    PolicyReport,
    scan_file,
    scan_paths,
    scan_repository,
)

__all__ = [
    "APPROVED_ACQUISITION_ADAPTERS",
    "APPROVED_LAZY_READERS",
    "APPROVED_METADATA_OPERATIONS",
    "DEFAULT_POLICY",
    "DataAccessPolicy",
    "PathContainment",
    "PolicyFinding",
    "PolicyReport",
    "POLICY_REGISTRATION_REQUIREMENTS",
    "PR346_BOUNDED_ADAPTER_REGISTRATIONS",
    "check_path_containment",
    "scan_file",
    "scan_paths",
    "scan_repository",
]
