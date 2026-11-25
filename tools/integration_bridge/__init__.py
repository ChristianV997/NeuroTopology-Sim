"""Integration bridge for the ecosystem-assembly pipeline.

Owned exclusively by claude/ecosystem-integration. This package never
re-implements a scientific module's logic (topology, falsification,
statistics) — it discovers, validates, invokes through existing public
adapters, and packages. See docs/integration_acceptance.md for the
ownership boundary and merge gates.
"""
from __future__ import annotations
