import pytest
import time
from tests.btc_icft.test_toe_literature_bridge_validator import (
    test_validator_accepts_complete_bridge,
    generated,
    _generated_base,
)

def test_validator_fixture_performance(generated):
    """
    Regression test ensuring the TOE literature bridge validator fixture
    does not regress into O(N) subprocess calls per test which previously
    caused 60+ second timeouts during isolated batch testing.
    """
    start = time.perf_counter()
    test_validator_accepts_complete_bridge(generated)
    elapsed = time.perf_counter() - start
    
    # Under optimized (module-scoped + copy) fixture, this should take < 0.5s.
    # We set a generous upper bound of 2 seconds for CI environments.
    assert elapsed < 2.0, f"Validator test took {elapsed}s, expected < 2.0s!"
