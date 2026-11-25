"""Deterministic schema tests for batch3_source_registry.yaml.

No network. No optional dependencies. Finite JSON only.
"""

import json
import pathlib

import pytest
import yaml

REGISTRY = (
    pathlib.Path(__file__).resolve().parents[2]
    / "configs"
    / "research"
    / "batch3_source_registry.yaml"
)

REQUIRED_SOURCE_KEYS = {
    "id",
    "name",
    "url",
    "authors",
    "release_date",
    "version_tag",
    "version_source_url",
    "license",
    "license_source_url",
    "license_scope",
    "risk_assessment",
    "evidence_class",
    "classification",
    "classification_kind",
    "adapter_boundary",
    "recommendation_notes",
}

ALLOWED_CLASSIFICATIONS = {"INTEGRATE", "EMULATE", "REFERENCE_ONLY", "REJECT"}

# Exact upstream release and license artifacts reviewed for this registry.
# A changed source, tag, release date, or SPDX label must fail offline tests.
EXPECTED_SOURCE_FACTS = {
    "mne-python": (
        "https://github.com/mne-tools/mne-python",
        "v1.13.2",
        "2026-09-11",
        "https://github.com/mne-tools/mne-python/releases/tag/v1.13.2",
        "BSD-3-Clause",
        "https://github.com/mne-tools/mne-python/blob/v1.13.2/LICENSE.txt",
    ),
    "mne-bids": (
        "https://github.com/mne-tools/mne-bids",
        "v0.20.0",
        "2026-09-29",
        "https://github.com/mne-tools/mne-bids/releases/tag/v0.20.0",
        "BSD-3-Clause",
        "https://github.com/mne-tools/mne-bids/blob/v0.20.0/LICENSE",
    ),
    "pybids": (
        "https://github.com/bids-standard/pybids",
        "0.22.0",
        "2026-03-12",
        "https://github.com/bids-standard/pybids/releases/tag/0.22.0",
        "MIT",
        "https://github.com/bids-standard/pybids/blob/0.22.0/LICENSE",
    ),
    "bids-validator": (
        "https://github.com/bids-standard/bids-validator",
        "3.0.2",
        "2026-09-18",
        "https://github.com/bids-standard/bids-validator/releases/tag/3.0.2",
        "MIT",
        "https://github.com/bids-standard/bids-validator/blob/3.0.2/LICENSE",
    ),
    "dandi-cli": (
        "https://github.com/dandi/dandi-cli",
        "0.75.0",
        "2026-04-29",
        "https://github.com/dandi/dandi-cli/releases/tag/0.75.0",
        "Apache-2.0",
        "https://github.com/dandi/dandi-cli/blob/0.75.0/LICENSE",
    ),
    "pynwb": (
        "https://github.com/NeurodataWithoutBorders/pynwb",
        "4.2.0",
        "2026-09-02",
        "https://github.com/NeurodataWithoutBorders/pynwb/releases/tag/4.2.0",
        "BSD-3-Clause-style + custom Enhancement clause",
        "https://github.com/NeurodataWithoutBorders/pynwb/blob/4.2.0/license.txt",
    ),
    "nilearn": (
        "https://github.com/nilearn/nilearn",
        "0.14.1",
        "2026-09-04",
        "https://github.com/nilearn/nilearn/releases/tag/0.14.1",
        "BSD-3-Clause",
        "https://github.com/nilearn/nilearn/blob/0.14.1/LICENSE",
    ),
    "mne-connectivity": (
        "https://github.com/mne-tools/mne-connectivity",
        "v0.9.0",
        "2026-08-24",
        "https://github.com/mne-tools/mne-connectivity/releases/tag/v0.9.0",
        "BSD-3-Clause",
        "https://github.com/mne-tools/mne-connectivity/blob/v0.9.0/LICENSE",
    ),
    "gudhi": (
        "https://github.com/GUDHI/gudhi-devel",
        "tags/gudhi-release-3.13.0",
        "2026-07-02",
        "https://github.com/GUDHI/gudhi-devel/releases/tag/tags%2Fgudhi-release-3.13.0",
        "MIT",
        "https://github.com/GUDHI/gudhi-devel/blob/tags/gudhi-release-3.13.0/LICENSE",
    ),
    "ripser-py": (
        "https://github.com/scikit-tda/ripser.py",
        "v0.6.15",
        "2026-05-27",
        "https://github.com/scikit-tda/ripser.py/releases/tag/v0.6.15",
        "MIT",
        "https://github.com/scikit-tda/ripser.py/blob/v0.6.15/LICENSE.txt",
    ),
    "datalad": (
        "https://github.com/datalad/datalad",
        "1.7.1",
        "2026-10-06",
        "https://github.com/datalad/datalad/releases/tag/1.7.1",
        "MIT",
        "https://github.com/datalad/datalad/blob/1.7.1/COPYING",
    ),
    "openlineage": (
        "https://github.com/OpenLineage/OpenLineage",
        "1.54.0",
        "2026-10-13",
        "https://github.com/openlineage/OpenLineage/releases/tag/1.54.0",
        "Apache-2.0",
        "https://github.com/openlineage/OpenLineage/blob/1.54.0/LICENSE",
    ),
    "the-virtual-brain": (
        "https://github.com/the-virtual-brain/tvb-root",
        "2.10.0",
        "2025-07-25",
        "https://github.com/the-virtual-brain/tvb-root/releases/tag/2.10.0",
        "GPL-3.0-or-later",
        "https://github.com/the-virtual-brain/tvb-root/blob/2.10.0/LICENSE",
    ),
    "neurolib": (
        "https://github.com/neurolib-dev/neurolib",
        "v0.7.0",
        "2024-04-02",
        "https://github.com/neurolib-dev/neurolib/releases/tag/v0.7.0",
        "MIT",
        "https://github.com/neurolib-dev/neurolib/blob/v0.7.0/LICENSE",
    ),
    "rea": (
        "https://github.com/morluto/rea",
        "rea-agents-6.5.0",
        "2026-10-14",
        "https://github.com/morluto/rea/releases/tag/rea-agents-6.5.0",
        "MIT",
        "https://github.com/morluto/rea/blob/rea-agents-6.5.0/LICENSE",
    ),
    "langgraph": (
        "https://github.com/langchain-ai/langgraph",
        "1.2.15",
        "2026-10-12",
        "https://github.com/langchain-ai/langgraph/releases/tag/1.2.15",
        "MIT",
        "https://github.com/langchain-ai/langgraph/blob/1.2.15/LICENSE",
    ),
}


