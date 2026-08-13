from collections.abc import Mapping

STATUS_FALLBACK_MULTIPLIERS: Mapping[str, float] = {
    "a": 1.0,
    "d": 0.75,
    "i": 0.0,
    "u": 0.0,
    "s": 0.0,
}
UNRECOGNISED_STATUS_MULTIPLIER = 0.85


def availability_multiplier(*, status: str, chance_of_playing_next_round: int | None) -> float:
    """A player's current-week availability, separate from their underlying role.

    `chance_of_playing_next_round`, when FPL supplies it, already reflects `status`
    (verified: every non-'a' status in live data carries a populated, consistent
    chance value). Multiplying the two would double-count the same information, so
    `status` is used only as a fallback when no chance value is present.
    """
    if chance_of_playing_next_round is not None:
        return chance_of_playing_next_round / 100

    return STATUS_FALLBACK_MULTIPLIERS.get(status, UNRECOGNISED_STATUS_MULTIPLIER)
