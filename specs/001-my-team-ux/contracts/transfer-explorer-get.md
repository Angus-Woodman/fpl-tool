# Contract: `GET /my-team/transfers/{player_out_id}` (Transfer Explorer)

This endpoint and `GET /my-team/transfers/{id}/preview` (see
[transfer-preview-get.md](./transfer-preview-get.md)) are the two API
contract changes for this feature. `GET /my-team` and
`POST /my-team/transfers/{id}/apply` are **unchanged**.

## Change

`candidates[]` (`RankedTransferCandidateResponse`) gains two fields.
Candidates that fail a transfer-legality constraint are now included in the
response instead of being omitted — and keep their full comparison data
(`resulting_bank`, `team_gain_by_horizon`, `direct_xpts_difference`,
`gameweeks_evaluated`), since `evaluate_single_transfer` already computes
these regardless of legality for in-pool (same-position, not-owned)
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
// Legal candidate: identical shape, plus is_legal/unavailable_reasons.
{
  "player_id": 123,
  "web_name": "Example",
  "team_short_name": "EXA",
  "price": 8.5,
  "resulting_bank": 1.2,
  "team_gain_by_horizon": { "1": 0.3, "3": 0.9, "5": 1.4 },
  "direct_xpts_difference": 0.4,
  "gameweeks_evaluated": 5,
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
  "is_legal": false,
  "unavailable_reasons": ["insufficient_bank"]
}
```


## Backward compatibility

- `is_legal` and `unavailable_reasons` are additive; existing consumers that
  ignore unknown fields are unaffected other than now receiving more rows in
  `candidates[]`.
- `resulting_bank`, `team_gain_by_horizon`, `direct_xpts_difference`, and
  `gameweeks_evaluated` keep their existing types and are always present,
  exactly as today — they are **not** made nullable (see
  [research.md](../research.md), decision 1).
- `candidates[].length` can now be larger than before for the same request,
  since previously-filtered candidates are included.
- Sort order: a single key across the whole pool — descending
  `team_gain_by_horizon[primary_horizon]`, `player_id` tie-break — applied
  uniformly to legal and illegal candidates alike (see
  [research.md](../research.md), decision 2); no segregation by legality.
