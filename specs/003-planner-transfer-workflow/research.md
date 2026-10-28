# Phase 003 Research

Date: 2026-10-28 (revised after the Phase 003 / Phase 004 split). Source of intent: [spec.md](spec.md) (active clarifications Q-1 to Q-3 and Q-6 to Q-8 resolved; Q-4 and Q-5 withdrawn with Duplicate Plan). The earlier Duplicate Plan research (transactional copy, identity remapping, advisory-lock naming, verbatim stored prices) was removed from this phase and survives only in Git history (commit `a3c5144`). Evidence is source inspection of the repository plus one throwaway pure-Python micro-benchmark (not committed). Nothing was run against any database. No `NEEDS CLARIFICATION` remains.

Format: **Decision**, **Rationale**, **Alternatives considered**.

## 1. Evaluating hypothetical transfers without touching persisted plans

**Decision.** Evaluate each candidate by building an in-memory copy of the canonical `Plan` (frozen dataclasses, `dataclasses.replace`) containing one added or replaced `TransferDecision`, replay it with `evaluate_plan`, and compare with a baseline replay computed once. The acceptance verdict is a pure, non-raising function extracted from `validate_candidate` in `fpl_engine.planning.mutations`, which `validate_candidate` then wraps to raise exactly as today. The decision identities for hypothetical decisions are deterministic `uuid5` values.

**Rationale.** `evaluate_plan` is pure and needs only player position and team metadata. `validate_candidate` already holds the rules the commit path enforces (new diagnostics, new or worsened per-gameweek shortfall); sharing one implementation means the Explorer cannot offer as confirmable what the Planner rejects (SC-003). Frozen dataclasses make accidental mutation impossible by construction; tests add a database no-write assertion.

**Alternatives.** (a) Call `apply_intents` per candidate and catch `MutationRejectedError`: raises at the first problem, so no gameweek-level detail, no multiple reasons, and re-evaluates the baseline each time. (b) Reimplement bank, club-limit and chip checks for ranking: duplicated rules would drift (rejected by constitution I). (c) Persist a draft plan or a "preview receipt": violates "no writes on read" and adds state.

## 2. Ranking: reuse `rank_replacement_candidates` unchanged

**Decision.** Call it with the plan's displayed gameweek-N squad, the candidate pool, and projections for gameweeks `[N, N+4]`; use only its ordering and best-XI gain by horizon. Discard its budget and club-limit flags; the plan assessment is the legality authority. Pass `bank=0.0`.

**Rationale.** The user's requirement is reuse of existing ranking. Gain does not depend on legality (`evaluate_single_transfer` computes it whenever the composition is valid), so ignoring the flags is safe. My Team behaviour is untouched because shared code is not changed.

**Alternatives.** Add an injectable "before" selection to cache the best-XI per gameweek: kept as a gated optimisation (section 6), not done up front. Fork a Planner-specific ranker: rejected (duplicate logic).

**Caveat.** `rank_replacement_candidates` slices horizons by count of supplied gameweeks, so the service supplies the contiguous prefix of covered gameweeks starting at N; a gap ends coverage and is reported as partial.

## 3. Plan impact via replay and per-gameweek scoring

**Decision.** For each horizon gameweek, impact = `score_gameweek` total (excluding hit) for the candidate evaluation minus the same for the baseline, using the evaluated squad, that gameweek's saved slot roles and planned chip. Per-gameweek hit differences come from the two evaluations and are reported separately; net = saved-plan impact minus hit change.

**Rationale.** This reproduces exactly how the Planner scores a gameweek, so the number matches what the plan would show after confirming. Slot-based lineups already make the incoming player inherit the outgoing player's role in every gameweek, including captaincy, bench order and chip effects. Replay also applies later planned decisions, Wildcard carry-forward and Free Hit restoration without new logic.

**Alternatives.** Raw projection difference: rejected by Q-6. Re-optimise the lineup: that is the best-XI measure, kept separate (Q-1).

## 4. Assumed continuation beyond the plan's end

**Decision.** For horizon gameweeks after `plan.end_gameweek`, use the evaluation's permanent squad after the final gameweek (`EvaluatedGameweek.permanent_players`, which restores the pre-Free-Hit squad) and the final gameweek's slot roles, no chip, no transfers. If those roles are not a legal XI for the restored squad, report the continuation unavailable. Label and total it separately.

