"""Autonomous experiment daemon.

Loop: read the pending queue from the Obsidian vault -> ask Ollama (or fall
back to FIFO) which experiment to run next -> route it local or AWS Spot ->
parse metrics from the run log -> summarize with Ollama -> write the result
back to the vault -> toast -> sleep.
"""
import json
import re
import subprocess
import time
from datetime import datetime

from agents.ollama_client import generate, is_available
from agents.prompts import render_next_step, render_summarize
from memory.vault_writer import get_pending_experiments, mark_running, write_run_log
from orchestrator.job_router import submit_spot_job, wait_for_results

REPO_ROOT = r"C:\Users\HP\OneDrive\Documentos\GitHub\NeuroTopology-Sim"
POLL_INTERVAL = 300  # 5 minutes
LOCAL_THRESHOLD_HOURS = 0.5  # jobs under 30 min run locally


def main_loop():
    print(f"[Daemon] Starting at {datetime.now().isoformat()}")
    while True:
        try:
            tick()
        except Exception as e:
            print(f"[Daemon] Error in tick: {e}")
            _toast("NeuroTopology Daemon Error", str(e))
        time.sleep(POLL_INTERVAL)


def tick():
    pending = get_pending_experiments()
    if not pending:
        print("[Daemon] No pending experiments. Sleeping.")
        return

    experiment_name = _choose_next(pending)
    experiment = next(e for e in pending if e["name"] == experiment_name)
    mark_running(experiment["_file"])
    print(f"[Daemon] Running: {experiment_name}")

    if float(experiment.get("estimated_hours", 1)) <= LOCAL_THRESHOLD_HOURS:
        result = _run_local(experiment)
    else:
        result = _run_aws(experiment)

    metrics = _parse_metrics(result["log"])
    summary = generate(render_summarize(experiment, metrics)) or "No summary available."
    git_hash = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT
    ).decode().strip()

    write_run_log(experiment, metrics, summary, git_hash, result.get("s3_prefix") or "local")

    _toast(f"{experiment_name} complete", f"eta_sq={metrics.get('eta_sq', '?')} p={metrics.get('p_value', '?')}")


def _choose_next(pending: list) -> str:
    """Ask Ollama which experiment to run next; fall back to FIFO order."""
    if is_available():
        prompt = render_next_step(pending)
        decision_json = generate(prompt)
        if decision_json:
            try:
                decision = json.loads(decision_json)
                candidate = decision["experiment"]
                if any(e["name"] == candidate for e in pending):
                    return candidate
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
    return pending[0]["name"]  # FIFO fallback


def _run_local(experiment: dict) -> dict:
    cmd = ["python", experiment["script"]] + experiment.get("args", "").split()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    return {"log": result.stdout + result.stderr, "s3_prefix": None}


def _run_aws(experiment: dict) -> dict:
    submit_spot_job(experiment)
    return wait_for_results(experiment["name"])


def _parse_metrics(log: str) -> dict:
    metrics = {}
    if m := re.search(r"eta_sq[=:]\s*([\d.]+)", log):
        metrics["eta_sq"] = float(m.group(1))
    if m := re.search(r"p[_-]?value[=:]\s*([\d.eE+-]+)", log):
        metrics["p_value"] = float(m.group(1))
    if m := re.search(r"n_subjects[=:]\s*(\d+)", log):
        metrics["n_subjects"] = int(m.group(1))
    return metrics


def _toast(title: str, message: str):
    safe_title = title.replace("'", "''")
    safe_message = message.replace("'", "''")
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.Visible = $true
$notify.ShowBalloonTip(5000, '{safe_title}', '{safe_message}', [System.Windows.Forms.ToolTipIcon]::Info)
"""
    subprocess.run(["powershell", "-Command", script], capture_output=True)


if __name__ == "__main__":
    main_loop()
