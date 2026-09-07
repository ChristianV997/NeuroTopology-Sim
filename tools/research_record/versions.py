"""Version constants for the research-record contract.

Bump ``REPORT_SCHEMA_VERSION`` whenever the *output* JSON/Markdown/CSV shape
changes in a way consumers must know about. Bump ``COMPILER_VERSION``
whenever the compiler's behavior changes (including bug fixes) even if the
output schema is unchanged.
"""
from __future__ import annotations

REPORT_SCHEMA_VERSION = "1.0.0"
COMPILER_VERSION = "0.1.0"
