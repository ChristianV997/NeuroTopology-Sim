"""
Tests for DS005620 system index documentation.

Validates that all required doc files exist and contain the expected content
markers. Uses only pathlib and stdlib — no network, no real data, no runtime.
"""

from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"

SYSTEM_INDEX = DOCS / "ds005620_system_index.md"
COMMAND_SURFACE = DOCS / "ds005620_command_surface.md"
ARTIFACT_LIFECYCLE = DOCS / "ds005620_artifact_lifecycle.md"
AGENT_MAP = DOCS / "ds005620_agent_coordination_map.md"

# ---------------------------------------------------------------------------
# 1–4: Existence checks
# ---------------------------------------------------------------------------


def test_system_index_exists():
    assert SYSTEM_INDEX.exists(), f"Missing: {SYSTEM_INDEX}"


def test_command_surface_exists():
    assert COMMAND_SURFACE.exists(), f"Missing: {COMMAND_SURFACE}"


def test_artifact_lifecycle_exists():
    assert ARTIFACT_LIFECYCLE.exists(), f"Missing: {ARTIFACT_LIFECYCLE}"


def test_agent_coordination_map_exists():
    assert AGENT_MAP.exists(), f"Missing: {AGENT_MAP}"


# ---------------------------------------------------------------------------
# 5: System index stage mentions
# ---------------------------------------------------------------------------

REQUIRED_STAGES = [
    "P17.0",
    "P17.1",
    "P18.1",
    "P18.2",
    "P18.3",
    "P19.0",
    "P19.1",
    "P19.2",
    "P9",
    "P10",
    "P11",
]


def test_system_index_mentions_all_stages():
    text = SYSTEM_INDEX.read_text()
    for stage in REQUIRED_STAGES:
        assert stage in text, f"System index missing stage: {stage}"


# ---------------------------------------------------------------------------
# 6–8: Command surface keyword checks
# ---------------------------------------------------------------------------


def test_command_surface_mentions_e2e_ci():
    text = COMMAND_SURFACE.read_text()
    assert "ds005620-e2e-ci" in text


def test_command_surface_mentions_real_execution_gate():
    text = COMMAND_SURFACE.read_text()
    assert "ds005620-real-execution-gate" in text


def test_command_surface_mentions_generated_artifact_check():
    text = COMMAND_SURFACE.read_text()
    assert "ds005620-generated-artifact-check" in text


# ---------------------------------------------------------------------------
# 9: Command surface warns not to auto-run --execute --peer-reviewed-contract-confirmed
# ---------------------------------------------------------------------------


def test_command_surface_warns_no_auto_execute():
    text = COMMAND_SURFACE.read_text()
    # Both the flag names and a "must not" / "never" warning must appear
    assert "--execute" in text, "Command surface missing --execute flag reference"
    assert "--peer-reviewed-contract-confirmed" in text, (
        "Command surface missing --peer-reviewed-contract-confirmed flag reference"
    )
    lower = text.lower()
    has_warning = "must not" in lower or "never" in lower or "do not automate" in lower
    assert has_warning, (
        "Command surface does not contain a warning against automating "
        "--execute --peer-reviewed-contract-confirmed"
    )


# ---------------------------------------------------------------------------
# 10–11: Artifact lifecycle keyword checks
# ---------------------------------------------------------------------------


def test_artifact_lifecycle_mentions_ontology_evaluation():
    text = ARTIFACT_LIFECYCLE.read_text()
    assert "ontology evaluation" in text.lower()


def test_artifact_lifecycle_mentions_evidence_packet():
    text = ARTIFACT_LIFECYCLE.read_text()
    assert "evidence packet" in text.lower()


# ---------------------------------------------------------------------------
# 12: Artifact lifecycle states mock E2E is not real empirical evidence
# ---------------------------------------------------------------------------


def test_artifact_lifecycle_mock_e2e_not_real_evidence():
    text = ARTIFACT_LIFECYCLE.read_text()
    lower = text.lower()
    # Must contain a statement that mock E2E is not real empirical evidence
    assert "mock e2e" in lower, "Artifact lifecycle missing 'mock E2E' reference"
    has_not_real = (
        "not real empirical" in lower
        or "mock e2e is not" in lower
        or "do not constitute" in lower
        or "does not constitute" in lower
    )
    assert has_not_real, (
        "Artifact lifecycle does not state that mock E2E is not real empirical evidence"
    )


# ---------------------------------------------------------------------------
# 13–14: Agent coordination map checks
# ---------------------------------------------------------------------------


def test_agent_map_mentions_all_agents():
    text = AGENT_MAP.read_text()
    for agent in ("Claude", "Codex", "Copilot"):
        assert agent in text, f"Agent coordination map missing agent: {agent}"


def test_agent_map_mentions_close_superseded_prs():
    text = AGENT_MAP.read_text()
    lower = text.lower()
    assert "superseded" in lower, (
        "Agent coordination map does not mention closing superseded PRs"
    )


# ---------------------------------------------------------------------------
# 15: Unsafe phrase scan (narrow, targeted)
# ---------------------------------------------------------------------------

# Phrases that must never appear as assertions in these docs.
# Allowed only if the containing line or section header contains a guardrail marker.
UNSAFE_PHRASES = [
    "topology proves",
    "eeg proves",
    "q equals",
    "ontology solved",
    "consciousness proven",
]

# Section headings that permit unsafe phrases as *examples of what is forbidden*.
# The dots in must.not / do.not.use intentionally match any whitespace variant
# (e.g. "must not", "must-not"), not just literal periods.
GUARDRAIL_HEADING_RE = re.compile(
    r"(guardrail|forbidden|unsafe|must.not|do.not.use)",
    re.IGNORECASE,
)


def _find_preceding_section_heading(lines: list[str], line_idx: int) -> str:
    """Walk backwards from line_idx to find the most recent heading line."""
    for i in range(line_idx - 1, -1, -1):
        stripped = lines[i].strip()
        if stripped.startswith("#"):
            return stripped
    return ""


def _check_doc_for_unsafe_phrases(path: Path) -> list[str]:
    text = path.read_text()
    lines = text.splitlines()
    violations = []
    for idx, line in enumerate(lines):
        lower_line = line.lower()
        for phrase in UNSAFE_PHRASES:
            if phrase in lower_line:
                heading = _find_preceding_section_heading(lines, idx)
                if GUARDRAIL_HEADING_RE.search(heading):
                    # Allowed: it's an example under a guardrail section
                    continue
                violations.append(
                    f"{path.name}:{idx + 1}: unsafe phrase '{phrase}' found: {line.strip()!r}"
                )
    return violations


def test_docs_no_unsafe_direct_phrases():
    """All four docs must not contain unsafe assertion phrases outside guardrail sections."""
    all_violations: list[str] = []
    for doc in (SYSTEM_INDEX, COMMAND_SURFACE, ARTIFACT_LIFECYCLE, AGENT_MAP):
        all_violations.extend(_check_doc_for_unsafe_phrases(doc))
    assert not all_violations, (
        "Unsafe phrases found in docs:\n" + "\n".join(all_violations)
    )
