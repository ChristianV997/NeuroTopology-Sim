from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def clean_plan_dict() -> dict[str, Any]:
    """The base clean/complete plan (requirement fixture: clean complete
    plan). Individual scenario tests derive a variant by copying this
    dict and changing only the field(s) relevant to that scenario, so
    every failure scenario is isolated to exactly the dimension it
    targets."""
    return json.loads((FIXTURES_DIR / "clean_complete_plan.json").read_text())


def variant(base: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    data = copy.deepcopy(base)
    data.update(overrides)
    return data
