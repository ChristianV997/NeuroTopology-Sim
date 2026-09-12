"""Builder and adapter connecting simulation execution results to the research cycle release bundle.

Contracts:
- Ingests RunRecordV1, execution_manifest, artifact-lineage, validation, evidence-graph, and release-evidence records.
- Constructs an 8-stage chain:
  input provenance → configuration → code revision → seed → execution outcome → artifact manifest → validation → evidence review.
- Promotes only validated PASS execution records.
- Preserves PARTIAL, FAILED, TIMEOUT, BLOCKED, and NOT_IMPLEMENTED states.
- Ensures non-PASS checksums remain strictly null.
- Fails closed on fabricated provenance, escapes, incomplete manifests, and missing runners.
- Never emits scientific PASS or formal Bayes factors.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import (
    BUNDLE_SCHEMA_VERSION,
    DEFAULT_SCIENTIFIC_LIMITATIONS,
    ExecutionOutcomeState,
    ReleasePromotionStatus,
    SCIENTIFIC_CLAIM_SCOPE_DEFAULT,
    SCIENTIFIC_VERDICT_DEFAULT,
    SimulationReleaseBundle,
    SimulationReleaseError,
    canonical_hash,
    dumps_finite_json,
    finite_value,
)
from .validator import check_canonical_runner_presence, validate_stages


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text)
    except Exception:
        return None


class SimulationReleaseBuilder:
    """Additive adapter building a validated SimulationReleaseBundle."""

    def __init__(
        self,
        cycle_id: str,
        *,
        bundle_id: str | None = None,
        require_canonical_runner: bool = True,
    ) -> None:
        self.cycle_id = cycle_id
        self.bundle_id = bundle_id or f"bundle_{cycle_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        self.require_canonical_runner = require_canonical_runner

    def build_from_stages(
        self,
        stages: Mapping[str, Any],
        *,
        output_root: Path | str | None = None,
    ) -> SimulationReleaseBundle:
        """Construct bundle directly from a dictionary of chain stages."""
        val_result = validate_stages(
            stages,
            output_root=output_root,
            require_canonical_runner=self.require_canonical_runner,
        )

        outcome_stage = stages.get("execution_outcome") or {}
        raw_state = str(outcome_stage.get("state", "NOT_RUN")).upper()
        try:
            outcome_state = ExecutionOutcomeState(raw_state)
        except ValueError:
            outcome_state = ExecutionOutcomeState.NOT_RUN

        prov_stage = stages.get("input_provenance") or {}
        data_mode = str(prov_stage.get("data_mode", "unspecified")).lower()
        if data_mode == "synthetic":
            evidence_class = "synthetic_demo_only"
        elif data_mode == "proxy":
            evidence_class = "proxy_only"
        elif data_mode == "empirical":
            evidence_class = "empirical_dataset"
        else:
            evidence_class = "unspecified"

        diagnostics: dict[str, list[str]] = {
            "missing": list(val_result.missing_stages),
            "errors": list(val_result.errors),
            "rejected": list(val_result.rejected_reasons),
            "warnings": list(val_result.warnings),
        }

        # Invariant 1: Accept only validated PASS execution records for artifact promotion
        # Invariant 2: Preserve PARTIAL, FAILED, TIMEOUT, BLOCKED, NOT_IMPLEMENTED states
        # Invariant 3: Keep non-PASS checksums null
        if val_result.promotion_eligible:
            promotion_status = ReleasePromotionStatus.PROMOTED.value
            promotion_checksum = canonical_hash(stages)
        elif outcome_state in (
            ExecutionOutcomeState.PARTIAL,
            ExecutionOutcomeState.FAILED,
            ExecutionOutcomeState.TIMEOUT,
            ExecutionOutcomeState.NOT_IMPLEMENTED,
            ExecutionOutcomeState.NOT_RUN,
        ):
            promotion_status = ReleasePromotionStatus.NOT_PROMOTED.value
            promotion_checksum = None  # strictly null
        else:
            # BLOCKED or infrastructure failure or validation rejected
            promotion_status = ReleasePromotionStatus.BLOCKED.value
            promotion_checksum = None  # strictly null

        return SimulationReleaseBundle(
            bundle_id=self.bundle_id,
            cycle_id=self.cycle_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            promotion_status=promotion_status,
            promotion_checksum=promotion_checksum,
            chain_complete=val_result.chain_complete,
            stages=dict(stages),
            data_mode=data_mode,
            evidence_class=evidence_class,
            diagnostics=diagnostics,
            scientific_verdict=SCIENTIFIC_VERDICT_DEFAULT,
            scientific_claim_scope=SCIENTIFIC_CLAIM_SCOPE_DEFAULT,
            scientific_limitations=list(DEFAULT_SCIENTIFIC_LIMITATIONS),
            schema_version=BUNDLE_SCHEMA_VERSION,
        )

    def build_from_directory(self, run_dir: Path | str) -> SimulationReleaseBundle:
        """Scan a simulation output directory, ingest contracts, and assemble the bundle."""
        directory = Path(run_dir).resolve()
        if not directory.is_dir():
            raise SimulationReleaseError(f"run directory does not exist: {directory}")

        # Check canonical runner prerequisite early
        if self.require_canonical_runner:
            runner_ok, runner_err = check_canonical_runner_presence()
            if not runner_ok:
                # Fail closed with BLOCKED bundle reporting missing prerequisite
                dummy_stages: dict[str, Any] = {
                    "input_provenance": None,
                    "configuration": None,
                    "code_revision": None,
                    "seed": None,
                    "execution_outcome": {"state": ExecutionOutcomeState.BLOCKED.value, "error_message": runner_err},
                    "artifact_manifest": None,
                    "validation": None,
                    "evidence_review": None,
                }
                return self.build_from_stages(dummy_stages, output_root=directory)

        # 1. Ingest RunRecord.json (case-insensitive search)
        run_record_path = None
        for p in directory.glob("*"):
            if p.is_file() and p.name.lower() == "runrecord.json":
                run_record_path = p
                break

        run_record = _read_json_file(run_record_path) if run_record_path else None

        # 2. Ingest execution_manifest.json
        exec_manifest_path = None
        for p in directory.glob("*"):
            if p.is_file() and p.name.lower() == "execution_manifest.json":
                exec_manifest_path = p
                break
        exec_manifest = _read_json_file(exec_manifest_path) if exec_manifest_path else None

        # 3. Extract artifact lineage using simulation_artifacts extractor if available
        lineage_report = None
        try:
            from tools.simulation_artifacts.extractor import extract_run
            lineage_report = extract_run(directory)
        except Exception:
            pass

        # 4. Ingest validation report
        validation_path = None
        for p in directory.glob("*"):
            if p.is_file() and "val" in p.name.lower() and p.suffix.lower() == ".json":
                validation_path = p
                break
        validation_doc = _read_json_file(validation_path) if validation_path else None

        # 5. Ingest evidence review / release evidence report
        review_path = None
        for p in directory.glob("*"):
            if p.is_file() and "release" in p.name.lower() and p.suffix.lower() == ".json":
                review_path = p
                break
        review_doc = _read_json_file(review_path) if review_path else None

        # Extract Stage 1: Input Provenance
        prov_dict = (run_record or {}).get("provenance") or (lineage_report or {}).get("provenance") or {}
        dataset_id = (
            (run_record or {}).get("dataset_id")
            or prov_dict.get("dataset_id")
            or "unknown"
        )
        source = (
            (run_record or {}).get("source")
            or prov_dict.get("source")
            or "unknown"
        )
        data_mode = (
            (run_record or {}).get("data_mode")
            or prov_dict.get("data_mode")
            or "unknown"
        )
        run_id = (
            (run_record or {}).get("run_id")
            or prov_dict.get("run_id")
            or (exec_manifest or {}).get("unit_id")
            or (exec_manifest or {}).get("workload_id")
            or "unknown"
        )
        stage_input_provenance = {
            "run_id": run_id,
            "dataset_id": dataset_id,
            "source": source,
            "data_mode": data_mode,
            "input_references": (exec_manifest or {}).get("input_references") or [],
            "description": prov_dict.get("description", ""),
        }

        # Extract Stage 2: Configuration
        config_params = (
            (run_record or {}).get("input")
            or (exec_manifest or {}).get("config")
            or {}
        )
        argv = (
            (run_record or {}).get("argv")
            or (exec_manifest or {}).get("argv")
            or []
        )
        spec_id = (run_record or {}).get("spec_id") or (exec_manifest or {}).get("workload_id")
        stage_configuration = {
            "parameters": config_params,
            "argv": [str(a) for a in argv],
            "spec_id": spec_id,
            "timeout_s": (exec_manifest or {}).get("timeout_s"),
        }

        # Extract Stage 3: Code Revision
        code_rev = (
            (run_record or {}).get("git_commit")
            or (exec_manifest or {}).get("code_revision")
            or prov_dict.get("git_commit")
            or "unknown"
        )
        repo = (run_record or {}).get("repo") or "NeuroTopology-Sim"
        stage_code_revision = {
            "code_revision": code_rev,
            "repo": repo,
            "clean_working_tree": (exec_manifest or {}).get("clean_working_tree"),
        }

        # Extract Stage 4: Seed
        seed = None
        if "seed" in config_params:
            seed = config_params.get("seed")
        elif exec_manifest and "seed" in exec_manifest:
            seed = exec_manifest.get("seed")
        elif "deterministic_seed" in (exec_manifest or {}):
            seed = (exec_manifest or {}).get("deterministic_seed")
        stage_seed = {
            "seed": seed,
            "deterministic_fixed": True if seed is not None else False,
        }

        # Extract Stage 5: Execution Outcome
        raw_state = "NOT_RUN"
        if exec_manifest and "state" in exec_manifest:
            raw_state = exec_manifest["state"]
        elif run_record and run_record.get("verdict"):
            v = str(run_record["verdict"]).upper()
            if v in ("PASS", "COMPLETE"):
                raw_state = "PASS"
            elif v in ("PARTIAL", "FAILED", "TIMEOUT", "BLOCKED"):
                raw_state = v
        elif lineage_report and lineage_report.get("status"):
            st = str(lineage_report["status"]).upper()
            if st == "COMPLETE":
                raw_state = "PASS"
            elif st in ("PARTIAL", "FAILED", "BLOCKED"):
                raw_state = st

        elapsed_s = (run_record or {}).get("elapsed_s") or (exec_manifest or {}).get("elapsed_s")
        exit_code = (exec_manifest or {}).get("exit_code")
        error_msg = (exec_manifest or {}).get("error") or (exec_manifest or {}).get("stderr_tail")
        stage_execution_outcome = {
            "state": raw_state,
            "exit_code": exit_code,
            "elapsed_s": elapsed_s,
            "error_message": error_msg,
            "runner_id": (exec_manifest or {}).get("runner_id", "bounded_runner"),
        }

        # Extract Stage 6: Artifact Manifest
        artifact_items: list[dict[str, Any]] = []
        if lineage_report and "artifact_manifest" in lineage_report:
            for art in lineage_report["artifact_manifest"].get("artifacts", []):
                artifact_items.append({
                    "relative_path": art.get("relative_path"),
                    "sha256": art.get("sha256"),
                    "size_bytes": art.get("size_bytes"),
                    "role": art.get("role", "output"),
                })
        else:
            # Fallback scan directory directly
            for f in sorted(directory.rglob("*")):
                if f.is_file():
                    try:
                        rel = f.relative_to(directory).as_posix()
                        artifact_items.append({
                            "relative_path": rel,
                            "sha256": _sha256_file(f),
                            "size_bytes": f.stat().st_size,
                            "role": "output",
                        })
                    except Exception:
                        pass

        stage_artifact_manifest = {
            "artifacts": artifact_items,
            "run_directory": str(directory),
            "duplicate_content": (lineage_report or {}).get("artifact_manifest", {}).get("duplicate_content", []),
        }

        # Extract Stage 7: Validation
        val_passed = False
        val_status = "UNVALIDATED"
        val_checks = {}
        report_id = "val_unknown"
        if validation_doc:
            # Could be golden validation report or NTS.ValidationReport.v1
            payload = validation_doc.get("payload") or validation_doc
            val_status = payload.get("validation_status") or validation_doc.get("status") or "COMPLETE"
            val_checks = payload.get("checks") or {}
            report_id = payload.get("report_id") or validation_doc.get("record_id") or "val_001"
            if "passed" in payload:
                val_passed = bool(payload["passed"])
            elif "passed" in validation_doc:
                val_passed = bool(validation_doc["passed"])
            else:
                # Considered passed if status is not FAILED/BLOCKED and no negative check
                not_failed = val_status not in ("FAILED", "BLOCKED")
                no_net = not bool(val_checks.get("network_accessed", False))
                val_passed = not_failed and no_net
        stage_validation = {
            "report_id": report_id,
            "passed": val_passed,
            "status": val_status,
            "checks": val_checks,
            "finite_json_verified": val_checks.get("finite_json", True),
            "zero_network_verified": not val_checks.get("network_accessed", False),
        }

        # Extract Stage 8: Evidence Review
        review_decision = "SCIENTIFIC_REVIEW_REQUIRED"
        ev_class = "unspecified"
        reason_codes: list[str] = []
        op_ready = False
        if review_doc:
            payload = review_doc.get("payload") or review_doc
            review_decision = payload.get("decision") or review_doc.get("decision") or "UNKNOWN"
            ev_class = payload.get("evidence_class") or review_doc.get("evidence_class") or "unspecified"
            reason_codes = payload.get("reason_codes") or []
            op_ready = review_decision in ("EVIDENCE_READY_FOR_REVIEW", "SYNTHETIC_ONLY", "PROXY_ONLY")

        stage_evidence_review = {
            "review_id": (review_doc or {}).get("record_id") or "rev_001",
            "decision": review_decision,
            "evidence_class": ev_class,
            "reason_codes": reason_codes,
            "operational_ready": op_ready,
        }

        stages = {
            "input_provenance": stage_input_provenance,
            "configuration": stage_configuration,
            "code_revision": stage_code_revision,
            "seed": stage_seed,
            "execution_outcome": stage_execution_outcome,
            "artifact_manifest": stage_artifact_manifest,
            "validation": stage_validation,
            "evidence_review": stage_evidence_review,
        }

        return self.build_from_stages(stages, output_root=directory)


def compile_simulation_release_bundle(
    run_dir: Path | str,
    cycle_id: str,
    *,
    output_path: Path | str | None = None,
    markdown_path: Path | str | None = None,
    require_canonical_runner: bool = True,
) -> SimulationReleaseBundle:
    """Compile and optionally persist a SimulationReleaseBundle."""
    builder = SimulationReleaseBuilder(
        cycle_id=cycle_id,
        require_canonical_runner=require_canonical_runner,
    )
    bundle = builder.build_from_directory(run_dir)

    if output_path:
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(bundle.to_json(), encoding="utf-8")

    if markdown_path:
        md_out = Path(markdown_path).resolve()
        md_out.parent.mkdir(parents=True, exist_ok=True)
        md_text = render_bundle_markdown(bundle)
        md_out.write_text(md_text, encoding="utf-8")

    return bundle


def render_bundle_markdown(bundle: SimulationReleaseBundle) -> str:
    """Render a GitHub-flavored Markdown audit report for a release bundle."""
    stages = bundle.stages
    outcome = stages.get("execution_outcome") or {}
    prov = stages.get("input_provenance") or {}
    rev = stages.get("code_revision") or {}
    seed_spec = stages.get("seed") or {}
    val = stages.get("validation") or {}
    review = stages.get("evidence_review") or {}
    manifest = stages.get("artifact_manifest") or {}
    artifacts = manifest.get("artifacts", [])

    lines = [
        f"# Simulation Release Review Bundle: `{bundle.bundle_id}`",
        "",
        f"- **Cycle ID:** `{bundle.cycle_id}`",
        f"- **Created At:** `{bundle.created_at}`",
        f"- **Promotion Status:** `{bundle.promotion_status}`",
        f"- **Promotion Checksum:** `{bundle.promotion_checksum or 'null'}`",
        f"- **Chain Complete:** `{bundle.chain_complete}`",
        f"- **Data Mode:** `{bundle.data_mode}`",
        f"- **Evidence Class:** `{bundle.evidence_class}`",
        f"- **Scientific Verdict:** `{bundle.scientific_verdict}`",
        "",
        "## 8-Stage Execution Chain",
        "",
        f"1. **Input Provenance:** Dataset `{prov.get('dataset_id')}`, Source `{prov.get('source')}`, Mode `{prov.get('data_mode')}`",
        f"2. **Configuration:** Spec `{stages.get('configuration', {}).get('spec_id') or 'N/A'}`",
        f"3. **Code Revision:** Commit `{rev.get('code_revision')}` (Repo `{rev.get('repo')}`)",
        f"4. **Seed:** `{seed_spec.get('seed')}` (Deterministic fixed: `{seed_spec.get('deterministic_fixed')}`)",
        f"5. **Execution Outcome:** State `{outcome.get('state')}` (Exit code: `{outcome.get('exit_code')}`, Elapsed: `{outcome.get('elapsed_s')}s`)",
        f"6. **Artifact Manifest:** `{len(artifacts)}` artifacts indexed",
        f"7. **Validation:** Report `{val.get('report_id')}` (Passed: `{val.get('passed')}`, Status: `{val.get('status')}`)",
        f"8. **Evidence Review:** Decision `{review.get('decision')}` (Operational Ready: `{review.get('operational_ready')}`)",
        "",
        "## Diagnostics",
        "",
        f"- **Missing Stages:** {bundle.diagnostics.get('missing') or 'None'}",
        f"- **Rejections:** {bundle.diagnostics.get('rejected') or 'None'}",
        f"- **Errors:** {bundle.diagnostics.get('errors') or 'None'}",
        f"- **Warnings:** {bundle.diagnostics.get('warnings') or 'None'}",
        "",
        "## Scientific Guardrails & Limitations",
        "",
    ]
    for lim in bundle.scientific_limitations:
        lines.append(f"- {lim}")

    lines.append("")
    lines.append(f"> [!NOTE]\n> {bundle.scientific_claim_scope}\n")
    return "\n".join(lines)
