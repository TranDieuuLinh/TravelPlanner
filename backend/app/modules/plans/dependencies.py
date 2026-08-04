from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.session import get_db
from app.integrations.llm.factory import get_llm_client, get_ocr_llm_client
from app.integrations.routing import (
    OpenTripPlannerTransitProvider,
    ValhallaRouteProvider,
    ValhallaTravelTimeMatrixProvider,
)
from app.modules.places.auto_statistics.service import AutoPlaceStatisticsService
from app.modules.places.resolver import (
    DatabasePlaceResolver,
    FallbackPlaceResolver,
    GoogleMapsScraperPlaceResolver,
    GoogleMapsSearchClient,
    PlaceResolver,
    ProvisionalPlaceResolver,
)
from app.modules.places.alias_enricher import LLMPlaceAliasEnricher
from app.modules.places.repository import SqlAlchemyPlaceRepository
from app.modules.planning_runs.repository import PlanningRunRepository
from app.modules.plans.checks.backup_validator import BackupValidator
from app.modules.plans.explorer.explorer_service import ExplorerService
from app.modules.plans.explorer.response_formatter import ExploreResponseFormatter
from app.modules.plans.explorer.repository import ExplorerPersistenceRepository
from app.modules.plans.explorer.tools.image_ocr import ImageOcrService
from app.modules.plans.explorer.tools.url_reels.caption_structurer import (
    GeminiCaptionStructurer,
)
from app.modules.plans.explorer.tools.url_reels.service import UrlReelExtractionService
from app.modules.plans.explorer.tools.url_reels.transcript_cache import (
    SqlAlchemyYouTubeTranscriptCache,
)
from app.modules.plans.explorer.tools.url_reels.transcript_worker import (
    HttpYouTubeTranscriptWorker,
)
from app.modules.plans.explorer.tools.url_reels.youtube_transcript import (
    YouTubeTranscriptExtractor,
)
from app.modules.plans.explorer.timing import ExplorerTimingLogger
from app.modules.plans.place_selector.place_tool import RepositoryPlaceSelectionTool
from app.modules.plans.itinerary_optimizer import RouteFirstItineraryOptimizer
from app.modules.plans.place_selector import PlaceSelectorService
from app.modules.plans.trip_theme_planner.place_repository_adapter import PlaceRepositoryAdapter
from app.modules.plans.trip_theme_planner import TripThemePlannerService
from app.modules.plans.trip_theme_planner.research_tool import (
    RepositoryPlannerResearchTool,
)
from app.modules.plans.trip_theme_planner.research_tools_orchestrator import (
    ResearchToolsOrchestrator,
)
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer
from app.modules.plans.checks.overall_checker import OverallChecker
from app.modules.plans.plan_mutation_service import PlanMutationService
from app.modules.plans.routing.current_location_service import (
    CurrentLocationRouteService,
)
from app.modules.plans.repository import PlanRepository
from app.modules.plans.service import PlanService
from app.modules.plans.workflows.backup_plan_workflow import BackupPlanWorkflow
from app.modules.plans.workflows.main_plan_workflow import MainPlanWorkflow
from app.modules.preferences.service import PreferenceLearningService
from app.modules.users.repository import UserRepository


def get_plan_mutation_service(
    db: Annotated[Session, Depends(get_db)],
) -> PlanMutationService:
    place_repository = SqlAlchemyPlaceRepository(db)
    return PlanMutationService(
        place_resolver=_get_place_resolver(place_repository),
        place_repository=place_repository,
        route_optimizer=_get_route_optimizer(),
        checker=OverallChecker(),
        gmaps_client=_get_gmaps_search_client(),
    )


def _get_gmaps_search_client() -> GoogleMapsSearchClient | None:
    """Get Google Maps search client for autocomplete fallback."""
    if (
        settings.google_maps_scraper_executable
        or settings.google_maps_scraper_work_dir is not None
    ):
        return GoogleMapsSearchClient(
            executable=settings.google_maps_scraper_executable,
            work_dir=settings.google_maps_scraper_work_dir,
            timeout_seconds=settings.google_maps_scraper_timeout_seconds,
        )
    return None


