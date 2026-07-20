"""Code-executed onboarding registry for the real-signal EEG pipeline.

This is the runtime-loaded counterpart to configs/btc_icft/dataset_onboarding_registry.json.
It parses that declarative file into typed `DatasetConfig` objects that drive the
generic streaming processor and the generic Level-M / Level-T CLIs, so onboarding a
new OpenNeuro EEG dataset (of the "simple task-to-state map, one window per fixed
interval" shape) requires ONLY a new JSON entry -- zero new Python files.

Contrast with configs/btc_icft/*_real.yaml, which are documentation-only (nothing
parses them). THIS registry is real config: `get_dataset_config(dataset_id)` returns a
typed object the pipeline executes against.

Label policy (no_label_inference): `task_to_state` is authored by a human from
confirmed real BIDS task labels (discover them structurally via
tools.discover_openneuro_tasks). Semantic state labels are never inferred from task
strings by code -- structural discovery is automated, the mapping is not.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = _REPO_ROOT / "configs" / "btc_icft" / "dataset_onboarding_registry.json"


@dataclass(frozen=True)
class Contrast:
    """A single 2-class Level-M contrast: y=0 for `class0`, y=1 for `class1`,
    read from the window row's `label_field` (state_label / behavior_label /
    report_label)."""

    name: str
    label_field: str
    class0: str
    class1: str


@dataclass(frozen=True)
class DatasetConfig:
    dataset_id: str
    title: str
    task_to_state: dict[str, str]
    contrasts: tuple[Contrast, ...]
    default_task: str
    window_seconds: float
    max_windows_per_file: int
    max_channels: int
    # Level-M report.md text fragments (kept in config so each dataset's currently
    # published report text is reproduced byte-for-byte by the generic writer).
    report_input_heading: str
    report_input_source: str
    report_extra_window_lines: tuple[str, ...]
    report_extra_next_step_lines: tuple[str, ...]
    format_note: str

    def contrast(self, name: str) -> Contrast:
        for c in self.contrasts:
            if c.name == name:
                return c
        raise ValueError(f"Unknown task: {name}")


_VALID_LABEL_FIELDS = {"state_label", "behavior_label", "report_label"}


def _parse_dataset(raw: dict) -> DatasetConfig:
    contrasts = tuple(
        Contrast(
            name=c["name"],
            label_field=c["label_field"],
            class0=c["class0"],
            class1=c["class1"],
        )
        for c in raw.get("contrasts", [])
    )
    for c in contrasts:
        if c.label_field not in _VALID_LABEL_FIELDS:
            raise ValueError(
                f"dataset {raw.get('dataset_id')!r} contrast {c.name!r}: "
                f"invalid label_field {c.label_field!r} (expected one of {sorted(_VALID_LABEL_FIELDS)})"
            )
    return DatasetConfig(
        dataset_id=raw["dataset_id"],
        title=raw.get("title", raw["dataset_id"]),
        task_to_state=dict(raw["task_to_state"]),
        contrasts=contrasts,
        default_task=raw["default_task"],
        window_seconds=float(raw.get("window_seconds", 10.0)),
        max_windows_per_file=int(raw.get("max_windows_per_file", 2)),
        max_channels=int(raw.get("max_channels", 16)),
        report_input_heading=raw.get("report_input_heading", "## Input"),
        report_input_source=raw.get(
            "report_input_source", "- Source: real BIDS EEG signal."
        ),
        report_extra_window_lines=tuple(raw.get("report_extra_window_lines", [])),
        report_extra_next_step_lines=tuple(raw.get("report_extra_next_step_lines", [])),
        format_note=raw.get("format_note", ""),
    )


@lru_cache(maxsize=8)
def load_registry(path: str | None = None) -> dict[str, DatasetConfig]:
    """Load and parse the onboarding registry into {dataset_id: DatasetConfig}.

    Cached per path so repeated calls are cheap. Pass an explicit `path` (e.g. in
    tests) to load an alternate registry; the default is the repo's canonical
    configs/btc_icft/dataset_onboarding_registry.json.
    """
    registry_path = Path(path) if path else DEFAULT_REGISTRY_PATH
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    out: dict[str, DatasetConfig] = {}
    for ds_id, raw in data.get("datasets", {}).items():
        cfg = _parse_dataset(raw)
        if cfg.dataset_id != ds_id:
            raise ValueError(
                f"registry key {ds_id!r} != entry dataset_id {cfg.dataset_id!r}"
            )
        out[ds_id] = cfg
    return out


def get_dataset_config(dataset_id: str, path: str | None = None) -> DatasetConfig:
    """Return the typed config for one dataset, or raise KeyError with the list of
    registered dataset ids (so a misspelled --dataset-id fails loudly, not silently)."""
    registry = load_registry(path)
    if dataset_id not in registry:
        raise KeyError(
            f"dataset {dataset_id!r} not in onboarding registry. "
            f"Registered: {sorted(registry)}. Add an entry to "
            f"configs/btc_icft/dataset_onboarding_registry.json to onboard it."
        )
    return registry[dataset_id]


def registered_dataset_ids(path: str | None = None) -> list[str]:
    return sorted(load_registry(path))
