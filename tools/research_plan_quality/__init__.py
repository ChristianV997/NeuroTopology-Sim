"""Deterministic research-plan / preregistration-manifest quality rubric.

Inspired by PaperGym's rubric-centered evaluation idea, but no external
code is copied or imported -- every check here is freshly, independently
implemented against this package's own :class:`models.ResearchPlan`
input schema.

Owned exclusively by claude/research-plan-quality-rubric-20260910:
tools/research_plan_quality/**, scripts/audit_research_plan.py,
tests/research_plan_quality/**, docs/research/research_plan_quality_rubric.md.

This package evaluates the *quality of a plan*, never the *truth of a
scientific result*. Every output carries ``evidence_class =
"research_plan_audit"`` for exactly this reason: a high rubric score is
a statement about how well-specified a plan is, never a stand-in for
scientific confirmation. The evaluator never infers a missing field,
never fills in a method the plan didn't specify, and never fetches
anything over the network -- it is a pure function of the
``ResearchPlan`` the caller supplies.
"""
from __future__ import annotations
