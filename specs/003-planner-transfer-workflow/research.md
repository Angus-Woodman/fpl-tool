# Phase 003 Research

Date: 2026-10-28. Source of intent: [spec.md](spec.md) (Q-1 to Q-8 resolved). Evidence is source inspection of the repository plus one throwaway pure-Python micro-benchmark (not committed). Nothing was run against any database. No `NEEDS CLARIFICATION` remains.

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

## 12. Coordinator and conflicts

**Decision.** Commit through `getPlanSaveCoordinator(plan).enqueue([...])`. Add `abandon()` to drop the active conflicted envelope and resynchronise; the Explorer never calls `revalidate()`. Extract the Planner's departure-guard effect into a shared hook.

**Rationale.** `revalidate()` re-resolves and resends the original edit against the fresh plan, which would commit a transfer the user has not re-previewed, contradicting FR-034. The module-level coordinator map is shared across client-side navigation, so queue and revision tracking stay single-writer.

**Alternatives.** An Explorer-private save path (second writer). Duplicating the guard code (drift).

## 13. Duplicate Plan

**Decisions and rationale.**

- **One transaction, source locked.** `FOR UPDATE` on the source prevents a concurrent mutation between checks and copy, and is released at commit or rollback.
- **Reuse the proven writers.** `PlanRepository.create` fills the non-null legacy float columns exactly as creation does; `save_canonical` writes starting players, gameweeks, lineups and decisions. Passing an empty evaluation plus remapped stored sales copies saved selling prices verbatim and works for plans with shortfalls or blocked decisions (`save_canonical` otherwise raises on an unevaluated new sale).
- **Identity remapping as a pure function.** Slot, ownership and decision identities appear in lineups, boundary players, transfer decisions and `bank_assumptions`; one old-to-new map applied everywhere keeps the copy internally consistent and disjoint from the source. UUIDs per plan are unique by constraint, but `load_canonical` and `Plan.__post_init__` assume plan-local identity, and the client binds edits to `source_decision_id`, so sharing identifiers across plans would be fragile and violates FR-058.
- **Provenance text left verbatim.** Rebased plans store source labels such as `decision:<uuid>@...` referring to decisions removed from that plan; they are never looked up, so rewriting adds risk without benefit.
- **Revision 0, no receipts.** Receipts are keyed `(plan_id, mutation_id)` and tied to revisions; copying them could replay or collide.
- **Pending-edit detection.** Reuse `PlanMutationService._pending`'s resumability test (same base revision, evaluator version and rule fingerprint) so "resumable" has one definition; stale receipts do not block.
- **Names.** Pure rules in `plan_naming` plus `pg_advisory_xact_lock(hashtextextended(base, 0))` before reading family names. No unique index (no schema change); renames remain free-form.
- **No idempotency key** (Q-4). Single-flight client guard, no automatic retry, explicit unknown-outcome message.
- **Round-trip check** inside the transaction guards the persistence mapping.

**Alternatives.** Rebuild the copy from My Team (forbidden by the spec). Copy rows with SQL `INSERT ... SELECT` (bypasses the domain model and the remap, harder to test). Re-evaluate and re-price on copy (not verbatim). A unique constraint on names or a copy-lineage column (schema change, not needed).

## 14. Test data and safety

**Decision.** Integration tests use the existing isolated-schema fixtures on the `_test` database (`planner_session`, `ensure_test_database_url`), including two concurrent sessions for naming. The performance gate generates a synthetic full-season dataset (about 600 players, 20 clubs, one projection run) in an isolated schema; an optional read-only timing run against development data is offered for approval, never mutating it.

**Rationale.** AGENTS.md and constitution VII. Trimmed repository fixture JSON is not representative of pool size.

## 15. Schema and dependencies

**Decision.** No Alembic revision, no new dependency, no new service or container.

**Rationale.** Everything needed is derivable from the canonical tables; advisory locks are built into PostgreSQL 16.
