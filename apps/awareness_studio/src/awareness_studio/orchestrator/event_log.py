"""Append-only JSONL event log for orchestrator runs."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterator, List, Optional

from .event_model import EventEnvelope, canonical_json

logger = logging.getLogger(__name__)


class EventLog:
    """Append-only JSONL log rooted at out_dir/events.jsonl.

    Not process-safe; callers should serialize concurrent writes externally.
    """

    def __init__(self, out_dir: Path) -> None:
        self._path = Path(out_dir) / "events.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, event: EventEnvelope) -> None:
        """Append one event line (atomic write)."""
        line = event.to_jsonl() + "\n"
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        logger.debug("[event_log] %s %s %s", event.run_id[:8], event.stage, event.status)

    def load_all(self) -> List[EventEnvelope]:
        """Load all events from the log file."""
        if not self._path.exists():
            return []
        events: List[EventEnvelope] = []
        with self._path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(EventEnvelope.from_dict(json.loads(line)))
                except Exception as exc:
                    logger.warning("[event_log] skipping malformed line: %s", exc)
        return events

    def load_by_run_id(self, run_id: str) -> List[EventEnvelope]:
        return [e for e in self.load_all() if e.run_id == run_id]

    def list_recent(self, n: int = 20) -> List[EventEnvelope]:
        return self.load_all()[-n:]

    def iter_lines(self) -> Iterator[str]:
        """Yield raw JSONL lines for SSE streaming."""
        if not self._path.exists():
            return
        with self._path.open(encoding="utf-8") as fh:
            yield from fh


def load_global_log(base_dir: Optional[Path] = None) -> EventLog:
    """Return the global event log (base_dir/events.jsonl)."""
    from awareness_studio import config
    root = Path(base_dir) if base_dir else (config.APP_ROOT / "outputs" / "orchestrator")
    return EventLog(root)
