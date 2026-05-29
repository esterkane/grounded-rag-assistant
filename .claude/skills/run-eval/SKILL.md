---
name: run-eval
description: >-
  Run and interpret the grounded-rag-assistant evaluation harness — retrieval
  metrics (Precision@k, Recall@k, MRR, nDCG@k) across bm25 / vector / hybrid /
  hybrid+rerank, citation accuracy, insufficient-evidence accuracy, latency
  p50/p95, and the hybrid-MRR regression threshold. Use whenever the user wants
  to evaluate retrieval or answer quality, check eval results, compare retrieval
  modes, or investigate a metrics regression.
argument-hint: "[optional focus, e.g. 'rerank' or a retrieval mode]"
context: fork
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(make eval *)
  - Bash(make eval)
  - Bash(pytest *)
  - Bash(python -m app.eval* *)
---

Run and interpret the evaluation harness. Focus: $ARGUMENTS

## Steps

1. Confirm the local stack is up and the corpus is ingested (the harness needs
   Elasticsearch populated). If `make eval` fails on connectivity, tell the user
   to run `make up` and `make ingest` first.
2. Run `make eval`. It evaluates the gold set in `data/gold/queries.jsonl`,
   prints a metrics table across retrieval modes, and writes a timestamped JSON
   report to `eval_reports/`.
3. Read the results. **Prefer the `eval_report_summary` MCP tool** if the
   `project-context` server is connected — it parses the latest report and
   returns a compact summary instead of loading the full JSON into context. Fall
   back to reading the newest file in `eval_reports/` directly.

## What to report

Present a comparison, not a raw dump:

- **Retrieval quality** — Precision@k, Recall@k, MRR, nDCG@k for `bm25`,
  `vector`, `hybrid`, and `hybrid+rerank`. Call out which mode wins and where
  rerank helps or hurts.
- **Citation accuracy** — for answerable gold queries, the share of citations
  pointing to gold-relevant chunks.
- **Insufficient-evidence accuracy** — for non-answerable gold items, whether the
  `insufficient` flag was correctly set.
- **Latency** — p50 / p95 for retrieval and for full `/ask`.
- **Regression status** — whether hybrid MRR is above the configured threshold.
  If it dropped, say so plainly and do not suggest lowering the threshold;
  recommend using `/rag-debug` on the regressed queries.

## Next actions

End with concrete suggestions: which retrieval mode to default to, whether to
enable `RERANK_ENABLED`, and any gold-set or corpus gaps the metrics expose.
