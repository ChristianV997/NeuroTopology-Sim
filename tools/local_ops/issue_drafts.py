"""
GitHub issue draft generator for the local ops action queue (P26).

Reads action_queue.json and produces github_issue_drafts.md with Markdown issue
drafts. Never calls the GitHub API. Never submits issues.

CLI:
    python -m tools.local_ops.issue_drafts \
        --queue outputs/local_ops/action_queue.json \
        --out outputs/local_ops/github_issue_drafts.md

stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


_COMMON_GUARDRAILS = [
    "Do not execute real data as part of this issue's work.",
    "Do not download datasets automatically.",
    "Do not confirm peer review on behalf of a human.",
    "Do not push to git remotes, merge PRs, or close issues automatically.",
    "Preserve ontology quarantine and language firewall.",
]


def _format_guardrails() -> str:
    return "\n".join(f"- {g}" for g in _COMMON_GUARDRAILS)


def _issue_local_data_roots() -> str:
    return """\
## Draft: Provide local dataset roots (manual)

**Objective**: Enable real-execution planning by placing BIDS-formatted dataset files
locally for the six planned datasets.

**Context**:
This is the highest-impact unlock currently identified. Downstream pipelines
(multi-dataset autonomous iteration, real-execution gate) require local dataset
presence before real-data planning can proceed.

**Tasks**:
- [ ] Create `data/DS005620/`, `data/DS002094/`, `data/ds001787/`, `data/ds003969/`, `data/ds003816/`, `data/PhysioNet_GABA/`
- [ ] Place BIDS-formatted raw EEG in each directory
- [ ] Place `events.tsv` in each directory
- [ ] Run `make real-data-source-matrix` and verify `local_root_present: true`
- [ ] Run `make multi-dataset-autonomous-iteration-dry-run`

**Acceptance criteria**:
- `outputs/btc_icft/multi_dataset_real_execution/empirical_readiness_matrix.json` reports
  `local_root_present: true` for at least one dataset.
- No test regressions.

**Tests**:
- `python -m pytest tests/btc_icft -q`

**Suggested labels**: `manual`, `local-data`, `real-execution-gate`, `human-required`

**Guardrails**:
""" + _format_guardrails() + "\n"


def _issue_dataset_executor(ds_id: str = "DS002094") -> str:
    ds_lower = ds_id.lower()
    return f"""\
## Draft: Add {ds_id} dataset-specific executor

**Objective**: Add a {ds_id}-specific real-artifact build operator that mirrors the
DS005620 pipeline. Implementation-only; no real data run.

**Context**:
The multi-dataset framework currently supports one dataset-specific executor
(DS005620). Additional datasets share the framework skeleton but need per-dataset
executors to plan real artifact builds.

**Tasks**:
- [ ] Add `sciencer_d/btc_icft/pipelines/run_{ds_lower}_real_artifact_build_operator.py`
- [ ] Add `contracts/btc_icft/{ds_lower}/` config files
- [ ] Add `tests/btc_icft/test_{ds_lower}_executor.py`
- [ ] Add Makefile target `{ds_lower}-real-artifact-plan`
- [ ] Extend `docs/multi_dataset_real_execution_framework.md` with a {ds_id} section

**Acceptance criteria**:
- New test file passes.
- `make {ds_lower}-real-artifact-plan` produces a plan JSON without executing real data.
- Existing tests still pass.
- Ontology and language checks pass.

**Tests**:
- `python -m pytest tests/btc_icft/test_{ds_lower}_executor.py -q`
- `python -m pytest tests/btc_icft -q`
- `make ontology-language-check`

**Suggested labels**: `dataset-executor`, `{ds_lower}`, `agent-lane:claude`, `p1`

**Guardrails**:
{_format_guardrails()}
"""


def _issue_controls_validator() -> str:
    return """\
## Draft: Post-real-execution controls validator

**Objective**: Add a validator that checks whether real-execution outputs satisfy
contract requirements: trial counts, behavior compliance, label-contract compliance,
and runtime guardrails.

**Context**:
When real data is eventually executed by a human operator, downstream validation
needs a deterministic pass/fail on the output artifacts. The validator must handle
both present and absent outputs gracefully.

