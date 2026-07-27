"""Fail-closed AWS credential and S3 result-routing preflight for Braket."""
from __future__ import annotations

from dataclasses import dataclass
import os
from uuid import uuid4


@dataclass(frozen=True)
class S3Routing:
    """Validated Braket result destination; bucket/prefix are not secrets."""

    bucket: str
    prefix: str
    region: str
    account_id: str
    bucket_created: bool = False

    @property
    def destination_folder(self) -> tuple[str, str]:
        """Return the tuple accepted by ``AwsDevice.run``."""
        return (self.bucket, self.prefix)


def _is_missing_bucket_error(error: Exception) -> bool:
    """Return true only for explicit S3 nonexistence responses."""
    response = getattr(error, "response", None)
    code = str(response.get("Error", {}).get("Code", "")) if isinstance(response, dict) else ""
    return code in {"404", "NoSuchBucket", "NotFound"}


def resolve_s3_routing(*, bucket: str | None = None, prefix: str = "sciencerd/dm1", run_label: str = "thermal-sweep", create_if_missing: bool = True) -> S3Routing:
    """Validate credentials, caller identity, and writable/readable bucket access.

    Network calls occur only when a caller explicitly requests a live run.  The
    account and region are appended to the prefix to keep independently owned
    executions disjoint.  A failed preflight raises rather than guessing a
    bucket or silently running a local substitute.
    """
    selected_bucket = bucket or os.environ.get("SCIENCERD_BRAKET_BUCKET")
    region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION")
    if not region:
        raise RuntimeError("AWS/S3 preflight failed: set AWS_DEFAULT_REGION or AWS_REGION")
    try:
        import boto3
        session = boto3.Session(region_name=region)
        if session.get_credentials() is None:
            raise RuntimeError("AWS credentials are unavailable")
        account_id = str(session.client("sts").get_caller_identity()["Account"])
        selected_bucket = selected_bucket or f"amazon-braket-{region}-{account_id}"
        s3 = session.client("s3")
        created = False
        try:
            # ``head_bucket`` alone does not prove Braket can write task output.
            s3.head_bucket(Bucket=selected_bucket)
        except Exception as exc:
            if not create_if_missing or not _is_missing_bucket_error(exc):
                raise
            create_kwargs = {"Bucket": selected_bucket}
            if region != "us-east-1":
                create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
            s3.create_bucket(**create_kwargs)
            created = True
            s3.head_bucket(Bucket=selected_bucket)
        probe_key = f"{prefix.strip('/')}/_preflight/{uuid4().hex}.probe"
        s3.put_object(Bucket=selected_bucket, Key=probe_key, Body=b"ScienceR-Dsim Braket route preflight\n", ContentType="text/plain")
        s3.delete_object(Bucket=selected_bucket, Key=probe_key)
    except Exception as exc:  # provider errors differ across boto3 versions
        raise RuntimeError(f"AWS/S3 preflight failed: {exc}") from exc
    cleaned = "/".join(part for part in (prefix.strip("/"), account_id, region, run_label.strip("/")) if part)
    return S3Routing(bucket=selected_bucket, prefix=cleaned, region=region, account_id=account_id, bucket_created=created)
