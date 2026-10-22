"""Deterministic synthetic fixtures for Batch 2 security acceptance."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Network policy fixtures (source snippets)
# ---------------------------------------------------------------------------

NETWORK_SAFE_OPT_IN = '''
def fetch_object(key, *, allow_network: bool = False):
    if not allow_network:
        raise PermissionError("network disabled")
    return key
'''

NETWORK_DEFAULT_ENABLED = '''
def fetch_object(key, *, allow_network: bool = True):
    return key
'''

# ---------------------------------------------------------------------------
# Static scan fixtures (adversarial source snippets)
# ---------------------------------------------------------------------------

STATIC_FIXTURES: Dict[str, str] = {
    "curl_transfer": 'subprocess.run(["bash", "-c", "curl https://example.com/data.bin -o out.bin"])\n',
    "wget_transfer": 'cmd = "wget https://example.com/ds.tar -O ds.tar"\nsubprocess.call(cmd, shell=True)\n',
    "aws_sync": 'subprocess.check_call(["aws", "s3", "sync", "s3://bucket/ds", "./ds"])\n',
    "openneuro_download": 'subprocess.run(["openneuro", "download", "ds005620"])\n',
    "boto3_download_file": "client.download_file(Bucket=b, Key=k, Filename=path)\n",
    "boto3_get_object_full": 'body = client.get_object(Bucket=b, Key=k)["Body"].read()\n',
    "boto3_get_object_ranged": 'body = client.get_object(Bucket=b, Key=k, Range="bytes=0-99")["Body"].read(100)\n',
    "urllib_urlopen": "from urllib.request import urlopen\ndata = urlopen('https://example.com').read()\n",
}

# ---------------------------------------------------------------------------
# Path containment cases: (fixture_id, candidate, should_escape)
# ---------------------------------------------------------------------------

def path_cases() -> List[Tuple[str, str, bool]]:
    return [
        ("path_ok_child", "artifacts/report.json", False),
        ("path_traversal", "../etc/passwd", True),
        ("path_nested_traversal", "ok/../../outside", True),
        ("path_absolute_posix", "/tmp/escape", True),
        ("path_windows_drive", r"C:\Windows\System32\config", True),
        ("path_windows_unc", r"\\?\C:\escape", True),
    ]


# ---------------------------------------------------------------------------
# Evidence / provenance fixtures
# ---------------------------------------------------------------------------

EVIDENCE_FIXTURES: Dict[str, Dict[str, Any]] = {
    "evidence_complete": {
        "evidence_class": "engineering",
        "synthetic": True,
        "presented_as": "engineering",
        "provenance": {
            "checksum": "a" * 64,
            "git_commit": "3f3fe8593303184cb88eef056c1322f3d4e57a16",
            "fabricated": False,
        },
        "scientific_pass": False,
    },
    "fabricated_provenance": {
        "evidence_class": "engineering",
        "synthetic": True,
        "presented_as": "engineering",
        "provenance": {
            "checksum": "b" * 64,
            "git_commit": "deadbeef",
            "fabricated": True,
        },
    },
    "missing_checksum": {
        "evidence_class": "engineering",
        "synthetic": True,
        "presented_as": "engineering",
        "provenance": {"git_commit": "abc123"},
    },
    "missing_commit": {
        "evidence_class": "engineering",
        "synthetic": True,
        "presented_as": "engineering",
        "provenance": {"checksum": "c" * 64},
    },
    "synthetic_to_empirical": {
        "evidence_class": "synthetic",
        "synthetic": True,
        "presented_as": "empirical",
        "scientific_pass": True,
        "provenance": {
            "checksum": "d" * 64,
            "git_commit": "abc123",
        },
    },
}

# ---------------------------------------------------------------------------
# Artifact state fixtures
# ---------------------------------------------------------------------------

ARTIFACT_FIXTURES: Dict[str, Dict[str, Any]] = {
    "artifact_failed": {"run_id": "r1", "status": "FAILED", "scientific_pass": False},
    "artifact_partial": {"run_id": "r2", "status": "PARTIAL", "scientific_pass": False},
    "artifact_timed_out": {"run_id": "r3", "status": "TIMED_OUT", "scientific_pass": False},
    "artifact_interrupted": {
        "run_id": "r4",
        "status": "INTERRUPTED",
        "scientific_pass": False,
        "security_pass": True,  # illegal — harness must flag
    },
    "artifact_malformed": {"status": None, "scientific_pass": True},
    "artifact_complete": {
        "run_id": "r5",
        "status": "COMPLETE",
        "scientific_pass": False,
        "security_pass": False,
    },
}

# ---------------------------------------------------------------------------
# Non-finite JSON fixtures
# ---------------------------------------------------------------------------

NON_FINITE_PAYLOAD = {"score": float("nan"), "bound": float("inf")}
FINITE_PAYLOAD = {"score": 1.25, "bound": 0.0, "nested": {"ok": True}}
