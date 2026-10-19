"""Verify the root .dockerignore with a real, local Docker Engine.

This test builds a network-free ``FROM scratch`` image from a temporary
context containing only synthetic sentinel files. It deliberately fails when
Docker or a local Docker Engine is unavailable; it is intended for the
Docker-enabled job, not a test suite that silently skips engine coverage.
"""

from __future__ import annotations

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

ALLOWED_FILES = (
    "apps/awareness_studio/.env.example",
    "visible/source-marker.txt",
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


def _run_docker(args: list[str], *, timeout: int = DOCKER_TIMEOUT_SECONDS) -> str:
    """Run Docker without echoing command output that could contain file data."""
    try:
        completed = subprocess.run(
            ["docker", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"Docker operation {args[0]!r} timed out after {timeout}s")

    if completed.returncode != 0:
        pytest.fail(
            f"Docker operation {args[0]!r} failed with exit code "
            f"{completed.returncode}; command output is suppressed"
        )
    return completed.stdout.strip()


def _write_synthetic_file(context: Path, relative_path: str) -> None:
    """Create an inert marker file; never read repository credential files."""
    target = context.joinpath(*PurePosixPath(relative_path).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("synthetic docker-context sentinel\n", encoding="utf-8")


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

    # Inspect, but do not connect to, the selected Docker endpoint. This test
    # only allows local Unix sockets, Windows named pipes, or inherited FDs.
    endpoint = _run_docker(
        ["context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]
    ).lower()
    if not endpoint.startswith(("unix://", "npipe://", "fd://")):
        pytest.fail(
            "Docker-context test refuses a non-local Docker endpoint; "
            "only unix://, npipe://, or fd:// endpoints are allowed"
        )

    server_version = _run_docker(["version", "--format", "{{.Server.Version}}"])
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
            "FROM scratch\nCOPY . /context/\n", encoding="utf-8"
        )

        for relative_path in (*ALLOWED_FILES, *FORBIDDEN_FILES):
            _write_synthetic_file(context, relative_path)

        token = uuid.uuid4().hex
        image_tag = f"docker-context-policy-probe:{token}"
        container_name = f"docker-context-policy-probe-{token}"
        archive_path = temp_root / "synthetic-image-rootfs.tar"
        image_created = False
        container_created = False

        try:
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
                ]
            )
            image_created = True

            _run_docker(["create", "--name", container_name, image_tag])
            container_created = True
            _run_docker(
                ["export", "--output", str(archive_path), container_name]
            )

            exported_paths = _context_entries_from_export(archive_path)
            for relative_path in FORBIDDEN_FILES:
                assert relative_path not in exported_paths, (
                    "forbidden synthetic path entered Docker image: "
                    f"{relative_path}"
                )
            for relative_path in ALLOWED_FILES:
                assert relative_path in exported_paths, (
                    "expected non-secret context file was excluded: "
                    f"{relative_path}"
                )
        finally:
            cleanup_failures: list[str] = []
            for should_remove, args, label in (
                (container_created, ["rm", "--force", container_name], "container"),
                (image_created, ["image", "rm", "--force", image_tag], "image"),
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
