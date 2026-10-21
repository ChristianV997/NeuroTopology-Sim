"""Static detection of unsafe remote-materialization patterns (fixture-oriented)."""
from __future__ import annotations

import ast
import re
from typing import List

from tools.release_readiness.batch2_security.schema import (
    REMEDIATION_OWNERS,
    Finding,
    ThreatClass,
)

_SHELL_TRANSFER = re.compile(
    r"(?i)\b(?:curl|wget)\s+(?:https?://|s3://|ftp://)"
)
_AWS_FULL = re.compile(r"(?i)\baws\s+s3\s+(?:cp|sync)\b")
_OPENNEURO = re.compile(r"(?i)\bopenneuro\s+download\b")
_DATALAD = re.compile(r"(?i)\bdatalad\s+install\b")
_FULL_DATASET = re.compile(
    r"(?i)\b(?:download_all|sync_dataset|full_dataset_download|aws\s+s3\s+sync)\b"
)


def _owners(threat: ThreatClass) -> List[str]:
    return list(REMEDIATION_OWNERS[threat.value])


def _normalized_command_line(line: str) -> str:
    """Collapse list/argv punctuation so `["aws", "s3", "sync"]` matches prose patterns."""
    normalized = re.sub(r"[\[\],\"'()]", " ", line)
    return re.sub(r"\s+", " ", normalized).strip()


def scan_source_text(source: str, *, fixture_id: str | None = None) -> List[Finding]:
    """Scan source text for full-object / full-dataset / shell / urllib transfer risks."""
    findings: List[Finding] = []
    for line_number, line in enumerate(source.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        normalized = _normalized_command_line(line)
        haystacks = (line, normalized)
        if any(_SHELL_TRANSFER.search(text) for text in haystacks):
            findings.append(
                Finding(
                    threat_class=ThreatClass.UNAUTHORIZED_SHELL_TRANSFER.value,
                    severity="critical",
                    message="curl/wget remote transfer detected",
                    fixture_id=fixture_id,
                    location=f"L{line_number}",
                    remediation_owners=_owners(ThreatClass.UNAUTHORIZED_SHELL_TRANSFER),
                )
            )
        if any(_AWS_FULL.search(text) for text in haystacks):
            findings.append(
                Finding(
                    threat_class=ThreatClass.UNAUTHORIZED_AWS_FULL_TRANSFER.value,
                    severity="critical",
                    message="aws s3 cp/sync full transfer detected",
                    fixture_id=fixture_id,
                    location=f"L{line_number}",
                    remediation_owners=_owners(ThreatClass.UNAUTHORIZED_AWS_FULL_TRANSFER),
                )
            )
        if any(
            _OPENNEURO.search(text) or _DATALAD.search(text) or _FULL_DATASET.search(text)
            for text in haystacks
        ):
            findings.append(
                Finding(
                    threat_class=ThreatClass.FULL_DATASET_DOWNLOAD.value,
                    severity="critical",
                    message="full-dataset download / unbounded materialization path detected",
                    fixture_id=fixture_id,
                    location=f"L{line_number}",
                    remediation_owners=_owners(ThreatClass.FULL_DATASET_DOWNLOAD),
                )
            )

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return findings

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = ""
        qualified = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            qualified = func_name
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
            parts: list[str] = []
            cur: ast.AST = node.func
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
            qualified = ".".join(reversed(parts))

        if func_name in {"download_file", "download_fileobj"}:
            findings.append(
                Finding(
                    threat_class=ThreatClass.UNAUTHORIZED_BOTO3_FULL_OBJECT.value,
                    severity="critical",
                    message=f"boto3 full-object helper {func_name}()",
                    fixture_id=fixture_id,
                    location=f"L{getattr(node, 'lineno', 1)}",
                    remediation_owners=_owners(ThreatClass.UNAUTHORIZED_BOTO3_FULL_OBJECT),
                )
            )
        if func_name == "get_object":
            has_range = any(kw.arg == "Range" for kw in node.keywords)
            if not has_range:
                findings.append(
                    Finding(
                        threat_class=ThreatClass.UNBOUNDED_REMOTE_MATERIALIZATION.value,
                        severity="critical",
                        message="get_object() without Range (full-object materialization)",
                        fixture_id=fixture_id,
                        location=f"L{getattr(node, 'lineno', 1)}",
                        remediation_owners=_owners(ThreatClass.UNBOUNDED_REMOTE_MATERIALIZATION),
                    )
                )
        if func_name == "urlopen" or qualified.lower().startswith(
            ("urllib.request.urlopen", "urllib.urlopen", "requests.get", "httpx.get")
        ):
            findings.append(
                Finding(
                    threat_class=ThreatClass.UNRESTRICTED_URLLIB.value,
                    severity="error",
                    message=f"unrestricted HTTP retrieval via {qualified or func_name}",
                    fixture_id=fixture_id,
                    location=f"L{getattr(node, 'lineno', 1)}",
                    remediation_owners=_owners(ThreatClass.UNRESTRICTED_URLLIB),
                )
            )
        # Body.read() with no size argument after get_object is unbounded materialization.
        if func_name == "read" and isinstance(node.func, ast.Attribute) and not node.args:
            receiver = ""
            if isinstance(node.func.value, ast.Name):
                receiver = node.func.value.id.lower()
            elif isinstance(node.func.value, ast.Attribute):
                receiver = node.func.value.attr.lower()
            if receiver in {"body", "response", "resp", "stream", "payload"}:
                findings.append(
                    Finding(
                        threat_class=ThreatClass.UNBOUNDED_REMOTE_MATERIALIZATION.value,
                        severity="error",
                        message=f"unbounded {receiver}.read() with no size budget",
                        fixture_id=fixture_id,
                        location=f"L{getattr(node, 'lineno', 1)}",
                        remediation_owners=_owners(ThreatClass.UNBOUNDED_REMOTE_MATERIALIZATION),
                    )
                )
    return findings
