# Pinned Submission Contract (PlanSaveCoordinator)

Defines how Explorer transfer confirmations are submitted and tracked by the plan's save coordinator (`apps/web/src/lib/plan-save-coordinator.ts`), and exactly what `abandon()` may discard. It extends the coordinator without changing `enqueue`, the queue, `retry`, `reconcile`, or the behaviour of Planner-authored edits.

Requirements: FR-034, FR-035, FR-041, FR-049 to FR-052; scenarios US2-18 to US2-24; success criterion SC-014; tests C1 to C21 in [quickstart.md](../quickstart.md).

## Why a separate path

`enqueue()` batches are field-level intents. At dispatch they are re-resolved against the latest acknowledged plan and sent with `expected_revision` equal to the latest acknowledged revision (this is what makes queued Planner edits rebase safely). A previewed transfer is different: its prices, selling price, hit, impact and conflicts were computed for one exact revision, so it must either be sent against that revision or not at all. It is therefore never queued, never re-resolved and never replayed.

## Surface (conceptual; signatures finalised in implementation)

| Member | Behaviour |
|---|---|
| `submitPinned({ intents, expectedRevision })` | Returns `{ type: "started", submissionId }` or `{ type: "refused", reason }`. Never enqueues. |
| `snapshot.pinned` | `PinnedSubmission | null` (see data-model). At most one per plan. |
| `retry()` | Existing method; for a pinned `unknown` or `pending_unsaved` submission it resends the same envelope with the same mutation identity and the same pinned revision. |
| `reconcile()` | Existing method; looks up the pinned submission's own mutation identity. |
| `abandon()` | `Promise<AbandonResult>`: `{ type: "abandoned", previous: PinnedSubmission, serverReceiptRetained: boolean }`, `{ type: "nothing_to_abandon" }`, `{ type: "refused", reason: "outcome_pending" \| "reconcile_first" }` or `{ type: "refresh_failed", message }`. Discards only the pinned submission under the table below. `previous` is the cleared record, so its message and diagnostics can be kept by the caller. |
| `revalidate()` | Existing method; for a pinned submission it never replays: it behaves as `abandon()` when the status is `conflict` and is refused otherwise. For non-pinned active work it is unchanged. |
| `hasUnsavedWork()` | Existing method; true while a pinned submission is `sending`, `unknown`, `pending_unsaved` or `conflict`. |

## Submission preconditions (checked synchronously, in this order; first failure wins; nothing is sent or queued on refusal)

1. The plan is initialised and not missing: otherwise `not_ready` or `plan_missing`.
2. No pinned submission exists (any status, until `abandon()` clears it): otherwise `pinned_exists`. A terminal record (`committed`, `rejected`, `plan_missing`) is a notification that stays until `abandon()` acknowledges it (see "Clearing a rejected submission"); `submitPinned` never replaces one silently.
3. The coordinator is idle (no active envelope, empty queue): otherwise `busy`.
4. `acknowledged.revision === expectedRevision`: otherwise `stale_preview`.
5. Every intent resolves against the acknowledged plan without retargeting (outgoing player still owned, decision still present for an edit): otherwise `stale_preview`.

On success the coordinator creates a new mutation identity, freezes an envelope `{ mutation_id, expected_revision: expectedRevision, intents }`, makes it the active envelope and dispatches immediately. `expected_revision` is the pinned value, asserted equal to the acknowledged revision; it is never read from "latest" afterwards.

## States and server outcomes

| Status | Entered when | Active envelope retained | `hasUnsavedWork()` |
|---|---|---|---|
| `sending` | submitted, or same-identity retry in progress | yes | true |
| `committed` | 200 `committed` or `already_committed` whose mutation identity equals the pinned one | no | false |
| `rejected` | 422 (domain rejection including `prices_changed`, `player_not_selectable`, `selectability_unknown`, squad or financial rules) | no (the record keeps its message and diagnostics until `abandon()` acknowledges it) | false |
| `conflict` | known no-write outcomes: 409 `revision_conflict`, 409 `stale_reprepare_required`, 410 `planner_writer_retired`; or a receipt lookup returning those | yes | true |
| `pending_unsaved` | 503 `accepted_not_saved`, or a receipt lookup returning `accepted_not_saved`; the server holds a durable `validated_pending` receipt and the plan is unchanged | yes | true |
| `plan_missing` | 404 `plan_not_found` | no | false |
| `unknown` | anything else: network failure, timeout, malformed or unreadable response, 503 `outcome_unknown` or `not_accepted`, 409 `mutation_id_reused`, receipt lookup 404 `mutation_not_found` (inconclusive) | yes | true |

