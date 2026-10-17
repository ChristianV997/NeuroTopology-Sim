"""Package metadata required by registered execution's resource contract."""

from pathlib import Path
import tomllib


def test_memory_budget_monitor_is_a_runtime_dependency():
    """The app's declared install must provide the runner's required monitor."""
    project_file = Path(__file__).resolve().parents[2] / "pyproject.toml"
    project = tomllib.loads(project_file.read_text(encoding="utf-8"))
    requirements = project["project"]["dependencies"]

    assert any(
        requirement.split(";", 1)[0].strip().lower().startswith("psutil")
        for requirement in requirements
    )
