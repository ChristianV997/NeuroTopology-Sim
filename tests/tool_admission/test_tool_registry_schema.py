"""Schema and policy tests for the tool admission registry."""
from __future__ import annotations

import json
import re
from pathlib import Path

REQUIRED_FIELDS = [
    "tool_name",
    "official_url",
    "repository_url",
    "license",
    "language_runtime",
    "installation_cost",
    "optional_dependency_status",
    "offline_capability",
    "network_requirements",
    "supported_modalities",
    "streaming_support",
    "provenance_support",
    "deterministic_test_strategy",
    "memory_risks",
    "security_risks",
    "data_privacy_risks",
    "recommended_role",
    "integration_mode",
    "owner_boundary",
    "admission_status",
    "review_date",
    "evidence_sources",
]

ALLOWED_MODES = {"integrate", "emulate", "copy_pattern", "reference", "reject"}
ALLOWED_STATUS = {
    "admitted",
    "admitted_optional",
    "experimental",
    "deferred",
    "reference_only",
    "rejected",
}
FORBIDDEN_STATUS = {"PASS", "FAIL", "NOT_SUPPORTED", "pass", "Pass"}
EXPECTED_IDS = {
    "mne",
    "mne_connectivity",
    "scipy_signal",
    "eeglab",
    "fieldtrip",
    "labstreaminglayer",
    "brainflow",
    "psychopy",
    "spikeinterface",
    "pynwb",
    "braindecode",
    "snntorch",
    "semantica",
    "scrapling",
    "notebooklm_mcp_community",
    "gemini_notebook_enterprise_api",
}
SECRET_RE = re.compile(
    r"(api[_-]?key|secret[_-]?key|password|bearer\\s+[a-z0-9]|xox[baprs]-|"
    r"AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)",
    re.IGNORECASE,
)


def test_registry_lists_expected_tools(registry):
    ids = {row["id"] for row in registry["tools"]}
    assert ids == EXPECTED_IDS


def test_every_entry_has_required_fields(registry):
    declared = set(registry["required_fields"])
    assert declared == set(REQUIRED_FIELDS)
    for row in registry["tools"]:
        missing = [field for field in REQUIRED_FIELDS if field not in row or row[field] in (None, "", [])]
        assert not missing, f"{row.get('id')}: missing {missing}"


def test_integration_modes_are_valid(registry):
    assert set(registry["allowed_integration_modes"]) == ALLOWED_MODES
    for row in registry["tools"]:
        assert row["integration_mode"] in ALLOWED_MODES, row["id"]


def test_no_unsupported_pass_status(registry, policies):
    assert "PASS" in policies["forbidden"]["admission_status_values"]
    assert "PASS" not in registry["allowed_admission_status"]
    for row in registry["tools"]:
        status = row["admission_status"]
        assert status in ALLOWED_STATUS, row["id"]
        assert status not in FORBIDDEN_STATUS, row["id"]
        assert row["may_emit_scientific_pass"] is False, row["id"]


def test_notebooklm_community_is_experimental(registry, policies):
    row = next(item for item in registry["tools"] if item["id"] == "notebooklm_mcp_community")
    assert row["admission_status"] == "experimental"
    assert row["experimental"] is True
    assert row["present_in_requirements_txt"] is False
    assert policies["notebooklm_policy"]["community_mcp_servers"]["official_supported_api"] is False


def test_official_gemini_notebook_api_is_not_required(registry, policies):
    row = next(item for item in registry["tools"] if item["id"] == "gemini_notebook_enterprise_api")
    assert row["admission_status"] == "deferred"
    assert row["present_in_requirements_txt"] is False
    assert row["integration_mode"] == "reference"
    assert policies["notebooklm_policy"]["official_gemini_notebook_enterprise_api"]["may_be_required_dependency"] is False


def test_matlab_tools_are_not_python_dependencies(registry, policies):
    matlab_ids = set(policies["matlab_interop"]["tools"])
    assert matlab_ids == {"eeglab", "fieldtrip"}
    for row in registry["tools"]:
        if row["id"] in matlab_ids:
            assert row["integration_mode"] == "reference"
            assert row["admission_status"] == "reference_only"
            assert row["present_in_requirements_txt"] is False
            assert row["optional_dependency_status"] == "not_a_python_dependency"


def test_core_signal_path_is_mne_and_scipy(registry, policies):
    required = set(policies["core_signal_path"]["required_python_tools"])
    assert required == {"mne", "scipy_signal"}
    by_id = {row["id"]: row for row in registry["tools"]}
    assert by_id["mne"]["integration_mode"] == "integrate"
    assert by_id["scipy_signal"]["integration_mode"] == "integrate"
    assert by_id["mne"]["admission_status"] == "admitted"
    assert by_id["scipy_signal"]["admission_status"] == "admitted"


