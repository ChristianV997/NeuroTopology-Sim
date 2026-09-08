"""Awareness Studio research-cycle orchestrator package.

This branch (claude/awareness-cycle-contract-integration) owns only
``contract_adapters.py`` within this package -- ``compiler.py`` and
``state_machine.py`` (and everything else in the orchestrator, PR #283)
are read-only from here and are not present in this branch's history.
This file is deliberately minimal so it merges cleanly with PR #283's
own ``__init__.py`` rather than conflicting with it.
"""
from __future__ import annotations
