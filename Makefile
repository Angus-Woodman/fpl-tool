SHELL := /bin/bash

.PHONY: setup dev backend-dev frontend-dev db-up db-down db-logs db-test-up test test-integration lint typecheck format db-migrate db-revision data-refresh results-refresh projections-refresh dual-write-refresh predeadline-snapshot clean

TEST_DATABASE_URL ?= postgresql+psycopg://fpl:fpl@localhost:5432/fpl_test

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

db-test-up: db-up
	@docker compose exec -T postgres sh -c 'until pg_isready -U fpl -d fpl -q; do sleep 1; done'
	@docker compose exec -T postgres psql -U fpl -d fpl -tAc "SELECT 1 FROM pg_database WHERE datname='fpl_test'" | grep -q 1 \
		|| docker compose exec -T postgres createdb -U fpl -O fpl fpl_test
	cd apps/api && DATABASE_URL="$(TEST_DATABASE_URL)" uv run --package api alembic upgrade head

test:
	uv run --package fpl-engine pytest -q packages/fpl_engine/tests
	PYTHONPATH=packages/fpl_engine/src uv run --package api pytest -q apps/api/tests
	pnpm --filter web test:run

test-integration: db-test-up
	RUN_DB_TESTS=1 TEST_DATABASE_URL="$(TEST_DATABASE_URL)" PYTHONPATH=packages/fpl_engine/src \
		uv run --package api pytest -q apps/api/tests

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

results-refresh:
	cd apps/api && PYTHONPATH=src:../../packages/fpl_engine/src uv run --package api python -m api.scripts.import_player_stats

projections-refresh:
	cd apps/api && PYTHONPATH=src:../../packages/fpl_engine/src uv run --package api python -m api.scripts.generate_projections

dual-write-refresh:
	cd apps/api && PYTHONPATH=src:../../packages/fpl_engine/src uv run --package api python -m api.scripts.dual_write_projections

# Operational pre-deadline record: import current FPL data (captures one
# complete player-snapshot generation in the same pass), then generate and
# validate provenance-backed projections for every operational model from
# that shared generation. Deliberately excludes results ingestion (that's a
# post-gameweek evaluation concern, not a pre-deadline one).
predeadline-snapshot: data-refresh dual-write-refresh

clean:
	rm -rf .venv
	rm -rf node_modules apps/web/node_modules
	rm -rf apps/web/.next apps/web/coverage
	docker volume rm fpl_tool_postgres_data || true
