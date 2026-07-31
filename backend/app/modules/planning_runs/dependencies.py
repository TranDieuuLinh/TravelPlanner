from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.planning_runs.repository import PlanningRunRepository


def get_planning_run_repository(
    db: Annotated[Session, Depends(get_db)],
) -> PlanningRunRepository:
    return PlanningRunRepository(db)
