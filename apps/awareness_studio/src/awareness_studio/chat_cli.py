"""CLI: python -m awareness_studio.chat_cli --mode TEACH --question "What is consciousness?"

Optional flags:
  --stream      Stream tokens to stdout as they arrive (Anthropic/OpenAI)
  --build-index Force rebuild index before answering
  --k N         Number of chunks to retrieve (default 8)
"""
import argparse
import sys

from awareness_studio.answer_modes import build_chat_prompt
from awareness_studio.index_build import build_index, get_or_build_index

_VALID_MODES = ["TEACH", "EXPLAIN", "ELABORATE", "MATRIX", "CARD", "CANONICAL"]


def run_chat(question: str, mode: str, k: int = 8, stream: bool = False) -> str:
    """Retrieve context chunks, compose prompt, call LLM. Returns full text."""
    index = get_or_build_index()
    results = index.retrieve(question, k=k)
    chunks = [c for c, _ in results]

    from awareness_studio.llm_client import get_llm_client
    client = get_llm_client()
    system, user = build_chat_prompt(question, mode, chunks)

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
    args = parser.parse_args()

    if args.build_index:
        build_index()
        print("[index rebuilt]", file=sys.stderr)

    if args.stream:
        run_chat(args.question, args.mode, args.k, stream=True)
    else:
        result = run_chat(args.question, args.mode, args.k)
        print(result)


if __name__ == "__main__":
    main()
