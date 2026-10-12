# Contract: `GET /my-team/transfers/{player_out_id}/preview` (Transfer Preview)

## Change

A new rejection case is added **before** projections are loaded and before
legality evaluation: if `player_in_id` is not in the candidate pool for
`player_out_id` (different position than the outgoing player, or already in
the squad — decided by the shared `fpl_engine` pool-eligibility helper, not
by logic in `apps/api`; see [research.md](../research.md), decision 4), the
endpoint returns a structured failure rather than evaluating the transfer.
The success/`ready` response schema (`TransferPreviewResponse`, including
`is_legal`/`errors`) is **unchanged**.

Whether a candidate's availability status (`status != "a"`) should also be
out-of-pool is an **open decision** and is not specified here — see
[research.md](../research.md), decision 10.

### New case: out-of-pool candidate

The router already returns 422 for every failure code other than
`player_not_found` (as it does today for `player_not_in_squad` and
`missing_projections`), so this case needs no router change and the
frontend's existing `unavailable` preview state already displays `message`:

```jsonc
// 422, same shape as today's other TransferPreviewFailure cases
{
  "detail": {
    "code": "player_not_in_candidate_pool",
    "message": "Player 789 is not a valid replacement candidate for player 123",
    "missing_player_ids": []
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
