---
paths:
  - "**/*_test.py"
  - "**/test_*.py"
  - "tests/**/*"
---

# Test rules

- Use `pytest` and the existing fixtures and helpers. Inspect nearby tests before
  adding new ones.
- For a bug fix, add at least one regression test that **fails before the fix**
  and passes after it.
- Prefer focused assertions over broad snapshot-only tests.
- Do not duplicate scenarios already covered by existing tests.
- Keep test data minimal and readable.
- Tests that need Elasticsearch or PostgreSQL are integration tests and require
  the local stack (`make up`); keep pure-logic tests (such as RRF fusion) free of
  live services so they run fast.
- The evaluation regression test (Phase 4) fails when hybrid MRR drops below a
  configurable threshold. Keep that threshold meaningful: it must pass on the
  current baseline and would fail on a deliberate degradation. Do not weaken the
  threshold to make a failing run pass — investigate the regression instead.
- For grounded-generation tests: an answerable query must return valid citations
  that map to real retrieved chunks; an off-corpus query must take the
  insufficient-evidence path rather than hallucinating.
