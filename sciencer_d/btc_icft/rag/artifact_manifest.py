#!/usr/bin/env python3
"""Awareness Research RAG artifact manifest builder (P20.0).

Stdlib-only. Scans local BTC/ICFT output artifacts and docs, builds a
claim-safe ingestion manifest, and emits JSONL/JSON/CSV/Markdown outputs
for Notion/RAG chatbot indexing.

Does NOT call external APIs, create embeddings, infer labels, fabricate
targets, activate contracts, or make consciousness/soul/liberation/afterlife
ontology proof claims.

Safe claim:
"BTC/ICFT artifacts were converted into a claim-safe RAG ingestion manifest
for retrieval, review, and paper-preparation workflows."
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAFE_CLAIM = (
    "BTC/ICFT artifacts were converted into a claim-safe RAG ingestion manifest"
    " for retrieval, review, and paper-preparation workflows."
)

# Quarantine-scan list only — never promoted, always checked against content.
BANNED_PHRASES: tuple[str, ...] = (
    "proves consciousness",
    "consciousness proven",
    "soul proven",
    "afterlife proven",
    "liberation detected",
    "ontology solved",
    "ultimate reality",
    "q equals self",
    "q equals soul",
    "q_abs equals suffering",
    "f_dress equals karma",
    "sedated implies no_experience",
    "unresponsive implies unconscious",
    "topology proves liberation",
    "eeg proves consciousness",
    "direct liberation score",
    "direct soul measurement",
)

MAX_TEXT_READ = 20 * 1024       # 20 KB
MAX_YAML_READ = 10 * 1024       # 10 KB
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

TEXT_EXTENSIONS = {".md", ".txt"}
STRUCTURED_EXTENSIONS = {".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml"}
ALL_EXTENSIONS = TEXT_EXTENSIONS | STRUCTURED_EXTENSIONS

IGNORE_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv"}


# ---------------------------------------------------------------------------
# Stage inference
# ---------------------------------------------------------------------------

def infer_stage(path: Path) -> str:
    """Infer pipeline stage from file path."""
    parts = [p.lower() for p in path.parts]
    name = path.name.lower()

    if any("target_aware_activation" in p for p in parts) or "target_aware_activation" in name:
        return "target_aware_activation"
    if any("ds005620_contract_activation" in p for p in parts) or "ds005620_contract_activation" in name:
        return "ds005620_contract_activation"
    if any("eeg_reader_preflight" in p for p in parts) or "eeg_reader_preflight" in name:
        return "eeg_reader_preflight"
    if any("eeg_signal_mt" in p for p in parts) or "eeg_signal_mt" in name or "signal_mt" in name:
        return "eeg_signal_mt"
    if any("eeg_level_m" in p for p in parts) or "eeg_level_m" in name:
        return "eeg_level_m"
    if any("eeg_level_t" in p for p in parts) or "eeg_level_t" in name:
        return "eeg_level_t"
    if any("signal_blocks" in p for p in parts) or "signal_blocks" in name:
        return "signal_blocks"
    if any("eeg_studies" in p for p in parts) or "eeg_studies" in name:
        return "eeg_studies"
    if any("eeg_labels" in p for p in parts) or "eeg_label" in name:
        return "eeg_labels"
    if any("eeg_targets" in p for p in parts) or "eeg_target" in name:
        return "eeg_targets"
    if any("label_adapter" in p for p in parts) or "label_adapter" in name:
        return "label_adapter_readiness"
    if any("label_contract" in p for p in parts) or "label_contract" in name or "contract_draft" in name:
        return "label_contract_drafts"
    if any("docs" == p for p in parts):
        return "docs"
    if any("configs" == p for p in parts) or path.suffix in {".yaml", ".yml"}:
        return "configs"
    return "unknown"


# ---------------------------------------------------------------------------
# Dataset inference
# ---------------------------------------------------------------------------

def infer_dataset_id(path: Path) -> str:
    s = str(path).lower()
    if "ds005620" in s:
        return "DS005620"
    if "ds002094" in s:
        return "DS002094"
    if "ds001787" in s:
        return "ds001787"
    if "ds003969" in s:
        return "ds003969"
    if "ds003816" in s:
        return "ds003816"
    if "physionet_gaba" in s or "gaba" in s:
        return "PhysioNet_GABA"
    if "synthetic" in s or "mock" in s or "fixture" in s:
        return "synthetic"
    return "unknown"


# ---------------------------------------------------------------------------
# Evidence state inference
# ---------------------------------------------------------------------------

def infer_evidence_state(path: Path, content_snippet: str = "") -> str:
    s = str(path).lower() + content_snippet.lower()
    if "mock" in s or "fixture" in s:
        return "mock_fixture"
    if "synthetic" in s:
        return "synthetic"
    if "human_review" in s or "human-review" in s:
        return "human_review_required"
    if "blocked" in s:
        return "blocked"
    if "pending" in s or "empirical_pending" in s:
        return "empirical_pending"
    if path.suffix in {".json", ".jsonl", ".csv", ".md"} and path.stat().st_size > 0:
        return "operational_artifact"
    return "unknown"


# ---------------------------------------------------------------------------
# Index priority
# ---------------------------------------------------------------------------

_HIGH_PRIORITY_NAMES = {
    "report.md", "omega_event.json", "summary", "metrics_signal_mt.json",
    "activation_smoke_summary.json", "target_injection_report.json",
    "label_alignment_report.json", "artifact_report.json",
}

_STAGE_PRIORITIES = {
    "target_aware_activation": 1,
    "ds005620_contract_activation": 1,
    "eeg_signal_mt": 1,
    "docs": 1,
    "eeg_labels": 2,
    "eeg_targets": 2,
    "eeg_level_t": 2,
    "eeg_level_m": 2,
    "label_adapter_readiness": 2,
    "label_contract_drafts": 2,
    "eeg_reader_preflight": 2,
    "signal_blocks": 3,
    "eeg_studies": 3,
    "configs": 3,
}


def infer_index_priority(path: Path, stage: str, claim_safety_status: str) -> int:
    if claim_safety_status == "quarantined_banned_phrase":
        return 5
    name = path.name.lower()
    if any(p in name for p in _HIGH_PRIORITY_NAMES):
        return 1
    if stage in _STAGE_PRIORITIES:
        return _STAGE_PRIORITIES[stage]
    if path.suffix in {".csv", ".tsv"} and stage not in {"target_aware_activation", "eeg_signal_mt"}:
        return 4
    return 5


# ---------------------------------------------------------------------------
# RAG mode inference
# ---------------------------------------------------------------------------

def infer_rag_mode(stage: str, claim_safety_status: str, path: Path) -> str:
    if claim_safety_status == "quarantined_banned_phrase":
        return "ontology_safe_mode"
    name = path.name.lower()
    if stage in {"docs"} or name.endswith("_runbook.md"):
        return "artifact_explainer"
    if "activation" in stage or "activation" in name:
        return "claim_card_generator"
    if stage in {"eeg_signal_mt", "eeg_level_m", "eeg_level_t"}:
        return "topology_metric_explainer"
    if stage in {"eeg_labels", "label_contract_drafts", "label_adapter_readiness"}:
        return "dataset_status_assistant"
    if stage in {"eeg_targets"}:
        return "intervention_safety_review"
    if "report" in name or "plan" in name:
        return "paper_outline_generator"
    return "artifact_explainer"


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def _extract_text_summary(path: Path) -> tuple[str, str]:
    """Returns (title, summary) for .md/.txt files."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:MAX_TEXT_READ]
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        title = lines[0][:120] if lines else path.stem
        summary = " ".join(lines[:3])[:500] if lines else ""
        return title, summary
    except Exception as exc:
        return path.stem, f"read_error: {exc}"


