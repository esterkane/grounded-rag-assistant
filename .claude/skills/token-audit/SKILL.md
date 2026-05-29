---
name: token-audit
description: >-
  Inspect the grounded-rag-assistant Claude Code configuration for token bloat
  and recommend what to shorten, move into path-scoped rules, move into skills,
  expose through MCP resources, or delete. Use when Claude Code starts getting
  slower, repetitive, or less precise over a long build session.
argument-hint: "[optional area to focus on]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(find .claude -maxdepth 4 -type f *)
  - Bash(wc -l *)
---

Audit the Claude Code setup for token efficiency. Focus: $ARGUMENTS

Inspect:
- `CLAUDE.md` and `CLAUDE.local.md`
- `.claude/rules/**/*.md`
- `.claude/skills/**/SKILL.md`
- `.claude/agents/**/*.md`
- `.mcp.json`

Return:

## Always-loaded content to shorten

- `<file>` — <specific change>

## Procedures that should become skills

- <procedure> — <proposed skill name>

## Rules that should become path-scoped

- <rule currently global> — <recommended `paths` globs>

## MCP / context improvements

- <server / tool / resource> — <recommendation>

## Exact edits recommended

1. <edit>
2. <edit>
3. <edit>

Reminders to apply: keep `CLAUDE.md` to stable facts and standards only; prefer
path-scoped rules over a long global file; prefer skills over always-loaded
procedures; use `context: fork` on verbose skills; disable unused MCP servers
with `/mcp`; and use `/clear` between unrelated tasks and `/compact` before the
context gets messy.
