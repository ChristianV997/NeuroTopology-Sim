"""
Golden eval harness for the Monk+Scientist RAG system.

Usage:
    python -m awareness_studio.eval_runner [--no-llm] [--questions PATH] [--k N] [--verbose]

--no-llm mode:  validates retrieval coverage and prompt structure only (no API key needed).
Full LLM mode:  runs the complete pipeline and checks LLM output against golden criteria.

Exit code: 0 = all pass, 1 = some failures.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from awareness_studio.answer_modes import build_chat_prompt
from awareness_studio.index_build import get_or_build_index
from awareness_studio.prompts import SYSTEM_PROMPT

_DEFAULT_GOLDEN = Path(__file__).resolve().parent.parent.parent / "tests" / "golden_questions.json"


# ── Result data class ─────────────────────────────────────────────────────────

@dataclass
class EvalResult:
    question_id: str
    mode: str
    question: str
    passed: bool
    failures: List[str]
    retrieved_count: int
    llm_used: bool


# ── No-LLM checks ─────────────────────────────────────────────────────────────

def _check_no_llm(entry: dict, k: int, verbose: bool) -> EvalResult:
    """Validate retrieval coverage and prompt structure without calling the LLM."""
    qid = entry["id"]
    question = entry["question"]
    mode = entry["mode"]
    min_sources = entry.get("min_sources", 1)
    must_include = entry.get("must_include", [])
    must_not_include = entry.get("must_not_include", [])

    failures: List[str] = []

    # 1. Retrieval coverage
    index = get_or_build_index()
    results = index.retrieve(question, k=k)
    retrieved = len([c for c, s in results if s > 0])

    if retrieved < min_sources:
        failures.append(
            f"min_sources not met: need {min_sources}, got {retrieved} non-zero results"
        )

    # 2. Prompt structure: assemble prompt and verify must_include patterns
    #    are present in the combined system+user prompt (they are the *instructions*,
    #    so they will appear as formatting requirements).
    chunks = [c for c, _ in results]
    system, user = build_chat_prompt(question, mode, chunks)
    combined_prompt = system + "\n" + user

    for term in must_include:
        if term.lower() not in combined_prompt.lower():
            failures.append(f"must_include '{term}' not found in assembled prompt")

    # 3. must_not_include: these phrases must not appear in the *system prompt* itself
    #    (would indicate an unsafe guardrail breach in the instructions).
    for term in must_not_include:
        if term.lower() in SYSTEM_PROMPT.lower():
            failures.append(f"must_not_include '{term}' found in SYSTEM_PROMPT (guardrail leak)")

    if verbose:
        status = "PASS" if not failures else "FAIL"
        print(f"  [{status}] {qid} ({mode}) — retrieved={retrieved}")
        for f in failures:
            print(f"    ✗ {f}")

    return EvalResult(
        question_id=qid,
        mode=mode,
        question=question,
        passed=not failures,
        failures=failures,
        retrieved_count=retrieved,
        llm_used=False,
    )


# ── Full LLM checks ───────────────────────────────────────────────────────────

def _check_with_llm(entry: dict, k: int, verbose: bool) -> EvalResult:
    """Run full pipeline and check LLM output against golden criteria."""
    from awareness_studio.llm_client import get_llm_client

    qid = entry["id"]
    question = entry["question"]
    mode = entry["mode"]
    min_sources = entry.get("min_sources", 1)
    must_include = entry.get("must_include", [])
    must_not_include = entry.get("must_not_include", [])

    failures: List[str] = []

    index = get_or_build_index()
    results = index.retrieve(question, k=k)
    retrieved = len([c for c, s in results if s > 0])
    chunks = [c for c, _ in results]

    # Call LLM
    client = get_llm_client()
    system, user = build_chat_prompt(question, mode, chunks)
    try:
        output = client.complete(system, user)
    except Exception as exc:
        return EvalResult(
            question_id=qid, mode=mode, question=question,
            passed=False, failures=[f"LLM error: {exc}"],
            retrieved_count=retrieved, llm_used=True,
        )

    output_lower = output.lower()

    # 1. must_include in LLM output
    for term in must_include:
        if term.lower() not in output_lower:
            failures.append(f"must_include '{term}' absent from LLM output")

    # 2. must_not_include absent from LLM output
    for term in must_not_include:
        if term.lower() in output_lower:
            failures.append(f"must_not_include '{term}' found in LLM output")

    # 3. min_sources: "Sources used" section and at least min_sources source entries
    source_entries = output.count("chunk `")
    if source_entries < min_sources:
        failures.append(
            f"min_sources not met in output: need {min_sources} chunk refs, found {source_entries}"
        )

    if verbose:
        status = "PASS" if not failures else "FAIL"
        print(f"  [{status}] {qid} ({mode}) — retrieved={retrieved} sources_in_output={source_entries}")
        for f in failures:
            print(f"    ✗ {f}")
        if not failures and verbose:
            preview = output[:200].replace("\n", " ")
            print(f"    ↳ {preview}…")

    return EvalResult(
        question_id=qid,
        mode=mode,
        question=question,
        passed=not failures,
        failures=failures,
        retrieved_count=retrieved,
        llm_used=True,
    )


# ── Runner ────────────────────────────────────────────────────────────────────

def run_eval(
    questions_path: Path = _DEFAULT_GOLDEN,
    no_llm: bool = True,
    k: int = 8,
    verbose: bool = True,
    ids: Optional[List[str]] = None,
) -> List[EvalResult]:
    with open(questions_path, encoding="utf-8") as fh:
        golden = json.load(fh)

    if ids:
        golden = [q for q in golden if q["id"] in ids]

    results: List[EvalResult] = []
    check_fn = _check_no_llm if no_llm else _check_with_llm

    for entry in golden:
        if verbose:
            llm_tag = "(no-llm)" if no_llm else "(llm)"
            print(f"\n[{entry['id']}] {llm_tag} {entry['question'][:70]}")
        result = check_fn(entry, k=k, verbose=verbose)
        results.append(result)

    return results


def _print_summary(results: List[EvalResult]) -> None:
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n{'─'*60}")
    print(f"Results: {passed}/{total} passed")
    if passed < total:
        print("\nFailing questions:")
        for r in results:
            if not r.passed:
                print(f"  {r.question_id} [{r.mode}]: {r.question[:60]}")
                for f in r.failures:
                    print(f"    ✗ {f}")
    else:
        print("All checks passed ✓")
    print(f"{'─'*60}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Awareness Studio golden eval harness"
    )
    parser.add_argument(
        "--no-llm", action="store_true", default=False,
        help="Validate retrieval coverage + prompt structure only (no API key needed)",
    )
    parser.add_argument(
        "--questions", default=str(_DEFAULT_GOLDEN),
        help="Path to golden_questions.json",
    )
    parser.add_argument(
        "--k", type=int, default=8,
        help="Number of chunks to retrieve per question",
    )
    parser.add_argument(
        "--ids", nargs="*",
        help="Run only specific question IDs (e.g. --ids q001 q003)",
    )
    parser.add_argument(
        "--verbose", action="store_true", default=True,
        help="Print per-question detail",
    )
    parser.add_argument(
        "--quiet", action="store_true", default=False,
        help="Suppress per-question detail (summary only)",
    )
    args = parser.parse_args()

    verbose = not args.quiet
    results = run_eval(
        questions_path=Path(args.questions),
        no_llm=args.no_llm,
        k=args.k,
        verbose=verbose,
        ids=args.ids,
    )
    _print_summary(results)

    all_passed = all(r.passed for r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