def test_registry_exists_and_parses():
    assert REGISTRY.is_file()
    with REGISTRY.open() as f:
        data = yaml.safe_load(f)
    assert data["schema_version"] == "2.0"
    assert data["access_date"] == "2026-10-23"
    assert data["reviewed_pr_head"] == "573d1480c14a6f9b0694e501797d4a7455cb7656"
    assert data["live_main_at_review"] == "d78f54128b6fd60c30665c9e9cff307056dbdd82"
    assert len(data["sources"]) == len(EXPECTED_SOURCE_FACTS)


def test_every_source_has_required_fields_and_clear_recommendation_scope():
    with REGISTRY.open() as f:
        data = yaml.safe_load(f)
    sources = data["sources"]
    ids = [source["id"] for source in sources]
    assert len(ids) == len(set(ids))
    assert set(ids) == set(EXPECTED_SOURCE_FACTS)
    for source in sources:
        missing = REQUIRED_SOURCE_KEYS - set(source)
        assert not missing, f"{source.get('id')} missing {missing}"
        assert source["classification"] in ALLOWED_CLASSIFICATIONS
        assert source["classification_kind"] == "compatibility_recommendation"
        assert source["authors"] == "not assessed"
        assert "legal compatibility" in source["license_scope"].lower()
        assert set(source["risk_assessment"]) == {
            "security",
            "known_vulnerabilities",
            "maintenance",
            "dependencies",
            "data_access",
        }
        assert set(source["risk_assessment"].values()) == {"not assessed"}
        assert source["url"].startswith("https://")
        json.dumps(source, allow_nan=False)


@pytest.mark.parametrize(("source_id", "expected"), EXPECTED_SOURCE_FACTS.items())
def test_source_version_release_and_license_match_reviewed_upstream_artifact(source_id, expected):
    with REGISTRY.open() as f:
        data = yaml.safe_load(f)
    source = next(item for item in data["sources"] if item["id"] == source_id)
    actual = (
        source["url"],
        source["version_tag"],
        source["release_date"],
        source["version_source_url"],
        source["license"],
        source["license_source_url"],
    )
    assert actual == expected, f"{source_id} source, release, or license evidence drifted"


