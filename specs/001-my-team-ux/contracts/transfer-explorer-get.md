# Contract: `GET /my-team/transfers/{player_out_id}` (Transfer Explorer)

This endpoint and Preview (see
[transfer-preview-get.md](./transfer-preview-get.md)) gain additive fields
and eligibility behaviour. Apply gains an incoming-eligibility recheck
with unchanged request/success schemas, documented in the same contract.
`GET /my-team` is unchanged.

## Change

`candidates[]` (`RankedTransferCandidateResponse`) gains three fields:
`is_legal`, `unavailable_reasons`, and advisory `status: string`.
Candidates that fail a transfer-legality constraint are now included in the
response instead of being omitted — and keep their full comparison data
(`resulting_bank`, `team_gain_by_horizon`, `direct_xpts_difference`,
`gameweeks_evaluated`), since `evaluate_single_transfer` already computes
these regardless of legality for in-pool (same-position, not-owned,
`can_select` and `can_transact` both explicitly true)
candidates. This is a purely additive change: no existing field becomes
optional or changes meaning.

### Before

```jsonc
{
  "player_id": 123,
  "web_name": "Example",
  "team_short_name": "EXA",
  "price": 8.5,
  "resulting_bank": 1.2,
  "team_gain_by_horizon": { "1": 0.3, "3": 0.9, "5": 1.4 },
  "direct_xpts_difference": 0.4,
  "gameweeks_evaluated": 5
}
```

### After

```jsonc
// Legal candidate: advisory injury does not disable Preview or Apply.
{
  "player_id": 123,
  "web_name": "Example",
  "team_short_name": "EXA",
  "price": 8.5,
  "resulting_bank": 1.2,
  "team_gain_by_horizon": { "1": 0.3, "3": 0.9, "5": 1.4 },
  "direct_xpts_difference": 0.4,
  "gameweeks_evaluated": 5,
  "status": "i",
  "is_legal": true,
  "unavailable_reasons": []
}

// Unavailable candidate: now included rather than omitted, with the same
// full comparison data as a legal candidate -- only is_legal/
// unavailable_reasons differ. "unavailable_reasons" carries raw codes;
// apps/web maps them to user-facing text via the shared mapping in
// data-model.md -- the API does not return pre-formatted text.
{
  "player_id": 456,
  "web_name": "TooExpensive",
  "team_short_name": "EXP",
  "price": 14.0,
  "resulting_bank": -2.5,
  "team_gain_by_horizon": { "1": 0.6, "3": 1.5, "5": 2.1 },
  "direct_xpts_difference": 0.9,
  "gameweeks_evaluated": 5,
  "status": "a",
  "is_legal": false,
  "unavailable_reasons": ["insufficient_bank"]
}
```


## Pool And Advisory Status

Retrieve same-position profiles without the old `status == "a"` filter;
the shared domain helper excludes owned players and any incoming player
whose upstream flags do not both explicitly permit selection/transaction.
Known non-selectable players are absent and have no Preview. Status is
advisory, mapped to user-facing text in Explorer and Preview; it never
appears in `unavailable_reasons`. Existing availability/minutes projections
and the unified gain sort are unchanged.

For an otherwise relevant profile with unknown flags (and neither
explicitly false), return an explicit refresh-required failure before
projection loading, not a silently truncated/empty pool. Use the existing
HTTP 422 failure shape:

```json
{
  "detail": {
    "code": "selectability_unknown",
    "message": "Refresh FPL player data before exploring these transfers.",
    "missing_player_ids": []
  }
}
```

`missing_player_ids` remains reserved for missing projections; unknown
selectability uses its own code/message. A known false flag excludes the
player without an unknown-data failure, even if the other flag is missing.
Outgoing players are not subject to the incoming flags.

Precedence: structural exclusion (owned, then wrong position), then known
non-selectable, then unknown. The failure fires only for otherwise-relevant profiles
that reach the unknown tier. A bootstrap refresh normally resolves it; if the upstream
source omits the field the diagnostic intentionally persists rather than returning an
incomplete pool.

## Backward compatibility

- `is_legal`, `unavailable_reasons` and `status` are additive; existing consumers that
  ignore unknown fields are unaffected other than now receiving more rows in
  `candidates[]`.
- `resulting_bank`, `team_gain_by_horizon`, `direct_xpts_difference`, and
  `gameweeks_evaluated` keep their existing types and are always present,
  exactly as today — no additional nullability is introduced;
  `direct_xpts_difference` remains `number | null` as before (see
  [research.md](../research.md), decision 1).
- `candidates[].length` can now be larger than before for the same request,
  since previously-filtered candidates are included.
- Sort order: a single key across the whole pool — descending
  `team_gain_by_horizon[primary_horizon]`, `player_id` tie-break — applied
  uniformly to legal and illegal candidates alike (see
  [research.md](../research.md), decision 2); no segregation by legality.