def _extract_json_summary(path: Path) -> tuple[str, str]:
    """Returns (title, summary) for .json files."""
    KEYS_OF_INTEREST = (
        "safe_claim", "claim", "allowed_claim", "promotion_reason",
        "activation_smoke_passed", "predictive_metrics_available",
        "contract_activation_allowed", "ready_for_target_aware_p11",
        "ready_for_p11_with_targets", "extraction_ready",
        "warnings",
    )
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(data, dict):
            return path.stem, f"type={type(data).__name__}"
        selected = {k: v for k, v in data.items() if k in KEYS_OF_INTEREST}
        if not selected:
            selected = dict(list(data.items())[:5])
        summary = "; ".join(f"{k}={v!r}" for k, v in selected.items())[:500]
        return path.stem, summary
    except json.JSONDecodeError as exc:
        return path.stem, f"json_parse_error: {exc}"
    except Exception as exc:
        return path.stem, f"read_error: {exc}"


def _extract_csv_summary(path: Path) -> tuple[str, str]:
    """Returns (title, summary) for .csv/.tsv files."""
    import csv as _csv
    try:
        delim = "\t" if path.suffix == ".tsv" else ","
        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            reader = _csv.reader(fh, delimiter=delim)
            rows = []
            for i, row in enumerate(reader):
                rows.append(row)
                if i >= 3:
                    break
        if not rows:
            return path.stem, "empty_csv"
        header = rows[0]
        summary = f"columns={header}; row_count={len(rows)-1}"[:500]
        return path.stem, summary
    except Exception as exc:
        return path.stem, f"read_error: {exc}"


