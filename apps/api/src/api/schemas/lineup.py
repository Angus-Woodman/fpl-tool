from typing import Literal

from pydantic import BaseModel


class LineupRearrangementResponse(BaseModel):
    first_player_id: int
    second_player_id: int
    kind: Literal["substitution", "bench_priority"]
