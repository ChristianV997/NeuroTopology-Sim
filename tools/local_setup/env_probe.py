from __future__ import annotations

import argparse, os, platform, shutil, sys
from pathlib import Path
from .reporting import write_json, write_markdown


def probe_environment(cwd: Path | None = None) -> dict:
    cwd = cwd or Path.cwd()
    repo_root = cwd
    req = repo_root / "requirements.txt"
    mk = repo_root / "Makefile"
    main = repo_root / "main.py"
    system = platform.system()
    release = platform.release()
    is_wsl = "microsoft" in release.lower() or bool(os.environ.get("WSL_DISTRO_NAME"))
    is_windows_native = system == "Windows" and not is_wsl
    in_venv = (hasattr(sys, "base_prefix") and sys.prefix != getattr(sys, "base_prefix", sys.prefix)) or bool(os.environ.get("VIRTUAL_ENV"))
    warnings, errors, recs = [], [], []
    if is_windows_native:
        warnings.append("Windows native Python detected; WSL2 is recommended for reproducible local runs.")
    if not in_venv:
        warnings.append("Virtual environment is not active.")
    if not main.exists():
        errors.append("main.py missing; ensure command runs from repository root.")
    detected = "recommended" if is_wsl and in_venv else "acceptable" if system in {"Linux", "Darwin"} and in_venv else "warning"
    if errors:
        detected = "error"
    recs.append("Use WSL2 + Ubuntu and run from Linux filesystem path (e.g., ~/projects/ScienceR-Dsim).")
    next_cmds = ["python -m tools.local_setup.setup_plan --out outputs/local_setup/setup_plan.json --markdown-out outputs/local_setup/setup_plan.md", "python -m tools.local_setup.smoke_runner --mode dry-run --out outputs/local_setup/smoke_results.json --markdown-out outputs/local_setup/smoke_results.md"]
    report = {
        "ok": not errors,
        "warnings": warnings,
        "errors": errors,
        "recommendations": recs,
        "detected_environment": detected,
        "next_commands": next_cmds,
        "platform": {"system": system, "release": release, "is_wsl": is_wsl, "is_windows_native": is_windows_native},
        "python": {"version": sys.version.split()[0], "executable": sys.executable, "virtualenv_active": in_venv},
        "tools": {"pip": shutil.which("pip") is not None or shutil.which("python -m pip") is not None, "git": shutil.which("git") is not None, "make": shutil.which("make") is not None},
        "repo": {
            "root": str(repo_root.resolve()),
            "requirements_txt_exists": req.exists(),
            "makefile_exists": mk.exists(),
            "main_py_exists": main.exists(),
            "directories": {k: (repo_root / k).exists() for k in ["tests", "tools", "outputs", "configs", "apps/awareness_studio"]},
        },
        "resources": {"disk_free_bytes": shutil.disk_usage(repo_root).free if repo_root.exists() else None, "cpu_count": os.cpu_count()},
        "env_vars_present": {k: bool(os.environ.get(k)) for k in ["OPENAI_API_KEY", "GITHUB_TOKEN", "ANTHROPIC_API_KEY"]},
    }
    return report


def to_markdown(report: dict) -> str:
    lines = [
        "# Local Environment Report",
        f"- **Status**: {'OK' if report['ok'] else 'Issues found'}",
        f"- **Detected environment**: `{report['detected_environment']}`",
        "## Warnings",
    ]
    lines.extend([f"- {w}" for w in report["warnings"]] or ["- None"])
    lines.append("## Errors")
    lines.extend([f"- {e}" for e in report["errors"]] or ["- None"])
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--markdown-out", required=True)
    args = ap.parse_args()
    report = probe_environment()
    write_json(args.out, report)
    write_markdown(args.markdown_out, to_markdown(report))


if __name__ == "__main__":
    main()
