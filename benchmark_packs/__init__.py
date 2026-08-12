"""benchmark_packs assembles curated collections of already-governed
`ReportPipelineSpecV1`/`PipelineJobV1`/`ReportPackV1`/`HtmlReportPackV1`
artifacts into a single `BenchmarkPackV1` -- it contains no scientific
logic of its own, mutates no seed registry, and downloads nothing.

Placed as a top-level product package (siblings: `workflows/`,
`job_runner/`) rather than under `benchmarks/`, because `benchmarks/` is
this repository's data-governance registry namespace
(`DatasetRecordV1`/`ArtifactRecordV1`/`BenchmarkRegistry` -- dataset-use
tracking and split/holdout enforcement). `BenchmarkPackV1` is an
unrelated concept -- a product artifact (a curated demo/methods/sample
pack of report packs) -- and nesting it under `benchmarks/` would invite
exactly the `BenchmarkPackV1` vs. `BenchmarkRegistry` confusion this
milestone was explicitly asked to avoid. See docs/benchmark_pack_generator.md.
"""
