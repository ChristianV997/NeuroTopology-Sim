"""Network-disabled defaults and explicit opt-in checks."""
from __future__ import annotations

import ast
import socket
from contextlib import contextmanager
from typing import Iterator, List

from tools.release_readiness.batch2_security.schema import (
    REMEDIATION_OWNERS,
    Finding,
    ThreatClass,
)


class NetworkGuardError(RuntimeError):
    """Raised when the harness attempts network I/O under no_network()."""


@contextmanager
def no_network() -> Iterator[None]:
    """Block outbound socket creation during harness execution."""

    def _blocked(*_args, **_kwargs):
        raise NetworkGuardError("batch2 security harness forbids network access")

    original_socket = socket.socket
    original_create = socket.create_connection
    socket.socket = _blocked  # type: ignore[assignment]
    socket.create_connection = _blocked  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket = original_socket  # type: ignore[assignment]
        socket.create_connection = original_create  # type: ignore[assignment]


def _network_arg_names() -> set[str]:
    return {"allow_network", "network_enabled", "download_enabled", "network"}


def find_network_default_enabled(source: str, *, fixture_id: str | None = None) -> List[Finding]:
    """Return findings when network flags default to True (fail-open)."""
    findings: List[Finding] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        findings.append(
            Finding(
                threat_class=ThreatClass.NETWORK_DEFAULT_ENABLED.value,
                severity="critical",
                message=f"unparseable network policy fixture: {exc}",
                fixture_id=fixture_id,
                remediation_owners=list(REMEDIATION_OWNERS[ThreatClass.NETWORK_DEFAULT_ENABLED.value]),
            )
        )
        return findings

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        defaults = list(node.args.defaults)
        positional = list(node.args.posonlyargs) + list(node.args.args)
        first_default = len(positional) - len(defaults)
        for index, argument in enumerate(positional):
            if index < first_default or argument.arg.lower() not in _network_arg_names():
                continue
            default = defaults[index - first_default]
            if isinstance(default, ast.Constant) and default.value is True:
                findings.append(
                    Finding(
                        threat_class=ThreatClass.NETWORK_DEFAULT_ENABLED.value,
                        severity="critical",
                        message=f"{node.name}({argument.arg}=True) network enabled by default",
                        fixture_id=fixture_id,
                        location=f"{node.name}:{getattr(node, 'lineno', 1)}",
                        remediation_owners=list(
                            REMEDIATION_OWNERS[ThreatClass.NETWORK_DEFAULT_ENABLED.value]
                        ),
                    )
                )
        for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
            if (
                argument.arg.lower() in _network_arg_names()
                and isinstance(default, ast.Constant)
                and default.value is True
            ):
                findings.append(
                    Finding(
                        threat_class=ThreatClass.NETWORK_DEFAULT_ENABLED.value,
                        severity="critical",
                        message=f"{node.name}({argument.arg}=True) keyword network enabled by default",
                        fixture_id=fixture_id,
                        location=f"{node.name}:{getattr(node, 'lineno', 1)}",
                        remediation_owners=list(
                            REMEDIATION_OWNERS[ThreatClass.NETWORK_DEFAULT_ENABLED.value]
                        ),
                    )
                )
    return findings


def network_opt_in_is_safe(source: str) -> bool:
    """True when every network flag defaults to False or is required (no default True)."""
    return not find_network_default_enabled(source)
