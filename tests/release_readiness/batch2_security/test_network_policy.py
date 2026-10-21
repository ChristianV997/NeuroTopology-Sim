"""Network-disabled defaults and explicit opt-in."""
from __future__ import annotations

import pytest

from tools.release_readiness.batch2_security import fixtures as fx
from tools.release_readiness.batch2_security.network_policy import (
    NetworkGuardError,
    find_network_default_enabled,
    network_opt_in_is_safe,
    no_network,
)
from tools.release_readiness.batch2_security.schema import ThreatClass


def test_safe_opt_in_defaults_to_false():
    assert network_opt_in_is_safe(fx.NETWORK_SAFE_OPT_IN) is True
    assert find_network_default_enabled(fx.NETWORK_SAFE_OPT_IN) == []


def test_default_enabled_is_detected():
    findings = find_network_default_enabled(
        fx.NETWORK_DEFAULT_ENABLED, fixture_id="network_default_enabled"
    )
    assert findings
    assert findings[0].threat_class == ThreatClass.NETWORK_DEFAULT_ENABLED.value
    assert "allow_network=True" in findings[0].message


def test_no_network_guard_blocks_sockets():
    with pytest.raises(NetworkGuardError):
        with no_network():
            import socket

            socket.create_connection(("127.0.0.1", 9), timeout=0.01)
