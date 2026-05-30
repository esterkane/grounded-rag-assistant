"""CLI entry point for the evaluation harness (`make eval`).

Runs retrieval metrics across all modes and (when an LLM provider is available)
answer-quality metrics, prints a human-readable table, and writes a timestamped
JSON report + summary to the configured report directory.
"""

import argparse
from datetime import UTC, datetime

from elasticsearch import Elasticsearch

from app.config import get_settings
from app.eval.gold import load_gold
from app.eval.harness import run_evaluation
from app.eval.report import render_summary, write_report
from app.ingestion.embedder import SentenceTransformersEmbedder


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RAG evaluation harness.")
    parser.add_argument(
        "--no-answers",
        action="store_true",
        help="Skip the LLM answer-quality eval (retrieval metrics only).",
    )
    args = parser.parse_args()

    settings = get_settings()

    from app.observability import configure_logging

    configure_logging(settings)
    gold = load_gold(settings.eval_gold_path)
    client = Elasticsearch(settings.elasticsearch_url, request_timeout=60)
    embedder = SentenceTransformersEmbedder(settings.embedding_model)

    report = run_evaluation(
        gold,
        client=client,
        embedder=embedder,
        settings=settings,
        with_answers=not args.no_answers,
    )

    print(render_summary(report))

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path, summary_path = write_report(report, settings.eval_report_dir, timestamp)
    print(f"\nReport written to:\n  {json_path}\n  {summary_path}")


if __name__ == "__main__":
    main()