Coordinator `status` for existing Planner UI: `sending` is `saving`; `conflict` is `conflict`; `unknown` and `pending_unsaved` are `not_saved`; `rejected` is `error` with the rejection message; `plan_missing` is `missing`. Existing buttons keep their meaning.

Success is only `committed` with the Explorer's own `submissionId`. A newer acknowledged revision, `synchronize()`, or the acknowledgement of any other mutation never changes `pinned` to `committed`.

## What `abandon()` may discard

`abandon()` discards the pinned submission and nothing else. It never discards the queue, a non-pinned active envelope, or any other state.

| Status | Result | Server contact | Notes |
|---|---|---|---|
| no pinned submission | `nothing_to_abandon` | none | no-op |
| `sending` | refused `outcome_pending` | none | outcome unknown by definition |
| `unknown` | refused `reconcile_first` | none | the user must `reconcile()` (check by identity) or `retry()` with the same identity; reconciling may turn it into `committed`, `pending_unsaved`, `conflict` or leave it `unknown` |
| `pending_unsaved` | allowed | plan refresh only | client-side only: the server's durable pending receipt is not cancelled, deleted or committed (see "Abandoning an accepted-but-not-saved transfer"); result carries `serverReceiptRetained: true` |
| `conflict` | allowed | plan refresh only | |
| `rejected` | allowed | none | clears the record and recomputes the coordinator status (the `error` raised by the rejection is cleared); no refresh needed; the caller keeps the message from `previous` (see "Clearing a rejected submission") |
| `committed` | allowed | none | acknowledges and clears the record |
| `plan_missing` | allowed | none | clears the record; coordinator stays `missing` |

Mechanics:

1. The only envelope `abandon()` may clear is the active one whose mutation identity equals the pinned submission's. If the active envelope is anything else, nothing is cleared.
2. For `conflict` and `pending_unsaved`, the plan is loaded first. On success, in a single published update: acknowledged and displayed plan become the loaded plan, the active envelope and `pinned` are cleared, the coordinator status is recomputed, and queued work resumes. If the load fails, nothing is discarded, the status stays as it was and a message says the refresh failed. If the plan no longer exists the coordinator becomes `missing`.
3. Queued Planner edits are never discarded or altered. After the refresh they resume under the existing rebasing rules for field-level intents. The abandoned transfer's intents are never queued or replayed.
4. Concurrent or repeated `abandon()` calls while one is in progress are ignored.
5. After `abandon()` the Explorer refreshes its context and requires a new preview before another confirmation (FR-049, FR-051).

## Abandoning an accepted-but-not-saved transfer

`pending_unsaved` means the server durably accepted the transfer (a validated pending receipt bound to its mutation identity and base revision, Phase 002 `contracts/planner-api.md`) but did not save it to the plan. The plan is unchanged.

- `abandon()` is client-side only. It clears the pinned record and the active envelope and refreshes the plan. It sends no mutation, no receipt request and nothing that cancels, deletes or commits the receipt; the API has no such operation and none is added.
- The pending receipt therefore remains on the server. It is inert: the server never applies a pending receipt by itself, it can only be resumed by repeating the same request with the same mutation identity, and the client discards that identity. It becomes stale once the plan revision advances. It is never a committed transfer and never appears in the plan.
- `AbandonResult` reports `serverReceiptRetained: true`, so callers cannot treat the operation as a cancellation.
- Adding the transfer later means a fresh preview and a new submission with a new mutation identity; the discarded identity is never reused.

Required Explorer wording and behaviour:

1. While the status is `pending_unsaved` the Explorer offers "Retry same transfer" and "Check save status" first and, as a secondary action labelled "Stop tracking this transfer" (never "Cancel", "Delete", "Discard" or "Remove"), with this explanation visible next to it before the user acts: "The server accepted this transfer but could not save it. If you stop tracking it, it will not be added to your plan and this app will not retry it. The server may keep a pending record of it, which is not a saved transfer."
2. After `abandon()` the Explorer shows a persistent notice: "Transfer not added to your plan. The server may still hold a pending record of it; that record is not a saved transfer and this app will not retry it." The Explorer never states or implies that this transfer was saved, cancelled, deleted or removed (the only permitted uses of those words are the negated forms in the wording above), does not highlight the incoming player, does not navigate to the Planner as a success and requires a fresh preview before another confirmation.
3. The refreshed plan is the only source of what is saved.

