"""Content-free tests for Docker build-context exclusion policy."""

from __future__ import annotations

import fnmatch
from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCKERIGNORE = REPOSITORY_ROOT / ".dockerignore"
POLICY_FIXTURE = (
    REPOSITORY_ROOT / "tests/docker_context/fixtures/required_ignore_rules.txt"
)
SAFE_ENV_EXAMPLE = "apps/awareness_studio/.env.example"


def _matches_rule(rule: str, path: str) -> bool:
    """Match the simple path rules used by this policy test."""
    normalized_rule = rule.strip("/")
    parts = path.split("/")

    if normalized_rule.startswith("**/"):
        tail = normalized_rule[3:]
        return any(
            fnmatch.fnmatchcase("/".join(parts[start:end]), tail)
            for start in range(len(parts))
            for end in range(start + 1, len(parts) + 1)
        )

    if "/" in normalized_rule:
        return fnmatch.fnmatchcase(path, normalized_rule)

    return fnmatch.fnmatchcase(path, normalized_rule)


def _is_ignored(rules: list[str], path: str) -> bool:
    ignored = False
    for raw_rule in rules:
        if not raw_rule or raw_rule.startswith("#"):
            continue
        negated = raw_rule.startswith("!")
        rule = raw_rule[1:] if negated else raw_rule
        if _matches_rule(rule, path):
            ignored = not negated
    return ignored


class TestDockerBuildContextPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = POLICY_FIXTURE.read_text(encoding="utf-8").splitlines()

    @unittest.skipUnless(
        DOCKERIGNORE.is_file(),
        "Docker omits .dockerignore from the image; host execution verifies this mapping.",
    )
    def test_fixture_rules_are_present_in_repository_dockerignore(self) -> None:
        dockerignore_rules = DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        for rule in self.rules:
            with self.subTest(rule=rule):
                self.assertIn(rule, dockerignore_rules)

    def test_synthetic_secret_and_local_state_paths_are_excluded(self) -> None:
        synthetic_paths = (
            ".env",
            "apps/awareness_studio/.env.local",
            "nested/module/.aws/credentials",
            "sandbox/credentials.json",
            "sandbox/service-account-test.json",
            ".azure/accessTokens.json",
            "nested/.config/gcloud/application_default_credentials.json",
            ".config/gh/hosts.yml",
            "config/.docker/config.json",
            "module/.npmrc",
            "module/.pypirc",
            "module/.netrc",
            "module/.git-credentials",
            "module/.envrc",
            "terraform/.terraform.d/credentials.tfrc.json",
            "users/.ssh/id_ed25519",
            "keys/id_rsa",
            "certs/client.pem",
            "certs/client.key",
            "certs/client.p12",
            "certs/client.p8",
            "certs/client.pfx",
            "certs/client.ppk",
            "certs/ca.crt",
            "certs/ca.cer",
            "certs/ca.der",
            ".venv/bin/python",
            "apps/awareness_studio/venv/bin/python",
            "tools/.tox/py/bin/python",
            "apps/awareness_studio/.nox/py/bin/python",
            "nested/repo/.git/config",
        )

        for path in synthetic_paths:
            with self.subTest(path=path):
                self.assertTrue(_is_ignored(self.rules, path), path)

    def test_only_repository_tracked_env_example_is_reincluded(self) -> None:
        self.assertTrue((REPOSITORY_ROOT / SAFE_ENV_EXAMPLE).is_file())
        self.assertFalse(_is_ignored(self.rules, SAFE_ENV_EXAMPLE))
        exceptions = [rule[1:] for rule in self.rules if rule.startswith("!")]
        self.assertEqual([SAFE_ENV_EXAMPLE], exceptions)

    def test_required_source_and_test_paths_remain_in_context(self) -> None:
        required_paths = (
            "apps/awareness_studio/src/awareness_studio/__init__.py",
            "apps/awareness_studio/tests/research_cycle/test_execution_dependency_contract.py",
            "apps/awareness_studio/Dockerfile",
            "docker/ci/core.Dockerfile",
            "Dockerfile",
            "tests/docker_context/test_build_context_policy.py",
            "tests/docker_context/fixtures/required_ignore_rules.txt",
        )

        for path in required_paths:
            with self.subTest(path=path):
                self.assertTrue((REPOSITORY_ROOT / path).exists(), path)
                self.assertFalse(_is_ignored(self.rules, path), path)

    def test_docker_workflow_uses_the_protected_repository_root_context(self) -> None:
        workflow = (REPOSITORY_ROOT / ".github/workflows/docker-build.yml").read_text(
            encoding="utf-8"
        )
        required_commands = (
            (
                "docker build --progress=plain -f docker/ci/core.Dockerfile "
                "-t neurotopology-sim:core-cpu ."
            ),
            (
                "docker build --progress=plain -t awareness-studio:latest "
                "-f apps/awareness_studio/Dockerfile ."
            ),
            (
                "docker build --progress=plain -f Dockerfile "
                "-t neurotopology-sim:production-root ."
            ),
        )

        for command in required_commands:
            with self.subTest(command=command):
                self.assertIn(command, workflow)

    def test_no_dockerfile_specific_ignore_overrides_root_policy(self) -> None:
        override_paths = (
            "Dockerfile.dockerignore",
            "docker/ci/core.Dockerfile.dockerignore",
            "apps/awareness_studio/Dockerfile.dockerignore",
        )
        for path in override_paths:
            with self.subTest(path=path):
                self.assertFalse((REPOSITORY_ROOT / path).exists(), path)


if __name__ == "__main__":
    unittest.main()
