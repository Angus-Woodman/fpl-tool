# fpl-tool

Local-first Fantasy Premier League decision-support application.

## Purpose

This repository contains Phase 0-1 foundation for an FPL tool with:
- Next.js frontend
- FastAPI backend
- standalone Python `fpl_engine` package
- PostgreSQL in Docker Compose
- strict typing, linting, tests, and CI
- typed FPL bootstrap ingestion (teams, players, gameweeks)

## Development Environment Strategy

### Host prerequisites
- Git
- Docker Desktop
- mise
- VS Code (optional but recommended)

### Managed by mise
- Node.js
- Python
- uv
- pnpm

### Project-local state
- frontend dependencies in `node_modules/`
- Python virtual environment in `.venv/`
- application dependencies from `pyproject.toml` and `pnpm-lock.yaml`

### Dockerised
- PostgreSQL database
- PostgreSQL persistent volume: `fpl_tool_postgres_data`

## Architecture

- `apps/web`: Next.js + TypeScript frontend
- `apps/api`: FastAPI app, application services, infrastructure adapters
- `packages/fpl_engine`: standalone domain and analytics package
- `data/fixtures/fpl`: external API JSON fixtures for contract tests

## Repository structure

- `apps/web`
- `apps/api`
- `packages/fpl_engine`
- `data/fixtures/fpl`
- `compose.yml`
- `Makefile`
- `.github/workflows/ci.yml`

## Quick start

1. Clone and enter repository.
2. Run `mise install`.
3. Run `make setup`.
4. Copy env file: `cp .env.example .env`.
5. Start database: `make db-up`.
6. Run backend: `make backend-dev`.
7. Run frontend: `make frontend-dev`.

`make dev` intentionally does not orchestrate multiple long-running processes; use separate terminals.

## Common commands

- `make setup`
- `make dev`
- `make backend-dev`
- `make frontend-dev`
- `make db-up`
- `make db-down`
- `make db-migrate`
- `make data-refresh`
- `make test`
- `make lint`
- `make typecheck`
- `make format`

## Migrations

- Apply migrations: `make db-migrate`
- Create migration: `make db-revision m="description"`

## Testing strategy

- Domain/unit tests concentrated in `packages/fpl_engine/tests`
- Backend tests in `apps/api/tests`
- Frontend unit tests with Vitest + React Testing Library
- Optional PostgreSQL integration tests are marked and run with `RUN_DB_TESTS=1`

## Data ingestion (Phase 1)

Implemented flow:

external FPL API -> typed external DTOs -> parser/mapper -> domain objects -> repositories

No raw dictionaries should pass through core business logic.

Import command:

- `make data-refresh`

This command fetches `bootstrap-static`, validates the payload, maps to domain entities, and upserts:

- Teams
- Players
- Gameweeks

Environment variables used:

- `DATABASE_URL`
- `FPL_API_BASE_URL`

Local import endpoints:

- `POST /imports/fpl/run` triggers import of teams, players, gameweeks, and fixtures.
- `GET /imports/fpl/status` returns the latest in-memory import status and summary.

## Clean reset

To remove generated state while keeping source code:

1. Delete local dependencies and virtual environment:
   - `rm -rf node_modules apps/web/node_modules .venv`
2. Stop and remove database container:
   - `make db-down`
3. Remove database volume:
   - `docker volume rm fpl_tool_postgres_data`
4. Optional frontend build cleanup:
   - `rm -rf apps/web/.next apps/web/coverage`

## Design principles

- Domain isolation from HTTP/framework/infrastructure details
- Thin FastAPI route handlers
- Explicit typed contracts and settings
- Incremental vertical slices and test-first behaviour
