from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from api.core.settings import get_settings
from api.models.entities import PlanModel
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
from api.services.initialize_planner_foundations import InitializePlannerFoundationsService
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check or explicitly initialize Planner foundations"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    engine = create_engine(get_settings().database_url)
    try:
        with Session(engine) as session:
            identifiers = list(session.scalars(select(PlanModel.id).order_by(PlanModel.id)))
            session.rollback()
            service = InitializePlannerFoundationsService(
                session, SquadPlayerLookupRepository(session)
            )
            reports = [service.execute(identifier, apply=args.apply) for identifier in identifiers]
            print(json.dumps([asdict(report) for report in reports], indent=2))
            if any(report.status == "legacy_pending" for report in reports):
                raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