**Rationale.** Matches the product decision of 2026-10-28. `Ownership` slot identity survives Free Hit replacement (replacements take the outgoing slot), so roles by slot map onto the restored squad. Legality can fail only when a Free Hit final gameweek permuted positions across slots; reporting that is honest and avoids silently repairing a lineup.

**Alternatives.** Use the selected gameweek's roles (earlier proposal, superseded). Fall back to the last non-Free-Hit gameweek's roles: more complex and not requested.

## 5. Conflict classification and what is shown

**Decision.** Selected-gameweek diagnostic or shortfall means `unavailable`; a later gameweek's first diagnostic or shortfall means `blocked_by_later_decision` and carries that gameweek and decision. Values are valid through the last good gameweek (structural: through c-1; financial: through c; nothing after). Same-gameweek sale of the candidate is detected before building the plan (the plan constructor would raise `same_gameweek_round_trip`).

**Rationale.** `evaluate_plan` already stops producing squads after a structural problem (`dependency_blocked` for later gameweeks) and flags financial chains; the rule reuses that, and satisfies "valid information up to the first downstream conflict" without inventing dependent values. Matches the 002 contract's blocked-evaluation semantics.

**Alternatives.** Hide conflicting candidates (rejected by Q-2). Offer repair batches (rejected by Q-2).

## 6. Performance

**Evidence (measured, pure engine, noisy, no database).**

| Operation | 8-gameweek plan | 38-gameweek plan |
|---|---|---|
| `evaluate_plan` once | 1.4-2.3 ms | 2.8-5.7 ms |
| Replay of 300 candidates | 0.34-0.56 s | 1.3-1.4 s |
| `rank_replacement_candidates`, 300 candidates x 5 gameweeks | 0.7-1.25 s | (not plan-dependent) |

A first profile showed the optimiser dominating ranking (two `optimise_lineup` calls per candidate per gameweek, "before" selection recomputed per candidate). Expected request total for the gated case: roughly 1.5-2.5 s before network; 38-gameweek plans may exceed 3 s (non-gating).

**Decision.** Implement the straightforward correct path, measure end to end on a synthetic full-season dataset in the guarded test database, and optimise only if the gate exceeds 70% of budget, in this order: (a) memoise the "before" best-XI per gameweek inside the ranking call; (b) resume replay from the selected gameweek; (c) skip replay for candidates already excluded by cheap exact rules. Each lever needs an equality test against the straightforward path. No parallelism, cross-request caching or precomputation.

**Rationale.** Matches Q-8 ("not premature optimisation") while acknowledging measured risk. Optimisations preserve semantics and are independently testable.

**Alternatives.** Approximate legality with arithmetic: rejected (correctness). Cache candidate results by plan revision: adds invalidation risk for no demonstrated need.

## 7. Price-change guard on confirmation (Q-7)

**Decision.** Add optional `expected_outgoing_market_tenths` and `expected_incoming_price_tenths` to `add_transfer` and `edit_transfer`. When present, `_capture` compares them with the freshly captured prices and rejects with a `prices_changed` diagnostic (HTTP 422) if either differs; the saved quote is always the server's capture. The Explorer sends the guard taken from its preview; the inline picker sends none.

**Rationale.** The 002 contract forbids browser-authored quotes; a compare-only guard respects that while preventing silent acceptance of different assumptions. It uses the existing single writer, receipts and digest (the guard is part of the immutable envelope, so retries are identical). 422 is handled by the coordinator as a rejection with diagnostics, preserving prior state.

**Alternatives.** A new Explorer commit endpoint (a second writer, rejected). 409 (the coordinator treats 409 as a revision conflict and offers revalidate, which is the wrong semantics). Server-side preview tokens (new state).

## 8. Selectability on the write path (Q-3)

**Decision.** Extract `incoming_selectability_exclusion` from `candidate_pool_exclusion`; `_capture` checks it for the incoming player of every added transfer and every edit that changes the incoming player. Rejections are `player_not_selectable` or `selectability_unknown` (refresh required). Replay of saved decisions never checks it.

**Rationale.** Closes the gap where only the browser filtered (playing status, not selectability). Reuses the same pure rule and precedence as My Team apply. Requires the lookup repository to return the two flags (defaulted fields, so existing callers are unaffected).

**Alternatives.** Check inside `evaluate_plan`: would retroactively invalidate saved decisions (forbidden by Q-3). Filter only in the Explorer: not authoritative.

