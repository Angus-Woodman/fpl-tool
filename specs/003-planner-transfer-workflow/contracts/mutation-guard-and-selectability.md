# Mutation Guard and Selectability Contract

Additive changes to the existing `POST /plans/{plan_id}/mutations` contract from Planner Foundations ([planner-api.md](../../002-planner-foundations/contracts/planner-api.md)). Envelope, revision, retry identity, receipts, outcomes and the single-writer rule are unchanged.

## Intent additions

`add_transfer` and `edit_transfer` accept two optional fields. Both or neither; each a positive integer tenths (<= existing `MAX_PRICE_TENTHS`); unknown combinations are schema 422.

| Field | Meaning |
|---|---|
| `expected_outgoing_market_tenths` | the outgoing player's latest market price the user previewed (for `edit_transfer`: the price of the decision's outgoing player) |
| `expected_incoming_price_tenths` | the incoming player's latest market price the user previewed |

Rules:

- The guard is **compare-only**. The saved transfer always uses the prices the server captures itself; browser values are never stored and never used to compute money (the 002 rule against browser-authored quotes stands).
- If either captured price differs from its expected value, the whole mutation is rejected before any receipt is created.
- The guard is part of the immutable envelope and therefore of the digest. A retry of the same `mutation_id` resumes from the stored receipt and does not re-run the comparison (prices were captured at acceptance).
- Callers that send no guard (the existing inline picker) behave exactly as today.

### Rejection

HTTP 422, body `PlannerErrorResponse` with `code: "prices_changed"`, `message`, and `diagnostics: [ { code: "prices_changed", message, gameweek_number, player_id } ]`. No plan change, no receipt. The coordinator treats it as a rejection (previous accepted state kept). The Explorer responds by fetching a fresh preview; it never resubmits automatically.

## Selectability rule

Applied inside the shared mutation path (`_capture`), so it covers the Explorer and the existing inline picker:

| Intent | Checked |
|---|---|
| `add_transfer` | incoming player |
| `edit_transfer` that changes `incoming_player_id` | the new incoming player |
| `edit_transfer` that leaves the incoming player unchanged | not checked |
| replay of saved decisions (GET, other mutations) | never checked |

Source of truth: the imported `can_select` and `can_transact` flags through the pure `incoming_selectability_exclusion` rule (same precedence as My Team: known non-selectable, then unknown).

Rejections (HTTP 422, `diagnostics` populated):

| `code` | Meaning |
|---|---|
| `player_not_selectable` | either flag is false |
| `selectability_unknown` | a flag is missing; message says a data refresh is required |

Playing status (injury, doubt, suspension) is never a reason.

## Compatibility

- Old clients (no guard) and saved receipts decode unchanged. Pending receipts store operations (captured prices), not the guard.
- The guard schema fields are optional, so existing contract and router tests pass unmodified; new cases cover guard, mismatch, both-or-neither, selectability and digest.
