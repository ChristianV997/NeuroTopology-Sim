"""
Load and save HypothesisSpec from/to YAML or JSON files.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Union

import yaml

from governance.spec import (
    ArtifactsSpec,
    Control,
    DataSpec,
    Discriminator,
    HypothesisSpec,
    PassFail,
    Readout,
)


def _parse_spec(data: Dict[str, Any]) -> HypothesisSpec:
    """Build a HypothesisSpec from a raw dict (from YAML or JSON)."""
    discriminator = None
    if data.get("discriminator"):
        d = data["discriminator"]
        discriminator = Discriminator(
            description=d.get("description", ""),
            mode=d.get("mode", ""),
            config=d.get("config", {}),
        )

    readouts = [
        Readout(name=r["name"] if isinstance(r, dict) else r,
                module=r.get("module", "") if isinstance(r, dict) else "")
        for r in data.get("readouts", [])
    ]

    controls = [
        Control(name=c["name"] if isinstance(c, dict) else c,
                config=c.get("config", {}) if isinstance(c, dict) else {})
        for c in data.get("controls", [])
    ]

    data_raw = data.get("data")
    data_spec = None
    if data_raw:
        data_spec = DataSpec(
            mode=data_raw.get("mode", "synthetic"),
            dataset_id=data_raw.get("dataset_id", ""),
            params=data_raw.get("params", {}),
        )

    pf_raw = data.get("pass_fail", {})
    pass_fail = PassFail(
        criteria=pf_raw.get("criteria", ""),
        thresholds=pf_raw.get("thresholds", {}),
    )

    art_raw = data.get("artifacts", {})
    artifacts = ArtifactsSpec(expected=art_raw.get("expected", []))

    return HypothesisSpec(
        id=data.get("id", ""),
        title=data.get("title", ""),
        claim_type=data.get("claim_type", ""),
        layer=data.get("layer", ""),
        summary=data.get("summary", ""),
        discriminator=discriminator,
        readouts=readouts,
        controls=controls,
        data=data_spec,
        pass_fail=pass_fail,
        artifacts=artifacts,
        alternatives_considered=data.get("alternatives_considered", []),
    )


def load_spec(path: Union[str, Path]) -> HypothesisSpec:
    """Load a HypothesisSpec from a YAML or JSON file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Spec file not found: {path}")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if path.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    elif path.suffix == ".json":
        data = json.loads(text)
    else:
        raise ValueError(f"Unsupported file format: {path.suffix} (use .yaml, .yml, or .json)")
    return _parse_spec(data)


def _spec_to_dict(spec: HypothesisSpec) -> Dict[str, Any]:
    """Convert a HypothesisSpec to a plain dict for serialisation."""
    d: Dict[str, Any] = {
        "id": spec.id,
        "title": spec.title,
        "claim_type": spec.claim_type,
        "layer": spec.layer,
        "summary": spec.summary,
    }
    if spec.discriminator is not None:
        d["discriminator"] = {
            "description": spec.discriminator.description,
            "mode": spec.discriminator.mode,
            "config": spec.discriminator.config,
        }
    if spec.readouts:
        d["readouts"] = [{"name": r.name, "module": r.module} for r in spec.readouts]
    if spec.controls:
        d["controls"] = [{"name": c.name, "config": c.config} for c in spec.controls]
    if spec.data is not None:
        d["data"] = {
            "mode": spec.data.mode,
            "dataset_id": spec.data.dataset_id,
            "params": spec.data.params,
        }
    d["pass_fail"] = {
        "criteria": spec.pass_fail.criteria,
        "thresholds": spec.pass_fail.thresholds,
    }
    d["artifacts"] = {"expected": spec.artifacts.expected}
    if spec.alternatives_considered:
        d["alternatives_considered"] = spec.alternatives_considered
    return d


def save_spec(spec: HypothesisSpec, path: Union[str, Path]) -> None:
    """Save a HypothesisSpec to a YAML or JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    d = _spec_to_dict(spec)
    with open(path, "w", encoding="utf-8") as fh:
        if path.suffix in {".yaml", ".yml"}:
            yaml.dump(d, fh, allow_unicode=True, sort_keys=False)
        elif path.suffix == ".json":
            json.dump(d, fh, indent=2, ensure_ascii=False)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")
