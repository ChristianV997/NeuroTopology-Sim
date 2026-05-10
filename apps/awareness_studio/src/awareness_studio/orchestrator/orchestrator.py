"""Orchestrator v0.1 — 8-stage dry-run pipeline.

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

logger = logging.getLogger(__name__)


# ── Config / result types ─────────────────────────────────────────────────────

@dataclass
class OrchestratorConfig:
    dry_run: bool = True
    seed: int = 42
    run_cards_dir: Optional[Path] = None   # where to look for *.run.json
    out_base_dir: Optional[Path] = None    # defaults to outputs/orchestrator/


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "out_dir": str(self.out_dir),
            "stages_completed": self.stages_completed,
            "stages_failed": self.stages_failed,
            "dry_run": self.dry_run,
            "artifacts": {k: str(v) for k, v in self.artifacts.items()},
            "error": self.error,
        }


# ── Orchestrator ──────────────────────────────────────────────────────────────

class Orchestrator:
    def __init__(self, config: Optional[OrchestratorConfig] = None) -> None:
        self._cfg = config or OrchestratorConfig()

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
            )

        now = _now or datetime.now(timezone.utc)
        run_id = self._make_run_id(cfg, now)

        from awareness_studio import config as app_config
        out_base = cfg.out_base_dir or (app_config.APP_ROOT / "outputs" / "orchestrator")
        out_dir = out_base / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        log = EventLog(out_dir)
        stages_completed: List[str] = []
        stages_failed: List[str] = []
        artifacts: Dict[str, Path] = {}
        context: Dict[str, Any] = {}

        stage_fns = {
            "ingest_inputs":      self._stage_ingest_inputs,
            "propose_hypotheses": self._stage_propose_hypotheses,
            "plan_experiments":   self._stage_plan_experiments,
            "execute":            self._stage_execute,
            "validate":           self._stage_validate,
            "digest":             self._stage_digest,
            "draft_report":       self._stage_draft_report,
            "ops_update":         self._stage_ops_update,
        }

        for stage in PIPELINE_STAGES:
            fn = stage_fns[stage]
            t0 = time.monotonic()
            log.append(EventEnvelope.make(run_id, stage, "start", _now=now))
            try:
                result = fn(run_id, cfg, out_dir, context, _now=now)
                dur = (time.monotonic() - t0) * 1000
                context[stage] = result
                artifacts.update(result.get("artifacts", {}))
                log.append(EventEnvelope.make(
                    run_id, stage, "ok",
                    payload={k: str(v) if isinstance(v, Path) else v
                             for k, v in result.items() if k != "artifacts"},
                    duration_ms=round(dur, 1),
                    _now=now,
                ))
                stages_completed.append(stage)
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
                break

        artifacts["events_jsonl"] = log.path
        return OrchestratorResult(
            run_id=run_id,
            out_dir=out_dir,
            stages_completed=stages_completed,
            stages_failed=stages_failed,
            dry_run=cfg.dry_run,
            artifacts=artifacts,
        )

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
            },
            {
                "h_id": "h002",
                "text": "Upadana (clinging) functions as a latching mechanism stabilized by samsaric loops.",
                "confidence": "low",
                "source": "template",
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
                 "mode": s.mode, "params": s.params}
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
                    "status": "dry_run_skipped",
                    "metrics": {
                        "I_mean": 0.5, "I_std": 0.05, "I_final": 0.48,
                        "vort_mean": 1.0, "n_steps": 50.0,
                        "Qz_mean": 0.0, "Qabs_mean": 0.0, "f_dress": 0.0,
                    },
                })
            else:
                results.append({
                    "spec_id": spec["spec_id"],
                    "mode": spec["mode"],
                    "status": "not_implemented",
                })
        return {"results": results, "dry_run": cfg.dry_run}

    def _stage_validate(
        self, run_id: str, cfg: OrchestratorConfig, out_dir: Path,
        ctx: Dict[str, Any], *, _now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        results = ctx.get("execute", {}).get("results", [])
        checks: List[Dict] = []
        for r in results:
            passed = "metrics" in r or r.get("status") in ("dry_run_skipped",)
            checks.append({
                "spec_id": r.get("spec_id"),
                "passed": passed,
                "note": "dry_run stub" if cfg.dry_run else "live",
            })
        all_passed = all(c["passed"] for c in checks)
        if not all_passed:
            raise RuntimeError(f"Validation failed: {[c for c in checks if not c['passed']]}")
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
            f"**Stages:** {len(PIPELINE_STAGES)} planned, all completed  ",
            f"**Validation:** {n_pass}/{len(checks)} checks passed",
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
            mark = "PASS" if c["passed"] else "FAIL"
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
                "action": "dry_run" if cfg.dry_run else "upsert",
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
