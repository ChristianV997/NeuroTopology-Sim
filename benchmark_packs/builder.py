"""`build_benchmark_pack` -- orchestrates `job_runner.batch` to execute a
`BenchmarkPackSpecV1` and assemble the resulting `BenchmarkPackV1`. Also
provides the default curated pack-spec generators
(`make_builtin_demo_pack_spec`/`make_fixture_demo_pack_spec`/
`make_methods_supplement_pack_spec`) built only from this repository's
own already-committed contract artifacts or synthetic test fixtures --
never from a download.

This module contains no report-pipeline scientific logic of its own: it
only calls `job_runner.batch.create_batch_from_specs`/`run_batch` (which
themselves call `job_runner.store.JobStore.create_job`/
`job_runner.runner.run_pipeline_job` unmodified) and reads back the
`PipelineJobResultV1` records those calls already wrote.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

from benchmark_packs.pack_manifest import BenchmarkPackV1
from benchmark_packs.pack_spec import BenchmarkPackSpecV1
from benchmark_packs.renderer import render_benchmark_pack_index

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"
_DS005620_SOURCE = _REPO_ROOT / "contracts" / "btc_icft" / "ds005620" / "pitnn_cohort"
_DS000245_SOURCE = _REPO_ROOT / "contracts" / "fmri_tda" / "ds000245"

_BUILDER_LIMITATIONS: list[str] = [
    "benchmark_packs.builder only orchestrates job_runner.batch.create_batch_from_specs/run_batch and, "
    "through those, job_runner.runner.run_pipeline_job -- it contains no feature extraction, no raw "
    "EEG/fMRI signal processing, and no LLM call.",
    "This benchmark pack is not itself evidence -- it is a curated collection of already-governed report "
    "packs the underlying pipeline runs already produced.",
]


def _relative_path(path: Union[str, Path]) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        return str(p)


def build_benchmark_pack(spec: BenchmarkPackSpecV1) -> BenchmarkPackV1:
    """1. Validates `spec`. 2. Materializes any embedded `pipeline_specs`
    dicts to files (never mutating the original spec object) and combines
    them with `pipeline_spec_paths`. 3. Creates one job per spec via
    `job_runner.batch.create_batch_from_specs` -- never executes yet.
    4. If `spec.run_immediately`, runs that batch via `job_runner.batch.run_batch`.
    5. Reads back every job's `PipelineJobV1`/`PipelineJobResultV1` to
    assemble `BenchmarkPackV1`. 6. If `spec.include_html` and any HTML
    report packs were produced, renders the pack's own static index.
    Never invents a report/HTML pack id for a job that did not produce
    one."""
    from job_runner.batch import batch_manifest_path, create_batch_from_specs, run_batch
    from job_runner.store import JobStore
    from workflows.report_pipeline import ReportPipelineSpecV1

    spec.validate_or_raise()

    materialized_paths: list[str] = list(spec.pipeline_spec_paths)
    if spec.pipeline_specs:
        materialize_dir = Path(spec.output_root) / "pipeline_specs"
        for idx, pipeline_spec_dict in enumerate(spec.pipeline_specs):
            pspec = ReportPipelineSpecV1.from_dict(pipeline_spec_dict)
            pspec_path = materialize_dir / f"spec_{idx:03d}.json"
            pspec.write_json(pspec_path)
            materialized_paths.append(str(pspec_path))

    batch_manifest = create_batch_from_specs(
        materialized_paths, spec.jobs_root, requested_outputs=spec.requested_outputs, batch_name=spec.pack_name,
    )
    job_ids = list(batch_manifest.job_ids)

    if spec.run_immediately:
        bmp = batch_manifest_path(spec.jobs_root, batch_manifest.batch_id)
        batch_manifest = run_batch(bmp, max_jobs=spec.max_jobs)

    store = JobStore(spec.jobs_root)
    pipeline_ids: list[str] = []
    report_pack_ids: list[str] = []
    html_pack_ids: list[str] = []
    dataset_ids: set = set()
    modalities: set = set()
    input_modes: set = set()
    generated_report_pack_paths: list[str] = []
    generated_html_paths: list[str] = []
    completed = failed = 0

    for job_id in job_ids:
        job = store.load_job(job_id)
        if job.pipeline_spec:
            pid = job.pipeline_spec.get("pipeline_id")
            if pid:
                pipeline_ids.append(pid)
            if job.pipeline_spec.get("dataset_id"):
                dataset_ids.add(job.pipeline_spec["dataset_id"])
            if job.pipeline_spec.get("modality"):
                modalities.add(job.pipeline_spec["modality"])
            if job.pipeline_spec.get("input_mode"):
                input_modes.add(job.pipeline_spec["input_mode"])

        result = store.load_result(job_id)
        if result is None:
            continue
        if result.job_status == "failed":
            failed += 1
            continue
        if result.job_status in ("completed", "completed_with_warnings"):
            completed += 1
        if result.report_pack_id:
            report_pack_ids.append(result.report_pack_id)
            if result.report_pack_path:
                generated_report_pack_paths.append(result.report_pack_path)
        if result.html_pack_id:
            html_pack_ids.append(result.html_pack_id)
            if result.index_html_path:
                generated_html_paths.append(result.index_html_path)

    total_jobs = len(job_ids)
    not_run = total_jobs - completed - failed
    if not_run == total_jobs:
        status = "not_run"
    elif completed == total_jobs:
        status = "completed"
    elif failed == total_jobs:
        status = "failed"
    else:
        status = "completed_with_failures"

    execution_summary = {
        "total_jobs": total_jobs, "completed": completed, "failed": failed, "not_run": not_run, "status": status,
    }
    coverage_summary = {
        "n_datasets": len(dataset_ids), "n_modalities": len(modalities), "n_input_modes": len(input_modes),
        "n_report_packs": len(report_pack_ids), "n_html_packs": len(html_pack_ids),
    }

    pack = BenchmarkPackV1.make(
        source_spec_id=spec.benchmark_pack_spec_id, batch_id=batch_manifest.batch_id,
        report_pack_ids=report_pack_ids, html_pack_ids=html_pack_ids,
        pack_name=spec.pack_name, pack_kind=spec.pack_kind, pack_purpose=spec.pack_purpose,
        job_ids=job_ids, pipeline_ids=pipeline_ids,
        dataset_ids=sorted(dataset_ids), modalities=sorted(modalities), input_modes=sorted(input_modes),
        generated_report_pack_paths=generated_report_pack_paths, generated_html_paths=generated_html_paths,
        execution_summary=execution_summary, coverage_summary=coverage_summary,
        limitations=list(_BUILDER_LIMITATIONS) + list(spec.limitations),
        reproducibility_commands=[
            "python -m benchmark_packs.export_benchmark_pack build --spec <BenchmarkPackSpec.json>",
        ],
    )

    if spec.include_html and generated_html_paths:
        index = render_benchmark_pack_index(pack, spec.output_root)
        pack.generated_index_path = index.index_html_path

    pack.validate_or_raise()
    pack.write_json(Path(spec.output_root) / "BenchmarkPack.json")
    return pack


def make_builtin_demo_pack_spec(
    *, output_root: str, pack_name: str = "ds005620 / ds000245 builtin demo pack",
    include_html: bool = False, run_immediately: bool = False,
) -> BenchmarkPackSpecV1:
    """Curated pack over the four already-committed `builtin_*` modes --
    two ds005620 (EEG) and two ds000245 (fMRI) -- reusing this
    repository's own already-committed `contracts/btc_icft/ds005620/`/
    `contracts/fmri_tda/ds000245/` artifacts. No download, no
    reprocessing of raw data; each `builtin_*` mode preserves its own
    existing evidence/claim ceiling unmodified."""
    from workflows.report_pipeline import ReportPipelineSpecV1

    entries = [
        ("builtin_ds005620_cohort_summary", "ds005620", "EEG", [str(_DS005620_SOURCE)]),
        ("builtin_ds005620_spatial_defect_map", "ds005620", "EEG", [str(_DS005620_SOURCE)]),
        ("builtin_ds000245_schaefer100_motcorr", "ds000245", "fMRI", [str(_DS000245_SOURCE)]),
        ("builtin_ds000245_kmeans100", "ds000245", "fMRI", [str(_DS000245_SOURCE)]),
    ]
    pipeline_specs = []
    for input_mode, dataset_id, modality, source_paths in entries:
        pspec = ReportPipelineSpecV1.make(
            input_mode=input_mode, dataset_id=dataset_id, modality=modality,
            output_root=f"{output_root}/reports/{input_mode}", source_paths=source_paths,
            registry_path=str(_SEED_REGISTRY), include_report=True,
            limitations=["Builtin demo entry -- reuses this repository's own already-committed contract artifacts."],
            provenance=f"Generated by benchmark_packs.builder.make_builtin_demo_pack_spec ({input_mode}).",
        )
        pipeline_specs.append(pspec.to_dict())

    return BenchmarkPackSpecV1.make(
        pack_name=pack_name, pack_kind="demo_pack",
        pack_purpose="Public demo pack over this repository's already-committed builtin ds005620/ds000245 report pipelines.",
        pipeline_specs=pipeline_specs, requested_outputs=["html_report_pack" if include_html else "report_pack"],
        output_root=output_root, include_html=include_html, run_immediately=run_immediately,
        limitations=[
            "This demo pack reuses already-committed contract artifacts only -- no dataset download, no raw "
            "preprocessing beyond what the underlying builtin pipeline modes already perform.",
        ],
        provenance="Generated by benchmark_packs.builder.make_builtin_demo_pack_spec.",
        metadata={"synthetic": False, "source": "builtin_contracts"},
    )


def make_fixture_demo_pack_spec(
    fixture_dir: Union[str, Path], *, output_root: str, pack_name: str = "synthetic EEG/fMRI fixture demo pack",
    include_html: bool = False, run_immediately: bool = False,
) -> BenchmarkPackSpecV1:
    """Curated pack over one synthetic EEG (`mne_bids_derived_features`)
    and one synthetic fMRI (`fmri_derived_features`) demo, generated via
    `tests.fixtures.report_pipeline_demo`'s existing generator functions
    -- deterministic, synthetic data only, never a real dataset. Clearly
    marked synthetic in both `limitations` and `metadata`."""
    from tests.fixtures import report_pipeline_demo as demo
    from workflows.report_pipeline import ReportPipelineSpecV1

    fixture_dir = Path(fixture_dir)
    fixture_dir.mkdir(parents=True, exist_ok=True)
    eeg_dir = fixture_dir / "eeg"
    fmri_dir = fixture_dir / "fmri"
    eeg_dir.mkdir(parents=True, exist_ok=True)
    fmri_dir.mkdir(parents=True, exist_ok=True)

    eeg_features_path, eeg_mapping_path = demo.write_mne_bids_derived_features_demo(eeg_dir)
    fmri_features_path, fmri_mapping_path = demo.write_fmri_derived_features_demo(fmri_dir)

    eeg_spec = ReportPipelineSpecV1.make(
        input_mode="mne_bids_derived_features", dataset_id="demo_eeg_derived_ds", modality="EEG",
        output_root=f"{output_root}/reports/mne_bids_derived_features",
        feature_table_path=str(eeg_features_path), mapping_path=str(eeg_mapping_path),
        include_evidence_bundle=True, include_report=True,
        limitations=["Synthetic fixture demo entry -- not a real dataset."],
        provenance="Generated by benchmark_packs.builder.make_fixture_demo_pack_spec (synthetic EEG).",
    )
    fmri_spec = ReportPipelineSpecV1.make(
        input_mode="fmri_derived_features", dataset_id="demo_fmri_derived_ds", modality="fMRI",
        output_root=f"{output_root}/reports/fmri_derived_features",
        feature_table_path=str(fmri_features_path), mapping_path=str(fmri_mapping_path),
        include_evidence_bundle=True, include_report=True,
        limitations=["Synthetic fixture demo entry -- not a real dataset."],
        provenance="Generated by benchmark_packs.builder.make_fixture_demo_pack_spec (synthetic fMRI).",
    )

    return BenchmarkPackSpecV1.make(
        pack_name=pack_name, pack_kind="internal_regression_pack",
        pack_purpose="Internal regression pack over synthetic EEG/fMRI derived-feature demo fixtures.",
        pipeline_specs=[eeg_spec.to_dict(), fmri_spec.to_dict()],
        requested_outputs=["html_report_pack" if include_html else "report_pack"],
        output_root=output_root, include_html=include_html, run_immediately=run_immediately,
        limitations=[
            "This pack is built entirely from synthetic (randomly generated) test fixtures -- it does not "
            "reference any real subject, dataset, or empirical measurement.",
        ],
        provenance="Generated by benchmark_packs.builder.make_fixture_demo_pack_spec.",
        metadata={"synthetic": True, "source": "tests.fixtures.report_pipeline_demo"},
    )


def make_methods_supplement_pack_spec(
    *, output_root: str, pack_name: str = "methods paper supplement pack",
    include_html: bool = True, run_immediately: bool = False,
) -> BenchmarkPackSpecV1:
    """Curated cross-modality pack (one EEG builtin + one fMRI builtin)
    intended as a methods-paper supplement -- same already-committed
    contract artifacts as `make_builtin_demo_pack_spec`, a narrower
    selection with `pack_kind="methods_supplement"`."""
    from workflows.report_pipeline import ReportPipelineSpecV1

    eeg_spec = ReportPipelineSpecV1.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root=f"{output_root}/reports/builtin_ds005620_cohort_summary", source_paths=[str(_DS005620_SOURCE)],
        registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["Methods-supplement demo entry -- reuses already-committed contract artifacts."],
        provenance="Generated by benchmark_packs.builder.make_methods_supplement_pack_spec (EEG).",
    )
    fmri_spec = ReportPipelineSpecV1.make(
        input_mode="builtin_ds000245_schaefer100_motcorr", dataset_id="ds000245", modality="fMRI",
        output_root=f"{output_root}/reports/builtin_ds000245_schaefer100_motcorr", source_paths=[str(_DS000245_SOURCE)],
        registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["Methods-supplement demo entry -- reuses already-committed contract artifacts."],
        provenance="Generated by benchmark_packs.builder.make_methods_supplement_pack_spec (fMRI).",
    )

    return BenchmarkPackSpecV1.make(
        pack_name=pack_name, pack_kind="methods_supplement",
        pack_purpose="Cross-modality (EEG + fMRI) methods-paper supplement over already-committed builtin report pipelines.",
        pipeline_specs=[eeg_spec.to_dict(), fmri_spec.to_dict()],
        requested_outputs=["html_report_pack" if include_html else "report_pack"],
        output_root=output_root, include_html=include_html, run_immediately=run_immediately,
        limitations=[
            "This pack reuses already-committed contract artifacts only -- no dataset download, no raw "
            "preprocessing beyond what the underlying builtin pipeline modes already perform.",
        ],
        provenance="Generated by benchmark_packs.builder.make_methods_supplement_pack_spec.",
        metadata={"synthetic": False, "source": "builtin_contracts"},
    )
