#!/usr/bin/env python3
"""P20.1 Awareness Research RAG ingestion pack builder (stdlib only)."""

from __future__ import annotations

import csv
import datetime
import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

SAFE_CLAIM = (
    "BTC/ICFT artifacts remain candidate proxy and operational telemetry evidence only; "
    "human review is required before any empirical or ontological interpretation."
)
DEFAULT_MAX_CHARS_PER_CHUNK = 1800
DEFAULT_OVERLAP_CHARS = 200
DEFAULT_INCLUDE_PRIORITY_MAX = 3
WITHHOLD_PREFIX = "withhold_chunk::"

SCIENTIFIC_GUARDRAILS: tuple[str, ...] = (
    "Do not claim EEG/topology/Q/Q_abs/f_dress prove consciousness, self, soul, liberation, afterlife, enlightenment, or ontology.",
    "Use controlled benchmark framing with human-review-required provenance.",
    "Treat all outputs as claim-safe retrieval context, not ontology proof.",
)

CHUNK_FIELDS: tuple[str, ...] = (
    "chunk_id",
    "artifact_id",
    "source_path",
    "relative_path",
    "file_type",
    "stage",
    "dataset_id",
    "evidence_state",
    "claim_safety_status",
    "index_priority",
    "recommended_rag_mode",
    "chunk_role",
    "chunk_text",
    "source_summary",
    "safe_claim",
    "required_context",
    "forbidden_claims_found",
    "retrieval_tags",
    "guardrails",
    "next_action",
)

TEXT_EXTS = {"md", "txt", "json", "jsonl", "yaml", "yml", "csv", "tsv"}


@dataclass
class IngestionChunk:
    chunk_id: str
    artifact_id: str
    source_path: str
    relative_path: str
    file_type: str
    stage: str
    dataset_id: str
    evidence_state: str
    claim_safety_status: str
    index_priority: int
    recommended_rag_mode: str
    chunk_role: str
    chunk_text: str
    source_summary: str
    safe_claim: str
    required_context: str
    forbidden_claims_found: list[str]
    retrieval_tags: list[str]
    guardrails: list[str]
    next_action: str

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "artifact_id": self.artifact_id,
            "source_path": self.source_path,
            "relative_path": self.relative_path,
            "file_type": self.file_type,
            "stage": self.stage,
            "dataset_id": self.dataset_id,
            "evidence_state": self.evidence_state,
            "claim_safety_status": self.claim_safety_status,
            "index_priority": self.index_priority,
            "recommended_rag_mode": self.recommended_rag_mode,
            "chunk_role": self.chunk_role,
            "chunk_text": self.chunk_text,
            "source_summary": self.source_summary,
            "safe_claim": self.safe_claim,
            "required_context": self.required_context,
            "forbidden_claims_found": list(self.forbidden_claims_found),
            "retrieval_tags": list(self.retrieval_tags),
            "guardrails": list(self.guardrails),
            "next_action": self.next_action,
        }


