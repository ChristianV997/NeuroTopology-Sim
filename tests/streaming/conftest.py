"""Reuse mocked boto3 fixtures for fail-closed S3 subject-sync tests.

pytest rejects ``pytest_plugins`` in non-root conftests during whole-tree collection,
so import the fixture directly instead.
"""

from tests.performance.streaming_optimization.conftest import fake_s3_modules, ranged_body  # noqa: F401
