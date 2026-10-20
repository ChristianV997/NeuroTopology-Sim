"""Verify the root .dockerignore with a real, local Docker Engine.

This test builds a network-free ``FROM scratch`` image from a temporary
context containing only synthetic sentinel files. It deliberately fails when
Docker or a local Docker Engine is unavailable; it is intended for the
Docker-enabled job, not a test suite that silently skips engine coverage.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import uuid

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCKERIGNORE = REPOSITORY_ROOT / ".dockerignore"
DOCKER_TIMEOUT_SECONDS = 120
SYNTHETIC_DOCKERFILE = 'FROM scratch\nCOPY . /context/\nCMD ["context-probe"]\n'

ALLOWED_FILES = (
    "apps/awareness_studio/.env.example",
    "visible/source-marker.txt",
)

# Synthetic paths corresponding to files required by the root-context image
# builds. Only fixed marker bodies are created; repository files are not copied.
REQUIRED_BUILD_INPUTS = (
    "requirements-base.txt",
    "requirements.txt",
    "apps/awareness_studio/pyproject.toml",
    "apps/awareness_studio/src/awareness_studio/__init__.py",
    "apps/awareness_studio/tests/research_cycle/test_registered_execution.py",
    "apps/awareness_studio/tools/__init__.py",
    "apps/awareness_studio/inputs/suttacentral_seed_cards.jsonl",
    "AGENTS.md",
    "tools/__init__.py",
    "tools/literature_evidence/__init__.py",
    "tools/simulation_artifacts/__init__.py",
    "tools/simulation_execution/__init__.py",
    "tools/research_cycle_preflight/__init__.py",
    "tools/research_cycle_release/__init__.py",
    "tools/research_plan_quality/__init__.py",
    "tools/research_claim_gate/__init__.py",
    "tools/data_access/policy_enforcement/__init__.py",
    "scripts/build_awareness_evidence_graph.py",
    "tests/research_cycle_preflight/fixtures/complete_plan.json",
)

# Filenames only: file bodies in this temporary context are a fixed synthetic
# marker and never contain real credentials or private-key material.
FORBIDDEN_FILES = (
    ".env",
    ".env.local",
    ".env.example",
    "apps/awareness_studio/.env",
    "apps/awareness_studio/.env.production",
    "nested/project/.env.test",
    "nested/project/.env.example",
    ".aws/credentials",
    "home/user/.azure/accessTokens.json",
    "home/user/.config/gcloud/application_default_credentials.json",
    "home/user/.config/gh/hosts.yml",
    "home/user/.ssh/id_ed25519",
    "home/user/.kube/config",
    "home/user/.terraform.d/credentials.tfrc.json",
    "home/user/.docker/config.json",
    "home/user/.npmrc",
    "home/user/.pypirc",
    "home/user/.netrc",
    "home/user/.git-credentials",
    "home/user/.envrc",
    "nested/credentials",
    "nested/credential",
    "nested/credentials.json",
    "nested/credentials.yaml",
    "nested/credentials.yml",
    "nested/credentials.toml",
    "nested/credentials.txt",
    "nested/cloud_credentials.json",
    "nested/service-account.json",
    "nested/service_account.json",
    "nested/repo/.git/HEAD",
    "nested/repo/.git/config",
    "nested/project/.venv/pyvenv.cfg",
    "nested/project/venv/pyvenv.cfg",
    "nested/project/.tox/py/pyvenv.cfg",
    "nested/project/.nox/py/pyvenv.cfg",
    "home/user/.ssh/id_rsa",
    "nested/keys/id_rsa_backup",
    "nested/keys/id_ed25519_backup",
    "nested/certs/server.pem",
    "nested/certs/server.key",
    "nested/certs/client.p12",
    "nested/certs/client.p8",
    "nested/certs/client.pfx",
    "nested/certs/client.ppk",
    "nested/certs/ca.crt",
    "nested/certs/ca.cer",
    "nested/certs/ca.der",
    "nested/certs/chain.p7b",
    "nested/certs/chain.p7c",
    "nested/certs/keystore.jks",
    "nested/certs/keystore.kdb",
)


def _docker_environment() -> dict[str, str]:
    """Prevent a raw host override from bypassing the inspected context."""
    environment = os.environ.copy()
    environment.pop("DOCKER_HOST", None)
    return environment


def _sanitize_docker_diagnostic(stderr: str | None) -> str:
    """Map bounded daemon stderr to a short allowlisted diagnostic.

    Raw Docker output is intentionally never included in failures: it can
    contain host paths, registry details, or environment-derived values.
    """
    bounded_stderr = (stderr or "")[:4096].lower()
    marker = "error response from daemon:"
    if marker not in bounded_stderr:
        return "Docker diagnostic unavailable (unrecognized output; details redacted)"

    engine_message = bounded_stderr.split(marker, 1)[1]
    if "no command specified" in engine_message:
        return "Docker Engine diagnostic: no command specified"
    if "permission denied" in engine_message:
        return "Docker Engine diagnostic: local endpoint permission denied"
    if "no such image" in engine_message:
        return "Docker Engine diagnostic: image not found"
    if "no such container" in engine_message:
        return "Docker Engine diagnostic: container not found"
    if "no space left on device" in engine_message:
        return "Docker Engine diagnostic: runner storage exhausted"
    if "read-only file system" in engine_message:
        return "Docker Engine diagnostic: runner storage is read-only"
    if "conflict" in engine_message:
        return "Docker Engine diagnostic: resource conflict"
    if "invalid reference format" in engine_message:
        return "Docker Engine diagnostic: invalid generated reference"
    return "Docker Engine diagnostic unavailable (unrecognized error; details redacted)"


def _run_docker(
    args: list[str],
    *,
    timeout: int = DOCKER_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
) -> str:
    """Run Docker without echoing command output that could contain file data."""
    docker_environment = _docker_environment() if env is None else env
    try:
        completed = subprocess.run(
            ["docker", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=docker_environment,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"Docker operation {args[0]!r} timed out after {timeout}s")

    if completed.returncode != 0:
        if args and args[0] == "version":
            pytest.fail(
                "Docker CLI is present but no running Docker Engine is reachable "
                "from the allowed local endpoint; engine output is suppressed"
            )
        pytest.fail(
            f"Docker operation {args[0]!r} failed with exit code "
            f"{completed.returncode}; "
            f"{_sanitize_docker_diagnostic(completed.stderr)}"
        )
    return completed.stdout.strip()


def _select_local_docker_context() -> tuple[str, dict[str, str]]:
    """Pin and validate the inspected local context for every Docker command."""
    environment = _docker_environment()
    context_name = _run_docker(["context", "show"], env=environment).strip()
    if not context_name:
        raise RuntimeError("Docker context name is unavailable")

    # DOCKER_CONTEXT selects the same named context for subsequent commands;
    # DOCKER_HOST was removed above so it cannot override this inspected choice.
    environment["DOCKER_CONTEXT"] = context_name
    endpoint = _run_docker(
        [
            "context",
            "inspect",
            "--format",
            "{{.Endpoints.docker.Host}}",
            context_name,
        ],
        env=environment,
    ).lower()
    if not endpoint.startswith(("unix://", "npipe://", "fd://")):
        raise RuntimeError(
            "Docker-context test refuses a non-local Docker endpoint; "
            "only unix://, npipe://, or fd:// endpoints are allowed"
        )
    return context_name, environment


def _write_synthetic_file(context: Path, relative_path: str) -> None:
    """Create an inert marker file; never read repository credential files."""
    target = context.joinpath(*PurePosixPath(relative_path).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("synthetic docker-context sentinel\n", encoding="utf-8")


def _synthetic_dockerfile_contents() -> str:
    """Return the inert scratch recipe used for build-context inspection."""
    return SYNTHETIC_DOCKERFILE


def test_synthetic_scratch_image_has_a_command_for_container_creation() -> None:
    """Keep docker create valid without running an image executable."""
    dockerfile = _synthetic_dockerfile_contents()

    assert dockerfile.startswith("FROM scratch\n")
    assert 'CMD ["context-probe"]' in dockerfile


def _context_entries_from_export(archive_path: Path) -> set[str]:
    """Return paths copied under /context in the exported container rootfs."""
    entries: set[str] = set()
    with tarfile.open(archive_path, mode="r:*") as archive:
        for member in archive.getmembers():
            name = member.name.replace("\\", "/")
            while name.startswith("./"):
                name = name[2:]
            parts = PurePosixPath(name).parts
            if parts and parts[0] == "context" and len(parts) > 1:
                entries.add("/".join(parts[1:]))
    return entries


def test_docker_engine_applies_repository_dockerignore_to_synthetic_context(
    request: pytest.FixtureRequest,
) -> None:
    """Prove Docker omits forbidden paths and retains the sole env exception."""
    docker_cli = shutil.which("docker")
    if docker_cli is None:
        pytest.fail(
            "Docker CLI is required for this Docker-context test; "
            "the test must run in a Docker-enabled job and is not skipped"
        )

    if not DOCKERIGNORE.is_file():
        pytest.fail(f"repository Docker ignore policy is missing: {DOCKERIGNORE}")

    # Inspect, but do not connect to, the selected Docker endpoint. Pin one
    # sanitized context for inspection, engine operations, and cleanup.
    try:
        _, docker_environment = _select_local_docker_context()
    except RuntimeError as exc:
        pytest.fail(str(exc))

    server_version = _run_docker(
        ["version", "--format", "{{.Server.Version}}"], env=docker_environment
    )
    if not server_version:
        pytest.fail("a running Docker Engine is required for this test")
    request.node.user_properties.append(("docker_engine_version", server_version))
    print(f"Docker Engine server version: {server_version}")

    with TemporaryDirectory(prefix="docker-context-policy-") as temporary_directory:
        temp_root = Path(temporary_directory)
        context = temp_root / "synthetic-context"
        context.mkdir()
        shutil.copyfile(DOCKERIGNORE, context / ".dockerignore")
        (context / "Dockerfile").write_text(
            _synthetic_dockerfile_contents(), encoding="utf-8"
        )

        for relative_path in (*ALLOWED_FILES, *REQUIRED_BUILD_INPUTS, *FORBIDDEN_FILES):
            _write_synthetic_file(context, relative_path)

        token = uuid.uuid4().hex
        image_tag = f"docker-context-policy-probe:{token}"
        container_name = f"docker-context-policy-probe-{token}"
        archive_path = temp_root / "synthetic-image-rootfs.tar"
        image_cleanup_required = False
        container_cleanup_required = False

        try:
            # A timed-out client may not know whether the daemon completed the
            # operation. Arm cleanup before each mutating request so an
            # ambiguous response cannot leave a tagged image/container behind.
            image_cleanup_required = True
            _run_docker(
                [
                    "build",
                    "--no-cache",
                    "--pull=false",
                    "--network=none",
                    "--file",
                    str(context / "Dockerfile"),
                    "--tag",
                    image_tag,
                    str(context),
                ],
                env=docker_environment,
            )

            container_cleanup_required = True
            _run_docker(
                ["create", "--name", container_name, image_tag],
                env=docker_environment,
            )
            _run_docker(
                ["export", "--output", str(archive_path), container_name],
                env=docker_environment,
            )

            exported_paths = _context_entries_from_export(archive_path)
            for relative_path in FORBIDDEN_FILES:
                assert relative_path not in exported_paths, (
                    "forbidden synthetic path entered Docker image: "
                    f"{relative_path}"
                )
            for relative_path in (*ALLOWED_FILES, *REQUIRED_BUILD_INPUTS):
                assert relative_path in exported_paths, (
                    "expected non-secret context file was excluded: "
                    f"{relative_path}"
                )
        finally:
            cleanup_failures: list[str] = []
            for should_remove, args, label in (
                (
                    container_cleanup_required,
                    ["rm", "--force", container_name],
                    "container",
                ),
                (
                    image_cleanup_required,
                    ["image", "rm", "--force", image_tag],
                    "image",
                ),
            ):
                if not should_remove:
                    continue
                try:
                    completed = subprocess.run(
                        ["docker", *args],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=30,
                        env=docker_environment,
                    )
                except subprocess.TimeoutExpired:
                    cleanup_failures.append(f"{label} cleanup timed out")
                    continue
                if completed.returncode != 0:
                    cleanup_failures.append(
                        f"{label} cleanup failed (exit {completed.returncode})"
                    )

            # Preserve the original assertion/build failure, but surface
            # cleanup failures when the test body otherwise succeeded.
            if cleanup_failures and sys.exc_info()[0] is None:
                pytest.fail(
                    "Docker resource cleanup failed: " + "; ".join(cleanup_failures)
                )


@pytest.mark.parametrize(
    ("failed_operation", "expected_cleanup"),
    [
        ("build", "image"),
        ("create", "rm"),
    ],
    ids=("ambiguous-build-outcome", "ambiguous-create-outcome"),
)
def test_docker_resources_are_cleanup_armed_before_mutating_calls(
    monkeypatch: pytest.MonkeyPatch,
    failed_operation: str,
    expected_cleanup: str,
) -> None:
    """Attempt cleanup when Docker acted but its client response was lost."""
    monkeypatch.setattr(shutil, "which", lambda _: "docker-fixture")
    monkeypatch.setattr(
        sys.modules[__name__],
        "_select_local_docker_context",
        lambda: ("local-fixture", {"DOCKER_CONTEXT": "local-fixture"}),
    )

    def fake_run_docker(args: list[str], **_: object) -> str:
        operation = args[0]
        if operation == "version":
            return "synthetic-engine"
        if operation == failed_operation:
            # Model a lost/timeout response after a daemon-side effect.
            raise RuntimeError("synthetic ambiguous Docker response")
        return "synthetic-result"

    cleanup_commands: list[list[str]] = []

    def fake_subprocess_run(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        cleanup_commands.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(sys.modules[__name__], "_run_docker", fake_run_docker)
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)
    request = type(
        "SyntheticRequest",
        (),
        {"node": type("SyntheticNode", (), {"user_properties": []})()},
    )()

    with pytest.raises(RuntimeError, match="ambiguous Docker response"):
        test_docker_engine_applies_repository_dockerignore_to_synthetic_context(
            request
        )

    cleanup_operations = [command[1] for command in cleanup_commands]
    assert expected_cleanup in cleanup_operations
    if failed_operation == "create":
        assert "image" in cleanup_operations


@pytest.mark.parametrize(
    ("endpoint", "is_local"),
    [
        ("unix:///var/run/docker.sock", True),
        ("tcp://synthetic.invalid:2375", False),
    ],
    ids=("local-engine-context", "remote-engine-context"),
)
def test_docker_context_is_pinned_and_host_override_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
    is_local: bool,
) -> None:
    """Pin one inspected context and reject endpoints outside local schemes."""
    monkeypatch.setenv("DOCKER_HOST", "tcp://synthetic.invalid:2375")
    monkeypatch.setenv("DOCKER_CONTEXT", "local-fixture-context")
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        calls.append((command, environment))
        if command[1:3] == ["context", "show"]:
            stdout = "local-fixture-context\n"
        elif command[1:3] == ["context", "inspect"]:
            stdout = endpoint + "\n"
        else:
            stdout = "synthetic-engine\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    docker_environment = _docker_environment()
    if is_local:
        context_name, docker_environment = _select_local_docker_context()
        assert context_name == "local-fixture-context"
        assert len(calls) == 2
        assert calls[1][0][-1] == context_name
    else:
        with pytest.raises(RuntimeError, match="non-local Docker endpoint"):
            _select_local_docker_context()
        assert len(calls) == 2

    assert all("DOCKER_HOST" not in env for _, env in calls)
    assert "DOCKER_HOST" not in docker_environment
    assert docker_environment["DOCKER_CONTEXT"] == "local-fixture-context"


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        (
            "Error response from daemon: No command specified",
            "Docker Engine diagnostic: no command specified",
        ),
        (
            "Error response from daemon: permission denied while reading "
            "/home/synthetic-user/.docker/config.json; "
            "API_TOKEN=synthetic-secret-value",
            "Docker Engine diagnostic: local endpoint permission denied",
        ),
        (
            "unexpected diagnostic with /home/synthetic-user/private.txt "
            "and TOKEN=synthetic-secret-value",
            "Docker diagnostic unavailable (unrecognized output; details redacted)",
        ),
    ],
    ids=("known-engine-cause", "sensitive-text-not-exposed", "unknown-is-redacted"),
)
def test_docker_diagnostics_are_bounded_and_sanitized(
    stderr: str,
    expected: str,
) -> None:
    """Expose a short known cause, never raw paths or secret-like values."""
    diagnostic = _sanitize_docker_diagnostic(stderr)

    assert diagnostic == expected
    assert len(diagnostic) <= 100
    assert "/home/" not in diagnostic
    assert "synthetic-secret-value" not in diagnostic


def test_run_docker_includes_only_sanitized_engine_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Thread the safe classification into failures without exposing stderr."""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args,
            1,
            stdout="synthetic stdout secret",
            stderr=(
                "Error response from daemon: permission denied at "
                "/home/synthetic-user/.docker/config.json; "
                "API_TOKEN=synthetic-secret-value"
            ),
        ),
    )
    failures: list[str] = []

    def capture_failure(message: str) -> None:
        failures.append(message)
        raise RuntimeError("captured pytest failure")

    monkeypatch.setattr(pytest, "fail", capture_failure)

    with pytest.raises(RuntimeError, match="captured pytest failure"):
        _run_docker(["create", "synthetic-container"])

    assert len(failures) == 1
    assert "local endpoint permission denied" in failures[0]
    assert "synthetic-secret-value" not in failures[0]
    assert "synthetic stdout secret" not in failures[0]
