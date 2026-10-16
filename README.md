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

## Planner foundations rollout

The Planner stores one canonical, revisioned set of inputs (starting state, per-gameweek
decisions and lineup roles) and derives every figure by replay. Existing plans keep their
original rows and must be initialised once, explicitly. Nothing initialises a plan
implicitly: `GET /plans/{id}` only reports readiness.

Run from the repository root with the mise-pinned toolchain. The script follows `DATABASE_URL`
(from the environment or `apps/api/.env`) and has no `_test` guard, so never run `--apply` against
the development database merely to try it. To rehearse, point it at an isolated database for that
one command, for example `DATABASE_URL=postgresql+psycopg://fpl:fpl@localhost:5432/fpl_test ...`
(after `make db-test-up`).

1. **Back up first** (keep the file outside the repository):
   `mkdir -p ~/fpl-backups && docker compose exec -T postgres pg_dump -U fpl -d fpl -Fc > ~/fpl-backups/fpl-pre-planner.dump`
2. **Apply the additive schema:** `mise exec -- make db-migrate` (Alembic head `c6f91a2d83b0`). The new
   columns and tables are additive, so the old web/API keep reading the existing plan rows.
3. **Switch the web and API writers together.** The old `PUT /plans/{id}/gameweeks/{n}` and
   `PATCH /plans/{id}` now return `410 planner_writer_retired`, and the new web app saves only
   through `POST /plans/{id}/mutations`. Stop the old web/API, then start the updated ones. There
   is no legacy write fallback, so an old web build against the new API cannot save.
4. **Check readiness (read-only):**
   `cd apps/api && PYTHONPATH=src:../../packages/fpl_engine/src mise exec -- uv run --package api python -m api.scripts.initialize_planner_foundations --check`
   It prints one JSON report per plan (`ready_to_initialize`, `already_ready` or
   `legacy_pending` with diagnostics) and exits 1 while any plan is `legacy_pending`.
5. **Apply only after explicit operator approval** of the `--check` report and a fresh
   backup: the same command with `--apply`. Each plan is initialised in its own transaction,
   once only (re-runs report `already_ready`); original rows are kept and the first saved
   gameweek is used as the assumed boundary, with estimated purchase prices marked as such.
6. **Pending plans** (`legacy_pending`, for example missing gameweeks or unknown players) stay
   visible and read-only in the Planner with the retryable diagnostic. Repair the stored data
   and re-run `--check` / `--apply`; no other plan is affected.

Rollback limits: while no new-only write exists (no plan with revision above 0, none created on
the new schema, and no pending mutation receipts) `cd apps/api && mise exec -- uv run --package api
alembic downgrade -1` drops only the additive columns and tables and leaves the original rows untouched.
Once any plan has a Planner write or was created by the new code, the downgrade deliberately raises
"Back up/export and explicitly convert or restore before downgrade". Recovery from that point is
a restore of the pre-rollout backup (discarding later edits) or an explicit export and conversion;
an in-place downgrade is not lossless and is not offered.

Guarded database tests run with `make test-integration`, which uses only `TEST_DATABASE_URL`
(default `postgresql+psycopg://fpl:fpl@localhost:5432/fpl_test`) and refuses any database whose
name does not end in `_test`.

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