**Tasks**:
- [ ] Add `tools/validate_real_execution_controls.py`
- [ ] Add `tests/btc_icft/test_real_execution_controls.py`
- [ ] Add Makefile target `validate-real-execution-controls`
- [ ] Return structured JSON in both `available` and `not_available` states

**Acceptance criteria**:
- Validator returns deterministic JSON.
- Tests fully offline; no real data required.
- Ontology and language checks pass.

**Tests**:
- `python -m pytest tests/btc_icft/test_real_execution_controls.py -q`

**Suggested labels**: `controls`, `validator`, `agent-lane:codex`, `p1`

**Guardrails**:
""" + _format_guardrails() + "\n"


def _issue_stale_pr(pr_number: int = 114) -> str:
    return f"""\
## Draft: Review and clean stale open PR #{pr_number} (manual)

**Objective**: Determine whether PR #{pr_number} contains any unique unmerged content
after the P22–P25 work landed, and prepare a manual close recommendation.

**Context**:
PR #{pr_number} appears stale and likely superseded. Since this repository forbids
automatic PR closes, the recommendation is manual only.

**Tasks**:
- [ ] Fetch PR #{pr_number} diff and review it
- [ ] Compare against merged commits since P22
- [ ] Draft a supersession comment (or keep open if unique content exists)
- [ ] Save recommendation to `outputs/local_ops/pr_{pr_number}_recommendation.md`

**Acceptance criteria**:
- Recommendation exists.
- Operator can decide next step manually.

**Tests**: none.

**Suggested labels**: `repo-hygiene`, `manual`, `agent-lane:copilot`, `p3`

**Guardrails**:
{_format_guardrails()}
- Do not close, merge, or push PR #{pr_number} automatically.
"""


def _issue_oss_harvest() -> str:
    return """\
## Draft: OSS harvest — BIDS / MNE / MOABB adapter patterns

**Objective**: Survey open-source BIDS, MNE-Python, and MOABB ecosystems for adapter
patterns that could inform multi-dataset executor design.

**Context**:
The multi-dataset executor design lives inside this repo, but the broader OSS EEG
ecosystem has mature patterns worth cataloging. This is a docs-only task; no code
is pulled or installed.

**Tasks**:
- [ ] Add `docs/oss_harvest_bids_mne_moabb.md`
- [ ] One section per ecosystem
- [ ] Adapter pattern summary
- [ ] License compatibility notes (informational only)
- [ ] Suggested integration points

**Acceptance criteria**:
- Doc exists and passes language check.

**Tests**:
- `make ontology-language-check`
- `make github-governance-check`

**Suggested labels**: `oss-harvest`, `docs`, `agent-lane:claude`, `p2`

**Guardrails**:
""" + _format_guardrails() + """
- Do not auto-pull or install third-party packages.
"""


def _generate(actions: list[dict]) -> str:
    """Build the full issue-drafts markdown."""
    lines = [
        "# GitHub Issue Drafts (P26)",
        "",
        "These are **drafts only**. No issue is created, opened, or submitted by any",
        "automation in this repository. Copy-paste into GitHub manually only if you",
        "decide to file the issue.",
        "",
        "## Common Guardrails",
        "",
        _format_guardrails(),
        "",
        "---",
        "",
        _issue_local_data_roots(),
        "",
        "---",
        "",
        _issue_dataset_executor("DS002094"),
        "",
        "---",
        "",
        _issue_controls_validator(),
        "",
        "---",
        "",
        _issue_stale_pr(114),
        "",
        "---",
        "",
        _issue_oss_harvest(),
        "",
        "---",
        "",
        "## What this file never does",
        "",
        "- Submits issues to GitHub",
        "- Opens pull requests",
        "- Pushes to git remotes",
        "- Assigns reviewers",
        "- Applies labels via API",
        "",
        "---",
        "#local-ops #issue-drafts #sciencer-dsim",
    ]
    return "\n".join(lines)


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="Local ops issue draft generator (P26)")
    p.add_argument("--queue", default="outputs/local_ops/action_queue.json")
    p.add_argument("--out", default="outputs/local_ops/github_issue_drafts.md")
    args = p.parse_args(argv)

    queue_path = Path(args.queue)
    if queue_path.exists():
        data = json.loads(queue_path.read_text(encoding="utf-8"))
        actions = data.get("actions", [])
    else:
        actions = []

    md = _generate(actions)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"github_issue_drafts.md → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
