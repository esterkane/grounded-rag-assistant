# grounded-rag-assistant — developer task runner.
# Infra is pinned (see docs/INFRA.md). Never add `-v` to up/down: it would wipe
# the Elasticsearch and Postgres volumes. Use a separate, explicit reset target.

PYTHON ?= python
COMPOSE ?= docker compose

.DEFAULT_GOAL := help

.PHONY: help up down logs test lint ingest eval

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

up: ## Start Elasticsearch, Postgres, and the API
	$(COMPOSE) up -d --build

down: ## Stop the stack (keeps data volumes)
	$(COMPOSE) down

logs: ## Tail logs from all services
	$(COMPOSE) logs -f

test: ## Run the test suite
	$(PYTHON) -m pytest

lint: ## Lint with ruff
	ruff check .

ingest: ## Ingest the sample corpus into Elasticsearch (Phase 1)
	$(PYTHON) -m app.ingestion.run --path data/sample_corpus

eval: ## Run the evaluation harness (Phase 4)
	$(PYTHON) -m app.eval.run
