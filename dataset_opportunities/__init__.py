"""dataset_opportunities ranks already-imported `DatasetCandidateRecordV1`
scouting records (from `dataset_importers`) into `DatasetOpportunityRecordV1`
opportunities and produces human-reviewed next-action plans -- it contains
no scientific logic, downloads nothing, extracts no features, and creates
no evidence.

Placed as a top-level package (sibling to `dataset_importers/`,
`dataset_acquisition/`, `benchmark_packs/`) rather than folded into
`dataset_importers/`, because import (turning a catalog entry into a
`DatasetCandidateRecordV1`) and opportunity ranking (turning many
candidates into a ranked, actionable plan) are separate concerns with
separate audiences -- the same reasoning that kept `benchmark_packs/`
separate from `benchmarks/`. See docs/dataset_opportunity_pipeline.md.
"""
