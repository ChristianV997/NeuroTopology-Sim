"""Regression tests for shared GitHub Actions workflow boundaries."""

from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / ".github" / "workflows"


def _load(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), f"workflow is not a mapping: {path}"
    return value


def _events(workflow: dict) -> dict:
    # PyYAML's YAML 1.1 resolver may expose the unquoted GitHub `on` key as
    # boolean True. Accept both representations while validating the file.
    value = workflow.get("on", workflow.get(True, {}))
    return value if isinstance(value, dict) else {}


def _run_text(job: dict) -> str:
    return "\n".join(
        str(step.get("run", ""))
        for step in job.get("steps", [])
        if isinstance(step, dict)
    )


def test_every_workflow_is_parseable_and_needs_existing_jobs():
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        workflow = _load(path)
        jobs = workflow.get("jobs", {})
        assert isinstance(jobs, dict) and jobs, f"workflow has no jobs: {path}"
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            needs = job.get("needs", [])
            needs = [needs] if isinstance(needs, str) else list(needs or [])
            missing = [dependency for dependency in needs if dependency not in jobs]
            assert not missing, f"{path.name}:{job_name} has undefined needs: {missing}"


def test_automatic_cpu_jobs_use_base_profile_without_gpu_packages():
    job_refs = {
        ("ci.yml", "isolated-core-suite"),
        ("required-checks.yml", "core-tests"),
        ("ds005620-e2e.yml", "ds005620-e2e"),
        ("smoke.yml", "smoke"),
    }
    forbidden_install = re.compile(r"pip\s+install[^\n]*(torch|nvidia|cuda|cupy|tensorflow)", re.I)
    root_profile = re.compile(r"-r\s+requirements\.txt(?:\s|$)")
    for workflow_name, job_name in job_refs:
        workflow = _load(WORKFLOW_DIR / workflow_name)
        run_text = _run_text(workflow["jobs"][job_name])
        assert "requirements-base.txt" in run_text, f"{workflow_name}:{job_name} lost CPU profile"
        assert not forbidden_install.search(run_text), f"GPU package in CPU job: {workflow_name}:{job_name}"
        assert not root_profile.search(run_text), f"master profile in CPU job: {workflow_name}:{job_name}"


def test_optional_ml_is_not_installed_by_automatic_ci():
    workflow = _load(WORKFLOW_DIR / "ci.yml")
    assert "optional-ml-suite" not in workflow["jobs"]
    optional = _load(WORKFLOW_DIR / "optional-scientific.yml")
    assert set(_events(optional)) == {"workflow_dispatch"}
    assert "optional-ml-cpu" in optional["jobs"]


def test_core_cpu_jobs_use_singleton_isolated_batches():
    for workflow_name, job_name in (("ci.yml", "isolated-core-suite"), ("required-checks.yml", "core-tests")):
        workflow = _load(WORKFLOW_DIR / workflow_name)
        assert "--batch-size 1" in _run_text(workflow["jobs"][job_name])
    dockerfile = (ROOT / "docker" / "ci" / "core.Dockerfile").read_text(encoding="utf-8")
    assert '"--batch-size", "1"' in dockerfile


def test_pip_jobs_disable_cache_and_cleanup_temp_files():
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        workflow = _load(path)
        events = _events(workflow)
        if not ("pull_request" in events or "push" in events):
            continue
        text = path.read_text(encoding="utf-8")
        if "pip install" not in text:
            continue
        assert "PIP_NO_CACHE_DIR" in text, f"pip cache is unbounded in {path.name}"
        assert "pip cache purge" in text, f"pip cleanup is missing in {path.name}"
        assert "if: always()" in text, f"pip cleanup is not unconditional in {path.name}"


def test_production_root_image_is_manual_and_docker_contexts_are_scoped():
    workflow = _load(WORKFLOW_DIR / "docker-build.yml")
    production = workflow["jobs"]["production-root-image"]
    assert "workflow_dispatch" in str(production.get("if"))
    assert "run_full_root" in str(production.get("if"))
    docker_text = (WORKFLOW_DIR / "docker-build.yml").read_text(encoding="utf-8")
    assert "-f docker/ci/core.Dockerfile" in docker_text
    assert "-f apps/awareness_studio/Dockerfile apps/awareness_studio" in docker_text
    assert (ROOT / ".dockerignore").is_file()
