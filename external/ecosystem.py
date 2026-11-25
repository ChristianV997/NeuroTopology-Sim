from __future__ import annotations

from dataclasses import dataclass
import json
import math
import time
from pathlib import Path
from typing import Callable, Iterable
from urllib.request import Request, urlopen

import numpy as np

from core.topology import compute_Q_slice, compute_Qabs_slice, compute_Qz, compute_f_dress

MIN_MQTT_KEEPALIVE_S = 5
MQTT_KEEPALIVE_BUFFER_S = 5
F_DRESS_EPSILON = 1e-9


@dataclass
class SensorRecord:
    """Normalized sensor record for downstream processing."""

    timestamp: float
    sensor_id: str
    protocol: str
    payload: dict
    source: str = ""


class BaseSensorConnector:
    """Base connector contract for all external system integrations."""

    protocol = "unknown"

    def stream(self, max_records: int | None = None) -> Iterable[SensorRecord]:
        raise NotImplementedError


class FileSensorConnector(BaseSensorConnector):
    """Read newline-delimited JSON sensor records from a local file."""

    protocol = "file"

    def __init__(self, path: str | Path, sensor_id: str = "file_sensor"):
        self.path = Path(path)
        self.sensor_id = sensor_id

    def stream(self, max_records: int | None = None) -> Iterable[SensorRecord]:
        count = 0
        if not self.path.exists():
            # A configured feed file that is absent is a configuration error; returning an
            # empty stream made a missing sensor look like a successful zero-record ingest.
            raise FileNotFoundError(f"sensor file does not exist: {self.path}")
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                yield SensorRecord(
                    timestamp=float(payload.get("timestamp", time.time())),
                    sensor_id=str(payload.get("sensor_id", self.sensor_id)),
                    protocol=self.protocol,
                    payload=payload,
                    source=str(self.path),
                )
                count += 1
                if max_records is not None and count >= max_records:
                    return


