---
name: explore-codebase
description: >-
  Map code paths, dependencies, tests, configuration, and risks before
  implementation in the grounded-rag-assistant repo. Use this for unfamiliar
  code, architecture questions, broad or multi-file refactors, migration
  planning, or any "where is X handled?" / "how does Y work?" question — before
  editing anything.
argument-hint: "[question, feature, bug, or area to investigate]"
context: fork
agent: Explore
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(git grep *)
  - Bash(git log *)
  - Bash(find *)
---

Research: $ARGUMENTS

Rules:
1. Do not edit any files. This is a read-only investigation.
2. Start with `Glob` and `Grep`. Do not read large unrelated files.
3. Identify entry points, callers, tests, configuration, and risky dependencies.
4. Trace data flow through the RAG pipeline where relevant: ingestion → ES index
   → retrieval (bm25 / vector / hybrid RRF / rerank) → generation (provider →
   answerer → citations) → API.
5. Note any code that crosses the FastAPI-free boundary (FastAPI symbols inside
   `app/retrieval/` or `app/generation/`), since that is a known risk in this repo.
6. Prefer concrete file paths and exact symbol names over general guesses.
7. Return only this structure:

## Short answer

<one paragraph>

## Relevant files

- `<path>` — <why it matters>

## Execution flow

1. <step>
2. <step>
3. <step>

## Suggested implementation plan

1. <step>
2. <step>
3. <step>

## Risks and open questions

- <risk or open question>
