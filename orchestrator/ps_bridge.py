"""Run existing PowerShell scripts as subprocesses without rewriting them."""
import subprocess
from typing import Optional


def run_powershell(script_path: str, args: Optional[dict] = None) -> str:
    """Run an existing PowerShell script as a subprocess and return its stdout."""
    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", script_path]
    if args:
        for k, v in args.items():
            cmd += [f"-{k}", str(v)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"PowerShell error: {result.stderr}")
    return result.stdout
