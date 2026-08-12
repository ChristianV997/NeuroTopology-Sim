from __future__ import annotations

import pytest

from oss_opportunities.opportunity_batch import build_opportunities_from_candidates
from oss_opportunities.planner import plan_oss_integrations_from_opportunities
from oss_opportunities.renderer import (
    render_oss_opportunity_summary,
    render_oss_opportunity_summary_html,
    write_oss_opportunity_summary,
)
from oss_opportunities.validation import OssOpportunityStoreError
from tests._oss_opportunity_fixtures import (
    make_agpl_scraper_candidate,
    make_document_ingestion_candidate,
    make_frontend_stack_candidate,
)


def _batch_and_plan():
    batch = build_opportunities_from_candidates(
        [make_document_ingestion_candidate(), make_frontend_stack_candidate(), make_agpl_scraper_candidate()]
    )
    plan = plan_oss_integrations_from_opportunities(batch)
    return batch, plan


def test_markdown_render_contains_required_sections():
    batch, plan = _batch_and_plan()
    text = render_oss_opportunity_summary(batch, plan)
    for heading in (
        "## Sources scanned", "## Top repositories by category", "## Immediate adapter candidates",
        "## Architecture emulation candidates", "## Documentation references", "## License risk table",
        "## Security risk table", "## Rejected / deferred repositories", "## Proposed next PRs",
        "## Blocked actions", "## Limitations", "## Reproducibility",
    ):
        assert heading in text


def test_markdown_render_without_plan_still_works():
    batch, _ = _batch_and_plan()
    text = render_oss_opportunity_summary(batch)
    assert "# Open-Source Leverage Scouting Report" in text


def test_markdown_render_is_deterministic():
    batch, plan = _batch_and_plan()
    assert render_oss_opportunity_summary(batch, plan) == render_oss_opportunity_summary(batch, plan)


def test_markdown_includes_license_risk_and_blocked_actions():
    batch, plan = _batch_and_plan()
    text = render_oss_opportunity_summary(batch, plan)
    assert "AGPL-3.0" in text or "strong_copyleft_high" in text
    assert "copy_code_without_license_review" in text


def test_html_render_escapes_and_has_no_script_or_cdn():
    batch, plan = _batch_and_plan()
    html = render_oss_opportunity_summary_html(batch, plan)
    assert "<script" not in html
    assert "cdn." not in html.lower()
    assert "<title>Open-Source Leverage Scouting Report</title>" in html


def test_html_render_deterministic():
    batch, plan = _batch_and_plan()
    assert render_oss_opportunity_summary_html(batch, plan) == render_oss_opportunity_summary_html(batch, plan)


def test_render_never_claims_integration_was_performed():
    batch, plan = _batch_and_plan()
    text = render_oss_opportunity_summary(batch, plan)
    assert "does not perform any" in text


def test_render_raises_on_banned_phrase():
    from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES

    batch, plan = _batch_and_plan()
    batch.provenance = f"this {BANNED_REPORT_PHRASES[0]}"
    with pytest.raises(OssOpportunityStoreError):
        render_oss_opportunity_summary(batch, plan)


def test_write_oss_opportunity_summary_creates_markdown_and_html(tmp_path):
    batch, plan = _batch_and_plan()
    written = write_oss_opportunity_summary(batch, plan, tmp_path)
    assert written["markdown"].exists()
    assert written["html"].exists()
    assert "# Open-Source Leverage Scouting Report" in written["markdown"].read_text(encoding="utf-8")


def test_write_without_html_flag_skips_html(tmp_path):
    batch, plan = _batch_and_plan()
    written = write_oss_opportunity_summary(batch, plan, tmp_path, write_html=False)
    assert "html" not in written
    assert written["markdown"].exists()