def test_gudhi_license_scope_contains_gpl_and_project_legal_review():
    with REGISTRY.open() as f:
        data = yaml.safe_load(f)
    gudhi = next(source for source in data["sources"] if source["id"] == "gudhi")
    scope = gudhi["license_scope"]
    assert "GPL" in scope, scope
    assert "project legal review" in scope, scope


def test_unresolved_status_does_not_infer_security_or_legal_conclusions():
    """An unresolved license review stays unresolved.

    It must not be rewritten into a legal-compatibility verdict or a
    security/maintenance finding.
    """
    with REGISTRY.open() as f:
        data = yaml.safe_load(f)
    unresolved = [
        source
        for source in data["sources"]
        if "unresolved" in json.dumps(source).lower()
    ]
    assert [source["id"] for source in unresolved] == ["gudhi"], [source["id"] for source in unresolved]
    gudhi = unresolved[0]
    assert gudhi["license"] == "MIT"
    assert "https://gudhi.inria.fr/licensing/" in gudhi["license_scope"]
    assert set(gudhi["risk_assessment"].values()) == {"not assessed"}
    assert gudhi["classification_kind"] == "compatibility_recommendation"
    blob = json.dumps(gudhi).lower()
    for phrase in ("legally compatible", "no known cve", "low risk", "actively maintained"):
        assert phrase not in blob


def test_license_metadata_does_not_infer_security_maintenance_or_legal_conclusions():
    with REGISTRY.open() as f:
        data = yaml.safe_load(f)
    banned = (
        "low risk",
        "no known cve",
        "no known vulnerabilities",
        "actively maintained",
        "healthy",
        "legally compatible",
        "license compatible",
        "dependency-safe",
        "no cves",
    )
    for source in data["sources"]:
        assert set(source["risk_assessment"].values()) == {"not assessed"}
        blob = json.dumps(
            {
                "license": source["license"],
                "license_scope": source["license_scope"],
                "risk_assessment": source["risk_assessment"],
                "recommendation_notes": source["recommendation_notes"],
            }
        ).lower()
        for phrase in banned:
            assert phrase not in blob, f"{source['id']} infers {phrase!r} from license metadata"
        assert source["version_source_url"].startswith("https://")
        assert source["version_tag"] in source["version_source_url"] or (
            source["version_tag"].replace("/", "%2F") in source["version_source_url"]
        )


def test_version_tags_are_exact_pins():
    with REGISTRY.open() as f:
        data = yaml.safe_load(f)
    for source in data["sources"]:
        tag = source["version_tag"]
        assert not tag.endswith(".x"), tag
        assert ".x" not in tag.split("/")[-1], tag
        assert tag != "latest"


def test_pynwb_license_descriptor_includes_custom_enhancement_clause():
    with REGISTRY.open() as f:
        data = yaml.safe_load(f)
    pynwb = next(source for source in data["sources"] if source["id"] == "pynwb")
    assert pynwb["license"] == "BSD-3-Clause-style + custom Enhancement clause"
    assert "enhancement clause" in pynwb["license_scope"].lower()


def test_literature_topics_are_unassessed_recommendations_not_findings():
    with REGISTRY.open() as f:
        data = yaml.safe_load(f)
    text = json.dumps(data)
    assert "scientific_pass" not in text.lower()
    topics = data["literature_topics"]
    assert topics
    assert all(topic["status"] == "not assessed" for topic in topics)
    assert all(topic["classification"] == "REFERENCE_ONLY" for topic in topics)


def test_reject_and_integrate_labels_remain_recommendations():
    with REGISTRY.open() as f:
        data = yaml.safe_load(f)
    sources = {source["id"]: source for source in data["sources"]}
    assert sources["the-virtual-brain"]["classification"] == "REJECT"
    assert sources["the-virtual-brain"]["license"] == "GPL-3.0-or-later"
    assert sources["mne-python"]["classification"] == "INTEGRATE"
    assert "capability probe" in sources["mne-python"]["adapter_boundary"]
    assert sources["rea"]["classification"] == "REJECT"
