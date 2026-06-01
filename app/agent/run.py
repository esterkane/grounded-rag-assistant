"""CLI entry point for the agent (Project 2 Phase 2).

    python -m app.agent.run "your question"

Streams node-level events to stdout for debugging, then prints the final
grounded answer with its citations.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from app.agent.runner import stream_agent
from app.config import get_settings


def _summarize_update(node: str, value: Any) -> str:
    if not isinstance(value, dict):
        return f"[{node}]"
    if node == "plan":
        return f"[plan] sub_queries={value.get('sub_queries')}"
    if node == "retrieve":
        return f"[retrieve] accumulated_chunks={len(value.get('retrieved', []))}"
    if node == "reflect":
        return f"[reflect] action={value.get('next_action')}"
    if node in ("answer", "insufficient"):
        fa = value.get("final_answer") or {}
        return f"[{node}] answered={fa.get('answered')} insufficient={fa.get('insufficient')}"
    return f"[{node}]"


def _print_final(answer: dict[str, Any]) -> None:
    print("\n" + "=" * 60)
    if answer.get("insufficient"):
        print("INSUFFICIENT EVIDENCE")
    print(answer.get("answer", ""))
    claims = answer.get("claims") or []
    if claims:
        print("\nClaims & citations:")
        for c in claims:
            print(f"  - {c.get('text')}  {c.get('citations')}")
    sources = answer.get("sources") or []
    if sources:
        print("\nSources:")
        for s in sources:
            print(f"  - {s.get('chunk_id')}  {s.get('title')}  {s.get('source_url')}")


async def _run(args: argparse.Namespace) -> None:
    final: dict[str, Any] | None = None
    async for update in stream_agent(
        args.query,
        k=args.k,
        rerank=args.rerank,
        caller_roles=args.roles,
        max_hops=args.max_hops,
    ):
        for node, value in update.items():
            print(_summarize_update(node, value))
            if isinstance(value, dict) and value.get("final_answer"):
                final = value["final_answer"]
    if final is not None:
        _print_final(final)
    else:
        print("\n(no final answer produced)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the grounded-rag LangGraph agent.")
    parser.add_argument("query", help="The question to answer.")
    parser.add_argument("--k", type=int, default=8, help="Chunks to retrieve per hop.")
    parser.add_argument("--max-hops", type=int, default=2, dest="max_hops")
    parser.add_argument("--rerank", action="store_true", help="Cross-encoder rerank.")
    parser.add_argument(
        "--roles",
        nargs="*",
        default=["public"],
        help="Caller roles for permission filtering.",
    )
    args = parser.parse_args()

    from app.observability import configure_logging

    configure_logging(get_settings())
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
