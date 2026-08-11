SHELL := /bin/bash

.PHONY: setup dev backend-dev frontend-dev db-up db-down db-logs test lint typecheck format db-migrate db-revision data-refresh projections-refresh clean

setup:
	mise install
	pnpm install
	uv sync --all-packages --dev
	uv run pre-commit install

dev:
	@echo "Run in separate terminals: make db-up, make backend-dev, make frontend-dev"

backend-dev:
	cd apps/api && PYTHONPATH=src:../../packages/fpl_engine/src uv run --package api uvicorn api.main:app --reload --host $${API_HOST:-127.0.0.1} --port $${API_PORT:-8000}

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
	PYTHONPATH=packages/fpl_engine/src uv run --package api pytest -q apps/api/tests
	pnpm --filter web test:run

lint:
	uv run ruff check apps/api/src apps/api/tests packages/fpl_engine/src packages/fpl_engine/tests
	pnpm --filter web lint

typecheck:
	uv run --package fpl-engine mypy --config-file packages/fpl_engine/pyproject.toml packages/fpl_engine/src
	MYPYPATH=packages/fpl_engine/src uv run --package api mypy --config-file apps/api/pyproject.toml apps/api/src
	pnpm --filter web typecheck

format:
	uv run ruff format apps/api/src apps/api/tests packages/fpl_engine/src packages/fpl_engine/tests
	pnpm --filter web format

db-migrate:
	cd apps/api && uv run --package api alembic upgrade head

db-revision:
	cd apps/api && uv run --package api alembic revision --autogenerate -m "$(m)"

data-refresh:
	cd apps/api && PYTHONPATH=src:../../packages/fpl_engine/src uv run --package api python -m api.scripts.import_fpl_data

projections-refresh:
	cd apps/api && PYTHONPATH=src:../../packages/fpl_engine/src uv run --package api python -m api.scripts.generate_projections

clean:
	rm -rf .venv
	rm -rf node_modules apps/web/node_modules
	rm -rf apps/web/.next apps/web/coverage
	docker volume rm fpl_tool_postgres_data || true
