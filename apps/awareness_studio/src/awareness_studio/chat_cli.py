"""CLI: python -m awareness_studio.chat_cli --mode TEACH --question "What is consciousness?"

Optional flags:
  --stream      Stream tokens to stdout as they arrive (Anthropic/OpenAI)
  --build-index Force rebuild index before answering
  --k N         Number of chunks to retrieve (default 8)
  --tools       Enable external tool lookup (overrides TOOLS_ENABLED env)
"""
import argparse
import sys
from typing import List

from awareness_studio.answer_modes import build_chat_prompt
from awareness_studio.index_build import build_index, get_or_build_index

_VALID_MODES = ["TEACH", "EXPLAIN", "ELABORATE", "MATRIX", "CARD", "CANONICAL"]


def run_chat(
    question: str,
    mode: str,
    k: int = 8,
    stream: bool = False,
    use_tools: bool = False,
) -> str:
    """Retrieve context chunks, optionally call external tools, compose prompt, call LLM."""
    index = get_or_build_index()
    results = index.retrieve(question, k=k)
    chunks = [c for c, _ in results]

    from awareness_studio.llm_client import get_llm_client
    from awareness_studio.tool_router import (
        format_tool_results,
        get_tool_router,
        has_tool_trigger,
    )

    tool_suffix = ""
    tool_records = []
    if use_tools and has_tool_trigger(question):
        router = get_tool_router()
        router.reset_request()
        for spec in router.list_tools():
            if spec.provider in ("pubmed", "biorxiv"):
                res = router.call_tool(spec.name, {"query": question, "max_results": 3})
                tool_records.append(res)
                if router._calls_this_request >= router._max_calls:
                    break
        tool_suffix = format_tool_results(tool_records)

    client = get_llm_client()
    system, user = build_chat_prompt(question, mode, chunks)
    if tool_suffix:
        user = user + tool_suffix

    if stream:
        parts = []
        for token in client.complete_stream(system, user):
            print(token, end="", flush=True)
            parts.append(token)
        print()  # final newline
        return "".join(parts)

    return client.complete(system, user)


def main() -> None:
    parser = argparse.ArgumentParser(description="Awareness Studio — Guidance Chatbot")
    parser.add_argument("--mode", choices=_VALID_MODES, default="EXPLAIN")
    parser.add_argument("--question", required=True)
    parser.add_argument("--k", type=int, default=8, help="Chunks to retrieve")
    parser.add_argument(
        "--stream", action="store_true",
        help="Stream output tokens to stdout (requires Anthropic or OpenAI provider)",
    )
    parser.add_argument("--build-index", action="store_true", help="Force rebuild index first")
    parser.add_argument(
        "--tools", action="store_true",
        help="Enable external tool lookup (pubmed/biorxiv) for this query",
    )
    args = parser.parse_args()

    if args.build_index:
        build_index()
        print("[index rebuilt]", file=sys.stderr)

    if args.stream:
        run_chat(args.question, args.mode, args.k, stream=True, use_tools=args.tools)
    else:
        result = run_chat(args.question, args.mode, args.k, use_tools=args.tools)
        print(result)


if __name__ == "__main__":
    main()
