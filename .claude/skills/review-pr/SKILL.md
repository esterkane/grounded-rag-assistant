---
name: review-pr
description: >-
  Review the current branch or diff of grounded-rag-assistant for correctness,
  RAG-specific regressions, citation validity, security, test coverage, and
  architectural constraints. Use before opening, updating, or merging a PR, or
  when the user asks for a code review of recent changes.
argument-hint: "[base branch, default main]"
context: fork
agent: Explore
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(git status *)
  - Bash(git diff *)
  - Bash(gh pr *)
---

Review the current changes.

First inspect the diff:

```!
BASE="$ARGUMENTS"
[ -z "$BASE" ] && BASE="main"
git status --short
git diff --stat "$BASE"...HEAD 2>/dev/null || git diff --stat
git diff --name-only "$BASE"...HEAD 2>/dev/null || git diff --name-only
```

Review in focused passes — a single pass over many files dilutes attention and
produces contradictory findings:

1. **Per-file local correctness.** Logic, error handling, edge cases in each
   changed file on its own.
2. **Cross-file integration.** Data flow across ingestion → retrieval →
   generation → API; changed contracts on `/search`, `/ask`, admin endpoints.
3. **Test quality.** Are the changed behaviors covered? Does a bug fix include a
   regression test? Is the eval regression threshold still meaningful?
4. **Security & safety.** Secrets, chunk-`permissions` filtering, leaked internal
   errors, prompt-injection surface in retrieved content, destructive behavior.
5. **Performance.** Regressions with a concrete cause in the changed code.

RAG-specific checks to apply on every review:
- No FastAPI symbols imported in `app/retrieval/` or `app/generation/answerer.py`.
- Every citation in generated output maps to a `chunk_id` actually placed in the
  prompt context; the insufficient-evidence path is preserved.
- Ingestion stays idempotent — chunk IDs deterministic, upserts keyed by
  `chunk_id`.
- Retrieval results still carry method tags and full chunk metadata.

Report only **actionable** findings. For each:

- severity: blocker | important | minor
- location: `file:line` if available
- issue:
- why it matters:
- suggested fix:

Skip generic style preferences, speculative issues without a concrete code path,
and comments that do not change correctness, security, reliability, performance,
or maintainability.
