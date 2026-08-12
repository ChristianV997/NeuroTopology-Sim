"""Shared synthetic-fixture helpers for the oss_opportunities test suite.
Not a pytest test module itself (no test_ prefix)."""
from __future__ import annotations

from oss_opportunities.repository_candidate import OpenSourceRepositoryCandidateV1


def make_document_ingestion_candidate(repo_full_name: str = "microsoft/markitdown") -> OpenSourceRepositoryCandidateV1:
    return OpenSourceRepositoryCandidateV1.make(
        repo_full_name=repo_full_name, source="trendshift_daily", source_timeframe="daily",
        source_snapshot_date="2026-08-12", source_rank=1,
        name=repo_full_name.split("/")[-1], owner=repo_full_name.split("/")[0],
        description="Convert documents to markdown for LLMs and RAG pipelines",
        topics=["document-conversion", "markdown", "pdf"], primary_language="Python",
        stars=12000, star_gain=150, fork_count=800,
        license_spdx="MIT", license_name="MIT License", latest_activity_status="active",
        provenance="synthetic fixture, not a real Trendshift observation",
        limitations=["synthetic fixture only"],
    )


def make_agpl_scraper_candidate(repo_full_name: str = "D4Vinci/Scrapling") -> OpenSourceRepositoryCandidateV1:
    return OpenSourceRepositoryCandidateV1.make(
        repo_full_name=repo_full_name, source="trendshift_weekly", source_timeframe="weekly",
        source_snapshot_date="2026-08-12",
        name=repo_full_name.split("/")[-1], owner=repo_full_name.split("/")[0],
        description="Undetectable web scraping and crawling library",
        topics=["scraping", "crawler"], primary_language="Python",
        stars=5000, star_gain=80,
        license_spdx="AGPL-3.0", license_name="GNU AGPLv3", latest_activity_status="active",
        provenance="synthetic fixture, not a real Trendshift observation",
        limitations=["synthetic fixture only"],
    )


def make_frontend_stack_candidate(repo_full_name: str = "TanStack/router") -> OpenSourceRepositoryCandidateV1:
    return OpenSourceRepositoryCandidateV1.make(
        repo_full_name=repo_full_name, source="star_history_starmap", source_timeframe="frontend",
        source_snapshot_date="2026-08-12",
        name=repo_full_name.split("/")[-1], owner=repo_full_name.split("/")[0],
        description="Type-safe router for React applications",
        topics=["frontend", "react", "router"], primary_language="TypeScript",
        stars=9000, star_gain=40,
        license_spdx="MIT", license_name="MIT License", latest_activity_status="active",
        observed_categories=["frontend"],
        provenance="synthetic fixture, not a real Star History observation",
        limitations=["synthetic fixture only"],
    )


def make_unknown_license_candidate(repo_full_name: str = "unknown/proprietary-security-tool") -> OpenSourceRepositoryCandidateV1:
    return OpenSourceRepositoryCandidateV1.make(
        repo_full_name=repo_full_name, source="github_manual_seed", source_timeframe="",
        source_snapshot_date="2026-08-12",
        name="proprietary-security-tool", owner="unknown",
        description="security compliance pentest scanner",
        topics=["security", "pentest"], primary_language="Python", stars=100,
        license_spdx="unknown", license_name="unknown", latest_activity_status="unknown",
        provenance="synthetic fixture, not a real observation",
        limitations=["synthetic fixture only"],
    )


def make_sparse_candidate(repo_full_name: str = "some/sparse-repo") -> OpenSourceRepositoryCandidateV1:
    """No topics, no description, no stars -- exercises the fallback
    reject_or_defer leverage_category path."""
    return OpenSourceRepositoryCandidateV1.make(
        repo_full_name=repo_full_name, source="github_manual_seed", source_timeframe="",
        source_snapshot_date="2026-08-12", name="sparse-repo", owner="some",
        primary_language="", license_spdx="unknown", license_name="unknown",
        provenance="synthetic fixture, not a real observation",
        limitations=["synthetic fixture only"],
    )
