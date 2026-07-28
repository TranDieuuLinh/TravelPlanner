from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.integrations.llm.factory import get_llm_client
from app.modules.places.auto_statistics.service import AutoPlaceStatisticsService
from app.modules.places.repository import SqlAlchemyPlaceRepository
from app.modules.plans.checks.backup_validator import BackupValidator
from app.modules.plans.checks.overall_checker import OverallChecker
from app.modules.plans.explorer.explorer_service import ExplorerService
from app.modules.plans.explorer.response_formatter import ExploreResponseFormatter
from app.modules.plans.finder.finder_service import FinderService
from app.modules.plans.planner.planner_service import PlannerService
from app.modules.plans.repository import PlanRepository
from app.modules.plans.service import PlanService
from app.modules.plans.workflows.backup_plan_workflow import BackupPlanWorkflow
from app.modules.plans.workflows.main_plan_workflow import MainPlanWorkflow


def get_plan_service(
    db: Annotated[Session, Depends(get_db)],
) -> PlanService:
    project_dir = Path(__file__).resolve().parents[4]
    statistics = AutoPlaceStatisticsService(
        SqlAlchemyPlaceRepository(db),
        project_dir / "database" / "generated" / "place_region_statistics.json",
    )
    planner = PlannerService(get_llm_client(), statistics)
    finder = FinderService()
    main_workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=planner,
        finder=finder,
        checker=OverallChecker(),
    )
    backup_workflow = BackupPlanWorkflow(
        planner=planner,
        finder=finder,
        validator=BackupValidator(),
    )
    return PlanService(
        repository=PlanRepository(),
        explore_formatter=ExploreResponseFormatter(llm_client),
        main_workflow=main_workflow,
        backup_workflow=backup_workflow,
    )
