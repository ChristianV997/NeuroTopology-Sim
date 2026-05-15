"""
Agent role definitions for the local autonomous research team (P23).

Roles are loaded from configs/local_agents/agent_roster.json or use defaults.
stdlib only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AgentRole:
    """Definition of a single agent role."""
    role_id: str
    display_name: str
    description: str
    safe_to_auto_run: bool
    requires_human_review: bool
    requires_real_data: bool
    allowed_commands: list = field(default_factory=list)
    blocked_commands: list = field(default_factory=list)
    notes: str = ""


_DEFAULT_ROLES: list[dict] = [
    {
        "role_id": "mock_runner",
        "display_name": "Mock E2E Runner",
        "description": "Runs mock end-to-end pipeline for DS005620. No real data.",
        "safe_to_auto_run": True,
        "requires_human_review": False,
        "requires_real_data": False,
        "allowed_commands": ["make ds005620-e2e-mock", "make validate-ds005620-e2e"],
        "blocked_commands": [],
        "notes": "P18.1 mock execution only.",
    },
    {
        "role_id": "validator",
        "description": "Validates all pipeline outputs: contracts, language, ontology.",
        "display_name": "Pipeline Validator",
        "safe_to_auto_run": True,
        "requires_human_review": False,
        "requires_real_data": False,
        "allowed_commands": [
            "make validate-ds005620-contracts",
            "make ds005620-generated-language-check",
            "make validate-real-data-source-matrix",
        ],
        "blocked_commands": [],
        "notes": "",
    },
    {
        "role_id": "artifact_planner",
        "display_name": "Artifact Planner",
        "description": "Plans real artifact preparation. Does not execute real data.",
        "safe_to_auto_run": True,
        "requires_human_review": False,
        "requires_real_data": False,
        "allowed_commands": ["make ds005620-real-artifact-plan", "make real-data-source-matrix"],
        "blocked_commands": [],
        "notes": "P20 operator only.",
    },
    {
        "role_id": "gate_inspector",
        "display_name": "Real Execution Gate Inspector",
        "description": "Runs P18.3 execution gate checks. Always reports human_peer_review_required.",
        "safe_to_auto_run": True,
        "requires_human_review": True,
        "requires_real_data": False,
        "allowed_commands": ["make ds005620-real-execution-gate"],
        "blocked_commands": [],
        "notes": "Never confirms peer review.",
    },
    {
        "role_id": "obsidian_syncer",
        "display_name": "Obsidian Vault Syncer",
        "description": "Mirrors loop state and matrix outputs into Obsidian vault.",
        "safe_to_auto_run": True,
        "requires_human_review": False,
        "requires_real_data": False,
        "allowed_commands": ["make sync-obsidian"],
        "blocked_commands": [],
        "notes": "Write-only to vault_root; never touches source artifacts.",
    },
    {
        "role_id": "matrix_builder",
        "display_name": "Multi-Dataset Matrix Builder",
        "description": "Builds and validates the multi-dataset readiness matrix.",
        "safe_to_auto_run": True,
        "requires_human_review": False,
        "requires_real_data": False,
        "allowed_commands": [
            "make real-data-source-matrix",
            "make validate-real-data-source-matrix",
        ],
        "blocked_commands": [],
        "notes": "P22 matrix only.",
    },
    {
        "role_id": "real_data_executor",
        "display_name": "Real Data Executor",
        "description": "Executes real dataset pipelines. ALWAYS requires human peer review and gate confirmation.",
        "safe_to_auto_run": False,
        "requires_human_review": True,
        "requires_real_data": True,
        "allowed_commands": [],
        "blocked_commands": [
            "--execute --peer-reviewed-contract-confirmed",
            "wget",
            "curl",
            "dandi download",
        ],
        "notes": "Never auto-run. Requires gate + human confirmation.",
    },
    {
        "role_id": "safety_watcher",
        "display_name": "Safety Watcher",
        "description": "Monitors all loop events for policy violations and guardrail breaches.",
        "safe_to_auto_run": True,
        "requires_human_review": False,
        "requires_real_data": False,
        "allowed_commands": ["make local-agent-policy-check"],
        "blocked_commands": [],
        "notes": "Reads events; never writes to source artifacts.",
    },
]


def load_agent_roster(path: Optional[str | Path] = None) -> list[AgentRole]:
    """Load agent roles from JSON file or return defaults."""
    if path is not None:
        p = Path(path)
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            roles_data = raw.get("roles", raw) if isinstance(raw, dict) else raw
        else:
            roles_data = _DEFAULT_ROLES
    else:
        default_path = Path("configs/local_agents/agent_roster.json")
        module_fallback = Path(__file__).resolve().parent.parent.parent / "configs" / "local_agents" / "agent_roster.json"
        if default_path.exists():
            raw = json.loads(default_path.read_text(encoding="utf-8"))
            roles_data = raw.get("roles", raw) if isinstance(raw, dict) else raw
        elif module_fallback.exists():
            raw = json.loads(module_fallback.read_text(encoding="utf-8"))
            roles_data = raw.get("roles", raw) if isinstance(raw, dict) else raw
        else:
            roles_data = _DEFAULT_ROLES

    return [
        AgentRole(
            role_id=r["role_id"],
            display_name=r.get("display_name", r["role_id"]),
            description=r.get("description", ""),
            safe_to_auto_run=bool(r.get("safe_to_auto_run", False)),
            requires_human_review=bool(r.get("requires_human_review", False)),
            requires_real_data=bool(r.get("requires_real_data", False)),
            allowed_commands=list(r.get("allowed_commands", [])),
            blocked_commands=list(r.get("blocked_commands", [])),
            notes=r.get("notes", ""),
        )
        for r in roles_data
    ]


AGENT_ROLES: dict[str, AgentRole] = {r.role_id: r for r in load_agent_roster()}
