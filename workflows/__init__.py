"""Product-facing pipeline orchestration layer.

`workflows` does not implement new scientific logic -- it only chains
already-governed modules (`adapters.*`, `evidence.builder`,
`reports.evidence_report`) into one deterministic, guarded runner and
report-pack manifest. See docs/report_pipeline_runner.md.
"""
