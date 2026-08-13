from __future__ import annotations

import calendar
import datetime as dt


def is_established_at_club(
    team_join_date: dt.date | None, *, as_of: dt.date, cutoff_months: int
) -> bool:
    """Whether a player has been at their club long enough for a 38-game opportunity
    denominator (e.g. `starts / 38`) to be defensible.

    Does not detect loans away or mid-season returns; that information isn't
    available, so those cases are simply not treated as established (an accepted
    limitation, not solved). Has no dependency on the rest of fpl_engine, so it can
    be shared by fpl_engine.minutes and fpl_engine.projections without a cycle.
    """
    if team_join_date is None:
        return False

    return team_join_date <= _months_before(as_of, cutoff_months)


def _months_before(date: dt.date, months: int) -> dt.date:
    month_index = date.month - 1 - months
    year = date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(date.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)