## 9. Projections, run pinning and fixtures

**Decision.** Use model `component_v3` and `ProjectionRunRepository.get_latest` on first load; thereafter the client passes `projection_run_id` so ranking, list refreshes and previews use one run; the response says `newer_run_available`. Bound the projection query to `[N, N+4]` with optional `min_gameweek`/`max_gameweek` on `list_player_fixture_projections_for_run`. Fixture rows (opponent, home or away) come from the same rows; difficulty comes from the existing team read repository's effective difficulty (override or source) keyed by opponent short name.

**Rationale.** Preserves "explicit model and run, no silent substitution". Bounded queries keep payloads small. Reuses data the fixture ticker already shows.

**Alternatives.** A model selector (out of scope). The older "official pre-deadline run" rule (not implemented anywhere today). Fetching all gameweeks (needless rows).

## 10. Read transaction handling

**Decision.** `load_canonical` takes a shared row lock; the service ends its read transaction immediately after loading the plan, then does the remaining reads and compute.

**Rationale.** A multi-second ranking would otherwise hold a lock that blocks the plan's autosave writes (`FOR UPDATE`). Revision in the response plus `expected_revision` at confirm time covers staleness.

**Alternatives.** Run the whole request under the lock (blocks writers). Snapshot isolation (extra configuration).

## 11. Explorer routing, context and return

**Decision.** `/transfers?plan&gw&out&h&run` selects Planner mode; no `plan` parameter keeps today's component untouched. The Planner returns via `/plans/{id}?gw&highlight`. Before leaving for the Explorer the Planner `replaceState`s its own entry with `?gw=` so browser Back also restores the gameweek. A one-shot `sessionStorage` notice carries the confirmation message.

**Rationale.** Address-based context survives reload, new tabs and Back/Forward (FR-001, FR-006) with no new routes or global state. The existing `SquadPlayerCard.transferHref` already renders "Explore transfers".

**Alternatives.** Embedded panel in the Planner (larger rewrite of a 1,455-line component and closer to Phase 004). Query-free context in module state (lost on reload).

## 12. Coordinator: pinned submissions and abandon

**Evidence.** `PlanSaveCoordinator.drain()` builds every envelope with `expected_revision` equal to the coordinator's latest acknowledged revision at dispatch, and `enqueue()` accepts no caller revision (by design: Planner edits are field-level intents that are rebased at dispatch). A transfer previewed at revision N and enqueued after another edit was acknowledged would therefore be sent against N+1, silently applying a decision whose finances, impact and conflicts were computed for N. Separately, an Explorer that infers success from "acknowledged revision increased" could credit an unrelated edit.

**Decision.** Add one narrowly scoped path to the coordinator, leaving `enqueue`, the queue and every existing behaviour untouched:

- `submitPinned({ intents, expectedRevision })` sends the preview's descriptor against exactly `expectedRevision`. It never enqueues: it is refused, without sending anything, if the coordinator is not idle, if another pinned submission exists, if the acknowledged revision differs from `expectedRevision`, or if the intents no longer resolve against the acknowledged plan. It is never rebased, re-resolved or replayed.
- The coordinator tracks it as `snapshot.pinned` with its own mutation identity and outcome (`sending`, `committed`, `rejected`, `conflict`, `unknown`, `pending_unsaved`, `plan_missing`). The Explorer reports success only when `pinned` carries its own submission identity with status `committed`.
- `abandon()` discards only the pinned submission, only for the statuses listed in [contracts/pinned-submission.md](contracts/pinned-submission.md), refreshes the plan first when needed, and never touches the queue or any non-pinned in-flight work. Unknown outcomes are refused until reconciled or retried with the same identity.
- `revalidate()` on a pinned submission never replays it: it behaves as `abandon()` for a known conflict and is refused otherwise.
- Abandoning `pending_unsaved` is client-side only. The Phase 002 pending receipt is durable and has no cancel or delete operation; it stays inert because it only resumes if the same request is repeated with the same identity, which the client discards. The Explorer must therefore say that the transfer was not added, will not be retried, and that a pending record may remain (never "cancelled" or "removed"), and `abandon()` reports `serverReceiptRetained`.
- A `rejected` record is a notification, cleared only by `abandon()` (no server contact), so it can neither block a later confirmation nor be mistaken for one in flight; the Explorer keeps the message from the cleared record, reloads the preview and requires an explicit new confirmation with a new identity.
- Extract the Planner's departure-guard effect into a shared hook so the Explorer has identical protection.

