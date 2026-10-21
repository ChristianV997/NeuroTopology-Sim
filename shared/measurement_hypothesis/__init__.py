"""Two-layer measurement/hypothesis mapping contract.

The validator checks that a proposed mapping from an operational feature to a theoretical
interpretation is well formed, resolves to code, cites its sources, and is worded as a
proposal. It reads the existing claim gate and never changes an evidence state.
"""

from .schema import REPORT_SCHEMA, SCHEMA
from .validate import load_mapping, validate_mapping

__all__ = ["REPORT_SCHEMA", "SCHEMA", "load_mapping", "validate_mapping"]
