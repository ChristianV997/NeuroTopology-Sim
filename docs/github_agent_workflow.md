# GitHub Agent Workflow (DS005620)

## Agent lanes

- **Opus lane**: architecture/runtime/autonomy work for P18.2 implementation details.
- **Codex lane**: contracts/validators/CI-safe tooling for DS005620 artifact and contract checks.
- **Copilot lane**: GitHub hygiene, review templates, governance docs, and merge gating checklists.

## Branch naming

- Use focused branches with lane + scope, e.g. `copilot/p18-2-github-review-governance`.
- Keep branch scope narrow to reduce merge conflicts across parallel lanes.

## PR expectations

- Fill out every section of `.github/pull_request_template.md`.
- Declare phase/scope and execution-path impact.
- Declare all commands run, and list skipped commands with reason.
- Explicitly confirm guardrails are preserved.

## Review checklist

- Confirm claimed phase matches changed files.
- Confirm P12/P13/P11 execution implications are declared.
- Confirm mock E2E vs real/local behavior is explicit.
- Confirm no banned claim language in PR summary or docs.
- Confirm required tests/validators are listed and outputs are plausible.

## Merge decision criteria

- Merge only when guardrail checklist is complete and accurate.
- Merge only when phase-specific validation commands pass.
- Block merge if PR claims exceed available controls/artifacts.
- Block merge if a PR modifies critical benchmark gates without explicit review notes.

## Duplicate PR handling

- Close duplicate PRs after linking the canonical active PR.
- Preserve any unique checklist, evidence, or review notes before closing.
- Ask submitters to rebase onto the active lane if partial work is still needed.

## Stale issue handling

- Mark stale DS005620 governance issues after inactivity and missing reproduction details.
- Keep issues open when they include actionable artifacts, failing commands, or active blockers.
- Request updated command output before closure when context is outdated.

## How to avoid conflicting with parallel agents

- Avoid runtime-core edits in the governance lane.
- Do not edit contract implementation files owned by Codex lane.
- Keep governance changes in `.github/`, `docs/`, `tests/btc_icft/`, and minimal `Makefile`.
- Prefer additive docs/templates/tests rather than changing execution logic.
