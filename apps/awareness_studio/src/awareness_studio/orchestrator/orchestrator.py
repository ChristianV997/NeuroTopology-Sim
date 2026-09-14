"""Orchestrator v0.1 — 9-stage dry-run pipeline.

All outputs are deterministic in dry-run mode.
No network or LLM calls required for dry_run=True.

Output layout per run:
  outputs/orchestrator/<run_id>/
    events.jsonl
    EvidenceLogDraft.md
    Report.md
    GraphUpdate.json
    OpsQueueItem.json
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .event_log import EventLog
from .event_model import EventEnvelope, PIPELINE_STAGES
from awareness_studio.research_cycle import (
    Claim,
    EvidenceClass,
    EvidenceRecord,
    ExperimentSpec as LedgerExperimentSpec,
    Hypothesis as LedgerHypothesis,
    ResearchCycleLedger,
    SourceSnapshot,
    sha256_json,
    stable_id,
)

logger = logging.getLogger(__name__)


# ── Config / result types ─────────────────────────────────────────────────────

@dataclass
class OrchestratorConfig:
    dry_run: bool = True
    seed: int = 42
    run_cards_dir: Optional[Path] = None   # where to look for *.run.json
    out_base_dir: Optional[Path] = None    # defaults to outputs/orchestrator/
    ledger_path: Optional[Path] = None     # defaults to <run>/research_cycle.sqlite3


@dataclass
class ExperimentSpec:
    spec_id: str
    hypothesis: str
    mode: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratorResult:
    run_id: str
    out_dir: Path
    stages_completed: List[str]
    stages_failed: List[str]
    dry_run: bool
    artifacts: Dict[str, Path] = field(default_factory=dict)
    error: Optional[str] = None
    execution_state: str = "REVIEW_REQUIRED"
    scientific_evidence: bool = False
    ledger_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "out_dir": str(self.out_dir),
            "stages_completed": self.stages_completed,
            "stages_failed": self.stages_failed,
            "dry_run": self.dry_run,
            "artifacts": {k: str(v) for k, v in self.artifacts.items()},
            "error": self.error,
            "execution_state": self.execution_state,
            "scientific_evidence": self.scientific_evidence,
            "ledger_path": str(self.ledger_path) if self.ledger_path else None,
        }


# ── Orchestrator ──────────────────────────────────────────────────────────────

class Orchestrator:
    def __init__(self, config: Optional[OrchestratorConfig] = None) -> None:
        self._cfg = config or OrchestratorConfig()

    def run_registered(self, request, registry, preflight_request, *, ledger_path: Path, now: str | None = None):
        """Execute an explicitly bound plan through canonical admission and runtime.

        Unlike the legacy template planning cycle, this entry point requires a
        complete caller-supplied plan and registered workload before execution.
        """
        from .registered_execution import execute_registered
        return execute_registered(request, registry, preflight_request, ledger_path, now=now)

    def run(
        self,
        dry_run: Optional[bool] = None,
        config: Optional[OrchestratorConfig] = None,
        _now: Optional[datetime] = None,
    ) -> OrchestratorResult:
        cfg = config or self._cfg
        if dry_run is not None:
            cfg = OrchestratorConfig(
                dry_run=dry_run,
                seed=cfg.seed,
                run_cards_dir=cfg.run_cards_dir,
                out_base_dir=cfg.out_base_dir,
                ledger_path=cfg.ledger_path,
            )

        now = _now or datetime.now(timezone.utc)
        run_id = self._make_run_id(cfg, now)

        from awareness_studio import config as app_config
        out_base = cfg.out_base_dir or (app_config.APP_ROOT / "outputs" / "orchestrator")
        out_dir = out_base / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        log = EventLog(out_dir)
        ledger_path = cfg.ledger_path or (out_dir / "research_cycle.sqlite3")
        ledger = ResearchCycleLedger(ledger_path)
        ledger_metadata = {"seed": cfg.seed, "dry_run": cfg.dry_run, "run_cards_dir": str(cfg.run_cards_dir) if cfg.run_cards_dir else None}
        ledger.create_cycle(run_id, metadata=ledger_metadata, producer="awareness_studio.orchestrator")
        self._seed_research_cycle(ledger, run_id, cfg, ledger_metadata)
        stages_completed: List[str] = []
        stages_failed: List[str] = []
        artifacts: Dict[str, Path] = {}
        context: Dict[str, Any] = {}

        stage_fns = {
            "ingest_inputs":      self._stage_ingest_inputs,
            "propose_hypotheses": self._stage_propose_hypotheses,
            "plan_experiments":   self._stage_plan_experiments,
            "execute":            self._stage_execute,
            "fable_reasoning":    self._stage_fable_reasoning,
            "validate":           self._stage_validate,
            "digest":             self._stage_digest,
            "draft_report":       self._stage_draft_report,
            "ops_update":         self._stage_ops_update,
        }

        for stage in PIPELINE_STAGES:
            fn = stage_fns[stage]
            t0 = time.monotonic()
            ledger.append_event(
                run_id,
                "orchestrator_stage",
                producer="awareness_studio.orchestrator",
                status="IN_PROGRESS",
                payload={"stage": stage, "dry_run": cfg.dry_run},
            )
            log.append(EventEnvelope.make(run_id, stage, "start", _now=now))
            try:
                result = fn(run_id, cfg, out_dir, context, _now=now)
                dur = (time.monotonic() - t0) * 1000
                context[stage] = result
                artifacts.update(result.get("artifacts", {}))
                self._record_stage_result(ledger, run_id, stage, result, cfg, context)
                log.append(EventEnvelope.make(
                    run_id, stage, "ok",
                    payload={k: str(v) if isinstance(v, Path) else v
                             for k, v in result.items() if k != "artifacts"},
                    duration_ms=round(dur, 1),
                    _now=now,
                ))
                stages_completed.append(stage)
                ledger.append_event(
                    run_id,
                    "orchestrator_stage",
                    producer="awareness_studio.orchestrator",
                    status="COMPLETED",
                    payload={"stage": stage, "result": self._ledger_safe(result)},
                )
            except Exception as exc:
                dur = (time.monotonic() - t0) * 1000
                logger.exception("[orchestrator] stage %s failed", stage)
                log.append(EventEnvelope.make(
                    run_id, stage, "error",
                    error=str(exc),
                    duration_ms=round(dur, 1),
                    _now=now,
                ))
                stages_failed.append(stage)
                ledger.append_event(
                    run_id,
                    "orchestrator_stage",
                    producer="awareness_studio.orchestrator",
                    status="FAILED",
                    payload={"stage": stage, "reason": str(exc)},
                )
                break

        artifacts["events_jsonl"] = log.path
        artifacts["research_cycle_sqlite"] = ledger_path
        return OrchestratorResult(
            run_id=run_id,
            out_dir=out_dir,
            stages_completed=stages_completed,
            stages_failed=stages_failed,
            dry_run=cfg.dry_run,
            artifacts=artifacts,
            execution_state="REVIEW_REQUIRED" if cfg.dry_run else "NOT_IMPLEMENTED",
            scientific_evidence=False,
            ledger_path=ledger_path,
        )

    @staticmethod
    def _ledger_safe(value: Any) -> Any:
        if isinstance(value, Path):
            return value.as_posix()
        if isinstance(value, dict):
            return {str(key): Orchestrator._ledger_safe(item) for key, item in value.items() if key != "artifacts"}
        if isinstance(value, list):
            return [Orchestrator._ledger_safe(item) for item in value]
        return value

    def _seed_research_cycle(self, ledger: ResearchCycleLedger, run_id: str, cfg: OrchestratorConfig, metadata: Dict[str, Any]) -> None:
        limitations = ("Planning/interface evidence only; no scientific execution or conclusion is established.",)
        snapshot_id = stable_id("snapshot", {"cycle_id": run_id, "metadata": metadata})
        source_hash = sha256_json({"cycle_id": run_id, "metadata": metadata})
        ledger.append_record(run_id, SourceSnapshot(snapshot_id, run_id, "awareness_studio://orchestrator-config", source_hash, "planning", EvidenceClass.ENGINEERING_FACT, "Orchestrator configuration and planning only.", limitations, metadata={"synthetic_demo": False, "network_access": False}), producer="awareness_studio.orchestrator")
        evidence_id = stable_id("evidence", {"cycle_id": run_id, "snapshot_id": snapshot_id})
        ledger.append_record(run_id, EvidenceRecord(evidence_id, run_id, (snapshot_id,), "A research cycle was configured for planning; no measurement was executed.", "planning", EvidenceClass.ENGINEERING_FACT, "Planning/interface behavior only.", limitations, {"scientific_evidence": False}, (snapshot_id,)), producer="awareness_studio.orchestrator")
        claim_id = stable_id("claim", {"cycle_id": run_id, "evidence_id": evidence_id})
        ledger.append_record(run_id, Claim(claim_id, run_id, "The configured pipeline can be represented as a reviewable plan.", (evidence_id,), EvidenceClass.ENGINEERING_FACT, "Software planning behavior only; not a claim about biology or experiment outcomes.", limitations, parent_ids=(evidence_id,)), producer="awareness_studio.orchestrator")

    def _record_stage_result(self, ledger: ResearchCycleLedger, run_id: str, stage: str, result: Dict[str, Any], cfg: OrchestratorConfig, context: Dict[str, Any]) -> None:
        """Project stage outputs into the canonical ledger without promoting them.

        Missing solver, run, artifact, and validation nodes are represented by
        explicit blocked/review events.  No placeholder checksum or fabricated
        RunRecord is created for work that did not execute.
        """
        producer = "awareness_studio.orchestrator"
        limitations = ("Planning/interface evidence only; no scientific execution or conclusion is established.",)
        records = ledger.records(run_id)
        record_by_type = {record.record_type: record for record in records}
        claim = record_by_type.get("claim")
        if stage == "propose_hypotheses" and claim is not None:
            for item in result.get("hypotheses", []):
                hypothesis_id = stable_id("hypothesis", {"cycle_id": run_id, "h_id": item.get("h_id"), "text": item.get("text")})
                ledger.append_record(run_id, LedgerHypothesis(hypothesis_id, run_id, str(item.get("text", "")), (claim.record_id,), claim_scope="Hypothesis proposal only; not an empirical result.", scientific_limitations=limitations, parent_ids=(claim.record_id,)), producer=producer)
        elif stage == "plan_experiments":
            hypotheses = {item.get("h_id"): item for item in context.get("propose_hypotheses", {}).get("hypotheses", [])}
            for item in result.get("experiment_specs", []):
                source_hypothesis = hypotheses.get(item.get("hypothesis"), {})
                hypothesis_id = stable_id("hypothesis", {"cycle_id": run_id, "h_id": item.get("hypothesis"), "text": source_hypothesis.get("text")})
                experiment_id = stable_id("experiment", {"cycle_id": run_id, "spec": item})
                ledger.append_record(run_id, LedgerExperimentSpec(experiment_id, run_id, (hypothesis_id,), str(item.get("mode", "undeclared")), item.get("params", {}), claim_scope="Experiment planning only; no execution result.", scientific_limitations=limitations, parent_ids=(hypothesis_id,)), producer=producer)
        elif stage == "execute":
            status = "BLOCKED" if cfg.dry_run else "NOT_IMPLEMENTED"
            ledger.append_event(run_id, "execution_outcome", producer=producer, status=status, payload={"execution_state": "PLANNING_ONLY" if cfg.dry_run else "NOT_IMPLEMENTED", "scientific_evidence": False, "results": result.get("results", []), "reason": "No solver was invoked; no RunRecordV1 was fabricated."})
        elif stage == "digest":
            paths = {key: str(value) for key, value in result.get("artifacts", {}).items()}
            ledger.append_event(run_id, "planning_artifact", producer=producer, status="REVIEW_REQUIRED", payload={"planning_only": True, "scientific_evidence": False, "artifact_paths": paths, "reason": "These are interface/report artifacts, not scientific measurements."})
            ledger.append_event(run_id, "evidence_graph_update", producer=producer, status="REVIEW_REQUIRED", payload={"planning_only": True, "scientific_evidence": False, "reason": "Graph contains proposed hypotheses only."})
        elif stage == "validate":
            ledger.append_event(run_id, "validation_outcome", producer=producer, status="REVIEW_REQUIRED" if cfg.dry_run else "NOT_IMPLEMENTED", payload={"validation_status": "REVIEW_REQUIRED" if cfg.dry_run else "NOT_IMPLEMENTED", "scientific_evidence": False, "checks": result.get("checks", []), "reason": "Planning output cannot validate scientific execution."})
        elif stage == "ops_update":
            ledger.append_event(run_id, "release_review", producer=producer, status="REVIEW_REQUIRED", payload={"release_state": "REVIEW_REQUIRED", "execution_allowed": False, "scientific_evidence": False, "reason": "No autonomous release or claim promotion is permitted."})

    # ── Stage implementations ─────────────────────────────────────────────────

    def _stage_ingest_inputs(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        run_cards: List[Dict] = []
        if cfg.run_cards_dir and Path(cfg.run_cards_dir).exists():
            for p in sorted(Path(cfg.run_cards_dir).rglob("*.run.json")):
                try:
                    run_cards.append(json.loads(p.read_text(encoding="utf-8")))
                except Exception:
                    pass
        return {
            "run_cards_loaded": len(run_cards),
            "run_cards": run_cards,
            "dry_run": cfg.dry_run,
        }

    def _stage_propose_hypotheses(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        hypotheses = [
            {
                "h_id": "h001",
                "text": "Vedana (sensation tone) modulates tanha (craving) via gain-control dynamics.",
                "confidence": "medium",
                "source": "template",
                "proposal_only": True,
                "mutates_claims": False,
            },
            {
                "h_id": "h002",
                "text": "Upadana (clinging) functions as a latching mechanism stabilized by samsaric loops.",
                "confidence": "low",
                "source": "template",
                "proposal_only": True,
                "mutates_claims": False,
            },
        ]
        return {"hypotheses": hypotheses, "count": len(hypotheses)}

    def _stage_plan_experiments(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        specs = [
            ExperimentSpec(
                spec_id=f"exp_{run_id[:8]}_001",
                hypothesis="h001",
                mode="psi",
                params={"N": 64, "n_steps": 50, "seed": cfg.seed},
            ),
            ExperimentSpec(
                spec_id=f"exp_{run_id[:8]}_002",
                hypothesis="h002",
                mode="meditation",
                params={"n_epochs": 30, "seed": cfg.seed},
            ),
        ]
        return {
            "experiment_specs": [
                {"spec_id": s.spec_id, "hypothesis": s.hypothesis,
                 "mode": s.mode, "params": s.params, "planning_only": True,
                 "mutates_claims": False}
                for s in specs
            ],
            "count": len(specs),
        }

    def _stage_execute(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        specs = ctx.get("plan_experiments", {}).get("experiment_specs", [])
        results = []
        for spec in specs:
            if cfg.dry_run:
                results.append({
                    "spec_id": spec["spec_id"],
                    "mode": spec["mode"],
                    "status": "PLANNING_ONLY",
                    "planning_only": True,
                    "scientific_evidence": False,
                    "reason": "Dry-run plans the execution interface and invokes no solver.",
                })
            else:
                results.append({
                    "spec_id": spec["spec_id"],
                    "mode": spec["mode"],
                    "status": "NOT_IMPLEMENTED",
                    "scientific_evidence": False,
                    "reason": "Live solver execution is not implemented by Awareness Studio.",
                })
        return {"results": results, "dry_run": cfg.dry_run}

    def _stage_fable_reasoning(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Fable 5-powered metric interpretation over the execute stage's results.

        `llm_reasoning.fable_interpreter.FableInterpreter` makes a real
        Anthropic API call, which would violate this orchestrator's
        dry_run=True contract ("No network or LLM calls required"). Mirrors
        `_stage_execute`'s dry_run/live split: a deterministic stub in
        dry_run (what every current caller/test exercises), "not_implemented"
        live (wiring the real call is a separate feature decision).
        """
        results = ctx.get("execute", {}).get("results", [])
        interpretations = []
        for r in results:
            if cfg.dry_run:
                interpretations.append({
                    "spec_id": r.get("spec_id"),
                    "status": "PLANNING_ONLY",
                    "scientific_evidence": False,
                    "reason": "No LLM call made; planning output is not evidence.",
                })
            else:
                interpretations.append({
                    "spec_id": r.get("spec_id"),
                    "status": "NOT_IMPLEMENTED",
                    "scientific_evidence": False,
                })
        return {"interpretations": interpretations, "dry_run": cfg.dry_run}

    def _stage_validate(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        results = ctx.get("execute", {}).get("results", [])
        checks: List[Dict] = []
        for r in results:
            passed = False
            checks.append({
                "spec_id": r.get("spec_id"),
                "passed": passed,
                "status": "REVIEW_REQUIRED" if cfg.dry_run else "NOT_IMPLEMENTED",
                "scientific_evidence": False,
                "note": "planning/interface evidence only" if cfg.dry_run else "solver execution not implemented",
            })
        all_passed = all(c["passed"] for c in checks)
        # A non-passing planning check is an explicit review state, not a stage
        # exception.  This keeps the pipeline auditable without manufacturing a
        # scientific failure or success.
        return {"checks": checks, "all_passed": all_passed}

    def _stage_digest(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        hypotheses = ctx.get("propose_hypotheses", {}).get("hypotheses", [])
        results = ctx.get("execute", {}).get("results", [])

        # Write EvidenceLogDraft.md
        evidence_path = out_dir / "EvidenceLogDraft.md"
        lines = [
            f"# Evidence Log Draft — run {run_id}",
            "",
            f"**Generated:** {(_now or datetime.now(timezone.utc)).isoformat()}  ",
            f"**Dry run:** {cfg.dry_run}",
            "",
            "## Hypotheses",
            "",
        ]
        for h in hypotheses:
            lines += [
                f"### {h['h_id']}: {h['text']}",
                f"- Confidence: {h['confidence']}",
                f"- Source: {h['source']}",
                "",
            ]
        lines += ["## Experiment Results", ""]
        for r in results:
            lines += [
                f"### {r.get('spec_id', '?')}",
                f"- Mode: {r.get('mode')}",
                f"- Status: {r.get('status')}",
            ]
            if "metrics" in r:
                lines.append(f"- I_mean: {r['metrics']['I_mean']}")
            lines.append("")
        evidence_path.write_text("\n".join(lines), encoding="utf-8")

        # Write GraphUpdate.json
        graph_path = out_dir / "GraphUpdate.json"
        graph = {
            "run_id": run_id,
            "nodes": [{"id": h["h_id"], "label": h["text"], "type": "hypothesis"}
                      for h in hypotheses],
            "edges": [],
            "updated_at": (_now or datetime.now(timezone.utc)).isoformat(),
        }
        graph_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")

        return {
            "artifacts": {
                "EvidenceLogDraft.md": evidence_path,
                "GraphUpdate.json": graph_path,
            }
        }

    def _stage_draft_report(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        hypotheses = ctx.get("propose_hypotheses", {}).get("hypotheses", [])
        results = ctx.get("execute", {}).get("results", [])
        checks = ctx.get("validate", {}).get("checks", [])
        n_pass = sum(1 for c in checks if c["passed"])

        report_path = out_dir / "Report.md"
        lines = [
            f"# Orchestrator Report — {run_id}",
            "",
            f"**Date:** {(_now or datetime.now(timezone.utc)).isoformat()}  ",
            f"**Mode:** {'dry-run' if cfg.dry_run else 'live'}  ",
            f"**Stages:** {len(PIPELINE_STAGES)} planned; execution state is review-only  ",
            f"**Validation:** {n_pass}/{len(checks)} checks passed; planning output is not scientific evidence",
            "",
            "## Summary",
            "",
            f"This orchestrator run processed {len(hypotheses)} hypotheses across "
            f"{len(results)} experiment specs.",
            "",
            "## Hypotheses Evaluated",
            "",
        ]
        for h in hypotheses:
            lines.append(f"- **{h['h_id']}** ({h['confidence']}): {h['text']}")
        lines += [
            "",
            "## Validation Status",
            "",
        ]
        for c in checks:
            mark = "REVIEW_REQUIRED" if not c["passed"] else "COMPLETED"
            lines.append(f"- [{mark}] {c['spec_id']} — {c['note']}")
        lines += [
            "",
            "## Artifacts",
            "",
            f"All outputs in: `outputs/orchestrator/{run_id}/`",
            "",
            "| File | Description |",
            "|------|-------------|",
            "| events.jsonl | Append-only event log |",
            "| EvidenceLogDraft.md | Draft evidence card entries |",
            "| GraphUpdate.json | Knowledge graph delta |",
            "| Report.md | This report |",
            "| OpsQueueItem.json | Ops sync payload |",
        ]
        report_path.write_text("\n".join(lines), encoding="utf-8")

        return {"artifacts": {"Report.md": report_path}}

    def _stage_ops_update(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        ops_path = out_dir / "OpsQueueItem.json"
        item = {
            "run_id": run_id,
            "task": f"Review orchestrator output for run {run_id[:8]}",
            "priority": "normal",
            "status": "pending",
            "dry_run": cfg.dry_run,
            "links": {
                "report": str(out_dir / "Report.md"),
                "evidence": str(out_dir / "EvidenceLogDraft.md"),
            },
            "created_at": (_now or datetime.now(timezone.utc)).isoformat(),
            "airtable_payload": {
                "table": "Work Queue",
                "action": "planning_only" if cfg.dry_run else "not_implemented",
                "fields": {
                    "task": f"Orchestrator run {run_id[:8]}",
                    "priority": "normal",
                    "status": "pending",
                    "links": str(out_dir),
                },
            },
        }
        ops_path.write_text(json.dumps(item, indent=2), encoding="utf-8")
        return {"artifacts": {"OpsQueueItem.json": ops_path}}

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_run_id(cfg: OrchestratorConfig, now: datetime) -> str:
        d: dict = {"seed": cfg.seed, "dry_run": cfg.dry_run}
        if not cfg.dry_run:
            d["ts"] = now.isoformat()
        blob = json.dumps(d, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]
