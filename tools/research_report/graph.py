"""PR dependency/stacking graph, cycle detection, and recommended merge order.

A PR depends on another PR either explicitly (``depends_on``) or implicitly
by being stacked on top of it (its ``base_branch`` is the other PR's head
branch, rather than the repository's default branch). Both are folded into
one dependency graph so stacked PR chains (e.g. A <- B <- C) are treated the
same as explicitly declared dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PRNode:
    number: int
    branch: str | None
    base_branch: str | None
    state: str
    mergeable: bool | None
    ci_status: str
    superseded_by_pr: int | None
    depends_on: tuple[int, ...] = field(default_factory=tuple)


def build_dependency_edges(nodes: list[PRNode]) -> dict[int, set[int]]:
    """Return {pr_number: {pr_numbers it depends on}}."""
    branch_to_number = {node.branch: node.number for node in nodes if node.branch}
    edges: dict[int, set[int]] = {node.number: set(node.depends_on) for node in nodes}
    for node in nodes:
        if node.base_branch and node.base_branch in branch_to_number:
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
            # Residual cycle among `remaining`: stop rather than loop forever.
            break
        layers.append(ready)
        remaining -= set(ready)
    return layers


def recommended_merge_order(nodes: list[PRNode]) -> tuple[list[int], dict[int, str]]:
    """Compute a deterministic recommended merge order plus exclusion reasons.

    Returns ``(ordered_pr_numbers, excluded_reasons)``. A PR is excluded when
    it is not open, is known-unmergeable, is superseded, has failing CI, or
    depends (directly or transitively) on a PR that is itself excluded and
    not already merged.
    """
    by_number = {n.number: n for n in nodes}
    edges = build_dependency_edges(nodes)

    excluded: dict[int, str] = {}
    for node in nodes:
        if node.state != "open":
            excluded[node.number] = f"not_open:{node.state}"
        elif node.mergeable is False:
            excluded[node.number] = "not_mergeable"
        elif node.superseded_by_pr is not None:
            excluded[node.number] = f"superseded_by_pr_{node.superseded_by_pr}"
        elif node.ci_status == "failed":
            excluded[node.number] = "ci_failed"

    # Propagate exclusion to anything depending on an excluded/unmerged PR.
    changed = True
    while changed:
        changed = False
        for node in nodes:
            if node.number in excluded:
                continue
            for dep in edges.get(node.number, ()):
                dep_node = by_number.get(dep)
                dep_is_merged = dep_node is not None and dep_node.state == "merged"
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
