# Build phases

The six sequential build phases for `grounded-rag-assistant` are defined in the
**codex prompts file** (`project1-codex-prompts.md`).

**Action required:** copy the contents of `project1-codex-prompts.md` into this
file (`docs/BUILD_PHASES.md`), replacing this placeholder — but keep the
"Infrastructure overrides" section below at the top, above the pasted prompts.

## Infrastructure overrides (these supersede the build prompts)

The original build prompts were written against Elasticsearch 8.x with ~2 GB of
RAM. The current project uses:

- **Elasticsearch `9.4.1`** — image `docker.elastic.co/elasticsearch/elasticsearch:9.4.1`.
- **A 4 GB memory limit** on the Elasticsearch container, with a **2 GB JVM heap**.
- The Python `elasticsearch` client must be a **9.x** release to match.

Wherever a phase prompt says "Elasticsearch 8.x" or "~2 GB RAM", use the values
above instead. The exact `docker-compose.yml` service block is in `docs/INFRA.md`
and is enforced by `.claude/rules/infra.md`. Phase 0 must build against these.

## Corpus override (Phase 1)

The original Phase 1 prompt has you hand-place 3–6 sample docs in
`data/sample_corpus/`. Instead, the corpus is built from public Elastic GitHub
repositories via a fetch script. Phase 1 must additionally:

- Implement `app/ingestion/fetch_corpus.py`, wired to a `make corpus` target,
  that shallow-clones the source repos, selects topic-relevant `.md` files, and
  writes them into `data/sample_corpus/` with git-derived front-matter.
- Treat `data/sample_corpus/` as **gitignored** and reproducible — the repo
  contains the fetch script, not Elastic's content.

Full specification — source repos, topic filter, front-matter mapping, and
licensing notes — is in `docs/CORPUS.md`. The `make corpus` step runs before
`make ingest`.

---

Several parts of the Claude Code setup point here:

- The `/implement-phase` skill reads this file to get the phase spec, acceptance
  criteria, and the exact per-phase commit message.
- The `project-context` MCP server's `read_project_doc` tool can return this file
  on demand.
- `CLAUDE.md` references it as the build-discipline source of truth.

Phases at a glance:

0. Scaffold — repo structure, Docker Compose, `/health`.
1. Ingestion and indexing — loaders, chunking, embeddings, `rag_chunks` index.
2. Hybrid retrieval — BM25 + vector + RRF fusion, optional rerank.
3. Grounded generation with citations — provider abstraction, grounded answerer.
4. Evaluation harness — retrieval metrics, citation accuracy, regression test.
5. Review UI and feedback — Postgres logging, server-rendered review UI.
6. Observability, CI, deployment docs.
