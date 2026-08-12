"""oss_opportunities ranks candidate open-source repositories (from
Trendshift snapshots, Star History starmap snapshots, GitHub metadata, and
manual seed lists) for their leverage potential to NeuroTopology-Sim /
Awareness Studio -- it does not integrate anything, does not install
dependencies, does not execute or clone external code, and does not
redistribute raw third-party API data.

Placed as a top-level package, sibling to `external_tools/` and
`dataset_opportunities/`, rather than folded into either:

- `external_tools/` is this repository's small, hand-curated catalog of
  tools it has *already deliberately assessed* for adapter integration
  (`ExternalToolRecordV1`/`AdapterContractV1`) -- a manually reviewed
  registry, not a scouting pipeline.
- `dataset_opportunities/` ranks *datasets* discovered via EEGDash/MOABB --
  a different domain (data, not code/tooling) with a different source
  model (dataset catalogs, not repository-trend snapshots).
- `oss_opportunities/` (this package) ranks *repositories* discovered via
  Trendshift/Star History/GitHub metadata/manual seeds for engineering
  leverage -- close in shape to `dataset_opportunities` (candidate ->
  opportunity -> batch -> plan -> render) but a genuinely different input
  domain, so it is not folded into either existing package.

`tools/public_repo_harvest/` is a pre-existing, unrelated prototype (added
well before this package, under a different, looser coding convention: no
`from __future__ import annotations`, one-line function bodies, no
`validate_or_raise`/deterministic-ID discipline, no tests). It covers a
broader, more ad hoc "harvest reusable patterns across many subsystems"
scope and is neither reused nor modified by this package -- see
docs/oss_opportunity_pipeline.md for the full comparison.
"""
