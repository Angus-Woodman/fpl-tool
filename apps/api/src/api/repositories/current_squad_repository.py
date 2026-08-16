from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.models import PlayerModel, SquadModel, SquadPlayerModel, TeamModel


@dataclass(frozen=True)
class CurrentSquadPlayerRecord:
    player_id: int
    web_name: str
    first_name: str
    second_name: str
    team_name: str
    team_short_name: str
    position: str
    current_price: float
    status: str
    is_starting: bool
    bench_order: int | None
    is_captain: bool
    is_vice_captain: bool
    # Needed by the lineup optimiser's club-limit/domain shape, not by any
    # existing consumer -- defaulted so existing fixtures/tests are unaffected.
    team_id: int = 0


@dataclass(frozen=True)
class CurrentSquadRecord:
    squad_id: int
    name: str
    bank: float
    free_transfers: int
    players: list[CurrentSquadPlayerRecord]


@dataclass(frozen=True)
class CurrentSquadPlayerSave:
    player_id: int
    is_starting: bool
    bench_order: int | None
    is_captain: bool
    is_vice_captain: bool


class CurrentSquadRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_current(self) -> CurrentSquadRecord | None:
        squad = self._session.execute(select(SquadModel).limit(1)).scalar_one_or_none()
        if squad is None:
            return None

        rows = self._session.execute(
            select(
                PlayerModel.id,
                PlayerModel.web_name,
                PlayerModel.first_name,
                PlayerModel.second_name,
                TeamModel.name,
                TeamModel.short_name,
                PlayerModel.position,
                PlayerModel.current_price,
                PlayerModel.status,
                SquadPlayerModel.is_starting,
                SquadPlayerModel.bench_order,
                SquadPlayerModel.is_captain,
                SquadPlayerModel.is_vice_captain,
                PlayerModel.team_id,
            )
            .join(SquadPlayerModel, SquadPlayerModel.player_id == PlayerModel.id)
            .join(TeamModel, TeamModel.id == PlayerModel.team_id)
            .where(SquadPlayerModel.squad_id == squad.id)
            .order_by(
                SquadPlayerModel.is_starting.desc(),
                SquadPlayerModel.bench_order.asc().nulls_last(),
                PlayerModel.web_name.asc(),
            )
        ).all()

        players = [
            CurrentSquadPlayerRecord(
                player_id=row[0],
                web_name=row[1],
                first_name=row[2],
                second_name=row[3],
                team_name=row[4],
                team_short_name=row[5],
                position=row[6].value if hasattr(row[6], "value") else str(row[6]),
                current_price=float(row[7]),
                status=row[8],
                is_starting=row[9],
                bench_order=row[10],
                is_captain=row[11],
                is_vice_captain=row[12],
                team_id=row[13],
            )
            for row in rows
        ]

        return CurrentSquadRecord(
            squad_id=squad.id,
            name=squad.name,
            bank=float(squad.bank),
            free_transfers=squad.free_transfers,
            players=players,
        )

    def save_current(
        self,
        *,
        bank: float,
        free_transfers: int,
        players: list[CurrentSquadPlayerSave],
    ) -> CurrentSquadRecord:
        squad = self._session.execute(select(SquadModel).limit(1)).scalar_one_or_none()
        if squad is None:
            squad = SquadModel(name="My Team", bank=bank, free_transfers=free_transfers)
            self._session.add(squad)
            self._session.flush()
        else:
            squad.bank = bank
            squad.free_transfers = free_transfers
            squad.updated_at = dt.datetime.now(dt.UTC)

        self._session.execute(delete(SquadPlayerModel).where(SquadPlayerModel.squad_id == squad.id))

        self._session.add_all(
            [
                SquadPlayerModel(
                    squad_id=squad.id,
                    player_id=player.player_id,
                    is_starting=player.is_starting,
                    bench_order=player.bench_order,
                    is_captain=player.is_captain,
                    is_vice_captain=player.is_vice_captain,
                )
                for player in players
            ]
        )
        self._session.flush()

        record = self.get_current()
        if record is None:
            raise RuntimeError("Failed to reload current squad after save")

        return record
