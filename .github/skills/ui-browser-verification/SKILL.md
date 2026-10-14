---
name: ui-browser-verification
description: Verify frontend changes using the actual rendered application. Use when checking apps/web UI behaviour or running browser verification, temporary frontend previews or production-build checks without disrupting user-owned development servers.
---

# UI Browser Verification

Component tests passing is not sufficient evidence that a UI change works.

1. Reuse user-owned services without changing their lifecycle, or start an
   isolated verification preview as described below. Use browser tooling
   (Playwright MCP or equivalent) to load the actual affected page(s).
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

## Server Ownership And Build Isolation

- Treat existing frontend port 3000 and backend port 8000 processes as
   user-owned. Never kill, restart or replace them for verification. Inspect
   listeners read-only; never free a port by killing its process. Apply the
   same rule to other processes whose ownership is unknown.
- Normal `make frontend-dev` uses port 3000 and `.next`. Do not change its
   command, environment or output to accommodate verification.
- Production verification must use `NEXT_DIST_DIR=.next-copilot` for both
   build and preview. Never run an unqualified production build against the
   normal `.next` directory while `next dev` may be using it. Keep the override
   command-local; do not put it in the user's shell or environment files.
- Choose port 3100 only if unused; otherwise choose another unused non-dev
   port. Never replace an existing listener, including an old preview without
   confirmed ownership. Avoid concurrent builds/previews using the same output
   directory. A custom `NEXT_DIST_DIR` must also be ignored by Git and have its
   generated types path declared in `apps/web/tsconfig.json` before building;
   otherwise Next rewrites that config and can trigger a dev-server reload.
   `.next-copilot/types/**/*.ts` is already declared for this purpose.

From the repository root, using the pinned toolchain:

```sh
mise exec -- env NEXT_DIST_DIR=.next-copilot pnpm --filter web build
mise exec -- env NEXT_DIST_DIR=.next-copilot pnpm --filter web start --hostname 127.0.0.1 --port 3100
```

Use the same directory for both commands, replacing 3100 if occupied. Point
browser tests at that preview, for example:

```sh
mise exec -- env PLANNER_BASE_URL=http://127.0.0.1:3100 pnpm --filter web e2e tests/e2e/planner-foundations.spec.ts
```

Start a temporary preview only inside a cleanup-managed verification scope.
Record its exact owned terminal/process handle immediately. Use `try/finally`
or equivalent teardown to stop and await that preview and all other temporary
verification processes, including child processes, on success, test failure,
startup failure or interruption. When using an async terminal, terminate that
owned terminal in the cleanup step; never substitute a port-wide kill or leave
the preview running for the user. Confirm the owned process has exited and its
port is released before reporting completion. Do not stop reused user-owned
services. Build artifacts may remain in the ignored verification directory.

Report the preview URL/port, cleanup result and any verification not completed.
Do not change API CORS policy to accommodate verification; reuse existing
test-origin handling/guarded harnesses instead.

## Out of scope

- Do not perform unrelated visual redesigns while verifying a change.
- Do not add broad new E2E coverage beyond the journey actually affected.
