"""Render and persist evaluation reports."""

import json
from dataclasses import asdict
from pathlib import Path

from app.eval.harness import EvalReport, ModeMetrics

_MODE_LABELS = {
    "bm25": "BM25",
    "vector": "Vector",
    "hybrid": "Hybrid (RRF)",
    "hybrid_rerank": "Hybrid + Rerank",
}


def _row(m: ModeMetrics) -> str:
    label = _MODE_LABELS.get(m.mode, m.mode)
    return (
        f"{label:<16} {m.precision_at_k:>8.3f} {m.recall_at_k:>8.3f} "
        f"{m.mrr:>8.3f} {m.ndcg_at_k:>8.3f} {m.latency_p50_ms:>9.1f} {m.latency_p95_ms:>9.1f}"
    )


def render_summary(report: EvalReport) -> str:
    k = report.k
    lines = [
        "=" * 78,
        "GROUNDED-RAG-ASSISTANT — EVALUATION REPORT",
        "=" * 78,
        f"Gold set: {report.gold_size} queries "
        f"({report.answerable} answerable, {report.non_answerable} non-answerable)  |  k={k}",
        "",
        f"Retrieval metrics (averaged over {next(iter(report.retrieval.values())).queries} "
        "answerable queries):",
        "",
        f"{'Mode':<16} {'P@'+str(k):>8} {'R@'+str(k):>8} {'MRR':>8} "
        f"{'nDCG@'+str(k):>8} {'p50 ms':>9} {'p95 ms':>9}",
        "-" * 78,
    ]
    for mode in ("bm25", "vector", "hybrid", "hybrid_rerank"):
        if mode in report.retrieval:
            lines.append(_row(report.retrieval[mode]))
    lines.append("-" * 78)

    hybrid = report.retrieval.get("hybrid")
    if hybrid is not None:
        status = "PASS" if hybrid.mrr >= report.hybrid_mrr_threshold else "FAIL"
        lines.append(
            f"Hybrid MRR {hybrid.mrr:.3f}  vs threshold "
            f"{report.hybrid_mrr_threshold:.3f}  -> {status}"
        )

    lines.append("")
    a = report.answers
    if a.skipped_reason:
        lines.append(f"Answer-quality eval: SKIPPED ({a.skipped_reason})")
    else:
        lines.append(f"Answer-quality eval (provider={report.provider}):")
        lines.append(
            f"  Citation precision:        {a.citation_precision:.3f} "
            f"({a.answerable_evaluated} answerable queries)"
        )
        lines.append(
            f"  Insufficient-evidence acc: {a.insufficient_accuracy:.3f} "
            f"({a.nonanswerable_evaluated} non-answerable queries)"
        )
        lines.append(
            f"  /ask latency:              p50 {a.ask_latency_p50_ms:.1f} ms  "
            f"p95 {a.ask_latency_p95_ms:.1f} ms"
        )
    lines.append("=" * 78)
    return "\n".join(lines)


def report_to_dict(report: EvalReport) -> dict:
    data = asdict(report)
    # asdict turns the ModeMetrics values into dicts already.
    return data


def write_report(report: EvalReport, report_dir: str | Path, timestamp: str) -> tuple[Path, Path]:
    """Write a JSON report and a human-readable summary; return both paths."""
    directory = Path(report_dir)
    directory.mkdir(parents=True, exist_ok=True)

    json_path = directory / f"eval-{timestamp}.json"
    summary_path = directory / f"eval-{timestamp}.txt"

    payload = report_to_dict(report)
    payload["timestamp"] = timestamp
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    summary_path.write_text(render_summary(report), encoding="utf-8")
    return json_path, summary_path
