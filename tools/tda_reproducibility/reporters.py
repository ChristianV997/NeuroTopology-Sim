"""Reporting and formatting utilities for TDA reproducibility audit.

Generates:
- High-contrast CLI terminal summaries
- Markdown audit reports
- Obsidian mirror notes
"""
from __future__ import annotations

from tools.tda_reproducibility.types import AuditReport


def format_terminal_summary(report: AuditReport) -> str:
    """Format AuditReport as a human-readable CLI summary table."""
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("          TDA BACKEND REPRODUCIBILITY & EQUIVALENCE AUDIT")
    lines.append("=" * 78)
    lines.append(f"Timestamp (UTC): {report.created_at_utc}")
    lines.append(f"Python Version : {report.python_version}")
    lines.append(f"Platform       : {report.platform}")
    lines.append(f"Schema Version : {report.schema_version}")
    lines.append(f"Provenance Hash: {report.provenance_hash[:16]}...")
    lines.append("-" * 78)

    # 1. Backends Probe
    lines.append("\n[1] BACKEND AVAILABILITY & CAPABILITY PROBE")
    lines.append(f"{'Backend':<16} {'Status':<12} {'Version':<12} {'MaxDim':<8} {'Nature':<12}")
    lines.append("-" * 62)
    for p in report.probes:
        v_str = p.version if p.version else "N/A"
        nature = "exact" if p.is_exact else "approximate"
        lines.append(f"{p.backend_id:<16} {p.status:<12} {v_str:<12} {p.max_dimension_supported:<8} {nature:<12}")

    # 2. Fixture Results
    lines.append("\n[2] SYNTHETIC FIXTURE EXECUTION & AGREEMENT")
    lines.append(f"{'Fixture ID':<26} {'Points':<8} {'Agreement':<16} {'Notes'}")
    lines.append("-" * 78)
    for fix in report.fixture_results:
        lines.append(f"{fix.fixture_id:<26} {fix.num_points:<8} {fix.overall_agreement:<16} {fix.notes}")

    # 3. Disagreements (if any)
    lines.append("\n[3] CROSS-BACKEND EQUIVALENCE & DISAGREEMENTS")
    disagreements = []
    for fix in report.fixture_results:
        for comp in fix.pairwise_comparisons:
            if not comp.equivalent:
                disagreements.append((fix.fixture_id, comp))

    if not disagreements:
        lines.append("  All active backends in FULL NUMERICAL & TOPOLOGICAL AGREEMENT.")
    else:
        lines.append(f"  DETECTED {len(disagreements)} DISAGREEMENT(S):")
        for fix_id, comp in disagreements:
            lines.append(
                f"  - [{fix_id}] {comp.backend_a} vs {comp.backend_b} (dim {comp.dimension}): {comp.disagreement_reason}"
            )

    # 4. Invariants & Telemetry
    sc = report.summary_counts
    lines.append("\n[4] INVARIANT & TELEMETRY SUMMARY")
    lines.append(f"  Total Invariants Checked : {sc.get('total_invariants_checked', 0)}")
    lines.append(f"  Invariants Passed        : {sc.get('invariants_passed', 0)}")
    lines.append(f"  Invariants Failed        : {sc.get('invariants_failed', 0)}")
    lines.append(f"  Spatial Charge Isolated  : {'CONFIRMED (PASS)' if report.spatial_charge_isolation_confirmed else 'VIOLATED (FAIL)'}")
    lines.append(f"  All Invariants Passed    : {'YES' if report.all_invariants_passed else 'NO'}")

    # 5. Scientific Guardrails
    lines.append("-" * 78)
    lines.append("SCIENTIFIC GUARDRAILS:")
    lines.append(f"  {report.scientific_disclaimer}")
    lines.append("=" * 78)
    return "\n".join(lines)


