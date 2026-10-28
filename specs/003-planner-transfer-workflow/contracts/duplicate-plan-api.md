# Duplicate Plan API Contract

## POST /plans/{plan_id}/duplicate

Creates an independent, fully saved copy of the plan's canonical state. Not a mutation of the source: it writes no receipt and does not change the source's revision or update time.

Request body:

```json
{ "expected_revision": 7 }
```

`expected_revision` is the revision the caller has seen saved (the coordinator's acknowledged revision). Extra fields are rejected.

### 201 response

```text
plan: PlanResponse            # the new plan, revision 0, as GET /plans/{id} would return it
source_plan_id: int
source_plan_name: string
```

### Errors

| Status | `code` | When | Effect |
|---|---|---|---|
| 404 | `plan_not_found` | source missing | nothing created |
| 409 | `plan_not_ready` | source awaiting Planner initialisation | nothing created; source not initialised or modified |
| 409 | `revision_conflict` | `expected_revision` differs from the source's committed revision (body includes `current_revision`) | nothing created |
| 409 | `pending_edit_unresolved` | an accepted-but-unwritten mutation receipt is resumable at the current revision | nothing created |
| 422 | schema error | malformed body | nothing created |
| 500/503 | `duplicate_failed` | any storage or verification failure | whole transaction rolled back; nothing created |

A non-resumable (stale) pending receipt does not block duplication.

### Semantics

- One database transaction. Any failure, including the in-transaction round-trip verification, rolls everything back.
- Copies exactly the saved canonical inputs listed in the spec; regenerates every internal identifier consistently; copies stored selling prices verbatim; does not copy receipts or legacy snapshots; never reads My Team.
- Name: allocated under a per-family transaction advisory lock using the spec's naming rules (highest existing member plus one, deleted numbers reusable, 100-character fit). Two concurrent duplications of a family receive distinct names.
- The source plan row is locked `FOR UPDATE` for the duration, so a concurrent mutation either commits before the copy is taken (and then fails the revision check) or waits until after it.
- No idempotency key: a repeated request creates another copy. Single-flight is a client responsibility; an unknown outcome is reported to the user (spec FR-056).

### Frontend client

`duplicatePlan(planId, expectedRevision)` returns the response or throws a typed error carrying `status` and `code`. The control reads `expectedRevision` from the plan's save coordinator (acknowledged revision) and is enabled only when the coordinator reports `saved`, no queue and no in-flight envelope, and the plan is `ready`.