def _extract_yaml_summary(path: Path) -> tuple[str, str]:
    """Returns (title, summary) for .yaml/.yml files (no PyYAML)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:MAX_YAML_READ]
        lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
        summary = "; ".join(lines[:8])[:500]
        return path.stem, summary
    except Exception as exc:
        return path.stem, f"read_error: {exc}"


def extract_summary(path: Path) -> tuple[str, str]:
    """Dispatch to appropriate extractor. Returns (title, summary)."""
    ext = path.suffix.lower()
    if ext in {".md", ".txt"}:
        return _extract_text_summary(path)
    if ext == ".json":
        return _extract_json_summary(path)
    if ext == ".jsonl":
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            if not lines:
                return path.stem, "empty_jsonl"
            data = json.loads(lines[0])
            summary = "; ".join(f"{k}={v!r}" for k, v in list(data.items())[:5])[:500]
            return path.stem, summary
        except Exception as exc:
            return path.stem, f"read_error: {exc}"
    if ext in {".csv", ".tsv"}:
        return _extract_csv_summary(path)
    if ext in {".yaml", ".yml"}:
        return _extract_yaml_summary(path)
    return path.stem, "unsupported_type"


# ---------------------------------------------------------------------------
# Claim safety scan
# ---------------------------------------------------------------------------

def scan_claim_safety(text: str) -> tuple[str, list[str]]:
    """Returns (claim_safety_status, forbidden_claims_found)."""
    text_lower = text.lower()
    found = [phrase for phrase in BANNED_PHRASES if phrase in text_lower]
    if found:
        return "quarantined_banned_phrase", found
    return "safe", []


# ---------------------------------------------------------------------------
# Artifact ID
# ---------------------------------------------------------------------------

def make_artifact_id(path: Path, root: Path) -> str:
    """Stable path-based artifact ID."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    h = hashlib.sha256(str(rel).encode()).hexdigest()[:16]
    return f"art_{h}"


# ---------------------------------------------------------------------------
# ArtifactRecord dataclass
# ---------------------------------------------------------------------------

@dataclass
class ArtifactRecord:
    artifact_id: str
    path: str
    relative_path: str
    file_type: str
    size_bytes: int
    stage: str
    dataset_id: str
    evidence_state: str
    claim_safety_status: str
    index_priority: int
    title: str
    summary: str
    safe_claim: str
    forbidden_claims_found: list[str]
    recommended_rag_mode: str
    required_context: str
    next_action: str

    def to_dict(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "path": self.path,
            "relative_path": self.relative_path,
            "file_type": self.file_type,
            "size_bytes": self.size_bytes,
            "stage": self.stage,
            "dataset_id": self.dataset_id,
            "evidence_state": self.evidence_state,
            "claim_safety_status": self.claim_safety_status,
            "index_priority": self.index_priority,
            "title": self.title,
            "summary": self.summary,
            "safe_claim": self.safe_claim,
            "forbidden_claims_found": self.forbidden_claims_found,
            "recommended_rag_mode": self.recommended_rag_mode,
            "required_context": self.required_context,
            "next_action": self.next_action,
        }


# ---------------------------------------------------------------------------
# Record builder
# ---------------------------------------------------------------------------

