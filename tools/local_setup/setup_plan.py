from __future__ import annotations
import argparse, platform
from .reporting import write_json, write_markdown


def build_plan() -> dict:
    system = platform.system()
    windows = system == "Windows"
    steps = []
    if windows:
        steps = [
            "Install WSL2 Ubuntu.",
            "Inside Ubuntu install: sudo apt update && sudo apt install -y git make build-essential python3-venv python3-pip",
            "Clone repo in WSL home, e.g. ~/projects/ScienceR-Dsim",
            "python3 -m venv .venv && source .venv/bin/activate",
            "python -m pip install --upgrade pip setuptools wheel",
            "pip install -r requirements.txt",
            "python main.py --mode synthetic",
            "python -m pytest tests/btc_icft -q",
            "Open from WSL terminal with code . and select .venv/bin/python",
        ]
    else:
        steps = [
            "sudo apt update",
            "sudo apt install -y git make build-essential python3 python3-venv python3-pip",
            "python3 -m venv .venv",
            "source .venv/bin/activate",
            "python -m pip install --upgrade pip setuptools wheel",
            "pip install -r requirements.txt",
            "python main.py --mode synthetic",
            "python -m governance.validate",
            "python -m pytest tests/btc_icft -q",
            "make local-agent-healthcheck",
            "make local-ops-healthcheck",
            "make local-ops-run-loop-dry-run",
            "Fallback without make: python main.py --mode synthetic && python -m pytest tests/ -v --tb=short",
            "Open in VS Code from WSL with code . and use integrated terminal.",
        ]
    return {"platform": system, "steps": steps}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--markdown-out", required=True)
    a = p.parse_args()
    plan = build_plan()
    write_json(a.out, plan)
    md = "# Local Setup Plan\n\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(plan["steps"]))
    write_markdown(a.markdown_out, md)


if __name__ == "__main__":
    main()
