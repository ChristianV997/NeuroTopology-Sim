"""Analyze frozen-state transition operators from real feature artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from research_runtime.protocol import ProtocolSpec
from research_runtime.transitions import (
    condition_transition_operator,
    fit_feature_state_model,
    jensen_shannon_distance,
    operator_metrics,
)


def load_rows(root: Path, feature_names: tuple[str, ...]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(root.glob("*_transition_features.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            missing = set(feature_names) - set(reader.fieldnames or ())
            if missing:
                raise ValueError(f"{path} missing required features: {sorted(missing)}")
            for row in reader:
                row["source_file"] = path.name
                rows.append(row)
    if not rows:
        raise ValueError(f"no transition feature files found under {root}")
    return rows


def analyze(rows: list[dict[str, str]], protocol: ProtocolSpec) -> dict:
    subjects = sorted({row["subject_id"] for row in rows})
    development = np.asarray(
        [[float(row[name]) for name in protocol.feature_names] for row in rows], dtype=float
    )
    model = fit_feature_state_model(development, n_states=protocol.n_states, seed=protocol.split_seed)
    labels = model.transform(development)
    for row, label in zip(rows, labels):
        row["state"] = str(int(label))

    records = []
    for subject in subjects:
        subject_rows = [row for row in rows if row["subject_id"] == subject]
        conditions = {row["condition"] for row in subject_rows}
        if not {"meditation", "thinking"}.issubset(conditions):
            continue
        operators = {}
        for condition in ("meditation", "thinking"):
            selected = [row for row in subject_rows if row["condition"] == condition]
            op = condition_transition_operator(
                [int(row["state"]) for row in selected],
                [row["sequence_id"] for row in selected],
                protocol.n_states,
            )
            if not np.any(op):
                raise ValueError(f"subject {subject} condition {condition} has no transitions")
            operators[condition] = op
        med = operator_metrics(operators["meditation"])
        think = operator_metrics(operators["thinking"])
        records.append(
            {
                "subject_id": subject,
                "n_rows": len(subject_rows),
                "transition_entropy_difference": med["transition_entropy"] - think["transition_entropy"],
                "operator_js_distance": jensen_shannon_distance(operators["meditation"], operators["thinking"]),
                "self_transition_difference": med["self_transition_probability"] - think["self_transition_probability"],
                "reversibility_difference": med["reversibility_asymmetry"] - think["reversibility_asymmetry"],
            }
        )
    if not records:
        raise ValueError("no subjects contain both meditation and thinking transitions")
    return {
        "subjects_analyzed": len(records),
        "state_model": model.to_dict(),
        "records": records,
        "summary": {
            key: float(np.mean([record[key] for record in records]))
            for key in records[0]
            if key not in {"subject_id", "n_rows"}
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("features_dir", type=Path)
    parser.add_argument("--protocol", type=Path, default=Path("configs/research/state_transition_ds003969.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = ProtocolSpec.from_dict(json.loads(args.protocol.read_text(encoding="utf-8")))
    result = analyze(load_rows(args.features_dir, protocol.feature_names), protocol)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"subjects_analyzed": result["subjects_analyzed"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
