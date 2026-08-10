SHELL := /bin/bash

.PHONY: setup dev backend-dev frontend-dev db-up db-down db-logs test lint typecheck format db-migrate db-revision data-refresh clean

setup:
	mise install
	pnpm install
	uv sync --all-packages --dev
	uv run pre-commit install

dev:
	@echo "Run in separate terminals: make db-up, make backend-dev, make frontend-dev"

backend-dev:
	uv run --package api uvicorn api.main:app --reload --host $${API_HOST:-127.0.0.1} --port $${API_PORT:-8000}

frontend-dev:
	pnpm --filter web dev

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

db-logs:
	docker compose logs -f postgres

test:
	uv run --package fpl-engine pytest -q packages/fpl_engine/tests
	uv run --package api pytest -q apps/api/tests
	pnpm --filter web test:run

lint:
	uv run ruff check apps/api/src apps/api/tests packages/fpl_engine/src packages/fpl_engine/tests
	pnpm --filter web lint

typecheck:
	uv run --package fpl-engine mypy packages/fpl_engine/src
	uv run --package api mypy apps/api/src
	pnpm --filter web typecheck

format:
	uv run ruff format apps/api/src apps/api/tests packages/fpl_engine/src packages/fpl_engine/tests
	pnpm --filter web format

db-migrate:
	uv run --package api alembic upgrade head

db-revision:
	uv run --package api alembic revision --autogenerate -m "$(m)"

data-refresh:
	@echo "Phase 1 placeholder: data refresh command will be added with ingestion adapter."

clean:
	rm -rf .venv
	rm -rf node_modules apps/web/node_modules
	rm -rf apps/web/.next apps/web/coverage
	docker volume rm fpl_tool_postgres_data || true
