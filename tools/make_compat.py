"""Minimal Makefile recipe runner for Windows environments without GNU make."""
from __future__ import annotations
import re
import subprocess
import sys
import os
from pathlib import Path


def recipes(makefile: Path, target: str) -> list[str]:
    text = makefile.read_text(encoding="utf-8").splitlines()
    found = False; commands: list[str] = []
    for line in text:
        if line and not line.startswith((" ", "\t")) and ":" in line:
            found = line.split(":", 1)[0].strip() == target
            continue
        if found and line.startswith("\t"):
            commands.append(line[1:])
        elif found and line and not line.startswith((" ", "\t")):
            break
    if not commands:
        raise SystemExit(f"make_compat: target not found or has no recipe: {target}")
    return commands


def run_target(target: str, root: Path) -> int:
    env = os.environ.copy()
    venv_scripts = root / ".venv" / "Scripts"
    env["PATH"] = str(venv_scripts) + os.pathsep + env.get("PATH", "")
    for command in recipes(root / "Makefile", target):
        command = command.strip()
        allow_failure = bool(re.search(r"\s*\|\|\s*true\s*$", command))
        if command.startswith("$(MAKE) "):
            nested = re.sub(r"\s*\|\|\s*true\s*$", "", command[len("$(MAKE) "):].strip())
            code = run_target(nested, root)
        else:
            command = command.replace("$(if $(VAULT),$(VAULT),obsidian)", "obsidian")
            command = re.sub(r"\s*\|\|\s*true\s*$", "", command)
            code = subprocess.run(command, shell=True, cwd=root, env=env, check=False).returncode
        if code != 0 and not allow_failure:
            return code
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m tools.make_compat TARGET")
    raise SystemExit(run_target(sys.argv[1], Path(__file__).resolve().parents[1]))
