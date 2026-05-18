from __future__ import annotations
import argparse, shlex, subprocess, time, shutil
from .reporting import write_json, write_markdown

BLOCKED = ["--peer-reviewed-contract-confirmed", "ds005620", "download", "--execute"]


def planned_commands(has_make: bool) -> list[str]:
    cmds = ["python main.py --mode synthetic", "python -m governance.validate", "python -m pytest tests/btc_icft -q"]
    if has_make:
        cmds += ["make local-agent-healthcheck", "make local-ops-healthcheck", "make local-ops-run-loop-dry-run"]
    return cmds


def run(mode: str, timeout_s: int, continue_on_error: bool, max_commands: int) -> dict:
    cmds = planned_commands(shutil.which("make") is not None)[:max_commands]
    results = []
    if mode == "dry-run":
        for c in cmds:
            results.append({"command": c, "status": "planned", "return_code": None, "stdout_tail": "", "stderr_tail": "", "duration_s": 0, "troubleshooting_hint": "Dry-run only."})
        return {"mode": mode, "commands": results}
    for c in cmds:
        if any(b in c for b in BLOCKED):
            results.append({"command": c, "status": "skipped", "return_code": None, "stdout_tail": "", "stderr_tail": "Blocked by safety guard.", "duration_s": 0, "troubleshooting_hint": "Command blocked."})
            continue
        t0 = time.time(); p = subprocess.run(shlex.split(c), capture_output=True, text=True, timeout=timeout_s)
        ok = p.returncode == 0
        results.append({"command": c, "status": "succeeded" if ok else "failed", "return_code": p.returncode, "stdout_tail": p.stdout[-400:], "stderr_tail": p.stderr[-400:], "duration_s": round(time.time()-t0, 3), "troubleshooting_hint": "Activate .venv and install requirements if import errors occur."})
        if (not ok) and (not continue_on_error):
            break
    return {"mode": mode, "commands": results}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True); p.add_argument("--markdown-out", required=True)
    p.add_argument("--mode", choices=["dry-run", "run"], default="dry-run")
    p.add_argument("--max-commands", type=int, default=8); p.add_argument("--timeout-s", type=int, default=300)
    p.add_argument("--continue-on-error", action="store_true")
    a = p.parse_args()
    res = run(a.mode, a.timeout_s, a.continue_on_error, a.max_commands)
    write_json(a.out, res)
    md = "# Smoke Results\n\n" + "\n".join([f"- `{r['command']}`: **{r['status']}**" for r in res["commands"]])
    write_markdown(a.markdown_out, md)

if __name__ == '__main__':
    main()