def _hash16(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _detect_chunk_role(record: dict) -> str:
    relative_path_lower = str(record.get("relative_path", "")).lower()
    file_name = Path(relative_path_lower).name
    stage = str(record.get("stage", "unknown"))
    file_type = str(record.get("file_type", ""))
    status = str(record.get("claim_safety_status", ""))

    if status != "safe":
        return "quarantine_notice"
    if "runbook" in file_name:
        return "runbook_context"
    if "rag_artifact_manifest" in file_name:
        return "artifact_manifest"
    if file_name == "report.md":
        return "report_summary"
    if file_name == "omega_event.json":
        return "omega_event"
    if file_name.endswith(".yaml") or file_name.endswith(".yml") or stage == "configs":
        return "config_context"
    if "metric" in file_name or "metrics" in file_name or file_type in {"csv", "tsv"}:
        return "metrics_snapshot"
    if stage in {"eeg_labels", "label_adapter_readiness", "label_contract_drafts"}:
        return "dataset_status"
    if stage in {"eeg_signal_mt", "eeg_level_m", "eeg_level_t", "signal_blocks"}:
        return "topology_metric_context"
    if "claim" in file_name or "governance" in file_name:
        return "claim_governance_context"
    return "unknown"


def _read_manifest_jsonl(path: Path, max_artifacts: int | None = None) -> list[dict]:
    records: list[dict] = []
    if not path.is_file():
        return records
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if max_artifacts is not None and i >= max_artifacts:
            break
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _load_source_text(record: dict, artifact_root: Path) -> str:
    source_path = Path(str(record.get("path", "")))
    relative_path = Path(str(record.get("relative_path", "")))

    candidate_paths = [source_path]
    if not source_path.is_file() and relative_path:
        candidate_paths.append(artifact_root / relative_path)
        if str(relative_path).startswith("docs/"):
            candidate_paths.append(artifact_root.parent / relative_path)

    for path in candidate_paths:
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return ""
    return ""


def _chunk_text(text: str, max_chars_per_chunk: int, overlap_chars: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if max_chars_per_chunk <= 0:
        max_chars_per_chunk = DEFAULT_MAX_CHARS_PER_CHUNK
    if overlap_chars < 0:
        overlap_chars = 0
    if overlap_chars >= max_chars_per_chunk:
        overlap_chars = max_chars_per_chunk // 4

    chunks: list[str] = []
    start = 0
    step = max(1, max_chars_per_chunk - overlap_chars)
    while start < len(text):
        end = min(len(text), start + max_chars_per_chunk)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start += step
    return chunks


def _build_retrieval_tags(record: dict, role: str) -> list[str]:
    dataset = str(record.get("dataset_id", "unknown"))
    stage = str(record.get("stage", "unknown"))
    evidence = str(record.get("evidence_state", "unknown"))
    mode = str(record.get("recommended_rag_mode", "artifact_explainer"))
    safety = str(record.get("claim_safety_status", "safe"))
    priority = str(record.get("index_priority", 5))
    return [
        f"dataset:{dataset}",
        f"stage:{stage}",
        f"evidence_state:{evidence}",
        f"rag_mode:{mode}",
        f"chunk_role:{role}",
        f"claim_safety:{safety}",
        f"index_priority:{priority}",
    ]


def _is_chunk_indexable(record: dict, include_priority_max: int, include_quarantined: bool) -> tuple[bool, str]:
    status = str(record.get("claim_safety_status", "safe"))
    priority = int(record.get("index_priority", 5))
    if status != "safe" and not include_quarantined:
        return False, "quarantined"
    if priority > include_priority_max:
        return False, "priority_excluded"
    return True, "included"


def build_ingestion_pack(
    manifest_path: Path,
    artifact_root: Path,
    docs_root: Path,
    out_dir: Path,
    max_chars_per_chunk: int = DEFAULT_MAX_CHARS_PER_CHUNK,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    max_artifacts: int | None = None,
    include_priority_max: int = DEFAULT_INCLUDE_PRIORITY_MAX,
    include_quarantined: bool = False,
) -> dict:
    generated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    records = _read_manifest_jsonl(manifest_path, max_artifacts=max_artifacts)
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks: list[IngestionChunk] = []
    withheld_rows: list[dict] = []
    blockers: list[str] = []

    if not manifest_path.is_file():
        blockers.append("rag_manifest_missing")

    for record in records:
        role = _detect_chunk_role(record)
        source_text = _load_source_text(record, artifact_root)
        piece_list = _chunk_text(source_text, max_chars_per_chunk=max_chars_per_chunk, overlap_chars=overlap_chars)
        include, include_reason = _is_chunk_indexable(record, include_priority_max, include_quarantined)

        if not piece_list:
            withheld_rows.append(
                {
                    "artifact_id": record.get("artifact_id", "unknown"),
                    "relative_path": record.get("relative_path", ""),
                    "reason": "empty_or_unreadable_source",
                    "claim_safety_status": record.get("claim_safety_status", "unknown"),
                    "index_priority": record.get("index_priority", 5),
                }
            )
            continue

        if not include:
            withheld_rows.append(
                {
                    "artifact_id": record.get("artifact_id", "unknown"),
                    "relative_path": record.get("relative_path", ""),
                    "reason": include_reason,
                    "claim_safety_status": record.get("claim_safety_status", "unknown"),
                    "index_priority": record.get("index_priority", 5),
                }
            )

        for index, piece in enumerate(piece_list):
            chunk_id = "chk_" + _hash16(f"{record.get('artifact_id', 'unknown')}::{index}::{piece[:64]}")
            chunk = IngestionChunk(
                chunk_id=chunk_id,
                artifact_id=str(record.get("artifact_id", "unknown")),
                source_path=str(record.get("path", "")),
                relative_path=str(record.get("relative_path", "")),
                file_type=str(record.get("file_type", "unknown")),
                stage=str(record.get("stage", "unknown")),
                dataset_id=str(record.get("dataset_id", "unknown")),
                evidence_state=str(record.get("evidence_state", "unknown")),
                claim_safety_status=str(record.get("claim_safety_status", "safe")),
                index_priority=int(record.get("index_priority", 5)),
                recommended_rag_mode=str(record.get("recommended_rag_mode", "artifact_explainer")),
                chunk_role=role,
                chunk_text=piece,
                source_summary=str(record.get("summary", ""))[:500],
                safe_claim=str(record.get("safe_claim") or SAFE_CLAIM),
                required_context=(
                    f"{record.get('required_context', 'standard_artifact')}; "
                    "claim-safe retrieval pack; human review required before promotion"
                ),
                forbidden_claims_found=list(record.get("forbidden_claims_found", [])),
                retrieval_tags=_build_retrieval_tags(record, role),
                guardrails=list(SCIENTIFIC_GUARDRAILS),
                next_action=(
                    str(record.get("next_action", "index_in_scheduled_batch"))
                    if include
                    else f"{WITHHOLD_PREFIX}{include_reason}"
                ),
            )
            chunks.append(chunk)

    # Outputs
    chunk_dicts: list[dict] = []
    included_chunks: list[dict] = []
    quarantined_chunks: list[dict] = []
    for chunk in chunks:
        payload = chunk.to_dict()
        chunk_dicts.append(payload)
        if payload["claim_safety_status"] != "safe":
            quarantined_chunks.append(payload)
        if payload["claim_safety_status"] == "safe" and payload["index_priority"] <= include_priority_max:
            included_chunks.append(payload)

    with (out_dir / "rag_ingestion_chunks.jsonl").open("w", encoding="utf-8") as fh:
        for chunk in chunk_dicts:
            fh.write(json.dumps(chunk) + "\n")

    manifest = {
        "schema_version": "0.1",
        "generated_at": generated_at,
        "source_manifest": str(manifest_path),
        "artifact_root": str(artifact_root),
        "docs_root": str(docs_root),
        "counts": {
            "artifacts_seen": len(records),
            "chunks_total": len(chunk_dicts),
            "chunks_included": len(included_chunks),
            "chunks_quarantined": len(quarantined_chunks),
            "chunks_withheld": len(withheld_rows),
        },
        "params": {
            "max_chars_per_chunk": max_chars_per_chunk,
            "overlap_chars": overlap_chars,
            "max_artifacts": max_artifacts,
            "include_priority_max": include_priority_max,
            "include_quarantined": include_quarantined,
        },
        "required_chunk_fields": list(CHUNK_FIELDS),
        "blockers": blockers,
        "safe_claim": SAFE_CLAIM,
    }
    (out_dir / "rag_ingestion_pack.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with (out_dir / "rag_ingestion_index.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "chunk_id",
                "artifact_id",
                "relative_path",
                "dataset_id",
                "stage",
                "claim_safety_status",
                "index_priority",
                "chunk_role",
                "recommended_rag_mode",
                "next_action",
            ],
        )
        writer.writeheader()
        for chunk in chunk_dicts:
            writer.writerow(
                {
                    "chunk_id": chunk["chunk_id"],
                    "artifact_id": chunk["artifact_id"],
                    "relative_path": chunk["relative_path"],
                    "dataset_id": chunk["dataset_id"],
                    "stage": chunk["stage"],
                    "claim_safety_status": chunk["claim_safety_status"],
                    "index_priority": chunk["index_priority"],
                    "chunk_role": chunk["chunk_role"],
                    "recommended_rag_mode": chunk["recommended_rag_mode"],
                    "next_action": chunk["next_action"],
                }
            )

    (out_dir / "withheld_or_quarantined_chunks.json").write_text(
        json.dumps(
            {
                "withheld_artifacts": withheld_rows,
                "quarantined_chunks": quarantined_chunks,
                "action": "human_review_required",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (out_dir / "omega_event.json").write_text(
        json.dumps(
            {
                "event_type": "awareness_rag_ingestion_pack_built",
                "generated_at": generated_at,
                "safe_claim": SAFE_CLAIM,
                "no_external_api_called": True,
                "no_embeddings_created": True,
                "no_vector_db_used": True,
                "manifest_missing": "rag_manifest_missing" in blockers,
                "chunks_total": len(chunk_dicts),
                "chunks_included": len(included_chunks),
                "chunks_withheld": len(withheld_rows),
                "chunks_quarantined": len(quarantined_chunks),
                "blockers": blockers,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    report_lines = [
        "# Awareness RAG Ingestion Pack Report",
        "",
        f"**Generated:** {generated_at}",
        f"**Source manifest:** `{manifest_path}`",
        "",
        "## Summary",
        "",
        f"- Artifacts seen: {len(records)}",
        f"- Chunks built: {len(chunk_dicts)}",
        f"- Chunks included: {len(included_chunks)}",
        f"- Chunks withheld: {len(withheld_rows)}",
        f"- Quarantined chunks: {len(quarantined_chunks)}",
        "",
        "## Guardrails",
        "",
        "- Deterministic local stdlib-only packaging.",
        "- No external API calls, embeddings, or vector DB setup.",
        "- Human review required for withheld/quarantined material.",
        "",
        "## Safe Claim",
        "",
        SAFE_CLAIM,
    ]
    if blockers:
        report_lines += ["", "## Blockers", ""] + [f"- {b}" for b in blockers]
    (out_dir / "report.md").write_text("\n".join(report_lines), encoding="utf-8")

    return manifest


def create_mock_fixture_manifest(tmp_dir: Path) -> tuple[Path, Path]:
    """Create deterministic P20.0-style manifest + source artifacts in temp dir."""
    root = tmp_dir / "mock_outputs" / "btc_icft"
    out_manifest = tmp_dir / "mock_outputs" / "rag_manifest"
    root.mkdir(parents=True, exist_ok=True)
    out_manifest.mkdir(parents=True, exist_ok=True)

    artifacts: list[dict] = []

    def _add_artifact(relative_path: str, payload: str, *, file_type: str, stage: str, dataset_id: str, safety: str, priority: int, mode: str, forbidden: list[str] | None = None, summary: str = "") -> None:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        artifact_id = "art_" + _hash16(relative_path)
        artifacts.append(
            {
                "artifact_id": artifact_id,
                "path": str(path),
                "relative_path": relative_path,
                "file_type": file_type,
                "size_bytes": len(payload.encode("utf-8")),
                "stage": stage,
                "dataset_id": dataset_id,
                "evidence_state": "mock_fixture",
                "claim_safety_status": safety,
                "index_priority": priority,
                "title": Path(relative_path).stem,
                "summary": summary or f"mock {Path(relative_path).name}",
                "safe_claim": SAFE_CLAIM,
                "forbidden_claims_found": forbidden or [],
                "recommended_rag_mode": mode,
                "required_context": "mock_data_only_not_empirical",
                "next_action": "index_as_mock_with_provenance_label",
            }
        )

    _add_artifact(
        "report.md",
        "# Report\n\nCandidate proxy summary for controlled benchmark telemetry.",
        file_type="md",
        stage="eeg_signal_mt",
        dataset_id="DS005620",
        safety="safe",
        priority=1,
        mode="artifact_explainer",
        summary="mock report",
    )
    _add_artifact(
        "omega_event.json",
        json.dumps({"event_type": "mock", "safe_claim": SAFE_CLAIM, "no_external_api_called": True}),
        file_type="json",
        stage="target_aware_activation",
        dataset_id="DS005620",
        safety="safe",
        priority=1,
        mode="claim_card_generator",
        summary="mock omega event",
    )
    _add_artifact(
        "metrics_signal_mt.json",
        json.dumps({"q": 0.1, "q_abs": 0.2, "f_dress": 0.01, "safe_claim": "candidate proxy"}),
        file_type="json",
        stage="eeg_signal_mt",
        dataset_id="DS005620",
        safety="safe",
        priority=2,
        mode="topology_metric_explainer",
        summary="mock metrics",
    )
    _add_artifact(
        "configs/awareness_rag_ingestion_pack.yaml",
        "dataset_scope: awareness_rag_ingestion_pack\npipeline_id: awareness_rag_ingestion_pack_v0\n",
        file_type="yaml",
        stage="configs",
        dataset_id="DS005620",
        safety="safe",
        priority=3,
        mode="artifact_explainer",
        summary="mock config",
    )
    _add_artifact(
        "quarantine/bad_claim.md",
        "eeg proves consciousness in this banned mock phrase",
        file_type="md",
        stage="docs",
        dataset_id="DS005620",
        safety="quarantined_banned_phrase",
        priority=5,
        mode="ontology_safe_mode",
        forbidden=["eeg proves consciousness"],
        summary="quarantined mock",
    )

    manifest_path = out_manifest / "rag_artifact_manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as fh:
        for artifact in artifacts:
            fh.write(json.dumps(artifact) + "\n")
    return manifest_path, root


def build_with_mock_fixture(
    out_dir: Path,
    max_chars_per_chunk: int = DEFAULT_MAX_CHARS_PER_CHUNK,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    max_artifacts: int | None = None,
    include_priority_max: int = DEFAULT_INCLUDE_PRIORITY_MAX,
    include_quarantined: bool = False,
) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        manifest_path, artifact_root = create_mock_fixture_manifest(tmp_path)
        return build_ingestion_pack(
            manifest_path=manifest_path,
            artifact_root=artifact_root,
            docs_root=tmp_path / "docs",
            out_dir=out_dir,
            max_chars_per_chunk=max_chars_per_chunk,
            overlap_chars=overlap_chars,
            max_artifacts=max_artifacts,
            include_priority_max=include_priority_max,
            include_quarantined=include_quarantined,
        )
