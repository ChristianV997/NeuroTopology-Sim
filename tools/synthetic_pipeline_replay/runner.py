"""Runner for offline synthetic pipeline replay and boundary conformance verification.

Usage:
    python -m tools.synthetic_pipeline_replay.runner --output outputs/replay_report.json
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

import numpy as np

from .checker import evaluate_boundary
from .contracts import (
    BoundaryReport,
    BoundaryStatus,
    ReplayExitCode,
    ReplayReport,
    ReplayStatus,
)
from .stages import (
    FeatureExtractionStage,
    PreprocessingWindowStage,
    SignalGenerationStage,
    TopologySummaryStage,
)


class SyntheticPipelineReplayRunner:
    """Orchestrates sequential synthetic pipeline execution and audits all inter-stage boundaries."""

    def __init__(
        self,
        channels: Sequence[str] = ("Fp1", "Fp2", "C3", "C4"),
        sfreq_hz: float = 250.0,
        duration_s: float = 2.0,
        seed: int = 42,
    ) -> None:
        if not channels:
            raise ValueError("channels sequence cannot be empty")
        if len(channels) != len(set(channels)):
            raise ValueError(f"Duplicate channel names detected: {list(channels)}")
        if sfreq_hz <= 0 or not math.isfinite(sfreq_hz):
            raise ValueError(f"Sampling frequency must be positive and finite, observed {sfreq_hz}")
        if duration_s <= 0 or not math.isfinite(duration_s):
            raise ValueError(f"Duration must be positive and finite, observed {duration_s}")
        if not isinstance(seed, (int, np.integer)) or seed < 0:
            raise ValueError(f"Seed must be a non-negative integer, observed {seed}")

        self.channels = list(channels)
        self.sfreq_hz = float(sfreq_hz)
        self.duration_s = float(duration_s)
        self.seed = int(seed)

    def _build_report(
        self,
        boundary_reports: list[BoundaryReport],
        stages_executed: list[str],
    ) -> ReplayReport:
        total_bounds = len(boundary_reports)
        compatible_bounds = sum(1 for b in boundary_reports if b.status == BoundaryStatus.COMPATIBLE.value)
        incompatible_bounds = sum(1 for b in boundary_reports if b.status == BoundaryStatus.INCOMPATIBLE.value)
        missing_field_bounds = sum(1 for b in boundary_reports if b.status == BoundaryStatus.MISSING_REQUIRED_FIELD.value)
        not_comp_bounds = sum(1 for b in boundary_reports if b.status == BoundaryStatus.NOT_COMPARABLE.value)

        if incompatible_bounds > 0:
            overall_status = ReplayStatus.INCOMPATIBLE.value
        elif missing_field_bounds > 0:
            overall_status = ReplayStatus.INCONCLUSIVE.value
        elif not_comp_bounds > 0:
            overall_status = ReplayStatus.BLOCKED.value
        elif total_bounds > 0 and compatible_bounds == total_bounds:
            overall_status = ReplayStatus.COMPATIBLE.value
        else:
            overall_status = ReplayStatus.INCONCLUSIVE.value

        import platform
        sys_env = {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy_version": np.__version__,
        }

        return ReplayReport(
            replay_id=f"replay_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            pipeline_name="synthetic_eeg_topology_pipeline",
            status=overall_status,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            seed=self.seed,
            total_boundaries=total_bounds,
            compatible_boundaries=compatible_bounds,
            incompatible_boundaries=incompatible_bounds,
            boundaries=boundary_reports,
            stages_executed=stages_executed,
            system_environment=sys_env,
        )

    def run_replay(
        self,
        stage_perturbations: Mapping[str, Any] | None = None,
        dependency_overrides: dict[str, bool] | None = None,
    ) -> ReplayReport:
        """Run the 4-stage pipeline and evaluate boundary conformance.

        Args:
            stage_perturbations: Optional modifications injected to test negative cases.
            dependency_overrides: Optional overrides for optional dependency checks.

        Returns:
            ReplayReport containing comprehensive boundary audits.
        """
        perturbations = dict(stage_perturbations or {})
        boundary_reports: list[BoundaryReport] = []
        stages_executed: list[str] = []

        # ---------------------------------------------------------
        # Stage 1: Synthetic Signal Generation
        # ---------------------------------------------------------
        try:
            stage1 = SignalGenerationStage(
                channels=self.channels,
                sfreq_hz=self.sfreq_hz,
                duration_s=self.duration_s,
                seed=self.seed,
            )
            art1 = stage1.execute()
            stages_executed.append(stage1.STAGE_ID)
        except Exception as exc:
            err_b1 = BoundaryReport(
                boundary_id="b1_signal_generation_failure",
                producer_stage_id=SignalGenerationStage.STAGE_ID,
                consumer_stage_id=PreprocessingWindowStage.STAGE_ID,
                status=BoundaryStatus.INCOMPATIBLE.value,
                input_artifact_ref="init",
                output_artifact_ref="crashed",
                expected_contract={},
                observed_contract={},
                mismatches=[f"Stage 1 execution error: {type(exc).__name__}: {exc}"],
                missing_fields=[],
                diagnostics={"exception_type": type(exc).__name__, "exception_message": str(exc)},
            )
            boundary_reports.append(err_b1)
            return self._build_report(boundary_reports, stages_executed)

        # Apply any Stage 1 perturbations (e.g. for negative tests)
        if "stage_1" in perturbations:
            art1.update(perturbations["stage_1"])

        # ---------------------------------------------------------
        # Boundary 1: Stage 1 -> Stage 2 Contract
        # ---------------------------------------------------------
        n_samples_stage1 = int(round(self.duration_s * self.sfreq_hz))
        expected_contract_b1 = {
            "expected_artifact_id": "preprocessed_input_chunk",
            "expected_artifact_type": "SignalChunk",
            "schema_version": "NeuroTopologySim.SignalChunk.v1",
            "channel_ordering": list(self.channels),
            "expected_units": "uV",
            "sampling_rate_hz": self.sfreq_hz,
            "expected_shape": [len(self.channels), n_samples_stage1],
            "require_timestamps": True,
        }

        report_b1 = evaluate_boundary(
            boundary_id="b1_signal_to_preprocessing",
            producer_stage_id=stage1.STAGE_ID,
            consumer_stage_id=PreprocessingWindowStage.STAGE_ID,
            expected_contract=expected_contract_b1,
            observed_contract=art1,
            payload=art1.get("data"),
            dependency_override=dependency_overrides,
        )
        boundary_reports.append(report_b1)

        # ---------------------------------------------------------
        # Stage 2: Preprocessing / Windowing
        # ---------------------------------------------------------
        if report_b1.status == BoundaryStatus.COMPATIBLE.value:
            try:
                stage2 = PreprocessingWindowStage(window_duration_s=1.0)
                art2 = stage2.execute(art1)
                stages_executed.append(stage2.STAGE_ID)
            except Exception as exc:
                err_b2 = BoundaryReport(
                    boundary_id="b2_preprocessing_failure",
                    producer_stage_id=PreprocessingWindowStage.STAGE_ID,
                    consumer_stage_id=FeatureExtractionStage.STAGE_ID,
                    status=BoundaryStatus.INCOMPATIBLE.value,
                    input_artifact_ref=str(art1.get("artifact_id", "stage1_output")),
                    output_artifact_ref="crashed",
                    expected_contract={},
                    observed_contract={},
                    mismatches=[f"Stage 2 execution error: {type(exc).__name__}: {exc}"],
                    missing_fields=[],
                    diagnostics={"exception_type": type(exc).__name__, "exception_message": str(exc)},
                )
                boundary_reports.append(err_b2)
                return self._build_report(boundary_reports, stages_executed)

            # Apply any Stage 2 perturbations
            if "stage_2" in perturbations:
                art2.update(perturbations["stage_2"])

            # ---------------------------------------------------------
            # Boundary 2: Stage 2 -> Stage 3 Contract
            # ---------------------------------------------------------
            n_window_samples = int(round(1.0 * self.sfreq_hz))
            expected_contract_b2 = {
                "expected_artifact_id": "feature_extraction_input_window",
                "expected_artifact_type": "PreprocessedWindow",
                "schema_version": "NeuroTopologySim.PreprocessedWindow.v1",
                "channel_ordering": list(self.channels),
                "expected_units": "uV",
                "sampling_rate_hz": self.sfreq_hz,
                "expected_shape": [len(self.channels), n_window_samples],
                "require_timestamps": True,
            }

            report_b2 = evaluate_boundary(
                boundary_id="b2_preprocessing_to_feature_extraction",
                producer_stage_id=stage2.STAGE_ID,
                consumer_stage_id=FeatureExtractionStage.STAGE_ID,
                expected_contract=expected_contract_b2,
                observed_contract=art2,
                payload=art2.get("data"),
                dependency_override=dependency_overrides,
            )
            boundary_reports.append(report_b2)

            # ---------------------------------------------------------
            # Stage 3: Feature Extraction (CanonicalFeatureBundle)
            # ---------------------------------------------------------
            if report_b2.status == BoundaryStatus.COMPATIBLE.value:
                try:
                    stage3 = FeatureExtractionStage()
                    art3 = stage3.execute(art2)
                    stages_executed.append(stage3.STAGE_ID)
                except Exception as exc:
                    err_b3 = BoundaryReport(
                        boundary_id="b3_feature_extraction_failure",
                        producer_stage_id=FeatureExtractionStage.STAGE_ID,
                        consumer_stage_id=TopologySummaryStage.STAGE_ID,
                        status=BoundaryStatus.INCOMPATIBLE.value,
                        input_artifact_ref=str(art2.get("artifact_id", "stage2_output")),
                        output_artifact_ref="crashed",
                        expected_contract={},
                        observed_contract={},
                        mismatches=[f"Stage 3 execution error: {type(exc).__name__}: {exc}"],
                        missing_fields=[],
                        diagnostics={"exception_type": type(exc).__name__, "exception_message": str(exc)},
                    )
                    boundary_reports.append(err_b3)
                    return self._build_report(boundary_reports, stages_executed)

                # Apply any Stage 3 perturbations
                if "stage_3" in perturbations:
                    art3.update(perturbations["stage_3"])

                # ---------------------------------------------------------
                # Boundary 3: Stage 3 -> Stage 4 Contract
                # ---------------------------------------------------------
                expected_contract_b3 = {
                    "expected_artifact_id": "topology_input_feature_bundle",
                    "expected_artifact_type": "CanonicalFeatureBundle",
                    "expected_feature_family": "pairwise_fc",
                    "schema_version": "NeuroTopologySim.CanonicalFeatureBundle.v1",
                    "channel_ordering": list(self.channels),
                    "expected_units": "dimensionless",
                    "expected_shape": [len(self.channels), len(self.channels)],
                    "required_dependency": "ripser",
                }

                report_b3 = evaluate_boundary(
                    boundary_id="b3_feature_extraction_to_topology",
                    producer_stage_id=stage3.STAGE_ID,
                    consumer_stage_id=TopologySummaryStage.STAGE_ID,
                    expected_contract=expected_contract_b3,
                    observed_contract=art3,
                    payload=art3.get("pairwise_fc_matrix"),
                    dependency_override=dependency_overrides,
                )
                boundary_reports.append(report_b3)

                # ---------------------------------------------------------
                # Stage 4: Topological Graph Persistence Summary
                # ---------------------------------------------------------
                if report_b3.status == BoundaryStatus.COMPATIBLE.value:
                    try:
                        stage4 = TopologySummaryStage()
                        art4 = stage4.execute(art3)
                        stages_executed.append(stage4.STAGE_ID)
                    except Exception as exc:
                        err_b4 = BoundaryReport(
                            boundary_id="b4_topology_summary_failure",
                            producer_stage_id=TopologySummaryStage.STAGE_ID,
                            consumer_stage_id="sink",
                            status=BoundaryStatus.INCOMPATIBLE.value,
                            input_artifact_ref=str(art3.get("artifact_id", "stage3_output")),
                            output_artifact_ref="crashed",
                            expected_contract={},
                            observed_contract={},
                            mismatches=[f"Stage 4 execution error: {type(exc).__name__}: {exc}"],
                            missing_fields=[],
                            diagnostics={"exception_type": type(exc).__name__, "exception_message": str(exc)},
                        )
                        boundary_reports.append(err_b4)
                        return self._build_report(boundary_reports, stages_executed)

        return self._build_report(boundary_reports, stages_executed)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic Pipeline Replay Conformance Runner")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("outputs/synthetic_pipeline_replay/replay_report.json"),
        help="Path to write replay JSON report (default: outputs/synthetic_pipeline_replay/replay_report.json)",
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for synthetic signal generation")
    parser.add_argument("--sfreq", type=float, default=250.0, help="Sampling frequency in Hz (default: 250.0)")
    parser.add_argument("--duration", type=float, default=2.0, help="Signal duration in seconds (default: 2.0)")
    parser.add_argument(
        "--channels",
        "-c",
        nargs="+",
        default=["Fp1", "Fp2", "C3", "C4"],
        help="List of EEG channel names (default: Fp1 Fp2 C3 C4)",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress console stdout output")
    args = parser.parse_args(argv)

    # Input validation for CLI arguments
    if args.sfreq <= 0 or not math.isfinite(args.sfreq):
        if not args.quiet:
            print(f"Error: --sfreq must be positive and finite, observed {args.sfreq}", file=sys.stderr)
        return ReplayExitCode.CLI_ERROR.value

    if args.duration <= 0 or not math.isfinite(args.duration):
        if not args.quiet:
            print(f"Error: --duration must be positive and finite, observed {args.duration}", file=sys.stderr)
        return ReplayExitCode.CLI_ERROR.value

    if not args.channels:
        if not args.quiet:
            print("Error: --channels cannot be empty", file=sys.stderr)
        return ReplayExitCode.CLI_ERROR.value

    # Path containment check for output path
    out_file = Path(args.output)
    try:
        resolved_out = out_file.resolve()
        cwd = Path.cwd().resolve()
        if not out_file.is_absolute():
            resolved_out.relative_to(cwd)
    except ValueError:
        if not args.quiet:
            print(
                f"Error: Output path '{args.output}' escapes current working directory (path traversal forbidden).",
                file=sys.stderr,
            )
        return ReplayExitCode.CLI_ERROR.value

    try:
        runner = SyntheticPipelineReplayRunner(
            channels=args.channels,
            sfreq_hz=args.sfreq,
            duration_s=args.duration,
            seed=args.seed,
        )
        report = runner.run_replay()
    except Exception as exc:
        if not args.quiet:
            print(f"Error initializing replay runner: {exc}", file=sys.stderr)
        return ReplayExitCode.CLI_ERROR.value

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(report.to_json(), encoding="utf-8")

    if not args.quiet:
        print(f"Replay completed: status={report.status}")
        print(f"Compatible boundaries: {report.compatible_boundaries}/{report.total_boundaries}")
        print(f"Report written to: {out_file.resolve()}")

    exit_code_map = {
        ReplayStatus.COMPATIBLE.value: ReplayExitCode.COMPATIBLE.value,
        ReplayStatus.INCOMPATIBLE.value: ReplayExitCode.INCOMPATIBLE.value,
        ReplayStatus.BLOCKED.value: ReplayExitCode.BLOCKED.value,
        ReplayStatus.INCONCLUSIVE.value: ReplayExitCode.INCONCLUSIVE.value,
    }
    return exit_code_map.get(report.status, ReplayExitCode.INCOMPATIBLE.value)


if __name__ == "__main__":
    sys.exit(main())
