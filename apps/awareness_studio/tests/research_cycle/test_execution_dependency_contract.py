"""Package metadata required by registered execution's resource contract."""

from pathlib import Path
import re
import tomllib


def _normalized_distribution_name(requirement: str) -> str:
    requirement = requirement.split(";", 1)[0].strip()
    match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement)
    if match is None:
        return ""
    return re.sub(r"[-_.]+", "-", match.group(0)).lower()


def test_memory_budget_monitor_is_a_runtime_dependency():
    """The app's declared install must provide the runner's required monitor."""
    project_file = Path(__file__).resolve().parents[2] / "pyproject.toml"
    project = tomllib.loads(project_file.read_text(encoding="utf-8"))
    requirements = project["project"]["dependencies"]

    assert any(_normalized_distribution_name(req) == "psutil" for req in requirements)


def test_dependency_contract_does_not_accept_a_package_name_prefix():
    assert _normalized_distribution_name("psutil-extra>=1") == "psutil-extra"
    assert _normalized_distribution_name("psutil_thing>=1") == "psutil-thing"


def test_web_research_ops_uses_the_repository_root_in_the_test_image():
    """The test image must retain the markers used by the default route path."""
    from awareness_studio.web.research_ops import find_repository_root

    expected_root = Path(__file__).resolve().parents[4]
    assert find_repository_root() == expected_root
    assert (expected_root / "AGENTS.md").is_file()
    assert (expected_root / "tools" / "literature_evidence").is_dir()


def test_git_marker_alone_cannot_hide_missing_literature_sources(tmp_path: Path):
    """An empty Docker test marker is not a substitute for runtime sources."""
    from awareness_studio.literature_bridge.repo_paths import (
        RepositoryRootNotFoundError,
        find_repository_root,
    )

    (tmp_path / ".git").mkdir()
    try:
        find_repository_root(tmp_path)
    except RepositoryRootNotFoundError:
        return
    raise AssertionError("repository marker must not replace missing source tree")
