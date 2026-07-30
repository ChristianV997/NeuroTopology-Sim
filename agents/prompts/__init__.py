"""Jinja2 prompt rendering for the Ollama-backed research assistant."""
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).parent

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_next_step(
    pending: list,
    recent_experiments: Optional[list] = None,
    compute_available: str = "local + AWS Spot",
    hours_available: float = 24,
) -> str:
    """Render the next-step experiment-selection prompt."""
    template = env.get_template("next_step.j2")
    return template.render(
        pending=pending,
        recent_experiments=recent_experiments or [],
        compute_available=compute_available,
        hours_available=hours_available,
    )


def render_summarize(experiment: dict, metrics: dict) -> str:
    """Render the run-summarization prompt."""
    template = env.get_template("summarize_run.j2")
    return template.render(
        experiment_name=experiment.get("name", "unknown"),
        eta_sq=metrics.get("eta_sq", "?"),
        p_value=metrics.get("p_value", "?"),
        n_subjects=metrics.get("n_subjects", "?"),
        atlas=metrics.get("atlas", experiment.get("atlas", "?")),
        notes=experiment.get("notes", ""),
    )


def render_codegen(
    task_description: str,
    input_path: str = "",
    output_path: str = "",
    available_modules: str = "",
) -> str:
    """Render the analysis-script codegen prompt."""
    template = env.get_template("codegen.j2")
    return template.render(
        task_description=task_description,
        input_path=input_path,
        output_path=output_path,
        available_modules=available_modules,
    )