def format_markdown_report(report: AuditReport) -> str:
    """Format AuditReport as a structured Markdown document."""
    lines: list[str] = []
    lines.append("# TDA Backend Reproducibility and Equivalence Audit Report\n")
    lines.append("> [!NOTE]")
    lines.append(f"> {report.scientific_disclaimer}\n")

    lines.append("## 1. Audit Metadata")
    lines.append(f"- **Timestamp (UTC)**: `{report.created_at_utc}`")
    lines.append(f"- **Python Version**: `{report.python_version}`")
    lines.append(f"- **Platform**: `{report.platform}`")
    lines.append(f"- **Schema Version**: `{report.schema_version}`")
    lines.append(f"- **Provenance Hash**: `{report.provenance_hash}`")
    lines.append(f"- **All Invariants Passed**: `{'PASS' if report.all_invariants_passed else 'FAIL'}`")
    lines.append(f"- **Spatial Charge Isolation**: `{'CONFIRMED' if report.spatial_charge_isolation_confirmed else 'VIOLATION'}`\n")

    lines.append("## 2. Backend Probes")
    lines.append("| Backend | Status | Version | Max Dim | Nature | Notes |")
    lines.append("|---|---|---|---|---|---|")
    for p in report.probes:
        v_str = f"`{p.version}`" if p.version else "*N/A*"
        nature = "exact" if p.is_exact else "approximate"
        lines.append(f"| `{p.backend_id}` | `{p.status}` | {v_str} | {p.max_dimension_supported} | {nature} | {p.notes} |")
    lines.append("")

    lines.append("## 3. Fixture Equivalence Matrix")
    lines.append("| Fixture ID | Points | Agreement Status | Active Backends | Notes |")
    lines.append("|---|---|---|---|---|")
    for fix in report.fixture_results:
        active_b = [k for k, v in fix.backend_results.items() if v.success]
        lines.append(f"| `{fix.fixture_id}` | {fix.num_points} | `{fix.overall_agreement}` | {', '.join(active_b)} | {fix.notes} |")
    lines.append("")

    lines.append("## 4. Disagreement and Invariant Log")
    disagreements = []
    for fix in report.fixture_results:
        for comp in fix.pairwise_comparisons:
            if not comp.equivalent:
                disagreements.append((fix.fixture_id, comp))

    if not disagreements:
        lines.append("- **Disagreements**: None detected across all active backends.")
    else:
        lines.append(f"- **Disagreements Detected**: {len(disagreements)}")
        for fix_id, comp in disagreements:
            lines.append(
                f"  - `{fix_id}` ({comp.backend_a} vs {comp.backend_b}, dim {comp.dimension}): {comp.disagreement_reason}"
            )
    lines.append("")

    return "\n".join(lines)


def format_obsidian_mirror(report: AuditReport) -> str:
    """Format AuditReport as an Obsidian mirror note."""
    lines: list[str] = []
    lines.append("---")
    lines.append("tags:")
    lines.append("  - topology")
    lines.append("  - tda")
    lines.append("  - reproducibility")
    lines.append("  - audit")
    lines.append(f"created: {report.created_at_utc}")
    lines.append(f"provenance: {report.provenance_hash[:16]}")
    lines.append("---\n")
    lines.append("# TDA Backend Reproducibility Audit Note\n")
    lines.append(f"**Audit Status**: {'PASS' if report.all_invariants_passed else 'FAIL'}")
    lines.append(f"**Spatial Charge Isolation**: {'CONFIRMED' if report.spatial_charge_isolation_confirmed else 'VIOLATED'}\n")
    lines.append("## Probed Backends")
    for p in report.probes:
        v = p.version if p.version else "not installed"
        lines.append(f"- [[{p.backend_id}]]: `{p.status}` (version: {v})")
    lines.append("\n## Fixture Equivalence Summary")
    for fix in report.fixture_results:
        lines.append(f"- `{fix.fixture_id}`: agreement = `{fix.overall_agreement}`")
    lines.append(f"\n## Guardrail Compliance\n{report.scientific_disclaimer}\n")
    return "\n".join(lines)
