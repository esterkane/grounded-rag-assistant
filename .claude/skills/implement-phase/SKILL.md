---
name: implement-phase
description: >-
  Implement one of the six sequential build phases of grounded-rag-assistant,
  defined in docs/BUILD_PHASES.md. Use whenever the user asks to build, start,
  continue, or implement a phase — Phase 0 (scaffold), Phase 1 (ingestion),
  Phase 2 (hybrid retrieval), Phase 3 (grounded generation), Phase 4 (evaluation
  harness), Phase 5 (review UI), or Phase 6 (observability/CI) — or refers to a
  phase number, its acceptance criteria, or the codex build prompts.
argument-hint: "[phase number or name, e.g. 'phase 2' or 'hybrid retrieval']"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Edit
  - Write
  - Bash(make *)
  - Bash(pytest *)
  - Bash(ruff *)
  - Bash(python -m app.* *)
  - Bash(docker compose up *)
  - Bash(docker compose logs *)
  - Bash(docker compose ps *)
  - Bash(git status *)
  - Bash(git diff *)
  - Bash(git add *)
  - Bash(git commit *)
---

Implement this build phase: $ARGUMENTS

This project is built in six phases, **in order, one at a time**. Over-scoping is
the main failure mode — stay strictly inside the requested phase.

## Workflow

1. **Read the phase spec.** Open `docs/BUILD_PHASES.md` and locate the requested
   phase. If the file is missing, ask the user where the build prompts live.
2. **Restate the acceptance criteria** for this phase in 3–6 bullets, plus the
   exact commit message the phase specifies. Confirm with the user if anything is
   ambiguous.
3. **Check prerequisites.** Verify the previous phase's deliverables exist (for
   example, do not start Phase 2 retrieval if `rag_chunks` is not populated). If a
   prerequisite is missing, stop and say so.
4. **Inspect before editing.** Look at existing implementation and nearby tests
   for the area you are about to touch.
5. **Implement within scope only.** Build exactly what the phase asks for and
   nothing more. Honor the path-scoped rules that load for the files you edit —
   especially `retrieval-generation.md` (no FastAPI coupling in `app/retrieval/`
   or `app/generation/answerer.py`).
6. **Respect the project constraints**: zero paid services; Python 3.11 + FastAPI;
   Elasticsearch for both BM25 and vector; provider-abstracted LLM (gemini +
   ollama); retrieval and generation as pure importable functions.
7. **Add or update focused tests** for the phase's behavior.
8. **Verify.** Run the narrowest relevant test first, then `make test` and
   `make lint`. Then walk each acceptance criterion explicitly and show it is met
   — run the actual command (`make up`, `GET /health`, `make ingest` twice,
   `make eval`, etc.) the criterion describes.
9. **Summarize**: files changed, behavior added, tests run, acceptance criteria
   status, unresolved risks.
10. **Commit** with the exact commit message from the phase spec (for example,
    `git commit -m "phase 2: hybrid retrieval with RRF and optional rerank"`).

## Stop and ask before

- Destructive commands, including `docker compose down -v`.
- Schema migrations beyond what the phase requires.
- Broad rewrites or refactors outside the phase scope.
- Dependency upgrades not listed in the phase spec.
- Editing secrets, `.env`, lockfiles, or generated files.
- Starting the next phase — finish and commit the current one first.