def _build_record(path: Path, scan_root: Path, dataset_id_override: str | None) -> ArtifactRecord:
    """Build a single ArtifactRecord for a file."""
    try:
        size = path.stat().st_size
    except OSError:
        size = 0

    try:
        rel = str(path.relative_to(scan_root))
    except ValueError:
        rel = str(path)

    ext = path.suffix.lower()
    stage = infer_stage(path)
    ds_id = dataset_id_override or infer_dataset_id(path)
    art_id = make_artifact_id(path, scan_root)

    try:
        if ext in {".md", ".txt"}:
            text_for_scan = path.read_text(encoding="utf-8", errors="replace")[:MAX_TEXT_READ]
        elif ext == ".json":
            text_for_scan = path.read_text(encoding="utf-8", errors="replace")[:MAX_TEXT_READ]
        elif ext in {".yaml", ".yml"}:
            text_for_scan = path.read_text(encoding="utf-8", errors="replace")[:MAX_YAML_READ]
        else:
            text_for_scan = ""
    except Exception:
        text_for_scan = ""

    claim_safety_status, forbidden = scan_claim_safety(text_for_scan)
    evidence_state = infer_evidence_state(path, text_for_scan[:200])
    priority = infer_index_priority(path, stage, claim_safety_status)
    rag_mode = infer_rag_mode(stage, claim_safety_status, path)

    title, summary = extract_summary(path)

    if claim_safety_status == "quarantined_banned_phrase":
        required_context = "human_review_required_before_indexing"
        next_action = "quarantine_and_human_review"
    elif evidence_state == "mock_fixture":
        required_context = "mock_data_only_not_empirical"
        next_action = "index_as_mock_with_provenance_label"
    elif evidence_state in {"empirical_pending", "human_review_required"}:
        required_context = "empirical_validation_pending"
        next_action = "await_human_review_then_index"
    elif priority == 1:
        required_context = "ready_for_priority_rag_indexing"
        next_action = "index_in_first_rag_batch"
    else:
        required_context = "standard_artifact"
        next_action = "index_in_scheduled_batch"

    return ArtifactRecord(
        artifact_id=art_id,
        path=str(path),
        relative_path=rel,
        file_type=ext.lstrip(".") or "unknown",
        size_bytes=size,
        stage=stage,
        dataset_id=ds_id,
        evidence_state=evidence_state,
        claim_safety_status=claim_safety_status,
        index_priority=priority,
        title=title,
        summary=summary,
        safe_claim=SAFE_CLAIM,
        forbidden_claims_found=forbidden,
        recommended_rag_mode=rag_mode,
        required_context=required_context,
        next_action=next_action,
    )


# ---------------------------------------------------------------------------
# scan_artifacts
# ---------------------------------------------------------------------------

def scan_artifacts(
    root: Path,
    docs_root: Path | None = None,
    dataset_id: str | None = None,
    include_docs: bool = True,
    max_artifacts: int | None = None,
) -> list[ArtifactRecord]:
    """Scan root (and optionally docs_root) for artifacts."""
    records: list[ArtifactRecord] = []
    scan_roots = [root]
    if include_docs and docs_root is not None and docs_root.is_dir() and docs_root != root:
        scan_roots.append(docs_root)

    seen_paths: set[Path] = set()

    for scan_root in scan_roots:
        if not scan_root.is_dir():
            continue
        for path in sorted(scan_root.rglob("*")):
            if max_artifacts is not None and len(records) >= max_artifacts:
                break
            if not path.is_file():
                continue
            if any(part in IGNORE_DIRS for part in path.parts):
                continue
            if any(part.startswith(".") for part in path.parts[:-1]):
                continue
            if path.suffix.lower() not in ALL_EXTENSIONS:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_SIZE:
                continue
            if path in seen_paths:
                continue
            seen_paths.add(path)

            record = _build_record(path, scan_root, dataset_id)
            records.append(record)

    return records


# ---------------------------------------------------------------------------
# Mock fixture creation
# ---------------------------------------------------------------------------

