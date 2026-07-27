"""Load the shared root result adapter without colliding with app-local tools."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
_ADAPTER_PATH = _REPOSITORY_ROOT / "tools" / "command_center" / "real_results_adapter.py"
_MODULE_NAME = "neurotopology_shared_real_results_adapter"


def _adapter():
    module = sys.modules.get(_MODULE_NAME)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Command Center adapter at {_ADAPTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def build_real_results():
    return _adapter().build_real_results()


def build_visualization_payload():
    return _adapter().build_visualization_payload()


def build_command_center_registry():
    return _adapter().build_command_center_registry()


def get_downloadable_artifact(artifact_id: str):
    return _adapter().get_downloadable_artifact(artifact_id)
