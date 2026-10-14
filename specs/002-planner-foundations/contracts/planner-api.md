# Planner Foundations API And Mutation Contract

Revised 2026-10-14. [spec.md](../spec.md) is fixed product intent; [data-model.md](../data-model.md) defines canonical inputs/replay. Integer `_tenths` fields represent money. This design has one public mutation operation for changes to an existing plan, no public prepare/commit protocol and no writable full-squad compatibility surface.

## Read, Create And Retired Writers

Retain list/detail GET, POST creation and DELETE. Creation captures saved My Team membership/bank into an independent boundary, defaults starting FT to 1 after GW1 (N/A at GW1), and initializes unknown purchase prices as nonblocking assumptions. It does not copy My Team's FT default. Creation/deletion retain their ordinary resource semantics; the mutation retry contract below covers existing-plan autosave.

Retire `PATCH /plans/{plan_id}` and `PUT /plans/{plan_id}/gameweeks/{gw}` from mutation: return **410 Gone**, structured `planner_writer_retired`, with the new mutation route. No adapter, implicit identity, snapshot-diff fallback or weaker writer remains. Update all Planner name/horizon/GW callers and tests in the same rollout. An old browser must reload/update; old writes cannot partially mutate canonical or quarantined legacy data. Public per-mutation commit endpoints are not introduced.

Read a coherent aggregate/revision in one consistent database snapshot, not revision N with child rows from N+1. GET replays canonical boundary/decisions and returns:

| Field | Meaning |
|-------|---------|
| `revision`, `evaluator_version` | Ordering/evaluation compatibility, not a historical version browser. |
| `starting_state` | Independent membership/slots/bank/bases/provenance, FT/chip declarations, boundary/legacy assumption source. |
| `gameweeks[].decisions` | Explicit transfer IDs, outgoing ownership bindings, incoming acquisitions and saved price inputs; chip and local lineup choices. |
| `gameweeks[].players` | Full replayed squad with slot/ownership/source-decision IDs, XI/bench/C/VC, latest market, evaluated basis and provenance. Never a writable target snapshot. |
| `gameweeks[].accounting` | Derived starting/closing bank, FT available/next, unlimited flag, count and hit; unavailable/null when structurally blocked, GW1 FT is N/A. |
| `gameweeks[].chip_availability` | Available/planned here/planned elsewhere/used before/rule-unavailable, reason and conflicting GW. |
| `gameweeks[].legal_rearrangements` | Engine target pairs/kind for current evaluated membership. |
| `evaluation_status`, `decision_errors` | Complete/blocked, affected decision/GW, reason and unmet ownership precondition. No silently skipped decision or fictitious valid financial totals. |
| `financial_status` | Replay-derived provisional reasons, per-GW shortfalls, earliest failure and branch-aware dependent chain, separate from persistence. |
| `initialization` | Legacy assumed boundary/quotes, readiness and diagnostics. No GET backfill or invented history. |

Existing projected-points effects remain unchanged. Compatibility float response fields, if retained for reads, are adapters from integer replay, never financial inputs. Live market/projection enrichment may change; saved market assumptions/acquisition prices and bank cannot change merely on refresh. Pending receipts do not alter canonical GET output.

## Single Mutation: POST /plans/{plan_id}/mutations

Envelope: `mutation_id` (UUID), `expected_revision`, and `intents` (normally one; an explicit ordered repair batch when needed). The digest covers the entire immutable envelope. No browser-authored transaction quotes, derived bank or whole-GW membership payloads are accepted.

| Intent | Inputs and effect |
|--------|-------------------|
| `change_captain`, `change_vice_captain` | GW and selected player ID. Engine resolves current slot, updates only that role/GW, validates distinct roles. |
| `swap_lineup_players` | GW and two selected player IDs. Engine applies legal starter/bench or outfield priority swap and My Team captaincy inheritance. |
| `activate_chip`, `remove_chip`, `move_chip` | Explicit chip/source/target and expected existing values. Contradictions reject; never silently clear a second chip. Replay existing transfers without repricing. |
| `add_transfer` | GW and explicit entering-state outgoing player/ownership plus incoming player. Latest observed prices captured server-side. |
| `edit_transfer` | Decision ID and explicit changed outgoing/incoming identity or explicit quote refresh. Capture current prices for this edited record only. |
| `remove_transfer` | Decision ID; remove the explicit net decision and replay, not a simulated FPL reverse transaction. |
| `set_starting_transfers`, `set_starting_chips` | One starting field/domain value; appropriate period/declaration validation. |
| `correct_purchase_price`, `confirm_purchase_price` | Starting ownership/player and value or confirmation. Q7 finances remain persistable; no speculative future transaction price. |
| `rename_plan`, `change_horizon` | Name or horizon; explicit compatible declarations if changing start requires them. Rebase rules in data model. |

All input changes in an explicit batch are applied before final whole-plan validation; it is one canonical revision/transaction, not a sequence of partially saved plans. This permits Example B's upstream edit plus user-chosen downstream removal/replacement, and atomic multi-transfer net sets. No automatic replacement transfer is added. An incoming player selected again in the same GW edits its original acquisition decision, not a new same-GW sale/round trip. Expose source decision IDs so the client can submit that explicit edit. A batch of purchase corrections/confirmations cannot include planning mutations: reject mixed batches, commit Q7 corrections first, and validate later planning repairs against their acknowledged revision. Merely including a correction never exempts a new transfer from Q2.

### Server Processing And Acceptance

