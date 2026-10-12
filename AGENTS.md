# Agent Instructions

This is the single source of truth for standing, repository-wide instructions
to AI coding agents. Task-specific procedures live in `.github/skills/`
instead of being duplicated here. Spec Kit governs how substantial feature
work is specified and planned: `.specify/` holds its tooling/configuration,
while generated feature specs, plans and tasks live under the repository-root
`specs/` directory. This file governs how agents behave in this repository
at all times.

## Engineering ownership

- The human remains responsible for product direction, architecture,
  trade-offs and correctness.
- Do not silently expand scope. Do not implement adjacent improvements merely
  because they appear useful.
- For substantial work, inspect the relevant code, tests and requirements
  before editing.
- Before substantial implementation, identify the relevant
  specification/acceptance criteria and state the proposed approach,
  important assumptions and risks.
- Prefer small coherent changes that can be independently reviewed and
  verified.
- Explain significant architectural departures before making them.

## Architecture

- `apps/web` is the Next.js presentation/client application.
- `apps/api` contains FastAPI/application/infrastructure concerns.
- `packages/fpl_engine` contains framework-independent FPL domain/decision
  logic.
- Domain code must not depend on FastAPI.
- FPL rules and legality must have an authoritative domain implementation
  rather than relying only on React/UI validation.
- External API calls belong in infrastructure adapters.
- Do not duplicate domain behaviour across layers unless there is a
  justified UX optimisation, in which case authoritative server/domain
  validation must remain.
- Database schema changes require Alembic migrations.

## Implementation discipline

- Preserve strict Python typing and TypeScript strict mode.
- Do not silently catch errors.
- Do not introduce dependencies without a concrete need.
- Do not rewrite working modules without a clear reason.
- Preserve backward-compatible behaviour unless the accepted specification
  intentionally changes it.
- Use versions declared by repository tooling (mise, lockfiles) rather than
  globally installed versions.
- Python dependencies stay in the project-local uv environment.
- JavaScript dependencies stay in the project-local pnpm workspace
  (`node_modules`).
- For local development, PostgreSQL runs through Docker Compose rather than
  as a native host service. CI may use an isolated PostgreSQL service
  container instead.
- Do not introduce dev containers, Codespaces or new infrastructure services
  without explicit justification.
- Do not containerise the frontend/backend development workflow without a
  clear reason.

## Testing and verification

- New domain behaviour requires focused domain tests.
- API/application behaviour should be tested at the appropriate
  service/router/integration boundary.
- UI behaviour should receive component tests where useful.
- Important user journeys and visual/interactive changes must also be
  verified in a real browser.
- Do not treat the coding agent's own statement that something works as
  verification.
- Run the smallest relevant checks while iterating, followed by the
  appropriate broader quality gates before completion.
- For substantial changes, inspect the final `git diff` and confirm there is
  no unintended scope.

## Database safety

- Never run destructive integration-test setup against the development
  database.
- Integration tests requiring PostgreSQL must use `TEST_DATABASE_URL`.
- Never bypass `ensure_test_database_url` or the `_test` database-name
  safeguard to make tests run.
- If the dedicated test database is unavailable, fail/skip according to the
  existing explicit mechanism rather than falling back to development data.
- Never truncate, drop or reset persistent development data unless the
  human explicitly requests it and understands the consequences.

## UI/browser work

For substantial UI work:

- inspect the rendered application rather than reasoning only from JSX;
- compare the result against the acceptance criteria;
- verify relevant interactive states;
- use browser automation for repeatable important journeys;
- add durable Playwright tests where the journey is important enough to
  protect against regression.

See `.github/skills/ui-browser-verification/SKILL.md` for the detailed
workflow.

## Completion report

For substantial tasks, report:

- files changed;
- important decisions/trade-offs;
- tests/checks run;
- browser verification performed, if applicable;
- known limitations;
- anything not verified;
- whether the final diff was reviewed for unintended changes.

## Skills

Task-specific workflows live under `.github/skills/`:

- `feature-implementation` — bounded feature implementation workflow.
- `ui-browser-verification` — verifying substantial UI changes in a real
  browser.
- `code-review` — independent review of completed work.
