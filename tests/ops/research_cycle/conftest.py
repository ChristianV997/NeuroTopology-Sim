"""Shared paths for operator-pack tests."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PACK = REPO_ROOT / "ops" / "research_cycle"
CATALOG = PACK / "catalog.json"
POSIX_SH = REPO_ROOT / "scripts" / "run_research_cycle_audit.sh"
POWERSHELL = REPO_ROOT / "scripts" / "run_research_cycle_audit.ps1"
OWNED_PATHS = (
    PACK,
    POSIX_SH,
    POWERSHELL,
    REPO_ROOT / "tests" / "ops" / "research_cycle",
    REPO_ROOT / "docs" / "ops" / "research_cycle_operator_pack.md",
)