**Rationale.** It is the smallest change that makes the previewed revision binding: the check and the envelope use the same pinned value, the server's expected-revision check remains the final authority, and the pinned path shares the coordinator's single in-flight slot, retry, reconcile and departure-guard machinery rather than creating a second writer. The module-level coordinator map keeps pinned state across client-side navigation, so unresolved submissions are not lost when the user moves between pages.

**Alternatives.**
- `enqueue(intents, { expectedRevision })`: mixes a pinned transfer into the FIFO queue whose design is to rebase at dispatch; a pinned item queued behind other work would almost always become stale and the two semantics would interact in subtle ways.
- An Explorer-private `mutatePlan` call: a second writer outside the single in-flight slot, queue ordering and departure guard.
- Check after sending: too late; the request is already applied.
- Reusing `revalidate()` after a conflict: replays the old transfer against a newer plan, which the product owner explicitly ruled out.
- Abandoning unknown outcomes by discarding locally: risks a later commit the user did not know about; instead the user reconciles first or retries with the same identity.

## 13. Test data and safety

**Decision.** Integration tests use the existing isolated-schema fixtures on the `_test` database (`planner_session`, `ensure_test_database_url`). The performance gate generates a synthetic full-season dataset (about 600 players, 20 clubs, one projection run) in an isolated schema; an optional read-only timing run against development data is offered for approval, never mutating it.

**Rationale.** AGENTS.md and constitution VII. Trimmed repository fixture JSON is not representative of pool size.

## 14. Schema and dependencies

**Decision.** No Alembic revision, no new dependency, no new service or container.

**Rationale.** Everything needed is derivable from the canonical tables, and the Explorer read paths take no locks beyond the existing plan row lock, which is released after the planning context is resolved.

## 15. Phase 004 adaptability (Branching Scenario Planner)

Phase 004's product direction is captured in [../004-branching-scenario-planner/vision.md](../004-branching-scenario-planner/vision.md). Phase 003 does not implement it; this section records the few design choices made to limit foreseeable rework, and the ones deliberately declined.

**Decision.** Three seams, each one function, one dataclass or one prop:

1. `resolve_planning_context(plan_id, gameweek) -> PlanningContext` (plan storage access, the only Explorer code that reads it) separated from a `PlanTransferAnalysisService` that takes a `PlanningContext`. The context holds a `ContextRef` (plan, gameweek, revision), the engine's linear `Plan`, player rule metadata and the baseline `PlanEvaluation`.
2. The analysis service is constructed from read-only ports only, so analysis cannot write by construction; engine functions take and return values.
3. The preview returns a commit descriptor (`commit.intent`, `guard`, `expected_revision`) and the `planning_context` ref; the Explorer UI receives a `commit` function prop whose default wraps the existing save coordinator.

**Rationale.** The engine already depends only on the canonical `Plan` value and `PlayerRuleData`. In Phase 004 a selected path from the common start to an option can be flattened into that same linear value, so hypothetical evaluation, ranking, plan impact and the acceptance verdict are reusable unchanged. The parts that must change are exactly the edges: how a context is resolved, how it is addressed (routes, URL, revision token) and where a confirmation is written (a draft option, never an immutable saved option). Making those edges explicit now is cheap; retrofitting them later would mean separating analysis from persistence inside a working feature.

**Alternatives considered.**
- *Build nothing extra and refactor in Phase 004*: smallest Phase 003, but Explorer services would reach into plan storage and writers, so Phase 004 would have to untangle them.
- *Generalised `Scenario`/`Option` abstraction now*: speculative; the vision leaves open questions (path flattening, continuation semantics, draft addressing) that Phase 004's specification should settle first.
- *Repository interface or dependency-injection framework for context sources*: unnecessary indirection; a function parameter is enough.
- *Option identifiers in the contract now*: would freeze guesses about Phase 004's identity model.

**Known adaptation points** (see the table in [plan.md](plan.md)): the resolver, the `planning_context` ref, Explorer routes and URL parameters, the commit adapter and coordinator semantics for drafts, the definition of "later planned decisions" and "plan end" for continuation, Planner navigation (return context becomes option-aware), and reference fixtures.