class RESTSensorConnector(BaseSensorConnector):
    """Poll a REST endpoint that returns one record or a list of records."""

    protocol = "rest"

    def __init__(self, url: str, sensor_id: str = "rest_sensor", timeout_s: float = 10.0):
        self.url = url
        self.sensor_id = sensor_id
        self.timeout_s = float(timeout_s)

    def stream(self, max_records: int | None = None) -> Iterable[SensorRecord]:
        req = Request(self.url, method="GET")
        with urlopen(req, timeout=self.timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        records = payload if isinstance(payload, list) else payload.get("records", [payload])
        for i, row in enumerate(records):
            if max_records is not None and i >= max_records:
                return
            yield SensorRecord(
                timestamp=float(row.get("timestamp", time.time())),
                sensor_id=str(row.get("sensor_id", self.sensor_id)),
                protocol=self.protocol,
                payload=dict(row),
                source=self.url,
            )


class MQTTSensorConnector(BaseSensorConnector):
    """Consume JSON payloads from an MQTT topic."""

    protocol = "mqtt"

    def __init__(
        self,
        host: str,
        topic: str,
        sensor_id: str = "mqtt_sensor",
        port: int = 1883,
        timeout_s: float = 3.0,
    ):
        self.host = host
        self.port = int(port)
        self.topic = topic
        self.sensor_id = sensor_id
        self.timeout_s = float(timeout_s)

    def stream(self, max_records: int | None = None) -> Iterable[SensorRecord]:
        try:
            import paho.mqtt.client as mqtt  # type: ignore
        except Exception as e:
            raise RuntimeError("MQTT connector requires paho-mqtt.") from e

        records: list[dict] = []

        # Callback signature is defined by paho-mqtt.
        def _on_message(client, userdata, msg):
            try:
                records.append(json.loads(msg.payload.decode("utf-8")))
            except Exception:
                records.append({"raw": msg.payload.decode("utf-8", errors="ignore")})

        client = mqtt.Client()
        client.on_message = _on_message
        # Keepalive must be at least a few seconds to avoid fast disconnect loops.
        # Keepalive is set above timeout to reduce premature disconnect risk while waiting for messages.
        keepalive = max(MIN_MQTT_KEEPALIVE_S, int(math.ceil(self.timeout_s)) + MQTT_KEEPALIVE_BUFFER_S)
        client.connect(self.host, self.port, keepalive=keepalive)
        client.subscribe(self.topic)
        client.loop_start()
        deadline = time.time() + self.timeout_s
        wanted = max_records if max_records is not None else 1
        while time.time() < deadline and len(records) < wanted:
            time.sleep(0.05)
        client.loop_stop()
        client.disconnect()
        for row in records[:wanted]:
            yield SensorRecord(
                timestamp=float(row.get("timestamp", time.time())),
                sensor_id=str(row.get("sensor_id", self.sensor_id)),
                protocol=self.protocol,
                payload=dict(row),
                source=f"{self.host}:{self.topic}",
            )


class WebSocketSensorConnector(BaseSensorConnector):
    """Read JSON payloads from a WebSocket endpoint."""

    protocol = "websocket"

    def __init__(self, url: str, sensor_id: str = "ws_sensor", timeout_s: float = 3.0):
        self.url = url
        self.sensor_id = sensor_id
        self.timeout_s = float(timeout_s)

    def stream(self, max_records: int | None = None) -> Iterable[SensorRecord]:
        try:
            from websocket import create_connection  # type: ignore
        except Exception as e:
            raise RuntimeError("WebSocket connector requires websocket-client.") from e

        ws = create_connection(self.url, timeout=self.timeout_s)
        wanted = max_records if max_records is not None else 1
        try:
            for _ in range(wanted):
                raw = ws.recv()
                row = json.loads(raw)
                yield SensorRecord(
                    timestamp=float(row.get("timestamp", time.time())),
                    sensor_id=str(row.get("sensor_id", self.sensor_id)),
                    protocol=self.protocol,
                    payload=dict(row),
                    source=self.url,
                )
        finally:
            ws.close()


class ConnectorRegistry:
    """Registry for plug-and-play sensor connectors."""

    def __init__(self):
        self._builders: dict[str, Callable[..., BaseSensorConnector]] = {}

    def register(self, kind: str, builder: Callable[..., BaseSensorConnector]) -> None:
        self._builders[kind] = builder

    def create(self, kind: str, **kwargs) -> BaseSensorConnector:
        if kind not in self._builders:
            raise ValueError(f"Unknown connector kind: {kind}")
        return self._builders[kind](**kwargs)

    @property
    def kinds(self) -> set[str]:
        return set(self._builders.keys())


def build_default_registry() -> ConnectorRegistry:
    """Build connector registry with default protocol implementations."""
    reg = ConnectorRegistry()
    reg.register("file", FileSensorConnector)
    reg.register("rest", RESTSensorConnector)
    reg.register("mqtt", MQTTSensorConnector)
    reg.register("websocket", WebSocketSensorConnector)
    return reg


def _compute_f_dress_scalar(q: float, qabs: float, eps: float = F_DRESS_EPSILON) -> float:
    return float((qabs - abs(q)) / (abs(q) + eps))


def extract_topology_metrics(payload: dict) -> dict:
    """Extract Q/Qabs/f_dress from sensor payloads in common formats."""
    if "Q" in payload and "Qabs" in payload:
        q = float(payload["Q"])
        qabs = float(payload["Qabs"])
        f_dress = float(payload.get("f_dress", _compute_f_dress_scalar(q, qabs)))
        return {"Q": q, "Qabs": qabs, "f_dress": f_dress}

    if "theta2d" in payload:
        theta = np.asarray(payload["theta2d"], dtype=float)
        q = float(compute_Q_slice(theta))
        qabs = float(compute_Qabs_slice(theta))
        return {"Q": q, "Qabs": qabs, "f_dress": _compute_f_dress_scalar(q, qabs)}

    if "psi3d" in payload:
        psi = np.asarray(payload["psi3d"])
        if np.isrealobj(psi):
            psi = psi.astype(complex)
        qz, qabs = compute_Qz(psi)
        q = float(np.mean(qz))
        qabs_mean = float(np.mean(qabs))
        return {"Q": q, "Qabs": qabs_mean, "f_dress": float(compute_f_dress(qz, qabs))}

    phase_deltas = payload.get("phase_deltas")
    if phase_deltas is not None:
        arr = np.asarray(phase_deltas, dtype=float)
        q = float(np.sum(arr) / (2 * np.pi))
        qabs = float(np.sum(np.abs(arr)) / (2 * np.pi))
        return {"Q": q, "Qabs": qabs, "f_dress": _compute_f_dress_scalar(q, qabs)}

    return {"Q": 0.0, "Qabs": 0.0, "f_dress": 0.0}
