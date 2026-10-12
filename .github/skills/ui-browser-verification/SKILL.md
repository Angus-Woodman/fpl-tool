---
name: ui-browser-verification
description: Verify substantial UI changes using the actual rendered application rather than static code inspection. Use after implementing or modifying UI behaviour, components, or user journeys in apps/web.
---

# UI Browser Verification

Component tests passing is not sufficient evidence that a UI change works.

1. Run the app (`make frontend-dev`, and `make backend-dev`/`make db-up` if
   the journey needs real data) and use browser tooling (Playwright MCP or
   equivalent) to load the actual affected page(s).
2. Verify the acceptance criteria/user journey end-to-end, not just the
   changed component in isolation.
3. Exercise the states relevant to the change: loading, success, error,
   empty, disabled, and key interactions (clicks, form input, navigation).
4. Do not declare success merely because `pnpm --filter web test:run` or
   `typecheck` passed — those do not prove the rendered behaviour is correct.
5. For journeys important enough to protect against regression, add or
   update a durable Playwright Test spec under `apps/web/tests/e2e/`. This is
   separate from exploratory MCP verification: Playwright Test is the
   automated regression suite; MCP/browser tooling is for interactive
   verification during implementation.
6. Report exactly what was observed (which states/journeys were exercised)
   and what could not be verified (e.g. requires data/auth not available
   locally).

## Out of scope

- Do not perform unrelated visual redesigns while verifying a change.
- Do not add broad new E2E coverage beyond the journey actually affected.