def create_mock_fixtures(tmp_dir: Path) -> Path:
    """Create deterministic mock artifacts in tmp_dir/mock_fixtures/. Returns fixture root."""
    root = tmp_dir / "mock_fixtures"
    root.mkdir(parents=True, exist_ok=True)

    (root / "report.md").write_text(
        "# Awareness Research Signal Report\n\noperational signal pipeline output. mock fixture only.\n",
        encoding="utf-8",
    )
    (root / "omega_event.json").write_text(
        json.dumps({
            "event_type": "awareness_rag_manifest_built",
            "safe_claim": SAFE_CLAIM,
            "no_embeddings_created": True,
            "no_external_api_called": True,
            "no_claim_promotion": True,
        }),
        encoding="utf-8",
    )
    (root / "metrics_signal_mt.json").write_text(
        json.dumps({
            "safe_claim": "metrics are candidate proxies only",
            "extraction_ready": True,
            "predictive_metrics_available": False,
        }),
        encoding="utf-8",
    )

    activation_dir = root / "target_aware_activation"
    activation_dir.mkdir(exist_ok=True)
    (activation_dir / "activation_smoke_summary.json").write_text(
        json.dumps({
            "activation_smoke_passed": True,
            "contract_activation_allowed": False,
            "safe_claim": "smoke test only",
        }),
        encoding="utf-8",
    )

    target_dir = root / "eeg_targets" / "DS005620"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "target_injection_report.json").write_text(
        json.dumps({
            "ready_for_p11_with_targets": False,
            "warnings": ["mock fixture only"],
        }),
        encoding="utf-8",
    )

    label_dir = root / "eeg_labels" / "DS005620"
    label_dir.mkdir(parents=True, exist_ok=True)
    (label_dir / "label_alignment_report.json").write_text(
        json.dumps({
            "ready_for_target_aware_p11": False,
            "allowed_claim": "label mapping is provisional only",
        }),
        encoding="utf-8",
    )

    (root / "artifact_report.json").write_text(
        json.dumps({
            "extraction_ready": True,
            "safe_claim": "artifact contract check only",
        }),
        encoding="utf-8",
    )

    config_dir = root / "configs"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "awareness_rag_manifest.yaml").write_text(
        "dataset_scope: awareness_rag_manifest\npipeline_id: awareness_rag_manifest_v0\n",
        encoding="utf-8",
    )

    return root


# ---------------------------------------------------------------------------
# write_outputs
# ---------------------------------------------------------------------------

