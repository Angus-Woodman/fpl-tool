from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.models import PlayerModel, TeamModel


@dataclass(frozen=True)
class PlayerReadItem:
    id: int
    web_name: str
    first_name: str
    second_name: str
    team_name: str
    team_short_name: str
    position: str
    current_price: float
    status: str


@dataclass(frozen=True)
class PlayerQuery:
    search: str | None
    position: str | None
    team_id: int | None
    status: str | None
    sort: str
    page: int
    page_size: int


@dataclass(frozen=True)
class PlayerQueryResult:
    items: list[PlayerReadItem]
    total: int
    page: int
    page_size: int


class PlayerReadRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_players(self, query: PlayerQuery) -> PlayerQueryResult:
        base = (
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
            )
            .join(TeamModel, TeamModel.id == PlayerModel.team_id)
        )

        count_stmt = select(func.count()).select_from(PlayerModel).join(
            TeamModel, TeamModel.id == PlayerModel.team_id
        )

        if query.search:
            like_term = f"%{query.search}%"
            search_filter = (
                PlayerModel.web_name.ilike(like_term)
                | PlayerModel.first_name.ilike(like_term)
                | PlayerModel.second_name.ilike(like_term)
            )
            base = base.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        if query.position:
            base = base.where(PlayerModel.position == query.position)
            count_stmt = count_stmt.where(PlayerModel.position == query.position)

        if query.team_id:
            base = base.where(PlayerModel.team_id == query.team_id)
            count_stmt = count_stmt.where(PlayerModel.team_id == query.team_id)

        if query.status:
            base = base.where(PlayerModel.status == query.status)
            count_stmt = count_stmt.where(PlayerModel.status == query.status)

        if query.sort == "price_desc":
            base = base.order_by(PlayerModel.current_price.desc())
        elif query.sort == "price_asc":
            base = base.order_by(PlayerModel.current_price.asc())
        else:
            base = base.order_by(PlayerModel.web_name.asc())

        offset = (query.page - 1) * query.page_size
        rows = self._session.execute(base.offset(offset).limit(query.page_size)).all()

        total = self._session.execute(count_stmt).scalar_one()

        items = [
            PlayerReadItem(
                id=row[0],
                web_name=row[1],
                first_name=row[2],
                second_name=row[3],
                team_name=row[4],
                team_short_name=row[5],
                position=row[6].value if hasattr(row[6], "value") else str(row[6]),
                current_price=float(row[7]),
                status=row[8],
            )
            for row in rows
        ]

        return PlayerQueryResult(
            items=items,
            total=total,
            page=query.page,
            page_size=query.page_size,
        )
