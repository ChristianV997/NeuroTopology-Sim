"""Generated in-memory synthetic inputs; tests do not read repository data fixtures."""
from __future__ import annotations

import pytest


@pytest.fixture
def synthetic_tsv() -> str:
    return "participant_id\tage\nsub-01\t20\nsub-02\t22\nsub-03\t25\n"


@pytest.fixture
def synthetic_readme() -> str:
    return "Synthetic test metadata.\nLicense: CC-BY-4.0\n"


@pytest.fixture
def synthetic_nemar() -> dict:
    return {"license": "CC0-1.0", "name": "synthetic-test-record"}


@pytest.fixture
def synthetic_listing() -> list[str]:
    return [
        "participants.tsv",
        "README",
        "sub-01/eeg/sub-01_task-rest_eeg.edf",
        "sub-01/eeg/sub-01_task-stroop_eeg.edf",
        "sub-02/eeg/sub-02_task-rest_eeg.edf",
        "sub-04/eeg/sub-04_task-rest_eeg.edf",
        "sub-01/eeg/sub-01_task-rest_eeg.edf.bak",
        "../escape/sub-01_task-rest_eeg.edf",
    ]


@pytest.fixture
def synthetic_dataset_description() -> dict:
    return {"License": "CC-BY-4.0", "Name": "synthetic-test-dataset"}


@pytest.fixture
def synthetic_catalog() -> dict:
    return {"license": "CC-BY-SA-4.0", "name": "synthetic-test-catalog-entry"}


@pytest.fixture
def synthetic_analysis_record() -> dict:
    return {"analyzed_n": 2, "excluded_subjects": ["sub-03"]}
