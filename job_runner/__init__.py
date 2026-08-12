"""Local-first, file-backed job runner for `workflows.report_pipeline`.

`job_runner` orchestrates existing governed modules
(`workflows.report_pipeline.run_report_pipeline`,
`workflows.html_report_pack.render_html_report_pack`) into a tracked job
lifecycle -- it contains no scientific logic of its own, mutates no seed
registry, and downloads nothing. See docs/job_runner.md.
"""
