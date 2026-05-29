# Claude Code setup for `grounded-rag-assistant`

This folder is a complete Claude Code configuration for building the
`grounded-rag-assistant` project. It applies the architecture guide (your
PDF-derived setup) to the specifics of the six-phase RAG build plan in the codex
prompts.

## What's in here

```
CLAUDE.md                         Always-loaded project facts, stack, commands, rules
.mcp.json                         Registers the project-context MCP server
.claude/
  settings.json                   Permissions (allow/deny) + a ruff post-edit hook
  rules/
    retrieval-generation.md       Path-scoped: the FastAPI-free constraint (critical)
    api.md                        Path-scoped: FastAPI boundary conventions
    ingestion.md                  Path-scoped: chunk IDs, idempotency, metadata
    db.md                         Path-scoped: Postgres / migration rules
    tests.md                      Path-scoped: pytest conventions
    infra.md                      Path-scoped: pinned ES 9.4.1 + 4 GB container config
  skills/
    explore-codebase/             Read-only investigation before editing
    implement-phase/              Implement one of the six build phases
    review-pr/                    Focused multi-pass review with RAG checks
    run-eval/                     Run + interpret the evaluation harness
    rag-debug/                    Diagnose a wrong / ungrounded answer
    token-audit/                  Find context bloat in this config
  agents/
    code-reviewer.md              Independent read-only reviewer subagent
    test-writer.md                Regression-test writer subagent
mcp/project-context/              A small dev-time MCP server (TypeScript)
docs/
  BUILD_PHASES.md                 Placeholder — replace with the codex prompts file
  INFRA.md                        Canonical docker-compose / Elasticsearch spec
  CORPUS.md                       Corpus sources (Elastic GitHub repos) + fetch spec
```

## How to install it

1. **Copy the contents into your repo root.** Everything here is meant to live at
   the top level of the `grounded-rag-assistant` repository — `CLAUDE.md` and
   `.mcp.json` at the root, the `.claude/` directory, and the `mcp/` directory.
   `.claude/` is a hidden folder; make sure your copy includes it.

2. **Provide the build phases.** Copy your `project1-codex-prompts.md` into
   `docs/BUILD_PHASES.md`, replacing the placeholder. The `/implement-phase` skill
   and the MCP server both read that file.

3. **Build the MCP server.** It ships as TypeScript source and must be compiled
   once (and again after edits):

   ```bash
   cd mcp/project-context
   npm install
   npm run build
   cd ../..
   ```

   This produces `mcp/project-context/build/index.js`, which `.mcp.json` points
   at. `node_modules/` and `build/` are gitignored; commit the `src/`,
   `package.json`, and `tsconfig.json` so teammates can rebuild.

4. **Start Claude Code and verify.** Run `claude` in the repo, then `/mcp` to
   confirm the `project-context` server connected, and `/memory` to confirm
   `CLAUDE.md` loaded.

## How it works, layer by layer

- **`CLAUDE.md`** is always in context. It holds stable facts only: the stack,
  the Make commands, the build discipline, and the one constraint that matters
  most — retrieval and generation must stay free of FastAPI so a later project
  can wrap them as MCP tools.

- **`.claude/rules/*.md`** load *only* when you edit a matching file (the `paths`
  globs in each rule's frontmatter). Editing something in `app/retrieval/` pulls
  in the FastAPI-free rule; editing a test pulls in the test rule. This keeps
  irrelevant instructions out of context and saves tokens.

- **`.claude/skills/*`** are on-demand workflows, invokable as `/explore-codebase`,
  `/implement-phase`, `/review-pr`, `/run-eval`, `/rag-debug`, `/token-audit`.
  The verbose ones use `context: fork` so their exploration output does not
  pollute the main conversation.

- **`.claude/agents/*`** are specialized subagents for isolated review and
  test-writing — use `code-reviewer` for an independent check that does not share
  the generating session's assumptions.

- **`.claude/settings.json`** is the real safety boundary: it allows the routine
  commands (`make`, `pytest`, `ruff`, safe `git` and `docker compose`) and denies
  the dangerous ones (reading `.env`/`secrets`, `rm -rf`, `git push`,
  `docker compose down -v`). A skill's `allowed-tools` only pre-approves tools for
  smoother prompts; it is **not** a hard restriction — the permissions here are.

- **`mcp/project-context/`** is a dev-time MCP server with four tools:
  `project_snapshot` (compact file tree), `read_project_doc` (bounded doc reads,
  including `BUILD_PHASES.md`), `summarize_ci_failure` (trims long test/CI logs to
  the actionable lines), and `eval_report_summary` (parses the latest
  `eval_reports/*.json` and returns just the metric highlights instead of the
  whole file). The last one is the most useful here — eval reports are large, and
  filtering them in code keeps the conversation small.

## Suggested operating loop per phase

1. `/explore-codebase "<area>"` — understand before editing.
2. Use **plan mode** for anything broad; direct execution for small fixes.
3. `/implement-phase "phase N"` — implement within scope, verify acceptance
   criteria, commit with the exact message.
4. `/run-eval` — once the eval harness exists (Phase 4+), check metrics.
5. `/review-pr main` — independent review before merge.
6. `/compact` between sub-tasks; `/clear` when switching phases.

## Notes and caveats

- **Verify frontmatter against your Claude Code version.** Skill and agent
  frontmatter fields (`context: fork`, `agent: Explore`, `allowed-tools`,
  `argument-hint`, `permissionMode`, `maxTurns`) follow the current docs your
  architecture guide cites, but Claude Code evolves quickly — if a skill does not
  load, check the field names against `claude` docs for your installed version.
- **The post-edit hook** in `settings.json` runs `ruff` on changed `.py` files
  using `$CLAUDE_FILE_PATH`. If your Claude Code version exposes a different
  variable name for the edited path, adjust the hook command; it is written to
  fail silently (`true` at the end) so a wrong variable never blocks an edit.
- **The project's own MCP layer is out of scope here.** The codex prompts defer
  the LangGraph + MCP layer that exposes the retriever and answerer as MCP tools
  to "Project 2." This setup is the *development* tooling for building Project 1;
  the FastAPI-free rule is what makes that later wrapping painless. Ask for the
  Project 2 prompts when Phase 6 is done.
