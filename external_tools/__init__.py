"""External tool integration registry + adapter contract.

Classifies external tools/libraries/platforms (MNE, BIDS, fMRIPrep,
Nilearn, MOABB, EEGDash, GUDHI, Ripser, NetworkX, BrainFlow, commercial
neurofeedback/qEEG competitors, hardware SDKs, ...) by license risk,
commercial-use status, and integration mode -- BEFORE any adapter is
built. See docs/external_tool_integration_strategy.md for the full
rationale.

This package is deliberately narrow: a record shape
(`ExternalToolRecordV1`), an adapter-contract schema
(`AdapterContractV1`) that a future adapter must satisfy, structural/
license-policy validation (`external_tools.validation`), and a registry
store + CLI (`external_tools.registry` / `external_tools.export_registry`).
It does not implement an MNE adapter, a BIDS adapter, an fMRIPrep/Nilearn
adapter, a MOABB/EEGDash importer, live EEG streaming, or any new topology
algorithm -- those are all future milestones this registry prepares for,
not delivers.
"""
from __future__ import annotations

from external_tools.adapter_contract import AdapterContractV1
from external_tools.tool_record import ExternalToolRecordV1

# ExternalToolRegistry (external_tools.registry) and the CLI
# (external_tools.export_registry) are deliberately NOT re-exported here:
# export_registry is also the CLI entry point
# (`python -m external_tools.export_registry`), and eagerly importing it
# from this package's __init__ causes Python to double-import it (once as
# `external_tools.export_registry`, once as `__main__`) under `-m`, exactly
# the problem `phase_space/__init__.py` and `benchmarks/__init__.py` avoid
# for their own CLI modules. Import directly:
# `from external_tools.registry import ExternalToolRegistry`
# `from external_tools.export_registry import main`.

__all__ = ["ExternalToolRecordV1", "AdapterContractV1"]
