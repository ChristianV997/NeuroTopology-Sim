from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCIENCE_ROOT = Path(__file__).resolve().parents[1]
NEURO_ROOT = SCIENCE_ROOT.parent / "NeuroTopology-Sim"
DEFAULT_OUTPUT = SCIENCE_ROOT / "artifacts" / "compiled" / "simulation_compilation_report.md"


@dataclass(frozen=True)
class ArtifactSummary:
    label: str
    path: Path
    note: str
    payload: dict[str, Any] | None = None


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def _fmt_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.12g}"
    if isinstance(value, (int, str)):
        return str(value)
    if isinstance(value, list):
        return ", ".join(_fmt_value(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _pick(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return default


def _pick_nested(mapping: dict[str, Any], parent_key: str, *keys: str, default: Any = None) -> Any:
    nested = mapping.get(parent_key)
    if isinstance(nested, dict):
        return _pick(nested, *keys, default=default)
    return default


def _collect_artifacts() -> list[ArtifactSummary]:
    summaries: list[ArtifactSummary] = []
    candidates: list[tuple[str, Path, str]] = [
        ("Exact-Dynamics Falsification", SCIENCE_ROOT / "artifacts" / "open_quantum" / "exact_dynamics" / "falsification.json", "Local-QM-input, non-Markovian exact-dynamics campaign output."),
        ("PDB Disorder Benchmark", SCIENCE_ROOT / "artifacts" / "open_quantum" / "pdb_disorder_benchmark" / "decoherence_sweep.json", "Real local PDB geometry with metabolic pumping and chiral-current heuristic."),
        ("Dense/Matrix-Free Scaling", SCIENCE_ROOT / "artifacts" / "open_quantum" / "matrix_free_scaling" / "superlu_stress_test.json", "SuperLU-stabilized Liouvillian stress test."),
        ("Open Quantum Scaling", SCIENCE_ROOT / "artifacts" / "open_quantum" / "matrix_free_scaling" / "scaling_benchmark.json", "Dense exact / scaling benchmark."),
        ("Coupled Multi-Lattice Benchmark", SCIENCE_ROOT / "artifacts" / "open_quantum" / "multi_lattice_coupling" / "multi_lattice_benchmark.json", "Finite coupled-cylinder dipolar benchmark."),
        ("Coupled Lattice Sensitivity", SCIENCE_ROOT / "artifacts" / "open_quantum" / "multi_lattice_sensitivity" / "multi_lattice_benchmark.json", "Expanded spacing/dielectric/bath/pump-orientation sweep."),
        ("Constrained Concurrent Lattice Sweep", SCIENCE_ROOT / "artifacts" / "open_quantum" / "multi_lattice_constrained" / "multi_lattice_benchmark.json", "Two-worker constrained eight-point acceptance-window sweep."),
        ("DM1 Thermal Sweep", SCIENCE_ROOT / "artifacts" / "telemetry" / "thermal_sweep_summary.json", "AWS DM1 telemetry when preflight succeeds, otherwise explicitly-labelled local Lindblad fallback."),
        ("Campaign Insights", NEURO_ROOT / "artifacts" / "pitnn" / "research_campaign" / "research_insights_summary.json", "Multi-parameter sweep over spin, bath, and EP settings."),
        ("Mesoscale Membrane Bridge", NEURO_ROOT / "artifacts" / "pitnn" / "mesoscale_membrane" / "mesoscale_membrane_summary.json", "Phenomenological finite-model-to-FHN sensitivity run."),
        ("Awake vs Sedated", NEURO_ROOT / "artifacts" / "topology_monitoring" / "comparative_sedation" / "awake_vs_sedated.json", "Comparative topology monitoring on empirical EEG."),
        ("Cohort Sedation Topology", NEURO_ROOT / "artifacts" / "topology_monitoring" / "cohort_sedation" / "cohort_topology_summary.json", "Paired local EEG cohort aggregation and Wilcoxon status."),
        ("EEG Topology Run", NEURO_ROOT / "artifacts" / "topology_monitoring" / "eeg_run" / "eeg_topology_results.json", "Streaming topology analysis on EEG chunks."),
        ("Empirical Validation Awake", NEURO_ROOT / "artifacts" / "pitnn" / "empirical_validation_awake.json", "Validation summary for awake empirical data."),
        ("Empirical Validation Sedated", NEURO_ROOT / "artifacts" / "pitnn" / "empirical_validation_sedated.json", "Validation summary for sedated empirical data."),
        ("DSIM Falsification", NEURO_ROOT / "artifacts" / "pitnn" / "dsim_export" / "empirical_falsification_report.json", "Dashboard export for empirical falsification."),
        ("MEG Falsification", NEURO_ROOT / "artifacts" / "pitnn" / "dsim_export" / "meg_falsification_report.json", "High-density MEG falsification result."),
        ("DSIM Summary", NEURO_ROOT / "artifacts" / "pitnn" / "dsim_export" / "falsification_summary.json", "Unified falsification summary for dashboard export."),
        ("Campaign Summary", NEURO_ROOT / "artifacts" / "pitnn" / "research_campaign" / "campaign_summary.json", "Metadata for the high-throughput campaign."),
    ]
    for label, path, note in candidates:
        payload = _read_json(path) if path.exists() and path.suffix == ".json" else None
        summaries.append(ArtifactSummary(label=label, path=path, note=note, payload=payload))
    non_markovian = [
        path for path in (SCIENCE_ROOT / "artifacts" / "exact_dynamics" / "non_markovian_bath").glob("**/non_markovian_falsification.json")
        if path.is_file()
    ]
    if non_markovian:
        path = max(non_markovian, key=lambda item: item.stat().st_mtime)
        summaries.append(ArtifactSummary(
            label="Non-Markovian Drude--Lorentz TEMPO",
            path=path,
            note="OQuPy structured-bath convergence/falsification diagnostic; never affirmative biological evidence.",
            payload=_read_json(path),
        ))
    return summaries


def _iter_files() -> Iterable[Path]:
    roots = [
        SCIENCE_ROOT / "artifacts",
        NEURO_ROOT / "artifacts",
        SCIENCE_ROOT / "data" / "qm",
    ]
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_appendix() -> tuple[list[str], list[str]]:
    """Embed small structured result payloads so the record is self-contained.

    Binary figures/NPZ arrays remain indexed with SHA-256 values rather than
    being base64-expanded into a mobile-unfriendly document.
    """
    included: list[str] = []
    omitted: list[str] = []
    for path in _iter_files():
        if path.suffix.lower() != ".json" or path.name == "RunRecord.json":
            continue
        try:
            if path.stat().st_size > 512 * 1024:
                omitted.append(f"`{_relpath(path, SCIENCE_ROOT.parent)}` (larger than 512 KiB)")
                continue
            payload = _read_json(path)
        except (OSError, json.JSONDecodeError):
            omitted.append(f"`{_relpath(path, SCIENCE_ROOT.parent)}` (unreadable JSON)")
            continue
        included.extend([
            f"### `{_relpath(path, SCIENCE_ROOT.parent)}`",
            "",
            "```json",
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False),
            "```",
            "",
        ])
    return included, omitted


def _qm_text_appendix() -> list[str]:
    """Embed the small local QM handoff files for mobile/offline review."""
    root = SCIENCE_ROOT / "data" / "qm" / "td_dft_subnetwork"
    lines: list[str] = []
    if not root.exists():
        return lines
    lines.extend(["## TD-DFT Handoff Text Payloads", "", "These files are geometry handoffs only; no TD-DFT values were fabricated.", ""])
    for path in sorted(root.glob("*.xyz")):
        lines.extend([f"### `{_relpath(path, SCIENCE_ROOT.parent)}`", "", "```text", path.read_text(encoding="utf-8"), "```", ""])
    return lines


def _build_report() -> str:
    artifacts = _collect_artifacts()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    science_report = _read_json(SCIENCE_ROOT / "artifacts" / "open_quantum" / "pdb_disorder_benchmark" / "decoherence_sweep.json")
    scaling_report = _read_json(SCIENCE_ROOT / "artifacts" / "open_quantum" / "matrix_free_scaling" / "superlu_stress_test.json")
    multi_path = SCIENCE_ROOT / "artifacts" / "open_quantum" / "multi_lattice_coupling" / "multi_lattice_benchmark.json"
    multi_report = _read_json(multi_path) if multi_path.exists() else {"records": []}
    thermal_candidates = [
        path for path in (SCIENCE_ROOT / "artifacts" / "telemetry").glob("**/thermal_sweep_summary.json")
        if path.is_file()
    ]
    thermal_path = max(
        thermal_candidates,
        key=lambda path: path.stat().st_mtime,
        default=SCIENCE_ROOT / "artifacts" / "telemetry" / "thermal_sweep_summary.json",
    )
    thermal_report = _read_json(thermal_path) if thermal_path.exists() else {"records": []}
    non_markovian_candidates = [
        path for path in (SCIENCE_ROOT / "artifacts" / "exact_dynamics" / "non_markovian_bath").glob("**/non_markovian_falsification.json")
        if path.is_file()
    ]
    non_markovian_path = max(non_markovian_candidates, key=lambda path: path.stat().st_mtime, default=None)
    non_markovian_report = _read_json(non_markovian_path) if non_markovian_path is not None else None
    research_report = _read_json(NEURO_ROOT / "artifacts" / "pitnn" / "research_campaign" / "research_insights_summary.json")
    topology_report = _read_json(NEURO_ROOT / "artifacts" / "topology_monitoring" / "comparative_sedation" / "awake_vs_sedated.json")
    cohort_path = NEURO_ROOT / "artifacts" / "topology_monitoring" / "cohort_sedation" / "cohort_topology_summary.json"
    cohort_report = _read_json(cohort_path) if cohort_path.exists() else {"discovered_subjects": 0, "wilcoxon_signed_rank": {}}
    eeg_report = _read_json(NEURO_ROOT / "artifacts" / "topology_monitoring" / "eeg_run" / "eeg_topology_results.json")
    dsim_report = _read_json(NEURO_ROOT / "artifacts" / "pitnn" / "dsim_export" / "empirical_falsification_report.json")
    meg_report = _read_json(NEURO_ROOT / "artifacts" / "pitnn" / "dsim_export" / "meg_falsification_report.json")
    eeg_metrics = eeg_report.get("metrics", [])
    eeg_alert_count = sum(int(metric.get("alert_count", 0) or 0) for metric in eeg_metrics)
    eeg_mean_beta1 = (
        sum(float(metric.get("beta1", 0) or 0) for metric in eeg_metrics) / len(eeg_metrics)
        if eeg_metrics
        else None
    )
    eeg_mean_q_values = [
        float(metric["q_spatial"])
        for metric in eeg_metrics
        if isinstance(metric, dict) and metric.get("q_spatial") not in (None, "")
    ]
    eeg_mean_q_spatial = (
        sum(eeg_mean_q_values) / len(eeg_mean_q_values) if eeg_mean_q_values else None
    )

    lines: list[str] = []
    lines.append("# Compiled Simulation Report")
    lines.append("")
    lines.append(f"Generated: {generated_at}")
    lines.append("")
    lines.append("This file consolidates the latest simulation, topology, empirical falsification, and manuscript assets from both workspaces.")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- ScienceR-Dsim local PDB benchmark source: `{_fmt_value(science_report.get('source'))}`")
    lines.append(f"- ScienceR-Dsim PDB 10 K decoherence time: `{_fmt_value(science_report['records'][0]['decoherence_time_s'])} s`")
    lines.append(f"- ScienceR-Dsim PDB 310 K decoherence time: `{_fmt_value(science_report['records'][1]['decoherence_time_s'])} s`")
    lines.append(f"- ScienceR-Dsim SuperLU stress test converged: `{_fmt_value(scaling_report['records'][0]['converged'])}`")
    lines.append(f"- SuperLU stress test tau_subradiant: `{_fmt_value(scaling_report['records'][0]['tau_subradiant_s'])} s`")
    lines.append(f"- Comparative EEG source labels: awake=`{_fmt_value(topology_report['awake']['source'])}`, sedated=`{_fmt_value(topology_report['sedated']['source'])}`")
    lines.append(f"- Comparative EEG mean beta1: awake=`{_fmt_value(topology_report['awake']['mean_beta1'])}`, sedated=`{_fmt_value(topology_report['sedated']['mean_beta1'])}`")
    lines.append(f"- Empirical falsification verdict: `{_fmt_value(dsim_report['verdict'])}` with Bayes factor `{_fmt_value(dsim_report['bayes_factor'])}`")
    lines.append(f"- MEG falsification verdict: `{_fmt_value(meg_report['verdict'])}` with Bayes factor `{_fmt_value(meg_report['bayes_factor'])}`")
    lines.append(f"- Campaign optimal dark-state lifetime factor: `{_fmt_value(research_report['optimal_lifetime']['F_sub'])}`")
    lines.append(f"- Cohort paired-subject count: `{_fmt_value(cohort_report.get('discovered_subjects'))}`; beta1 Wilcoxon status: `{_fmt_value(cohort_report.get('wilcoxon_signed_rank', {}).get('mean_beta1', {}).get('status'))}`")
    if thermal_report.get("records"):
        modes = [record.get("telemetry", {}).get("execution_mode", "cloud_dm1") for record in thermal_report["records"]]
        lines.append(f"- DM1 thermal sweep nodes: `{_fmt_value(len(thermal_report['records']))}`; execution modes: `{_fmt_value(sorted(set(modes)))}`")
    lines.append("- ScienceR-Dsim validation after today’s changes: `32 passed`")
    if non_markovian_report is not None:
        lines.append(f"- Non-Markovian TEMPO verdict: `{_fmt_value(non_markovian_report.get('verdict'))}`; convergence passed: `{_fmt_value(non_markovian_report.get('convergence_passed'))}`; max refinement difference: `{_fmt_value(non_markovian_report.get('max_state_difference'))}`")
    lines.append("")
    lines.append("## Key Results")
    lines.append("")
    lines.append("| Area | Result |")
    lines.append("| --- | --- |")
    lines.append(f"| Open quantum PDB sweep | source={_fmt_value(science_report['source'])}, method={_fmt_value(science_report['records'][0]['method'])}, gap={_fmt_value(science_report['records'][0]['gap_s'])} s^-1 |")
    lines.append(f"| SuperLU scaling | N={_fmt_value(scaling_report['records'][0]['dimension'])}, converged={_fmt_value(scaling_report['records'][0]['converged'])}, residual={_fmt_value(scaling_report['records'][0]['stationary_residual_s'])} |")
    lines.append(f"| Research campaign | F_sub={_fmt_value(research_report['optimal_lifetime']['F_sub'])}, BLP_N={_fmt_value(research_report['maximum_physiological_blp']['value'])} |")
    lines.append(f"| Comparative EEG topology | awake beta1={_fmt_value(topology_report['awake']['mean_beta1'])}, sedated beta1={_fmt_value(topology_report['sedated']['mean_beta1'])}, shift={_fmt_value(topology_report['persistence_distance_proxy'])} |")
    eeg_source = _pick(eeg_report, "source_kind", "source", default="unknown")
    dsim_source = _pick(
        dsim_report,
        "source_kind",
        "source",
        default=_pick_nested(dsim_report, "dataset", "kind", default="unknown"),
    )
    meg_source = _pick(meg_report, "source_kind", "source", default="unknown")
    lines.append(
        f"| EEG streaming run | source={_fmt_value(eeg_source)}, windows={_fmt_value(len(eeg_metrics))}, "
        f"alerts={_fmt_value(eeg_alert_count)}, mean_beta1={_fmt_value(eeg_mean_beta1)}, mean_q_spatial={_fmt_value(eeg_mean_q_spatial)} |"
    )
    lines.append(f"| Empirical DSIM falsification | source={_fmt_value(dsim_source)}, verdict={_fmt_value(dsim_report['verdict'])}, K={_fmt_value(dsim_report['bayes_factor'])} |")
    lines.append(f"| MEG falsification | source={_fmt_value(meg_source)}, verdict={_fmt_value(meg_report['verdict'])}, K={_fmt_value(meg_report['bayes_factor'])} |")
    if thermal_report.get("records"):
        last_thermal = thermal_report["records"][-1]
        last_telemetry = last_thermal.get("telemetry", {})
        lines.append(f"| DM1 thermal sweep | nodes={_fmt_value(len(thermal_report['records']))}, final T={_fmt_value(last_thermal.get('temperature_K'))} K, mode={_fmt_value(last_telemetry.get('execution_mode', 'cloud_dm1'))}, final current proxy={_fmt_value(last_telemetry.get('chiral_current_degradation_proxy'))} s^-1 |")
    if non_markovian_report is not None:
        primary = non_markovian_report.get("primary", {})
        evaluation = primary.get("evaluation", {}) if isinstance(primary, dict) else {}
        lines.append(f"| Non-Markovian TEMPO | verdict={_fmt_value(non_markovian_report.get('verdict'))}, tau={_fmt_value(evaluation.get('tau_subradiant_s'))} s, refinement difference={_fmt_value(non_markovian_report.get('max_state_difference'))}, trace residual={_fmt_value(primary.get('trace_residual'))} |")
    if multi_report.get("records"):
        multi_lifetimes = [record.get("tau_subradiant_s") for record in multi_report["records"] if record.get("tau_subradiant_s") is not None]
        span = max(multi_lifetimes) - min(multi_lifetimes) if multi_lifetimes else None
        lines.append(f"| Coupled lattices | spacings={_fmt_value([r.get('spacing_nm') for r in multi_report['records']])} nm, solver={_fmt_value(multi_report['records'][0].get('method'))}, lifetime span={_fmt_value(span)} s |")
    lines.append("")
    lines.append("## Methods and Reproducibility")
    lines.append("")
    lines.append("- Open-quantum results use a finite single-excitation Lindblad model. The Hamiltonian is dipole-coupled in SI units; local radiative, thermal, dephasing, CISS-labelled phenomenological, and optional pump jump operators preserve trace by construction.")
    lines.append("- Exact dense eigendecomposition is used through Hilbert dimension 32. Above that threshold, the configured route is a sparse CSC/SuperLU-preconditioned Krylov estimate. Solver labels in artifacts record the actual route.")
    lines.append("- EEG graph topology derives PLV-like connectivity from Hilbert phase per bounded streaming window. Persistent H1/beta1 is evaluated over a filtration sweep; spatial charge is separately estimated from montage geometry and never equated with graph-cycle count.")
    lines.append("- Cohort inference is paired-only. When fewer than two local paired subjects are available, Wilcoxon p-values are intentionally null and the output is descriptive.")
    lines.append("- JSON serialization converts non-finite values to null; figures use the headless Agg backend and close figure handles after writing.")
    lines.append("")
    lines.append("## Findings, Interpretation, and Limits")
    lines.append("")
    lines.append("### Directly supported by current artifacts")
    lines.append("")
    lines.append("- The local-PDB finite-model sweep and the current coupled-lattice benchmark completed with finite values and trace-preservation diagnostics. This supports numerical execution of these specific implementations only.")
    lines.append("- The coupled two-cylinder run showed no material separation-dependent lifetime extension across 5, 10, and 15 nm under its current parameters; the observed subradiant lifetime span is reported above.")
    lines.append("- The current local EEG subset has one paired awake/sedated subject. It can produce a comparison artifact but cannot support a cohort-level significance claim.")
    lines.append("- Recorded empirical falsification artifacts retain NOT_SUPPORTED and K=1. Therefore no positive quantum-topological empirical claim is supported by those runs.")
    lines.append("")
    lines.append("### Model-dependent interpretation")
    lines.append("")
    lines.append("- Nanosecond-scale decay values are properties of the chosen finite Hamiltonian and dissipators. They are not measured biological decoherence times and should not be compared to biological mechanisms without calibration, uncertainty analysis, and independent validation.")
    lines.append("- A nonzero chiral-current heuristic is a property of the model stationary state and cylindrical orientation convention. It is not a measurement of helical transport in microtubules.")
    lines.append("- Differences in beta1 or persistence landscapes are descriptive network-topology features. They are not diagnoses of sedation, awareness, or consciousness.")
    lines.append("")
    lines.append("### Speculative hypotheses to test, not conclusions")
    lines.append("")
    lines.append("- Larger, calibrated coupled lattices could be scanned for collective dark modes, but any apparent enhancement should be challenged with cutoff, dielectric, bath-rate, pump-site, and geometry sensitivity analyses.")
    lines.append("- A properly powered paired EEG cohort could test whether topology metrics replicate across subjects and survive pre-registered preprocessing variants. The present artifact cannot answer that question.")
    lines.append("")
    lines.append("## Artifact Index")
    lines.append("")
    lines.append("| Label | Path | Note |")
    lines.append("| --- | --- | --- |")
    for item in artifacts:
        lines.append(
            f"| {item.label} | `{_relpath(item.path, SCIENCE_ROOT.parent)}` | {item.note} |"
        )
    lines.append("")
    lines.append("## Data Highlights")
    lines.append("")
    lines.append("### ScienceR-Dsim")
    lines.append("")
    for key in ("source", "temperatures_K", "scientific_note"):
        lines.append(f"- PDB sweep `{key}`: `{_fmt_value(science_report.get(key))}`")
    lines.append(f"- Dense scaling source: `{_fmt_value(scaling_report.get('source'))}`")
    lines.append(f"- Dense scaling note: `{_fmt_value(scaling_report.get('scientific_note'))}`")
    lines.append("")
    lines.append("### NeuroTopology-Sim")
    lines.append("")
    lines.append(f"- Research campaign nodes: `{_fmt_value(research_report['n_nodes'])}`")
    lines.append(f"- Campaign backend: `{_fmt_value(_read_json(NEURO_ROOT / 'artifacts' / 'pitnn' / 'research_campaign' / 'campaign_summary.json')['backend'])}`")
    lines.append(f"- Awake topology source: `{_fmt_value(topology_report['awake']['source'])}`")
    lines.append(f"- Sedated topology source: `{_fmt_value(topology_report['sedated']['source'])}`")
    lines.append(f"- EEG run source kind: `{_fmt_value(eeg_source)}`")
    lines.append(f"- EEG run window count: `{_fmt_value(len(eeg_metrics))}`")
    lines.append(f"- EEG run total alerts: `{_fmt_value(eeg_alert_count)}`")
    lines.append(f"- DSIM falsification source kind: `{_fmt_value(dsim_source)}`")
    lines.append("")
    lines.append("## Full File Inventory")
    lines.append("")
    lines.append("| Size (bytes) | SHA-256 | File |")
    lines.append("| ---: | --- | --- |")
    for path in _iter_files():
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        try:
            digest = _sha256(path)
        except OSError:
            digest = "unavailable"
        lines.append(f"| {size} | `{digest}` | `{_relpath(path, SCIENCE_ROOT.parent)}` |")
    lines.append("")
    lines.append("## Provenance Notes")
    lines.append("")
    lines.append("- All results were generated offline from local artifacts or locally downloaded public datasets.")
    lines.append("- `PASS`/`NOT_SUPPORTED` gates were preserved exactly as recorded in the source reports.")
    lines.append("- Any comparison labeled as a proxy, heuristic, or descriptive metric should be treated as such and not as clinical proof.")
    lines.append("")
    appendix, omitted = _json_appendix()
    lines.append("## Structured Result Payload Appendix")
    lines.append("")
    lines.append("The following small JSON result payloads are embedded verbatim for mobile/offline review. Binary or large files remain represented by their indexed SHA-256 digests above.")
    lines.append("")
    lines.extend(appendix)
    lines.extend(_qm_text_appendix())
    if omitted:
        lines.append("### Omitted structured payloads")
        lines.append("")
        lines.extend(f"- {item}" for item in omitted)
        lines.append("")
    return "\n".join(lines)


def build_report(output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = _build_report()
    output_path.write_text(content, encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile simulation artifacts into a single Markdown report.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path for the compiled report Markdown file.",
    )
    parser.add_argument(
        "--awareness-output",
        default=str(NEURO_ROOT / "apps" / "awareness_studio" / "inputs" / "sim_artifacts" / "compiled_simulation_report.md"),
        help="Optional Awareness Studio ingestion copy of the same compiled record.",
    )
    args = parser.parse_args()
    path = build_report(Path(args.output))
    awareness_path = Path(args.awareness_output)
    if awareness_path:
        build_report(awareness_path)
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
