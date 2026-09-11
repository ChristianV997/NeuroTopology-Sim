"""Manifest loader and ingestion pipelines for the Awareness Studio evidence graph.

Supports:
- Unified multi-section JSON manifests.
- Awareness Studio multi-file manifests (section paths).
- Line-delimited JSONL record streams.
- Standalone nodes and edges lists.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .builder import EvidenceGraphBuilder
from .models import EvidenceGraph, GraphEdge, GraphNode, compute_content_checksum
from .types import (
    EdgeType,
    EvidenceClass,
    NodeStatus,
    NodeType,
    SafetyLabel,
)


def _classify_evidence(data: Mapping[str, Any]) -> str:
    """Infer evidence class from record metadata without claim promotion."""
    if data.get("is_synthetic") or data.get("data_mode") == "synthetic":
        return EvidenceClass.SYNTHETIC.value
    if data.get("is_proxy") or data.get("data_type") == "proxy_bayes_factor":
        return EvidenceClass.PROXY.value
    if data.get("is_formal") or data.get("evidence_class") == "formal":
        # Only true formal if preregistered, held out locked, and not synthetic
        if data.get("preregistered", False) and data.get("held_out_split_locked", False):
            return EvidenceClass.FORMAL.value
        return EvidenceClass.EMPIRICAL.value
    if data.get("data_mode") == "empirical" or data.get("data_type") == "empirical_dataset":
        return EvidenceClass.EMPIRICAL.value
    ev_cls = data.get("evidence_class")
    if ev_cls in (e.value for e in EvidenceClass):
        return ev_cls
    return EvidenceClass.UNKNOWN.value


def load_from_dict(
    data: Mapping[str, Any],
    builder: EvidenceGraphBuilder | None = None,
    base_dir: Path | None = None,
) -> EvidenceGraph:
    """Construct an EvidenceGraph from an in-memory manifest dictionary."""
    if builder is None:
        builder = EvidenceGraphBuilder(metadata=data.get("metadata", {}))

    # 1. Direct nodes list if provided
    if "nodes" in data and isinstance(data["nodes"], list):
        for raw_node in data["nodes"]:
            if not isinstance(raw_node, dict) or "node_id" not in raw_node:
                continue
            builder.add_node(
                GraphNode(
                    node_id=str(raw_node["node_id"]),
                    node_type=raw_node.get("node_type", NodeType.EVIDENCE_RECORD.value),
                    label=raw_node.get("label", str(raw_node["node_id"])),
                    status=raw_node.get("status", NodeStatus.ACTIVE.value),
                    evidence_class=raw_node.get("evidence_class", EvidenceClass.UNKNOWN.value),
                    safety_labels=raw_node.get("safety_labels", []),
                    properties=raw_node.get("properties", {}),
                    source_id=raw_node.get("source_id"),
                    checksum=raw_node.get("checksum", ""),
                    tags=raw_node.get("tags", []),
                )
            )

    # 2. Direct edges list if provided
    if "edges" in data and isinstance(data["edges"], list):
        for raw_edge in data["edges"]:
            if not isinstance(raw_edge, dict) or "source_id" not in raw_edge or "target_id" not in raw_edge:
                continue
            builder.link(
                edge_type=raw_edge.get("edge_type", EdgeType.REFERENCES.value),
                source_id=str(raw_edge["source_id"]),
                target_id=str(raw_edge["target_id"]),
                label=raw_edge.get("label", ""),
                confidence=raw_edge.get("confidence"),
                metadata=raw_edge.get("metadata"),
            )

    # 3. Sources
    sources = data.get("sources", data.get("literature_evidence", {}).get("sources", []))
    if isinstance(sources, list):
        for s in sources:
            if not isinstance(s, dict) or "source_id" not in s:
                continue
            sid = str(s["source_id"])
            builder.add_node(
                GraphNode(
                    node_id=sid,
                    node_type=NodeType.SOURCE_SNAPSHOT.value,
                    label=s.get("title") or sid,
                    status=s.get("status", NodeStatus.ACTIVE.value),
                    evidence_class=EvidenceClass.EMPIRICAL.value,
                    properties=s,
                    source_id=sid,
                    tags=list(s.get("tags", [])),
                )
            )

    # 4. Claims
    claims = data.get("claims", data.get("literature_evidence", {}).get("claims", []))
    if isinstance(claims, list):
        for c in claims:
            if not isinstance(c, dict) or "claim_id" not in c:
                continue
            cid = str(c["claim_id"])
            sid = c.get("source_id")
            builder.add_node(
                GraphNode(
                    node_id=cid,
                    node_type=NodeType.CLAIM.value,
                    label=c.get("claim_text") or cid,
                    status=c.get("claim_status", NodeStatus.PROPOSED.value),
                    evidence_class=c.get("evidence_class", EvidenceClass.UNKNOWN.value),
                    properties=c,
                    source_id=sid,
                )
            )
            if sid:
                builder.link(EdgeType.DERIVED_FROM, cid, str(sid), label="derived_from_source")
            if c.get("linked_hypothesis"):
                builder.link(EdgeType.SUPPORTS, cid, str(c["linked_hypothesis"]), label="supports_hypothesis")

    # 5. Hypotheses
    hypotheses = data.get("hypotheses", data.get("hypothesis_registry", {}).get("hypotheses", []))
    if isinstance(hypotheses, list):
        for h in hypotheses:
            if not isinstance(h, dict) or "hypothesis_id" not in h:
                continue
            hid = str(h["hypothesis_id"])
            builder.add_node(
                GraphNode(
                    node_id=hid,
                    node_type=NodeType.HYPOTHESIS.value,
                    label=h.get("precise_claim") or h.get("statement") or hid,
                    status=h.get("status", NodeStatus.PROPOSED.value),
                    evidence_class=EvidenceClass.UNKNOWN.value,
                    properties=h,
                    source_id=h.get("provenance", {}).get("source_id") if isinstance(h.get("provenance"), dict) else None,
                )
            )
            # Link claim IDs
            for cid in h.get("claim_ids", []):
                builder.link(EdgeType.DERIVED_FROM, hid, str(cid), label="grounded_in_claim")
            # Link evidence links
            for eid in h.get("evidence_links", []):
                builder.link(EdgeType.SUPPORTS, str(eid), hid, label="supports_hypothesis")
            for ceid in h.get("contradictory_evidence_links", []):
                builder.link(EdgeType.CONTRADICTS, str(ceid), hid, label="contradicts_hypothesis")
            # Link blockers
            for bid in h.get("blocked_by", []):
                builder.link(EdgeType.BLOCKED_BY, hid, str(bid), label="blocked_by")

    # 6. Experiments / Plans
    experiments = data.get("experiments", data.get("plans", data.get("experiment_plans", {}).get("plans", [])))
    if isinstance(experiments, list):
        for exp in experiments:
            if not isinstance(exp, dict) or ("experiment_id" not in exp and "plan_id" not in exp):
                continue
            eid = str(exp.get("experiment_id") or exp.get("plan_id"))
            hid = exp.get("hypothesis_id")
            builder.add_node(
                GraphNode(
                    node_id=eid,
                    node_type=NodeType.EXPERIMENT.value,
                    label=exp.get("domain", eid),
                    status=NodeStatus.ACTIVE.value,
                    evidence_class=_classify_evidence(exp),
                    properties=exp,
                )
            )
            if hid:
                builder.link(EdgeType.TESTS, eid, str(hid), label="tests_hypothesis")

    # 7. Runs / Executions
    runs = data.get("runs", data.get("executions", data.get("execution_results", {}).get("executions", [])))
    if isinstance(runs, list):
        for r in runs:
            if not isinstance(r, dict) or ("run_id" not in r and "execution_id" not in r):
                continue
            rid = str(r.get("run_id") or r.get("execution_id"))
            exp_id = r.get("experiment_id") or r.get("spec_id")
            builder.add_node(
                GraphNode(
                    node_id=rid,
                    node_type=NodeType.RUN.value,
                    label=f"Run {rid} ({r.get('data_mode', 'sim')})",
                    status=r.get("verdict", NodeStatus.ACTIVE.value).lower(),
                    evidence_class=_classify_evidence(r),
                    properties=r,
                )
            )
            if exp_id:
                builder.link(EdgeType.TESTS, rid, str(exp_id), label="executes_plan")
            # Artifacts generated by run
            raw_artifacts = r.get("artifacts")
            if isinstance(raw_artifacts, dict):
                for art_key, art_val in raw_artifacts.items():
                    art_id = f"art:{rid}:{art_key}"
                    builder.add_node(
                        GraphNode(
                            node_id=art_id,
                            node_type=NodeType.ARTIFACT.value,
                            label=art_key,
                            properties={"path": art_val, "run_id": rid},
                        )
                    )
                    builder.link(EdgeType.GENERATED_BY, art_id, rid, label="generated_by_run")

    # 8. Artifacts list
    artifacts = data.get("artifacts", [])
    if isinstance(artifacts, list):
        for art in artifacts:
            if not isinstance(art, dict) or "artifact_id" not in art:
                continue
            aid = str(art["artifact_id"])
            builder.add_node(
                GraphNode(
                    node_id=aid,
                    node_type=NodeType.ARTIFACT.value,
                    label=art.get("label", aid),
                    properties=art,
                )
            )
            if art.get("generator_id") or art.get("run_id"):
                gen_id = str(art.get("generator_id") or art.get("run_id"))
                builder.link(EdgeType.GENERATED_BY, aid, gen_id, label="generated_by")
            if art.get("validates_id"):
                builder.link(EdgeType.VALIDATES, aid, str(art["validates_id"]), label="validates_target")

    # 9. Validations / Reports
    validations = data.get("validations", data.get("reports", data.get("validation_reports", {}).get("reports", [])))
    if isinstance(validations, list):
        for val in validations:
            if not isinstance(val, dict) or "validation_id" not in val:
                continue
            vid = str(val["validation_id"])
            verdict = str(val.get("verdict", "PASS")).upper()
            status = NodeStatus.SUPPORTED.value if verdict == "PASS" else NodeStatus.FALSIFIED.value
            builder.add_node(
                GraphNode(
                    node_id=vid,
                    node_type=NodeType.VALIDATION.value,
                    label=f"Validation: {val.get('check_name', vid)}",
                    status=status,
                    evidence_class=EvidenceClass.EMPIRICAL.value,
                    properties=val,
                )
            )
            if val.get("target_id") or val.get("run_id"):
                target = str(val.get("target_id") or val.get("run_id"))
                builder.link(EdgeType.VALIDATES, vid, target, label="validates_target")
            if val.get("hypothesis_id"):
                hid = str(val["hypothesis_id"])
                if verdict == "PASS":
                    builder.link(EdgeType.SUPPORTS, vid, hid, label="validation_passed")
                else:
                    builder.link(EdgeType.CONTRADICTS, vid, hid, label="validation_failed")

    # 10. Theory Revisions
    revisions = data.get("theory_revisions", data.get("revisions", []))
    if isinstance(revisions, list):
        for rev in revisions:
            if not isinstance(rev, dict) or "revision_id" not in rev:
                continue
            revid = str(rev["revision_id"])
            hid = rev.get("hypothesis_id")
            builder.add_node(
                GraphNode(
                    node_id=revid,
                    node_type=NodeType.THEORY_REVISION.value,
                    label=f"Revision {revid} -> {rev.get('new_status', '')}",
                    status=NodeStatus.ACTIVE.value,
                    properties=rev,
                )
            )
            if hid:
                builder.link(EdgeType.REVISES, revid, str(hid), label="revises_hypothesis")
            if rev.get("supersedes_id"):
                builder.link(EdgeType.SUPERSEDES, revid, str(rev["supersedes_id"]), label="supersedes")

    # 11. Evidence records / updates
    evidence_items = data.get("evidence", data.get("evidence_records", data.get("evidence_updates", [])))
    if isinstance(evidence_items, list):
        for ev in evidence_items:
            if not isinstance(ev, dict) or "evidence_id" not in ev:
                continue
            evid = str(ev["evidence_id"])
            hid = ev.get("hypothesis_id")
            is_contra = bool(ev.get("is_contradictory", False))
            ev_class = _classify_evidence(ev)
            builder.add_node(
                GraphNode(
                    node_id=evid,
                    node_type=NodeType.EVIDENCE_RECORD.value,
                    label=f"Evidence {evid}",
                    status=NodeStatus.CONTRADICTED.value if is_contra else NodeStatus.ACTIVE.value,
                    evidence_class=ev_class,
                    properties=ev,
                    source_id=ev.get("source_ids", [None])[0] if ev.get("source_ids") else ev.get("source_id"),
                )
            )
            if hid:
                edge_type = EdgeType.CONTRADICTS if is_contra else EdgeType.SUPPORTS
                builder.link(edge_type, evid, str(hid), label="evidentiary_link")
            if ev.get("experiment_id"):
                builder.link(EdgeType.DERIVED_FROM, evid, str(ev["experiment_id"]), label="derived_from_experiment")
            if ev.get("source_id"):
                builder.link(EdgeType.REFERENCES, evid, str(ev["source_id"]), label="references_source")

    return builder.build()


def load_from_jsonl(
    jsonl_content_or_path: Path | str,
    builder: EvidenceGraphBuilder | None = None,
) -> EvidenceGraph:
    """Load graph projection from a line-delimited JSON stream or file."""
    if builder is None:
        builder = EvidenceGraphBuilder()

    lines: list[str] = []
    if isinstance(jsonl_content_or_path, Path) or (isinstance(jsonl_content_or_path, str) and "\n" not in jsonl_content_or_path and Path(jsonl_content_or_path).is_file()):
        lines = Path(jsonl_content_or_path).read_text(encoding="utf-8").splitlines()
    else:
        lines = str(jsonl_content_or_path).splitlines()

    for line in lines:
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#"):
            continue
        try:
            record = json.loads(line_clean)
        except json.JSONDecodeError:
            continue

        if not isinstance(record, dict):
            continue

        if "edge_type" in record and "source_id" in record and "target_id" in record:
            builder.link(
                edge_type=record["edge_type"],
                source_id=str(record["source_id"]),
                target_id=str(record["target_id"]),
                label=record.get("label", ""),
                confidence=record.get("confidence"),
                metadata=record.get("metadata"),
            )
        elif "node_type" in record and "node_id" in record:
            builder.add_node(
                GraphNode(
                    node_id=str(record["node_id"]),
                    node_type=record["node_type"],
                    label=record.get("label", str(record["node_id"])),
                    status=record.get("status", NodeStatus.ACTIVE.value),
                    evidence_class=record.get("evidence_class", EvidenceClass.UNKNOWN.value),
                    safety_labels=record.get("safety_labels", []),
                    properties=record.get("properties", {}),
                    source_id=record.get("source_id"),
                    checksum=record.get("checksum", ""),
                    tags=record.get("tags", []),
                )
            )
        else:
            # Try loading as single item dictionary
            load_from_dict({"evidence": [record]} if "evidence_id" in record else {"nodes": [record]}, builder=builder)

    return builder.build()


def load_manifest_file(manifest_path: Path | str) -> EvidenceGraph:
    """Resolve and load a manifest file (.json or .jsonl)."""
    path = Path(manifest_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {path}")

    text = path.read_text(encoding="utf-8")
    if path.suffix in (".jsonl", ".ndjson"):
        return load_from_jsonl(text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Fallback to jsonl attempt
        return load_from_jsonl(text)

    if not isinstance(data, dict):
        raise ValueError(f"Expected root JSON object in manifest '{path}', got {type(data).__name__}")

    return load_from_dict(data, base_dir=path.parent)