def write_outputs(
    records: list[ArtifactRecord],
    out_dir: Path,
    scan_root: Path,
    generated_at: str,
    blockers: list[str] | None = None,
) -> None:
    """Write all 7 required output files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    blockers = blockers or []

    quarantined = [r for r in records if r.claim_safety_status == "quarantined_banned_phrase"]
    safe = [r for r in records if r.claim_safety_status == "safe"]
    top_priority = [r for r in records if r.index_priority == 1]

    # rag_artifact_manifest.jsonl
    with (out_dir / "rag_artifact_manifest.jsonl").open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r.to_dict()) + "\n")

    # rag_artifact_manifest.json
    counts = {"total": len(records), "safe": len(safe), "quarantined": len(quarantined)}
    priorities = {str(i): sum(1 for r in records if r.index_priority == i) for i in range(1, 6)}
    stages: dict[str, int] = {}
    for r in records:
        stages[r.stage] = stages.get(r.stage, 0) + 1
    datasets: dict[str, int] = {}
    for r in records:
        datasets[r.dataset_id] = datasets.get(r.dataset_id, 0) + 1

    manifest_json = {
        "artifacts": [r.to_dict() for r in records],
        "counts": counts,
        "priorities": priorities,
        "stages": stages,
        "datasets": datasets,
        "quarantined_count": len(quarantined),
        "safe_count": len(safe),
        "generated_at": generated_at,
        "blockers": blockers,
    }
    (out_dir / "rag_artifact_manifest.json").write_text(
        json.dumps(manifest_json, indent=2), encoding="utf-8"
    )

    # rag_index_priority.csv
    import csv as _csv
    with (out_dir / "rag_index_priority.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = _csv.DictWriter(fh, fieldnames=[
            "artifact_id", "relative_path", "stage", "dataset_id",
            "evidence_state", "claim_safety_status", "index_priority",
            "recommended_rag_mode", "next_action",
        ])
        writer.writeheader()
        for r in records:
            writer.writerow({
                "artifact_id": r.artifact_id,
                "relative_path": r.relative_path,
                "stage": r.stage,
                "dataset_id": r.dataset_id,
                "evidence_state": r.evidence_state,
                "claim_safety_status": r.claim_safety_status,
                "index_priority": r.index_priority,
                "recommended_rag_mode": r.recommended_rag_mode,
                "next_action": r.next_action,
            })

    # quarantined_artifacts.json
    banned_phrase_counts: dict[str, int] = {}
    for r in quarantined:
        for phrase in r.forbidden_claims_found:
            banned_phrase_counts[phrase] = banned_phrase_counts.get(phrase, 0) + 1
    (out_dir / "quarantined_artifacts.json").write_text(
        json.dumps({
            "quarantined_artifacts": [r.to_dict() for r in quarantined],
            "banned_phrase_counts": banned_phrase_counts,
            "action": "human_review_required",
        }, indent=2),
        encoding="utf-8",
    )

    # omega_event.json
    (out_dir / "omega_event.json").write_text(
        json.dumps({
            "event_type": "awareness_rag_manifest_built",
            "safe_claim": SAFE_CLAIM,
            "artifact_count": len(records),
            "quarantined_count": len(quarantined),
            "top_priority_count": len(top_priority),
            "no_embeddings_created": True,
            "no_external_api_called": True,
            "no_claim_promotion": True,
            "generated_at": generated_at,
            "blockers": blockers,
        }, indent=2),
        encoding="utf-8",
    )

    # rag_ingestion_plan.md
    first_batch = [
        r for r in records
        if r.index_priority == 1 and r.claim_safety_status == "safe"
    ][:10]
    plan_lines = [
        "# RAG Ingestion Plan",
        "",
        "## Purpose",
        "Index BTC/ICFT research artifacts into a claim-safe RAG knowledge base.",
        "This plan was generated automatically. Human review is required before any",
        "live chatbot ingestion.",
        "",
        "## Highest Priority Artifacts",
        "",
    ]
    for r in first_batch:
        plan_lines.append(
            f"- `{r.relative_path}` (stage={r.stage}, mode={r.recommended_rag_mode})"
        )
    plan_lines += [
        "",
        "## Dataset-Specific Indexing",
        "",
        "Index each dataset's operational artifacts separately to preserve provenance.",
        "",
        "## Claim-Safe Context Rules",
        "",
        "- All artifacts are candidate proxy measurements only.",
        "- No artifact claims to measure consciousness, soul, liberation, or afterlife.",
        "- Human review is required before any claim is elevated to empirical status.",
        "",
        "## RAG Modes",
        "",
        "- artifact_explainer: for runbooks and reports",
        "- claim_card_generator: for activation summaries",
        "- topology_metric_explainer: for MT/Level-M/Level-T outputs",
        "- dataset_status_assistant: for label/adapter readiness",
        "- intervention_safety_review: for target injection artifacts",
        "- paper_outline_generator: for plan/report docs",
        "- ontology_safe_mode: for quarantined artifacts (do not promote)",
        "",
        "## Quarantined Artifacts",
        "",
        f"**Count:** {len(quarantined)}",
        "",
        "Quarantined artifacts must not be indexed until banned phrases are removed",
        "and human review confirms safe framing.",
        "",
        "## Next Ingestion Batch",
        "",
        "Run mock fixture first to validate output shape, then scan real outputs.",
    ]
    (out_dir / "rag_ingestion_plan.md").write_text("\n".join(plan_lines), encoding="utf-8")

    # report.md
    report_lines = [
        "# Awareness Research RAG Artifact Manifest",
        "",
        f"**Generated:** {generated_at}",
        f"**Root scanned:** {scan_root}",
        "",
        "## Stage",
        "",
        "P20.0 — artifact manifest builder. Not embeddings. Not OpenAI. Not Notion.",
        "",
        "## Artifact Counts",
        "",
        f"- Total: {len(records)}",
        f"- Safe: {len(safe)}",
        f"- Quarantined: {len(quarantined)}",
        f"- Priority 1: {priorities.get('1', 0)}",
        f"- Priority 2: {priorities.get('2', 0)}",
        f"- Priority 3: {priorities.get('3', 0)}",
        "",
        "## Priority Summary",
        "",
        "Priority 1 artifacts are recommended for the first RAG indexing batch.",
        "All metrics are candidate proxies only.",
        "",
        "## Quarantined Artifacts",
        "",
        f"**{len(quarantined)} artifact(s) quarantined** — contained language requiring human review.",
        "See quarantined_artifacts.json for details.",
        "",
        "## Recommended First RAG Batch",
        "",
    ]
    for r in first_batch:
        report_lines.append(f"- `{r.relative_path}`")
    report_lines += [
        "",
        "## Safe Claim",
        "",
        SAFE_CLAIM,
        "",
        "## Forbidden Claims / Guardrails",
        "",
        "This manifest does not assert measurement-based proof of awareness, soul,",
        "liberation, afterlife, enlightenment, or ontology. All metrics are candidate",
        "proxies only. Human review is required before claim elevation.",
        "",
        "## Next Required Step",
        "",
        "Human review of quarantined artifacts and priority-1 artifacts before live chatbot ingestion.",
    ]
    (out_dir / "report.md").write_text("\n".join(report_lines), encoding="utf-8")
