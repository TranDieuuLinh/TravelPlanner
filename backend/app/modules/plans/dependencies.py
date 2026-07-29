from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.integrations.llm.factory import get_llm_client
from app.modules.places.auto_statistics.service import AutoPlaceStatisticsService
from app.modules.places.resolver import (
    NominatimPlaceResolver,
    PlaceResolver,
    ProvisionalPlaceResolver,
)
from app.modules.places.repository import SqlAlchemyPlaceRepository
from app.modules.plans.checks.backup_validator import BackupValidator
from app.modules.plans.explorer.explorer_service import ExplorerService
from app.modules.plans.explorer.response_formatter import ExploreResponseFormatter
from app.modules.plans.explorer.repository import ExplorerPersistenceRepository
from app.modules.plans.explorer.tools.image_ocr import ImageOcrService
from app.modules.plans.explorer.tools.url_reels.service import UrlReelExtractionService
from app.modules.plans.finder.finder_service import FinderService
from app.modules.plans.finder.place_tool import RepositoryFinderPlaceTool
from app.modules.plans.planner.planner_service import PlannerService
from app.modules.plans.planner.research_tool import (
    RepositoryPlannerResearchTool,
)
from app.modules.plans.repository import PlanRepository
from app.modules.plans.service import PlanService
from app.modules.plans.workflows.backup_plan_workflow import BackupPlanWorkflow
from app.modules.plans.workflows.main_plan_workflow import MainPlanWorkflow
from app.modules.preferences.service import PreferenceLearningService
from app.modules.users.repository import UserRepository


def get_plan_service(
    db: Annotated[Session, Depends(get_db)],
) -> PlanService:
    project_dir = Path(__file__).resolve().parents[4]
    place_repository = SqlAlchemyPlaceRepository(db)
    statistics = AutoPlaceStatisticsService(
        place_repository,
        project_dir / "database" / "generated" / "place_region_statistics.json",
    )
    llm_client = get_llm_client()
    planner = PlannerService(
        statistics,
        llm_client,
        RepositoryPlannerResearchTool(place_repository),
    )
    finder = FinderService(RepositoryFinderPlaceTool(place_repository))
    main_workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=planner,
        finder=finder,
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
        image_ocr=ImageOcrService(llm_client),
        url_reels=UrlReelExtractionService(),
        place_resolver=_get_place_resolver(),
        explorer_persistence=ExplorerPersistenceRepository(db),
        preference_learning=PreferenceLearningService(),
        user_repository=UserRepository(db),
    )


def _get_place_resolver() -> PlaceResolver:
    if settings.place_resolver_provider == "nominatim":
        return NominatimPlaceResolver(
            base_url=settings.nominatim_base_url,
            user_agent=settings.nominatim_user_agent,
            timeout_seconds=settings.nominatim_timeout_seconds,
            min_interval_seconds=settings.nominatim_min_interval_seconds,
        )
    return ProvisionalPlaceResolver()
