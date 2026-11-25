from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import yaml

from database.database import add_metric, add_sensor_record, connect, finish_run, start_run
from external.ecosystem import build_default_registry, extract_topology_metrics
from runs.run_record import RunRecordV1, write_json

EXTERNAL_COLUMNS = ["timestamp", "sensor_id", "protocol", "source", "Q", "Qabs", "f_dress"]

# External ingest derives topology proxies from connector payloads. Fail closed:
# no empirical / scientific_pass claims without a separate promotion gate.
_EVIDENCE_CLASS = "external_sensor_topology_unvalidated"
_RUN_MODE = "external_ingest"
_METRIC_KIND = "external_sensor_topology"


def external_evidence_watermarks() -> dict:
    """Fail-closed provenance stamps for external CSV/meta/RunRecord outputs."""
    return {
        "evidence_class": _EVIDENCE_CLASS,
        "run_mode": _RUN_MODE,
        "metrics_are_empirical": False,
        "scientific_pass": False,
        "metric_kind": _METRIC_KIND,
    }


def run(
    config_path: str | Path,
    output_csv: str | Path,
    db_path: str | Path,
    max_records: int | None = None,
) -> pd.DataFrame:
    """Ingest live or batch sensor data from configured external connectors."""
    config_path = Path(config_path)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    external = config.get("external", {})
    connector_cfgs = external.get("connectors", [])
    registry = build_default_registry()

    conn = connect(db_path)
    run_id = start_run(
        conn, name="external_ingest", kind="external", params={"config_path": str(config_path)}
    )
    rows: list[dict] = []
    try:
        for cfg in connector_cfgs:
            kind = cfg.get("type", "file")
            params = dict(cfg.get("params", {}))
            connector = registry.create(kind, **params)
            for rec in connector.stream(max_records=max_records):
                metrics = extract_topology_metrics(rec.payload)
                row = {
                    "timestamp": rec.timestamp,
                    "sensor_id": rec.sensor_id,
                    "protocol": rec.protocol,
                    "source": rec.source,
                    "Q": metrics["Q"],
                    "Qabs": metrics["Qabs"],
                    "f_dress": metrics["f_dress"],
                }
                rows.append(row)
                add_sensor_record(
                    conn,
                    run_id=run_id,
                    timestamp=rec.timestamp,
                    sensor_id=rec.sensor_id,
                    protocol=rec.protocol,
                    payload=rec.payload,
                    q=row["Q"],
                    qabs=row["Qabs"],
                    source=rec.source,
                )
                add_metric(
                    conn, run_id, "Q", row["Q"], units="topological_charge", source=rec.sensor_id
                )
                add_metric(
                    conn,
                    run_id,
                    "Qabs",
                    row["Qabs"],
                    units="topological_charge_abs",
                    source=rec.sensor_id,
                )
    finally:
        finish_run(conn, run_id, status="finished")
        conn.close()

    df = pd.DataFrame(rows, columns=EXTERNAL_COLUMNS)
    df.to_csv(output_csv, index=False)

    marks = external_evidence_watermarks()
    meta = {
        "records": len(df),
        "config": str(config_path),
        "db": str(db_path),
        "csv": str(output_csv),
        **marks,
    }
    Path(str(output_csv) + ".meta.json").write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )

    metrics_summary = {
        "records": int(len(df)),
        "metric_kind": marks["metric_kind"],
    }
    if len(df) and "Q" in df.columns:
        metrics_summary["Q_mean"] = float(df["Q"].mean())
    if len(df) and "Qabs" in df.columns:
        metrics_summary["Qabs_mean"] = float(df["Qabs"].mean())

    blob = json.dumps(
        {"config": str(config_path), "metrics": metrics_summary},
        sort_keys=True,
        separators=(",", ":"),
    )
    record_id = hashlib.sha256(blob.encode()).hexdigest()[:16]
    record = RunRecordV1.make(
        run_id=record_id,
        run_kind="external",
        data_mode="external",
        metrics=metrics_summary,
        artifacts={
            "csv": str(output_csv),
            "meta": str(output_csv) + ".meta.json",
            "db": str(db_path),
        },
        source="pipelines.run_external",
        evidence_class=marks["evidence_class"],
        run_mode=marks["run_mode"],
        metrics_are_empirical=marks["metrics_are_empirical"],
        scientific_pass=marks["scientific_pass"],
        metric_kind=marks["metric_kind"],
    )
    record.input = {"config_path": str(config_path), "db_path": str(db_path)}
    write_json(record, output_csv.parent / "RunRecord.json")

    return df
