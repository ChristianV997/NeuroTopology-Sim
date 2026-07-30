"""Read/write helpers for the Obsidian vault used as the orchestrator's queue and log.

The vault is the source of truth for the experiment queue: notes under
Experiments/Pending are the FIFO/priority queue, Experiments/Running holds
in-flight experiments, and Experiments/Completed holds finished run logs.
"""
import shutil
from datetime import datetime
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

VAULT_ROOT = Path(r"C:\Users\HP\Documents\NeuroTopology-Vault")
TEMPLATES_DIR = Path(__file__).parent / "templates"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    trim_blocks=True,
    lstrip_blocks=True,
)


def write_run_log(
    experiment: dict,
    metrics: dict,
    ollama_summary: str,
    git_hash: str,
    s3_path: str,
) -> Path:
    """Write a completed run log to Obsidian and move the note Running -> Completed."""
    template = env.get_template("run_log.md.j2")
    content = template.render(
        experiment=experiment,
        metrics=metrics,
        ollama_summary=ollama_summary,
        git_hash=git_hash,
        s3_path=s3_path,
        date=datetime.now().isoformat(),
    )
    completed_dir = VAULT_ROOT / "Experiments" / "Completed"
    completed_dir.mkdir(parents=True, exist_ok=True)

    note_name = f"{datetime.now().strftime('%Y-%m-%d')}_{experiment['name']}.md"
    completed_path = completed_dir / note_name
    completed_path.write_text(content, encoding="utf-8")

    # Remove from Running if present (may have a different original filename)
    running_dir = VAULT_ROOT / "Experiments" / "Running"
    running_path = running_dir / note_name
    if running_path.exists():
        running_path.unlink()
    else:
        original = experiment.get("_file")
        if original is not None:
            candidate = running_dir / Path(original).name
            if candidate.exists():
                candidate.unlink()

    return completed_path


def get_pending_experiments() -> list:
    """Read all notes in Experiments/Pending as the experiment queue."""
    pending_dir = VAULT_ROOT / "Experiments" / "Pending"
    if not pending_dir.exists():
        return []

    experiments = []
    for note in sorted(pending_dir.glob("*.md")):
        lines = note.read_text(encoding="utf-8").splitlines()
        meta = _parse_frontmatter(lines)
        meta.setdefault("name", note.stem)
        meta["_file"] = note
        experiments.append(meta)
    return experiments


def mark_running(experiment_file: Path) -> Path:
    """Move a pending experiment note into Experiments/Running."""
    running_dir = VAULT_ROOT / "Experiments" / "Running"
    running_dir.mkdir(parents=True, exist_ok=True)
    destination = running_dir / Path(experiment_file).name
    shutil.move(str(experiment_file), str(destination))
    return destination


def _parse_frontmatter(lines: list) -> dict:
    """Parse a YAML frontmatter block (--- ... ---) at the top of a note."""
    if not lines or lines[0].strip() != "---":
        return {}
    end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None)
    if end is None:
        return {}
    return yaml.safe_load("\n".join(lines[1:end])) or {}
