# Contract: `GET /my-team/transfers/{player_out_id}/preview` (Transfer Preview)

## Change

A new rejection case is added **before** projections are loaded and before
legality evaluation: if `player_in_id` is not in the candidate pool for
`player_out_id` (different position, owned, or upstream incoming flags not
both explicitly true — decided by the shared `fpl_engine` helper, not
by logic in `apps/api`; see [research.md](../research.md), decision 4), the
endpoint returns a structured failure rather than evaluating the transfer.
The success/`ready` response gains `player_in_status: string`; all existing
fields, including `is_legal`/`errors`, keep their types and semantics.
The incoming flags are `can_select` and `can_transact` (see research
decision 10). `status` is advisory, not a pool input or legality reason.
An injured/doubtful/suspended player with both flags true is previewable
and applicable if otherwise legal. Existing projections remain unchanged.

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

If eligibility is unknown rather than explicitly false, use the same 422
`player_not_in_candidate_pool` shape with a message explaining that FPL
player data must be refreshed. Do not infer eligibility from status.

### Unchanged case: in-pool candidate that fails a legality constraint

Still returns a normal, `ready` preview — Transfer Preview remains reachable
and informative for these, only Apply stays disabled:

```jsonc
{
  "player_in_status": "i",
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

Display `player_in_status` with the same advisory mapping as candidate
`status`, separately from legality messages. Unknown status codes never
disable Apply. Eligible status-only warnings do not enter `errors`.

## Apply Eligibility Recheck

`POST /my-team/transfers/{player_out_id}/apply` retains its request and
success schemas. Resolve current incoming flags and run the shared pool
helper before projections/evaluation/save. Reject a known non-selectable
or unknown incoming player even if a previous Preview was legal, using
the existing HTTP 422 Apply failure shape and no write:

```json
{
  "detail": {
    "code": "transfer_illegal",
    "message": "This player cannot currently be selected as an incoming transfer.",
    "missing_player_ids": [],
    "errors": ["player_not_selectable"]
  }
}
```

Unknown flags use `errors: ["selectability_unknown"]` and a refresh-required
message. Wrong-position/owned incoming players also fail the shared helper
before evaluation; their failure remains `transfer_illegal` (position
exclusion may now be the specific `different_position` code). An owned
outgoing player need not pass incoming-selectability checks to be sold.
Otherwise legal candidates may Apply regardless of playing status. This
revalidates the latest imported data, not a live upstream transaction.

## Backward compatibility

- Additive advisory field and early eligibility rejection; no existing
  response field changes type or meaning.
- A caller that previously received a `ready`-but-illegal preview for an
  out-of-pool player (today's behaviour, not spec-compliant) will now
  receive this rejection instead — this is an intentional, in-scope
  behaviour change required by FR-013/FR-017, not a regression.
