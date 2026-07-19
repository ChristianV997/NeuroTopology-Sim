from __future__ import annotations

import pytest

from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES, validate_safe_text


def test_banned_phrases_includes_meditation_specific_additions():
    """Regression test for the drift this module fixes: these two phrases were
    only present in 4/9 files before consolidation."""
    assert "enlightenment proven" in BANNED_REPORT_PHRASES
    assert "nirvana confirmed" in BANNED_REPORT_PHRASES


def test_validate_safe_text_passes_clean_text():
    validate_safe_text("This is operational signal-window metadata.")  # must not raise


def test_validate_safe_text_raises_on_banned_phrase():
    with pytest.raises(ValueError, match="banned phrase detected"):
        validate_safe_text("This proves consciousness.")


def test_validate_safe_text_case_insensitive():
    with pytest.raises(ValueError):
        validate_safe_text("THIS PROVES CONSCIOUSNESS.")


def test_validate_safe_text_extra_phrases():
    validate_safe_text("clean text", extra_banned_phrases=("dataset-specific banned phrase",))
    with pytest.raises(ValueError, match="banned phrase detected"):
        validate_safe_text("contains dataset-specific banned phrase here", extra_banned_phrases=("dataset-specific banned phrase",))


def test_all_nine_consumer_modules_import_the_shared_constant():
    """Regression test for the consolidation itself: every module that used to
    carry its own copy of BANNED_REPORT_PHRASES must now import the shared one
    (verified by identity, not just equal value) -- catches a future accidental
    reintroduction of a local copy."""
    import sciencer_d.btc_icft.datasets.ds005620 as m1
    import sciencer_d.btc_icft.evaluation.ds005620_residual as m2
    import sciencer_d.btc_icft.level_m.ds005620_windows as m3
    import sciencer_d.btc_icft.level_m.ds003969_windows as m4
    import sciencer_d.btc_icft.level_m.ds001787_windows as m5
    import sciencer_d.btc_icft.level_t.ds005620_features as m6
    import sciencer_d.btc_icft.level_t.ds005620_real_topology as m7
    import sciencer_d.btc_icft.level_t.ds003969_real_topology as m8
    import sciencer_d.btc_icft.level_t.ds001787_real_topology as m9

    for mod in (m1, m2, m3, m4, m5, m6, m7, m8, m9):
        assert mod.BANNED_REPORT_PHRASES is BANNED_REPORT_PHRASES
