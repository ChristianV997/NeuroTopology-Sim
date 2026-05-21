from __future__ import annotations
import json
from pathlib import Path
from typing import Any

DATASET_ID = "DS002094"
DEFAULT_OUT = Path("outputs/btc_icft/ds002094_executor")
GUARDRAIL_FLAGS = {
    "executes_real_data": False,
    "downloads_data": False,
    "auto_confirms_peer_review": False,
    "infers_labels": False,
    "fabricates_targets": False,
    "auto_runs_mne_extraction": False,
    "auto_runs_level_m_extraction": False,
    "auto_runs_level_t_extraction": False,
    "auto_runs_real_benchmark": False,
    "empirical_claims_permitted": False,
    "ontology_promotion_allowed": False,
}
FORBIDDEN_PHRASES = [
    "proves consciousness","validates consciousness","final theory","q proves","qabs proves","fdress proves",
    "clinical efficacy","diagnosis","treatment","cure","ontology promotion"
]

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding='utf-8')

def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))
