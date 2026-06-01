.PHONY: up down logs test lint migrate corpus ingest eval demo mcp-server agent

up:
	docker compose up -d --build

down:
	docker compose down

migrate:
	docker compose run --rm api python -m app.db.migrate

logs:
	docker compose logs -f

test:
	docker compose run --rm api pytest

lint:
	docker compose run --rm api ruff check .

# Fetch the corpus from public Elastic GitHub repos (see docs/CORPUS.md).
# Runs on the host (needs git + network) and writes the bind-mounted data/ dir.
# Run this before `make ingest`. Pure standard library, so no app deps required.
corpus:
	python3 -m app.ingestion.fetch_corpus

ingest:
	docker compose run --rm api python -m app.ingestion.run --path data/sample_corpus

eval:
	docker compose run --rm api python -m app.eval

demo:
	docker compose up -d --build
	python3 -m app.ingestion.fetch_corpus
	docker compose run --rm api python -m app.ingestion.run --path data/sample_corpus
	docker compose run --rm -e API_URL=http://api:8000 api python -m app.demo

# Project 2 — LangGraph + MCP agent layer (scaffold in Phase 0).
# Starts the FastMCP server on stdio so an MCP client can connect. No tools yet.
# --no-deps: the placeholder server needs neither ES nor Postgres.
# -i: keep stdin open for the stdio transport. Exits cleanly on Ctrl-C / EOF.
mcp-server:
	docker compose run --rm --no-deps -i api python -m app.mcp.server

# Placeholder until Phase 2 wires `python -m app.agent.run`.
agent:
	@echo "agent: not implemented yet"
