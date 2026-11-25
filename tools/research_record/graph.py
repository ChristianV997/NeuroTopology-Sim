"""PR stacking graph, cycle detection, and recommended merge order.

A PR is "stacked" on another when its ``base_branch`` is that other PR's
head ``branch`` (rather than the repository's default branch), or when it
names the other PR explicitly via ``parent_pr``. Per
``configs/release/evidence_schema.yaml``'s ``stacked_parent_required`` and
``stacked_merged_parent_open_contradiction`` rules, a stacked PR's parent
must be identifiable, and a stacked child cannot be "merged" while its
parent is still open/draft -- both are checked here.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PRNode:
    number: int
    branch: str | None
    base_branch: str | None
    parent_pr: int | None
    merge_status: str
    status_category: str
    is_draft: bool | None
    is_ancestor_of_target: bool | None
    mergeable: bool | None
    ci_status: str
    superseded_by_pr: int | None
    duplicate_of_pr: int | None
    depends_on: tuple[int, ...] = field(default_factory=tuple)


def build_dependency_edges(nodes: list[PRNode]) -> dict[int, set[int]]:
    """Return {pr_number: {pr_numbers it depends on}}."""
    branch_to_number = {node.branch: node.number for node in nodes if node.branch}
    edges: dict[int, set[int]] = {node.number: set(node.depends_on) for node in nodes}
    for node in nodes:
        if node.parent_pr is not None:
            edges[node.number].add(node.parent_pr)
        elif node.base_branch and node.base_branch in branch_to_number:
            base_pr = branch_to_number[node.base_branch]
            if base_pr != node.number:
                edges[node.number].add(base_pr)
    return edges


def find_cycles(edges: dict[int, set[int]]) -> list[list[int]]:
    """Return each distinct cycle (as a list of PR numbers) found in ``edges``."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[int, int] = {n: WHITE for n in edges}
    stack: list[int] = []
    cycles: list[list[int]] = []

    def visit(node: int) -> None:
        color[node] = GRAY
        stack.append(node)
        for dep in sorted(edges.get(node, ())):
            if dep not in color:
                continue
            if color[dep] == GRAY:
                cycle_start = stack.index(dep)
                cycles.append(stack[cycle_start:] + [dep])
            elif color[dep] == WHITE:
                visit(dep)
        stack.pop()
        color[node] = BLACK

    for node in sorted(edges):
        if color[node] == WHITE:
            visit(node)
    return cycles


def topological_layers(node_numbers: list[int], edges: dict[int, set[int]]) -> list[list[int]]:
    """Kahn's algorithm restricted to ``node_numbers``, deterministic layer order."""
    allowed = set(node_numbers)
    restricted_edges = {n: {d for d in edges.get(n, ()) if d in allowed} for n in allowed}
    remaining = set(allowed)
    layers: list[list[int]] = []
    while remaining:
        ready = sorted(n for n in remaining if not (restricted_edges[n] & remaining))
        if not ready:
            break  # residual cycle among `remaining`
        layers.append(ready)
        remaining -= set(ready)
    return layers


def find_stacked_parent_violations(nodes: list[PRNode]) -> list[dict]:
    """Flag stacked children whose parent could not be identified, and
    stacked children marked merged while their parent is open/draft."""
    by_number = {n.number: n for n in nodes}
    edges = build_dependency_edges(nodes)
    violations: list[dict] = []
    for node in nodes:
        for parent_number in sorted(edges.get(node.number, set())):
            parent = by_number.get(parent_number)
            if parent is None:
                violations.append(
                    {
                        "pr_number": node.number,
                        "kind": "stacked_parent_missing",
                        "detail": f"PR #{node.number} is stacked on PR #{parent_number}, which is not present in this evidence set",
                    }
                )
                continue
            if node.merge_status == "merged" and parent.merge_status in ("open", "draft"):
                violations.append(
                    {
                        "pr_number": node.number,
                        "kind": "stacked_merged_parent_open",
                        "detail": f"PR #{node.number} is recorded merged while its parent PR #{parent_number} is still {parent.merge_status}",
                    }
                )
    return violations


def find_duplicate_violations(nodes: list[PRNode]) -> list[dict]:
    """Flag DUPLICATE-status entries with no pointer, and branch collisions.

    Mirrors evidence_schema.yaml's ``no_duplicate_branches_in_compiled_report``
    hard rule: two active (non-superseded, non-blocked) entries sharing the
    same non-null branch is a contradiction, not a coincidence.
    """
    violations: list[dict] = []
    for node in nodes:
        if node.status_category == "DUPLICATE" and node.duplicate_of_pr is None:
            violations.append(
                {
                    "pr_number": node.number,
                    "kind": "duplicate_marked_without_pointer",
                    "detail": f"PR #{node.number} has status_category=DUPLICATE but no duplicate_of_pr pointer",
                }
            )

    branch_to_numbers: dict[str, list[int]] = {}
    for node in nodes:
        if node.branch and node.merge_status not in ("blocked", "closed") and node.superseded_by_pr is None:
            branch_to_numbers.setdefault(node.branch, []).append(node.number)
    for branch, numbers in sorted(branch_to_numbers.items()):
        if len(numbers) > 1:
            for number in sorted(numbers):
                violations.append(
                    {
                        "pr_number": number,
                        "kind": "duplicate_branch",
                        "detail": f"branch {branch!r} is shared by multiple active PR entries: {sorted(numbers)}",
                    }
                )
    return violations


def recommended_merge_order(nodes: list[PRNode]) -> tuple[list[int], dict[int, str]]:
    """Compute a deterministic recommended merge order plus exclusion reasons."""
    by_number = {n.number: n for n in nodes}
    edges = build_dependency_edges(nodes)

    excluded: dict[int, str] = {}
    for node in nodes:
        if node.merge_status != "open":
            excluded[node.number] = f"not_open:{node.merge_status}"
        elif node.mergeable is False:
            excluded[node.number] = "not_mergeable"
        elif node.superseded_by_pr is not None:
            excluded[node.number] = f"superseded_by_pr_{node.superseded_by_pr}"
        elif node.duplicate_of_pr is not None:
            excluded[node.number] = f"duplicate_of_pr_{node.duplicate_of_pr}"
        elif node.ci_status in ("failed", "timed_out"):
            excluded[node.number] = f"ci_{node.ci_status}"
        elif node.status_category in ("CI_BLOCKED", "BILLING_BLOCKED", "SCIENTIFIC_REVIEW_REQUIRED"):
            excluded[node.number] = f"status_category_{node.status_category}"

    changed = True
    while changed:
        changed = False
        for node in nodes:
            if node.number in excluded:
                continue
            for dep in edges.get(node.number, ()):
                dep_node = by_number.get(dep)
                dep_is_merged = dep_node is not None and dep_node.merge_status == "merged"
                if dep_is_merged:
                    continue
                if dep in excluded or dep_node is None:
                    excluded[node.number] = f"blocked_on_dependency_{dep}"
                    changed = True
                    break

    eligible = sorted(n.number for n in nodes if n.number not in excluded)
    layers = topological_layers(eligible, edges)
    ordered = [pr for layer in layers for pr in layer]
    return ordered, excluded
