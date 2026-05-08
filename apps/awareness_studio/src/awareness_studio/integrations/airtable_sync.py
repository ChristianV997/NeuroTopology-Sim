"""
Airtable Ops Mirror sync engine.

Run cards are JSON files matching the pattern: {dir}/**/*.run.json
Each file is validated against RunCard schema before sync.

Table mappings
--------------
Runs        — one row per eval / chat run
Claims      — evidence card claims (stub, future)
Work Queue  — tasks / issues (stub, future)

Writes are gated:
  Requires AIRTABLE_ENABLED=true AND allow_write=True argument.
  Any other combination → dry-run: returns planned payloads, no HTTP calls.
"""
import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from awareness_studio import config

logger = logging.getLogger(__name__)

# ── Table names (override via env if your base uses different names) ──────────

TABLE_RUNS = "Runs"
TABLE_CLAIMS = "Claims"
TABLE_WORK_QUEUE = "Work Queue"


# ── Run card schema ───────────────────────────────────────────────────────────

@dataclass
class RunCard:
    run_id: str
    mode: str
    timestamp: str                    # ISO-8601
    input_hash: str                   # sha256[:16] of question
    metrics: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)
    notes: str = ""
    run_card_path: str = ""

    @classmethod
    def from_dict(cls, data: dict, path: str = "") -> "RunCard":
        return cls(
            run_id=data["run_id"],
            mode=data["mode"],
            timestamp=data["timestamp"],
            input_hash=data["input_hash"],
            metrics=data.get("metrics", {}),
            artifacts=data.get("artifacts", []),
            notes=data.get("notes", ""),
            run_card_path=path,
        )

    @classmethod
    def from_run_record_v1(cls, data: dict, path: str = "") -> "RunCard":
        """Build a RunCard from a ScienceR-Dsim RunRecord v1 .run.json file."""
        _REQUIRED = ("run_id", "mode", "created_at", "metrics", "artifacts")
        missing = [k for k in _REQUIRED if k not in data]
        if missing:
            raise ValueError(f"RunRecord v1 missing required keys: {missing}")

        artifacts_raw = data["artifacts"]
        artifacts_list: list
        if isinstance(artifacts_raw, dict):
            artifacts_list = [v for v in artifacts_raw.values() if v]
        elif isinstance(artifacts_raw, list):
            artifacts_list = artifacts_raw
        else:
            artifacts_list = []

        md_path = (
            artifacts_raw.get("md_path", "") if isinstance(artifacts_raw, dict) else ""
        )
        run_card_path = path or (
            artifacts_raw.get("json_path", "") if isinstance(artifacts_raw, dict) else path
        )

        input_hash = hashlib.sha256(
            json.dumps(data.get("input", {}), sort_keys=True).encode()
        ).hexdigest()[:16]

        notes = data.get("notes", "")
        if md_path:
            notes = f"md_path={md_path}" + (f" | {notes}" if notes else "")

        return cls(
            run_id=data["run_id"],
            mode=data["mode"],
            timestamp=data["created_at"],
            input_hash=input_hash,
            metrics=data.get("metrics", {}),
            artifacts=artifacts_list,
            notes=notes,
            run_card_path=run_card_path,
        )

    def to_airtable_fields(self) -> Dict[str, Any]:
        summary = (
            f"{self.mode} | {self.run_id[:8]} | "
            f"{self.timestamp[:10]} | "
            f"{len(self.metrics)} metrics"
        )
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "timestamp": self.timestamp,
            "input_hash": self.input_hash,
            "metrics_json": json.dumps(self.metrics, ensure_ascii=False),
            "artifacts_json": json.dumps(self.artifacts, ensure_ascii=False),
            "run_card_path": self.run_card_path,
            "summary": summary,
            "notes": self.notes,
        }


def make_run_card(
    run_id: str,
    mode: str,
    question: str,
    metrics: Optional[Dict[str, Any]] = None,
    artifacts: Optional[List[str]] = None,
    notes: str = "",
) -> RunCard:
    """Helper: construct a RunCard from chat/eval call parameters."""
    input_hash = hashlib.sha256(question.encode()).hexdigest()[:16]
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return RunCard(
        run_id=run_id,
        mode=mode,
        timestamp=ts,
        input_hash=input_hash,
        metrics=metrics or {},
        artifacts=artifacts or [],
        notes=notes,
    )


# ── Sync results ──────────────────────────────────────────────────────────────

@dataclass
class SyncSummary:
    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    dry_run: bool = True
    planned: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Core sync function ────────────────────────────────────────────────────────

