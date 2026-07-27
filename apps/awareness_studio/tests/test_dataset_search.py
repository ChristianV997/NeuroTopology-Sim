"""Offline tests for the candidate-only EEGDash tool."""
from __future__ import annotations

import sys
import types

from awareness_studio.tool_router import DatasetSearchToolRouter, has_tool_trigger, tool_names_for_question
from awareness_studio.tools.dataset_search import search_dataset_candidates


class _Frame:
    def to_dict(self, orient: str):
        assert orient == "records"
        return [
            {"dataset_id": "ds-demo", "name": "Propofol anesthesia EEG", "modality": "eeg", "task": "sedation", "n_subjects": 21, "source": "openneuro"},
            {"dataset_id": "ds-other", "name": "Visual EEG", "modality": "eeg", "task": "vision", "n_subjects": 4, "source": "openneuro"},
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


def test_dataset_router_uses_candidate_tool(monkeypatch):
    monkeypatch.setitem(sys.modules, "eegdash", types.SimpleNamespace(EEGDash=_EEGDash))
    result = DatasetSearchToolRouter().call_tool("eegdash_dataset_search", {"query": "anesthesia", "max_results": 3})
    assert result.success is True
    assert result.data[0]["accession"] == "ds-demo"


def test_dataset_questions_trigger_tool_routing():
    assert has_tool_trigger("Find an OpenNeuro anesthesia dataset")
    assert tool_names_for_question("Find an OpenNeuro anesthesia dataset") == {"eegdash_dataset_search"}
