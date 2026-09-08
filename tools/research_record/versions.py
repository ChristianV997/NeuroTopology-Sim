"""Version constants for the research-record contract.

Bump ``REPORT_SCHEMA_VERSION`` whenever the *output* JSON/Markdown/CSV shape
changes in a way consumers must know about. Bump ``INPUT_CONTRACT_VERSION``
whenever the set/shape of accepted input sections changes. Bump
``COMPILER_VERSION`` whenever the compiler's behavior changes (including
bug fixes) even if the output schema is unchanged.
"""
from __future__ import annotations

REPORT_SCHEMA_VERSION = "1.1.0"
INPUT_CONTRACT_VERSION = "1.1.0"
COMPILER_VERSION = "0.2.0"
