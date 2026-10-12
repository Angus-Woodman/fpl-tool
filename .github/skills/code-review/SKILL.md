---
name: code-review
description: Independently review completed work against the spec, architecture boundaries, and quality bar, without relying on the implementer's own narrative. Use before considering a change complete, especially for substantial features or anything touching domain rules, persistence, or UI.
---

# Code Review

Review completed work independently of how the implementation describes
itself. A green CI run is not sufficient for approval.

Review the diff for:

- conformity with the accepted spec/acceptance criteria;
- correctness, including edge cases the implementation narrative doesn't
  mention;
- architectural boundary violations (e.g. domain code depending on FastAPI,
  external API calls outside infrastructure adapters, FPL rules
  re-implemented in the UI instead of the domain layer);
- duplicated domain rules across layers;
- failure/error handling, especially silently swallowed errors;
- unsafe persistence/database behaviour (missing migrations, bypassing the
  `_test` database safeguard, destructive operations against non-test data);
- missing tests at the layer that owns the changed behaviour;
- insufficient browser verification for UI changes (see
  `ui-browser-verification`);
- unnecessary new dependencies;
- scope creep beyond the stated task;
- regressions in previously working behaviour;
- misleading or stale comments/documentation;
- unnecessary complexity relative to the size of the change.

Prioritise concrete defects and risks over style preferences. Call out
anything that was asserted to work but not actually verified.