def get_conversation_turn_service(
    db: Annotated[Session, Depends(get_db)],
) -> "ConversationTurnService":
    """Build a ConversationTurnService scoped to the current request's DB
    session. The supervisor uses the same LLM client as the rest of the
    planner so quota, rate limiting, and stub fallbacks stay unified."""
    # Late imports avoid a circular dependency: conversation_service imports
    # from app.modules.plans.router, which itself depends on this module.
    from app.modules.plans.chat_repository import TripChatRepository
    from app.modules.plans.chat_service import TripChatService
    from app.modules.plans.conversation_service import ConversationTurnService
    from app.modules.plans.conversation_supervisor import (
        ConstrainedConversationSupervisor,
    )

    repository = TripChatRepository(db)
    plan_service = get_plan_service(db)
    trip_chat_service = TripChatService(
        repository,
        plan_service,
        get_plan_mutation_service(db),
        SqlAlchemyPlaceRepository(db),
    )
    supervisor = ConstrainedConversationSupervisor(get_llm_client())
    return ConversationTurnService(
        repository=repository,
        trip_chat_service=trip_chat_service,
        mutation_service=get_plan_mutation_service(db),
        supervisor=supervisor,
    )



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
    planning_runs = PlanningRunRepository(db)
    research_tools = ResearchToolsOrchestrator(PlaceRepositoryAdapter(db))
    transcript_worker = (
        HttpYouTubeTranscriptWorker(
            base_url=settings.youtube_transcript_worker_url,
            token=settings.youtube_transcript_worker_token,
            timeout_seconds=(
                settings.youtube_transcript_worker_timeout_seconds
            ),
        )
        if (
            settings.youtube_transcript_worker_url
            and settings.youtube_transcript_worker_token
        )
        else None
    )
    transcript_session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db.get_bind(),
    )
    youtube_transcript = YouTubeTranscriptExtractor(
        cache=SqlAlchemyYouTubeTranscriptCache(
            transcript_session_factory
        ),
        worker=transcript_worker,
    )
    trip_theme_planner = TripThemePlannerService(
        statistics,
        llm_client,
        RepositoryPlannerResearchTool(place_repository),
        research_tools=research_tools,
    )
    place_selector = PlaceSelectorService(
        RepositoryPlaceSelectionTool(place_repository),
        route_optimizer=_get_itinerary_optimizer(),
    )
    main_workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=trip_theme_planner,
        place_selector=place_selector,
        planning_runs=planning_runs,
    )
    backup_workflow = BackupPlanWorkflow(
        place_selector=place_selector,
        validator=BackupValidator(),
    )
    return PlanService(
        repository=PlanRepository(),
        explore_formatter=ExploreResponseFormatter(llm_client),
        main_workflow=main_workflow,
        backup_workflow=backup_workflow,
        image_ocr=ImageOcrService(get_ocr_llm_client()),
        url_reels=UrlReelExtractionService(
            youtube_transcript=youtube_transcript,
            caption_structurer=GeminiCaptionStructurer(),
        ),
        place_resolver=_get_place_resolver(place_repository),
        place_alias_enricher=LLMPlaceAliasEnricher(llm_client),
        explorer_persistence=ExplorerPersistenceRepository(db),
        preference_learning=PreferenceLearningService(),
        user_repository=UserRepository(db),
        explorer_timing_logger=ExplorerTimingLogger(
            settings.explorer_timing_log_path
        ),
        planning_runs=planning_runs,
    )


def _get_place_resolver(
    place_repository: SqlAlchemyPlaceRepository | None = None,
) -> PlaceResolver:
    if settings.place_resolver_provider == "google_maps_scraper":
        external_resolver: PlaceResolver = ProvisionalPlaceResolver()
        if (
            settings.google_maps_scraper_executable
            or settings.google_maps_scraper_work_dir is not None
        ):
            external_resolver = GoogleMapsScraperPlaceResolver(
                executable=settings.google_maps_scraper_executable,
                work_dir=settings.google_maps_scraper_work_dir,
                timeout_seconds=(
                    settings.google_maps_scraper_timeout_seconds
                ),
                max_alias_queries=(
                    settings.google_maps_scraper_max_alias_queries
                ),
                max_concurrency=(
                    settings.google_maps_scraper_max_concurrency
                ),
            )
        if place_repository is not None:
            return FallbackPlaceResolver(
                DatabasePlaceResolver(
                    place_repository,
                    top_k=settings.database_place_resolver_top_k,
                    minimum_score=(
                        settings.database_place_resolver_minimum_score
                    ),
                    minimum_margin=(
                        settings.database_place_resolver_minimum_margin
                    ),
                ),
                external_resolver,
                verified_alias_repository=place_repository,
            )
        return external_resolver
    return ProvisionalPlaceResolver()


def _get_route_optimizer() -> GeographicRouteOptimizer:
    if settings.route_provider == "valhalla":
        return GeographicRouteOptimizer(
            ValhallaRouteProvider(
                base_url=settings.valhalla_base_url,
                timeout_seconds=settings.valhalla_timeout_seconds,
                min_interval_seconds=(
                    settings.valhalla_min_interval_seconds
                ),
            ),
            OpenTripPlannerTransitProvider(
                base_url=settings.opentripplanner_base_url,
                timeout_seconds=settings.opentripplanner_timeout_seconds,
                schedule_status=settings.opentripplanner_schedule_status,
            ),
            ValhallaTravelTimeMatrixProvider(
                base_url=settings.valhalla_base_url,
                timeout_seconds=settings.valhalla_timeout_seconds,
            ),
        )
    return GeographicRouteOptimizer()


def _get_itinerary_optimizer():
    legacy = _get_route_optimizer()
    if settings.itinerary_optimizer_mode == "legacy":
        return legacy
    return RouteFirstItineraryOptimizer(legacy)


def get_current_location_route_service() -> CurrentLocationRouteService:
    return CurrentLocationRouteService(_get_route_optimizer())
