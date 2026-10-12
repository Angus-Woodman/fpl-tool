# Contract: `GET /my-team/transfers/{player_out_id}` (Transfer Explorer)

This is the only API contract change for this feature. All other endpoints
(`GET /my-team`, `GET /my-team/transfers/{id}/preview`,
`POST /my-team/transfers/{id}/apply`) are **unchanged** — see
[data-model.md](../data-model.md) for why Transfer Preview needs no change.

## Change

`candidates[]` (`RankedTransferCandidateResponse`) gains two fields and
makes four existing fields optional. Candidates that fail a transfer-legality
constraint are now included in the response instead of being omitted.

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
// Legal candidate: same shape as before, plus is_legal/unavailable_reasons.
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

// Unavailable candidate: now included rather than omitted.
{
  "player_id": 456,
  "web_name": "TooExpensive",
  "team_short_name": "EXP",
  "price": 14.0,
  "resulting_bank": null,
  "team_gain_by_horizon": null,
  "direct_xpts_difference": null,
  "gameweeks_evaluated": null,
  "is_legal": false,
  "unavailable_reasons": ["insufficient_bank"]
}
```

## Backward compatibility

- `is_legal` and `unavailable_reasons` are additive; existing consumers that
  ignore unknown fields are unaffected other than now receiving more rows in
  `candidates[]`.
- `resulting_bank`, `team_gain_by_horizon`, `direct_xpts_difference`, and
  `gameweeks_evaluated` become nullable. Any caller currently assuming they
  are always present (the current `apps/web` frontend) must be updated as
  part of this feature — this is expected and in scope.
- `candidates[].length` can now be larger than before for the same request,
  since previously-filtered candidates are included.
- Sort order: legal candidates keep today's order (team gain at the primary
  horizon, descending); illegal candidates are appended after them, sorted
  by `player_id` (see [research.md](../research.md), decision 2).
