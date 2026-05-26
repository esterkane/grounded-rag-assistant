.PHONY: up down logs test lint ingest eval

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose run --rm api pytest

lint:
	docker compose run --rm api ruff check .

ingest:
	docker compose run --rm api python -m app.ingestion

eval:
	docker compose run --rm api python -m app.eval
