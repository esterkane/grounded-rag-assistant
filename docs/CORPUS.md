# Corpus reference — `grounded-rag-assistant`

This file specifies where the document corpus comes from and how it is built.
It supersedes the "hand-place 3–6 sample docs" instruction in the original
Phase 1 build prompt. Phase 1 must implement the fetch step described here.

## Corpus sources (GitHub repositories)

The corpus is built from public Elastic GitHub repositories — **not** by scraping
the rendered documentation website. Cloning repos gives clean Markdown source,
explicit per-repo licenses, and git metadata for provenance.

| Repo | Use | License |
|---|---|---|
| `elastic/elasticsearch-labs` | **Primary source.** Notebooks and example apps for search & AI — RAG, hybrid search, RRF, vector search, ELSER. README and `.md` files are directly on-topic. | Apache License 2.0 (permissive) |
| `elastic/docs-content` | **Secondary source.** Current home of Elasticsearch product documentation source in Markdown (since Elastic Stack 9.0). Reference and how-to docs. | Verify the repo's `LICENSE` file before redistributing — documentation content licensing differs from code licensing. |

Topic filter: ingest only files relevant to **search, vector search, hybrid
search, RRF, embeddings, semantic search, and RAG/AI-search**. Do not ingest the
entire repos (build tooling, unrelated guides, CI config, images).

## Build approach: a fetch script, not a committed mirror

`data/sample_corpus/` is **gitignored** and reproducible. The repo contains a
fetch script, not Elastic's content. This keeps redistribution out of scope and
makes the corpus reproducible.

The fetch script (`app/ingestion/fetch_corpus.py`, run via `make corpus`):

1. Shallow-clones (`--depth 1`) each source repo into a temporary directory, or
   updates an existing clone.
2. Walks each repo for `.md` files matching the topic filter above.
3. Copies selected files into `data/sample_corpus/`, namespaced by repo (for
   example `data/sample_corpus/elasticsearch-labs/...`).
4. Writes or normalizes front-matter on each file (see mapping below).
5. Prints a summary: repos fetched, files selected, files skipped.

Keep the selection deliberately small — aim for roughly 15–40 documents, enough
for meaningful retrieval and a gold set, not a full mirror.

## Front-matter mapping

Every file placed in `data/sample_corpus/` must carry the front-matter Phase 1
expects, derived from git:

| Front-matter field | Source |
|---|---|
| `title` | First H1 in the file, or the filename if no H1 |
| `source_url` | The GitHub blob URL: `https://github.com/<org>/<repo>/blob/<ref>/<path>` |
| `version` | The git tag or branch ref the file was fetched from |
| `last_updated` | Date of the file's last commit (`git log -1 --format=%cs -- <file>`) |

`source_url` doubles as attribution — keep it accurate so generated answers cite
back to the real Elastic source.

## Licensing notes (not legal advice)

- `elastic/elasticsearch-labs` is Apache 2.0 — permissive; fine to use, and even
  to redistribute with attribution and the license text.
- For `elastic/docs-content`, check the `LICENSE` file in the repo before
  committing or publishing any of its content. For a **local, non-published**
  RAG corpus the practical risk is low, but the fetch-script approach above
  avoids the question entirely by not committing the content.
- Preserve each source repo's `LICENSE` and attribution. The `source_url`
  front-matter provides per-document attribution.

## If a repo is unreachable

If the fetch script cannot reach GitHub (offline, network policy), it must fail
with a clear message and not leave a half-populated corpus. As a fallback for a
fully offline run, a few hand-written sample Markdown docs with valid
front-matter may be placed directly in `data/sample_corpus/`, exactly as the
original Phase 1 prompt described.
