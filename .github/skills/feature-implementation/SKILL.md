---
name: feature-implementation
description: Guide bounded feature implementation from spec/acceptance criteria through focused validation. Use when implementing a scoped feature, slice, or bug fix that has (or should have) a governing spec or clear acceptance criteria.
---

# Feature Implementation

Workflow for implementing a bounded slice of product behaviour.

1. Locate the governing spec/acceptance criteria (`.specify/specs/*` or the
   task description). If none exists for a substantial change, say so before
   proceeding.
2. Inspect the relevant implementation and existing tests before editing.
3. State the intended change surface, assumptions, risks and any
   architectural implications. Stop and ask if a significant architectural
   departure is required.
4. Implement the smallest coherent slice that satisfies the acceptance
   criteria. Do not expand scope or perform unrelated refactors.
5. Add or update tests at the layer that owns the behaviour (domain tests in
   `packages/fpl_engine`, service/router/integration tests in `apps/api`,
   component tests in `apps/web`).
6. Run focused validation for the changed area first.
7. Run the broader relevant quality gates (lint, typecheck, full test suite)
   before declaring completion.
8. For UI work, invoke the `ui-browser-verification` skill.
9. Inspect `git diff` in full and confirm there is no unintended scope.
10. Report completion against the acceptance criteria and explicitly list
    anything unverified or out of scope.

## Prohibited

- Silent scope expansion beyond the stated acceptance criteria.
- Unrelated refactors bundled into the same change.
- Declaring a feature done without running the tests that own its behaviour.