def sync_runs_from_run_cards(
    run_cards_dir: Optional[Path] = None,
    allow_write: bool = False,
) -> SyncSummary:
    """
    Discover .run.json files, validate, and sync to Airtable Runs table.

    Dry-run (default) — returns SyncSummary with planned payloads, no HTTP.
    Live write — requires AIRTABLE_ENABLED=true AND allow_write=True.
    """
    from awareness_studio import config as cfg
    summary = SyncSummary(dry_run=not (cfg.AIRTABLE_ENABLED and allow_write))

    if run_cards_dir is None:
        run_cards_dir = cfg.DATA_DIR / "run_cards"

    run_cards_dir = Path(run_cards_dir)
    card_files = sorted(run_cards_dir.rglob("*.run.json")) if run_cards_dir.exists() else []

    if not card_files:
        logger.info("[airtable-sync] No .run.json files found in %s", run_cards_dir)
        return summary

    cards = _load_run_cards(card_files)
    summary.total = len(cards)

    if summary.dry_run:
        for card in cards:
            summary.planned.append({
                "action": "upsert",
                "table": TABLE_RUNS,
                "key_field": "run_id",
                "key_value": card.run_id,
                "fields": card.to_airtable_fields(),
            })
        logger.info(
            "[airtable-sync] dry-run: would upsert %d records to %s",
            len(cards), TABLE_RUNS,
        )
        return summary

    client = _get_client(enabled=True)
    for card in cards:
        try:
            client.upsert_by_field(
                TABLE_RUNS, "run_id", card.run_id, card.to_airtable_fields()
            )
            summary.updated += 1
            logger.debug("[airtable-sync] upserted run %s", card.run_id)
        except Exception as exc:
            summary.errors.append(f"{card.run_id}: {exc}")
            logger.warning("[airtable-sync] failed to sync run %s: %s", card.run_id, exc)

    summary.created = summary.updated  # upsert doesn't distinguish; acceptable
    logger.info(
        "[airtable-sync] synced %d/%d runs to Airtable (%d errors)",
        summary.updated, summary.total, len(summary.errors),
    )
    return summary


def save_run_card(card: RunCard, base_dir: Optional[Path] = None) -> Path:
    """Persist a RunCard as a .run.json file in base_dir/run_cards/."""
    from awareness_studio import config as cfg
    if base_dir is None:
        base_dir = cfg.DATA_DIR
    out_dir = Path(base_dir) / "run_cards"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{card.run_id}.run.json"
    data = asdict(card)
    data["run_card_path"] = str(path)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    card.run_card_path = str(path)
    return path


# ── Claims stub ───────────────────────────────────────────────────────────────

def sync_claims_from_evidence_log(allow_write: bool = False) -> SyncSummary:
    """
    Stub: future sync of evidence log entries to Airtable Claims table.
    Returns dry-run summary indicating the feature is not yet implemented.
    """
    return SyncSummary(
        dry_run=True,
        planned=[{"note": "Claims sync not yet implemented — future work."}],
    )


# ── Status check ──────────────────────────────────────────────────────────────

def airtable_status() -> Dict[str, Any]:
    """Return configuration status without making any API calls."""
    from awareness_studio import config as cfg
    return {
        "enabled": cfg.AIRTABLE_ENABLED,
        "api_key_set": bool(cfg.AIRTABLE_API_KEY),
        "base_id_set": bool(cfg.AIRTABLE_BASE_ID),
        "tables": {
            "runs": TABLE_RUNS,
            "claims": TABLE_CLAIMS,
            "work_queue": TABLE_WORK_QUEUE,
        },
        "note": (
            "Ready — set AIRTABLE_ENABLED=true and pass allow_write=True to write."
            if cfg.AIRTABLE_API_KEY and cfg.AIRTABLE_BASE_ID
            else "Not configured — set AIRTABLE_API_KEY and AIRTABLE_BASE_ID."
        ),
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_run_cards(files: List[Path]) -> List[RunCard]:
    cards = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("schema_version") == "1":
                cards.append(RunCard.from_run_record_v1(data, str(path)))
            else:
                cards.append(RunCard.from_dict(data, str(path)))
        except Exception as exc:
            logger.warning("[airtable-sync] skipping %s: %s", path, exc)
    return cards


def _get_client(enabled: bool = False):
    from awareness_studio import config as cfg
    from awareness_studio.integrations.airtable_client import AirtableClient
    return AirtableClient(
        api_key=cfg.AIRTABLE_API_KEY,
        base_id=cfg.AIRTABLE_BASE_ID,
        enabled=enabled,
    )
