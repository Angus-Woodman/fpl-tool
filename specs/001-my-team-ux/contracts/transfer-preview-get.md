# Contract: `GET /my-team/transfers/{player_out_id}/preview` (Transfer Preview)

## Change

A new rejection case is added **before** legality evaluation: if
`player_in_id` is not in the candidate pool for `player_out_id` (different
position than the outgoing player, or already in the squad), the endpoint
now returns the same style of response already used for
`player_not_found`/`player_not_in_squad`, rather than evaluating the
transfer at all. The success/`ready` response schema (`TransferPreviewResponse`,
including `is_legal`/`errors`) is **unchanged**.

### New case: out-of-pool candidate

```jsonc
// 404, same shape as today's player_not_found case
{
  "detail": {
    "code": "player_not_in_candidate_pool",
    "message": "Player 789 is not a valid replacement candidate for player 123"
  }
}
```

### Unchanged case: in-pool candidate that fails a legality constraint

Still returns a normal, `ready` preview — Transfer Preview remains reachable
and informative for these, only Apply stays disabled:

```jsonc
{
  "is_legal": false,
  "errors": ["insufficient_bank"],
  "resulting_bank": -2.5,
  "...": "unchanged otherwise"
}
```

`errors` continues to carry raw codes; `apps/web` renders them through the
same shared legality-reason mapping used by Transfer Explorer (see
[data-model.md](../data-model.md)), instead of joining the raw codes
directly as it does today.

## Backward compatibility

- Additive rejection case only; no field on the existing `ready`/`error`
  response shapes changes.
- A caller that previously received a `ready`-but-illegal preview for an
  out-of-pool player (today's behaviour, not spec-compliant) will now
  receive this rejection instead — this is an intentional, in-scope
  behaviour change required by FR-013/FR-017, not a regression.
