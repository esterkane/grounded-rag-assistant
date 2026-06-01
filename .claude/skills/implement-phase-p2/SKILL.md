---
name: implement-phase-p2
description: >-
  Implement one of the four sequential Project 2 build phases of
  grounded-rag-assistant — the LangGraph + MCP agentic layer — defined in
  docs/PROJECT_2.md. Use whenever the user asks to build, start, continue, or
  implement a Project 2 phase: Phase 0 (scaffold), Phase 1 (MCP tools wrapping
  retriever and answerer), Phase 2 (LangGraph agent), Phase 3 (persistent
  checkpointing and observability), or Phase 4 (HTTP endpoint, CI, docs). Also
  use when the user mentions "p2", "project 2", "the agent layer", or "the MCP
  wrapper".
argument-hint: "[phase number, e.g. 'p2 phase 1' or 'agent phase']"
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
  - Bash(git checkout -b *)
  - Bash(git push -u origin *)
  - Bash(gh pr *)
---

Implement this Project 2 build phase: $ARGUMENTS

Project 2 builds on Project 1 by adding an agentic layer — MCP tools wrapping
the existing retriever and answerer, plus a LangGraph workflow that orchestrates
them. The four Project 2 phases are defined in `docs/PROJECT_2.md`. Over-scoping
is the main failure mode — stay strictly inside the requested phase.

## Workflow

1. **Read the phase spec.** Open `docs/PROJECT_2.md` and locate the requested
   phase. If the file is missing, ask the user where the Project 2 prompts live.
2. **Restate the acceptance criteria** for this phase in 3–6 bullets, plus the
   exact commit message and the feature branch name the phase specifies.
   Confirm with the user if anything is ambiguous.
3. **Check prerequisites.**
   - Project 1 is done (Phases 0–6 merged on main).
   - The previous Project 2 phase is merged on main. Do not start Phase 2 if
     Phase 1's PR is still open.
   - Required external services for the phase work: ES + Postgres healthy.
4. **Branch.** Create the feature branch named in the phase spec
   (`feat/p2-phase-N-<slug>`). Project 2 uses a feature-branch + PR workflow —
   do **not** commit directly to main.
5. **Inspect before editing.** For Project 2 work especially: read the
   functions in `app/retrieval/` and `app/generation/` you're about to import.
   Do not reimplement them — wrap them.
6. **Implement within scope only.** Build exactly what the phase asks for.
   Honor `.claude/rules/agent-mcp.md` (which load auto when you edit
   `app/agent/**` or `app/mcp/**`) and the FastAPI-free rule (still applies
   to `app/retrieval/` and `app/generation/answerer.py` — Project 2 must not
   regress that boundary).
7. **Honor the project constraints**: zero paid services; Gemini→Ollama
   fallback already exists; reuse the provider abstraction.
8. **Add or update focused tests** for the phase's behavior — including the
   insufficient-evidence path, which is the most important contract not to
   regress.
9. **Verify.** Run the narrowest relevant test first, then `make test` and
   `make lint`. Walk each acceptance criterion explicitly and show it is met.
10. **Commit and push the branch.** Use the exact commit message from the
    phase spec. Push to origin and report the PR URL. **Do not merge.**
    Let CI run; the user will merge from the GitHub UI once CI is green.

## Stop and ask before

- Modifying any file under `app/retrieval/` or `app/generation/answerer.py`
  beyond imports — those modules must remain FastAPI-free and stable across
  Project 2.
- Committing directly to main.
- Merging a Project 2 PR.
- Starting the next phase before the current PR is merged.
- Adding paid services, paid LLM keys, or vendor-locked dependencies.
