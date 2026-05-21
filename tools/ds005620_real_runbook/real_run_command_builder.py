from __future__ import annotations

def build_manual_command() -> dict:
    return {
        "command": "python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark --execute --peer-reviewed-contract-confirmed --out outputs/btc_icft/ds005620_real_benchmark_execution",
        "not_executed_by_tool": True,
        "requires_human_peer_review": True,
        "can_auto_execute": False,
        "manual_boundary_notice": "For human operator manual execution only."
    }