## Clearing a rejected submission

A 422 rejection (for example `prices_changed`) is a known outcome: nothing was written and no envelope is retained. The `rejected` record keeps its `message` and `diagnostics` only so the rejection can be reported. It is a notification to acknowledge, not a lock.

1. A rejected mutation identity is never retried, reconciled or reused; `retry()` and `reconcile()` do nothing for it and the Explorer offers no same-identity retry.
2. The Explorer clears the record by calling `abandon()` as soon as it observes its own submission `rejected` (always allowed; no server contact; no plan refresh). It keeps the message and diagnostic code from the returned `previous` record in its own state.
3. It then reloads the list and preview for the same outgoing and incoming player at the current revision, automatically for `prices_changed` (showing the new prices) and also for any other rejection so the preview reflects what the server now says. Nothing is submitted.
4. The rejection message stays visible above the fresh preview until the user confirms a new transfer, changes the outgoing player, candidate or horizon, or dismisses it.
5. Confirm on the fresh preview obeys the usual preconditions (no pinned record, coordinator idle, preview revision equals the acknowledged revision) and always needs a new explicit user action. The new submission gets a new mutation identity. Neither the coordinator nor the Explorer ever resubmits by itself.
6. If the Explorer was left before it acknowledged the rejection, the record persists with the singleton coordinator. On mount the Explorer shows the message of any terminal record (`rejected`, `committed` or `plan_missing`) once and clears it with `abandon()`; it never starts a submission from it and never navigates because of it. A `rejected` record never blocks Planner edits (`enqueue` is unaffected) and `hasUnsavedWork()` is false for it. Because the Explorer always acknowledges first, a rejection cannot permanently prevent confirming a newly previewed transfer.

## Overlap and ordering rules

- A Planner edit enqueued while a pinned submission is `sending` is queued behind it and dispatched afterwards against the then-acknowledged revision (existing behaviour).
- A pinned submission is refused while Planner edits are queued or in flight; it is never placed behind them.
- If another edit is acknowledged between preview and confirmation, the acknowledged revision no longer equals the preview's revision and the submission is refused (`stale_preview`); the Explorer also marks the preview stale as soon as it observes the revision change.
- If another browser tab advanced the server revision, the coordinator may not know yet: the request is sent with the previewed revision and the server's expected-revision check returns 409 `revision_conflict` (`conflict`), after which the user abandons and previews again.

## Navigation

- The coordinator is a module-level singleton per plan, so an unresolved pinned submission survives client-side navigation and is shown again when the user returns to the Explorer or opens the Planner. A hard reload loses client state; the existing same-identity receipt lookup does not apply to a lost identity, so after a reload the plan is simply reloaded and a fresh preview is required (the server remains the authority on what was saved).
- Leaving while the submission is `sending`, `unknown`, `pending_unsaved` or `conflict` triggers the departure warning (link click, `beforeunload`, Back and Forward guard).
- The Planner page shows its existing save-status message and buttons for a pinned submission. Its "Retry Same Edit" and "Check Save Status" act on the pinned envelope as described above; its "Revalidate With Current Data" never replays the transfer.

## Explorer rules built on this contract

- Confirm is enabled only when `pinned === null`, the coordinator is idle, and the preview's revision equals the acknowledged revision.
- Success is shown only when `pinned.submissionId` equals the Explorer's own submission and its status is `committed`; the Explorer then calls `abandon()` to clear the record and navigates to the Planner.
- On `rejected` (including `prices_changed`) the Explorer keeps the message, clears the record with `abandon()`, fetches a fresh preview and never resubmits; confirmation needs a new explicit action ("Clearing a rejected submission").
- On `conflict` the Explorer offers "Refresh and preview again", which calls `abandon()`.
- On `unknown` the Explorer offers "Check save status" (`reconcile()`) and "Retry same transfer" (`retry()`), and no abandon until reconciled.
- On `pending_unsaved` the Explorer offers retry, check status and, with the required warning, "Stop tracking this transfer"; afterwards it shows the not-added notice ("Abandoning an accepted-but-not-saved transfer").

## Compatibility

Existing coordinator tests (`apps/web/tests/plans/plan-save-coordinator.test.ts`) and Planner component tests must pass unmodified. All new code paths are gated on a pinned active envelope; with no pinned submission the coordinator behaves exactly as today.

## Phase 004 note

In Phase 004 the pinned revision would be re-keyed to an option or draft version, and the abandon semantics would apply to a draft-targeted submission. Nothing here names options or branches.