1. Serialize receipt creation/canonical writes on the plan row. Check an existing mutation ID/digest first: committed returns `already_committed` before evaluating expected revision; compatible pending resumes with its saved inputs. Mismatched digest rejects.
2. For a new ID, check expected revision, capture only new/explicitly edited prices and evaluate the whole candidate with the engine. Reject new structural violations and new/worse per-GW shortfalls under Q2; Q7 allows financially worsening provenance correction. Return affected-GW/decision diagnostics for rejected upstream dependencies, not an accepted invalid draft.
3. Durably record a valid `validated_pending` receipt containing the operation and necessary frozen financial inputs. This is the acceptance boundary, not a canonical-plan update. Do not claim acceptance if receipt persistence failed.
4. In a second bounded transaction, lock/reload the plan and receipt. Recheck receipt status/digest under this lock before checking the base: if a duplicate request committed meanwhile, return `already_committed` without writing, not a stale-base error. Otherwise recheck compatible revision and rule context, replay using saved observations, then atomically save canonical inputs, required selling-price materializations, revision+1 and the committed receipt. No half-recalculated plan may persist. The server automatically performs both stages in this one HTTP call.
5. A known canonical-write rollback after stage 3 returns accepted-but-not-saved; the pending receipt preserves the same quote for retry. A race advancing the revision instead returns explicit stale status. Do not treat either as a successful save.

The small private pending stage is retained because a lone rolled-back transaction cannot durably preserve an accepted quote for retry. It replaces client-visible prepare/commit, not canonical transaction atomicity. No aggregate history is stored, and ordinary successful autosave takes one request.

### Outcomes And Receipt Lookup

| Situation | Response / required behaviour |
|-----------|------------------------------|
| New commit | 200 `committed`, mutation ID, committed revision and current canonical plan. |
| Commit succeeded, response lost; same ID retried | 200 `already_committed`, original committed revision and current canonical plan; never execute/reprice/increment again. Works even if aggregate revision subsequently advanced. |
| Same ID, changed digest | 409 `mutation_id_reused`; never reinterpret an existing receipt. |
| New ID with stale expected revision | 409 `revision_conflict`, current revision/current canonical plan; no acceptance, price capture or write. Retain the intent for explicit reconciliation, not automatic overwrite. |
| Valid pending receipt, compatible base | Retry same POST resumes saved observations, regardless of live price refresh. GET receipt returns `accepted_not_saved` with a candidate regenerated only from this still-current base. |
| Pending base advanced / incompatible evaluator or rule context | 409 `stale_reprepare_required`, current revision and original intent metadata, **no reconstructed old candidate**. Retain local conflict context; explicitly rebase/revalidate with a new ID. Any new quote must be visible, not a silent retry reprice. |
| Canonical write failed after durable acceptance | 503 `accepted_not_saved`, mutation ID, base revision and validated candidate if the base is still compatible. Keep visible/retryable, pause dependent writes. |
| Database COMMIT outcome uncertain | 503 `outcome_unknown` if a response is possible; reconcile/retry the same ID. Never claim rollback or replay without first checking committed status. |
| Failure before durable acceptance / transport uncertainty | Pending/unverified or unknown outcome, never falsely accepted/saved. Retain intent, reconcile using the same ID. |
| New domain violation | 422 structured code/message/GW/decision/conflict/shortfall details. Previous accepted and retryable state survives. Schema 422 remains distinguishable. |
| Q7 correction committed with deficits | 200 `committed` plus derived `requires_resolution`; saved does not mean financially valid. |

`GET /plans/{plan_id}/mutations/{mutation_id}` provides committed/already-committed metadata plus current plan, compatible pending candidate, or explicit stale status as above. Unknown receipt is 404, not proof an original request is no longer in flight: retry/reconcile with the same ID, never blindly issue a new ID. Missing plan stops dependent writes. Receipt IDs/digests remain for the plan lifetime; there is no silent expiry/repricing. The current plan in a committed result can be newer than its committed revision; never reconstruct or overlay the original candidate on that newer state.

## Explicit Client Queue

One plan-scoped coordinator owns acknowledged revision/plan, one in-flight immutable envelope, any accepted-unsaved candidate, and a queue of field/domain intents. GW selection does not own or reset this state. Queue `change_captain(GW9,C)`, not a captured 15-player array or a `set_lineup` snapshot. Before dispatch, apply/rebase the next intent against the latest acknowledged evaluation, resolve current identities/decision bindings, then construct its expected-revision envelope and assign its ID. Once sent, that envelope is immutable for retries.

Example: queue captain C then vice D while captain saving is delayed. After captain acknowledgement, construct a vice-only request at the new revision; C stays captain. If the first intent was rejected, rebase the next against unchanged acknowledged state. If a target player has disappeared, surface/reselect that intent; do not silently target its replacement. Do not dispatch dependent edits past an accepted-unsaved or unknown outcome. Explicit repair batches are user-chosen, not silent queue merging.

Sequence/generation/revision guards prevent obsolete responses overwriting later acknowledged state or pending intents. Distinguish `saving`, `saved`, `not_saved` from provisional/financial resolution. Only a server-validated, durably accepted candidate supplies accepted unsaved calculations; unvalidated controls may show pending intent without claiming valid accepted results. On stale status, retain the user's context and require explicit reconciliation; no automatic cross-tab merge. Guard in-app departure/native unload while work is pending, and do not promise asynchronous unload persistence. A committed acknowledgement/reconciliation is the reload guarantee. There is no Save Gameweek button.

## Required Contract Examples

Protect Examples A/B and the moved-earliest-deficit case in the data model. Also test captain/vice queue rebasing, response loss after commit, identical duplicate request, changed-digest conflict, pending retry after price refresh, committed retry after a later revision, stale pending lookup without historical base, technical failure before/after acceptance, batch rollback, and 410 on both old writers with zero database changes. Reopening must derive the same corrected finances and preserved decisions; no snapshot diff or persisted validity flag may affect the result.