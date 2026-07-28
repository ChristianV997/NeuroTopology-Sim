"""Offline tests for the candidate-only EEGDash tool."""
from __future__ import annotations

import sys
import types

from awareness_studio.tool_router import DatasetSearchToolRouter, has_tool_trigger, tool_names_for_question
from awareness_studio.tools.dataset_search import search_dataset_candidates


class _Frame:
    """Shaped like the real `eegdash.schemas.Dataset` TypedDict (verified
    against installed eegdash==0.8.4, see dataset_search.py's module
    docstring): `tasks` plural, `recording_modality`, nested
    `demographics.subjects_count` -- not the guessed `task`/`modality`/
    `n_subjects` the module used to read before that field-name bug was
    found and fixed."""
    def to_dict(self, orient: str):
        assert orient == "records"
        return [
            {
                "dataset_id": "ds-demo", "name": "Propofol anesthesia EEG",
                "recording_modality": ["eeg"], "tasks": ["sedation", "rest"],
                "demographics": {"subjects_count": 21}, "source": "openneuro",
                "study_domain": "anesthesia",
            },
            {
                "dataset_id": "ds-other", "name": "Visual EEG",
                "recording_modality": ["eeg"], "tasks": ["vision"],
                "demographics": {"subjects_count": 4}, "source": "openneuro",
            },
        ]


class _EEGDash:
    def search_datasets(self, **kwargs):
        assert kwargs == {"modality": "eeg", "limit": 100}
        return _Frame()


def test_dataset_search_returns_candidates_only(monkeypatch):
    monkeypatch.setitem(sys.modules, "eegdash", types.SimpleNamespace(EEGDash=_EEGDash))
    candidates = search_dataset_candidates("propofol anesthesia consciousness")
    assert [item["accession"] for item in candidates] == ["ds-demo"]
    assert candidates[0]["candidate_to_verify"] is True
    assert candidates[0]["execution_allowed"] is False
    assert candidates[0]["bids_compliance_flag"] == "candidate_to_verify"


def test_dataset_search_reads_real_nested_and_plural_fields(monkeypatch):
    """Regression test for the field-name bug: the module used to read
    `row.get("task")` (singular), `row.get("n_subjects")` (top-level), and
    `row.get("modality")` -- none of which exist on the real
    `eegdash.schemas.Dataset` shape (`tasks` plural,
    `demographics.subjects_count` nested, `recording_modality`). Before the
    fix, this fixture's candidate would have participant_count=None,
    modality='eeg' (fallback only), task=''."""
    monkeypatch.setitem(sys.modules, "eegdash", types.SimpleNamespace(EEGDash=_EEGDash))
    candidates = search_dataset_candidates("propofol anesthesia consciousness")
    demo = candidates[0]
    assert demo["participant_count"] == 21  # from demographics.subjects_count, not a missing n_subjects
    assert demo["modality"] == ["eeg"]  # from recording_modality, not a missing modality
    assert demo["task"] == ["sedation", "rest"]  # from tasks (plural), not a missing task


def test_dataset_search_matches_on_study_domain_not_fictional_clinical_group(monkeypatch):
    """Regression test: `clinical_group` was never a real field on either
    confirmed eegdash response shape (DatasetModel or Dataset). A dataset
    whose ONLY match is through `study_domain` (or `clinical.purpose`/
    `tags.pathology`) must still be found -- the old code's
    `row.get("clinical_group")` would always return None and silently drop
    this kind of match."""
    class _StudyDomainOnlyFrame:
        def to_dict(self, orient: str):
            return [{
                "dataset_id": "ds-domain-only", "name": "Unlabelled resting EEG",
                "recording_modality": ["eeg"], "tasks": ["rest"],
                "demographics": {"subjects_count": 10}, "source": "openneuro",
                "study_domain": "anesthesia",  # the only place "anesthesia" appears
            }]

    class _EEGDashDomainOnly:
        def search_datasets(self, **kwargs):
            return _StudyDomainOnlyFrame()

    monkeypatch.setitem(sys.modules, "eegdash", types.SimpleNamespace(EEGDash=_EEGDashDomainOnly))
    candidates = search_dataset_candidates("anesthesia")
    assert [c["accession"] for c in candidates] == ["ds-domain-only"]


def test_dataset_router_uses_candidate_tool(monkeypatch):
    monkeypatch.setitem(sys.modules, "eegdash", types.SimpleNamespace(EEGDash=_EEGDash))
    result = DatasetSearchToolRouter().call_tool("eegdash_dataset_search", {"query": "anesthesia", "max_results": 3})
    assert result.success is True
    assert result.data[0]["accession"] == "ds-demo"


def test_dataset_questions_trigger_tool_routing():
    assert has_tool_trigger("Find an OpenNeuro anesthesia dataset")
    assert tool_names_for_question("Find an OpenNeuro anesthesia dataset") == {"eegdash_dataset_search"}
