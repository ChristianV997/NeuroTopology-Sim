"""Statistical-assumption audit.

Reviews declared cohort-statistics, null-calibration, and preregistration
reports. Does not recompute K or emit a scientific PASS.
"""

from .audit import audit_payload, audit_sources

__all__ = ["audit_payload", "audit_sources"]