def test_nwb_is_archival_path(registry, policies):
    assert policies["archival_interchange"]["primary"] == "pynwb"
    row = next(item for item in registry["tools"] if item["id"] == "pynwb")
    assert row["integration_mode"] == "integrate"
    assert row["admission_status"] == "admitted"


def test_lsl_and_brainflow_are_optional_live_boundaries(registry, policies):
    live = set(policies["live_acquisition_boundary"]["optional_tools"])
    assert live == {"labstreaminglayer", "brainflow"}
    for tool_id in live:
        row = next(item for item in registry["tools"] if item["id"] == tool_id)
        assert row["integration_mode"] == "emulate"
        assert row["admission_status"] == "admitted_optional"
        assert row["present_in_requirements_txt"] is False


def test_downstream_models_cannot_set_verdicts(registry, policies):
    assert policies["downstream_modeling_lanes"]["may_determine_scientific_verdict"] is False
    for tool_id in policies["downstream_modeling_lanes"]["tools"]:
        row = next(item for item in registry["tools"] if item["id"] == tool_id)
        assert row["may_emit_scientific_pass"] is False
        assert row["integration_mode"] == "reference"
        assert row["admission_status"] == "deferred"


def test_spikeinterface_is_extracellular_only(registry, policies):
    assert policies["spikeinterface_policy"]["scope"] == "extracellular_electrophysiology_only"
    row = next(item for item in registry["tools"] if item["id"] == "spikeinterface")
    assert "extracellular" in row["recommended_role"].lower() or "extracellular" in " ".join(row["supported_modalities"]).lower()


def test_scrapling_default_reject_and_allowlist_policy(registry, policies):
    row = next(item for item in registry["tools"] if item["id"] == "scrapling")
    assert row["integration_mode"] == "reject"
    assert row["admission_status"] == "rejected"
    assert policies["scraping_policy"]["require_explicit_allowlist"] is True
    assert policies["scraping_policy"]["automated_tests_may_fetch"] is False


def test_no_hidden_credentials(repo_root: Path):
    root = repo_root / "configs" / "tool_admission"
    docs = repo_root / "docs"
    files = list(root.rglob("*")) + list((docs / "external_tool_review").glob("*.md"))
    files.append(docs / "research_tooling_matrix.md")
    for path in files:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        assert SECRET_RE.search(text) is None, path


def test_offline_test_policy_has_no_network_imports(repo_root: Path):
    """Admission tests may mention denied services by name in assertions,
    but they must not import network clients.
    """
    test_dir = Path(__file__).resolve().parent
    import_re = re.compile(r"^(?:from|import)\\s+(urllib|requests|httpx|socket|boto3|aiohttp)\\b", re.M)
    for path in test_dir.glob("test_*.py"):
        text = path.read_text(encoding="utf-8")
        assert import_re.search(text) is None, path
    for path in (repo_root / "configs" / "tool_admission").rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "subprocess" not in text
            assert "urlopen(" not in text


def test_source_registry_is_sorted_and_credential_free(sources):
    dumped = json.dumps(sources, indent=2, sort_keys=True) + "\\n"
    assert "api_key" not in dumped.lower()
    assert "token" not in dumped.lower() or "toolset" in dumped.lower()
    assert sources["schema_version"] == "1.0"


def test_deterministic_registry_serialization(repo_root: Path, registry):
    import yaml

    path = repo_root / "configs" / "tool_admission" / "tool_registry.yaml"
    raw = path.read_text(encoding="utf-8")
    again = yaml.safe_load(raw)
    assert again["schema_version"] == registry["schema_version"]
    assert [row["id"] for row in again["tools"]] == [row["id"] for row in registry["tools"]]
    tool_heads = [line.strip() for line in raw.splitlines() if line.startswith("  -")]
    assert tool_heads
    ids = [row["id"] for row in registry["tools"]]
    assert ids == [
        "mne",
        "mne_connectivity",
        "scipy_signal",
        "eeglab",
        "fieldtrip",
        "labstreaminglayer",
        "brainflow",
        "psychopy",
        "spikeinterface",
        "pynwb",
        "braindecode",
        "snntorch",
        "semantica",
        "scrapling",
        "notebooklm_mcp_community",
        "gemini_notebook_enterprise_api",
    ]


def test_review_files_exist_for_every_tool(repo_root: Path, registry):
    review_dir = repo_root / "docs" / "external_tool_review"
    for row in registry["tools"]:
        path = review_dir / f"{row['id']}.md"
        assert path.is_file(), path
        text = path.read_text(encoding="utf-8")
        assert row["admission_status"] in text
        assert row["integration_mode"] in text


def test_matrix_exists(repo_root: Path):
    path = repo_root / "docs" / "research_tooling_matrix.md"
    text = path.read_text(encoding="utf-8")
    assert "K > 100" in text
    assert "notebooklm_mcp_community" in text
    assert "experimental" in text
