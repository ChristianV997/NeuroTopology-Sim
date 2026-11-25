from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from database.database import add_metric, add_sensor_record, connect, finish_run, start_run
from external.ecosystem import build_default_registry, extract_topology_metrics

EXTERNAL_COLUMNS = ["timestamp", "sensor_id", "protocol", "source", "Q", "Qabs", "f_dress"]


def run(config_path: str | Path, output_csv: str | Path, db_path: str | Path, max_records: int | None = None) -> pd.DataFrame:
    """Ingest live or batch sensor data from configured external connectors."""
    config_path = Path(config_path)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    external = config.get("external", {})
    connector_cfgs = external.get("connectors", [])
    registry = build_default_registry()

    conn = connect(db_path)
    run_id = start_run(conn, name="external_ingest", kind="external", params={"config_path": str(config_path)})
    rows: list[dict] = []
    status = "failed"  # recorded as failed unless every connector completes
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
                add_metric(conn, run_id, "Q", row["Q"], units="topological_charge", source=rec.sensor_id)
                add_metric(conn, run_id, "Qabs", row["Qabs"], units="topological_charge_abs", source=rec.sensor_id)
        status = "finished"
    finally:
        finish_run(conn, run_id, status=status)
        conn.close()

    df = pd.DataFrame(rows, columns=EXTERNAL_COLUMNS)
    df.to_csv(output_csv, index=False)
    Path(str(output_csv) + ".meta.json").write_text(
        json.dumps({"records": len(df), "config": str(config_path), "db": str(db_path)}, indent=2),
        encoding="utf-8",
    )
    return df
