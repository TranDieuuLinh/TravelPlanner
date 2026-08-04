from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.planning_runs.repository import PlanningRunRepository
from app.modules.plans.trip_theme_planner.place_repository_adapter import PlaceRepositoryAdapter
from app.modules.plans.trip_theme_planner.research_tools_orchestrator import ResearchToolsOrchestrator


def get_planning_run_repository(
    db: Annotated[Session, Depends(get_db)],
) -> PlanningRunRepository:
    return PlanningRunRepository(db)


def get_research_tools_orchestrator(
    db: Annotated[Session, Depends(get_db)],
) -> ResearchToolsOrchestrator:
    return ResearchToolsOrchestrator(PlaceRepositoryAdapter(db))
