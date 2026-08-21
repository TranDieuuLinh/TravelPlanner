from app.modules.explorer.public import YamlTagCatalog
from app.modules.place_checker.adapters.postgres_catalog import PostgresPlaceCatalog
from app.modules.place_checker.adapters.search_places_gap_source import (
    SearchPlacesGapSource,
)
from app.modules.place_checker.enums import RetrievalSourceKind
from app.modules.place_checker.evaluation.service import PlaceEvaluationService
from app.modules.place_checker.pipeline import PlaceCheckerPipeline
from app.modules.place_checker.resolution.enrichment import EvidenceEnrichmentService
from app.modules.place_checker.resolution.item_service import InputItemResolutionService
from app.modules.place_checker.resolution.service import EntityResolutionService
from app.modules.place_checker.retrieval.service import TargetedRetrievalService
from app.modules.place_checker.scoring.service import CandidateScoringService
from app.modules.place_checker.selection.food.service import (
    FoodRestaurantSelectionService,
)
from app.modules.place_checker.service import TripContextBuilder
from app.shared.tools.search_places import SearchPlacesTool
from app.shared.tools.search_places.ports import ExternalPlaceSearch


def build_postgres_place_checker_pipeline(
    database_url: str,
    *,
    external_place_search: ExternalPlaceSearch | None = None,
) -> PlaceCheckerPipeline:
    """Compose the rich PlaceChecker pipeline over the production KG schema."""
    tag_catalog = YamlTagCatalog()
    catalog = PostgresPlaceCatalog(
        database_url,
        tag_filter=tag_catalog.resolve,
    )
    search_tool = SearchPlacesTool(catalog, external_place_search)
    gap_source = SearchPlacesGapSource(
        search_tool,
        provider_name=catalog.provider_name,
        source_kind=RetrievalSourceKind.knowledge_graph,
        max_anchor_queries=1,
    )
    return PlaceCheckerPipeline(
        context_builder=TripContextBuilder(catalog),
        # Explorer and PlaceChecker share the cloud connection budget. Keep at
        # most two named-place resolutions in flight so external fallbacks do
        # not open a burst of Playwright browsers or database queries.
        entity_resolution=EntityResolutionService(search_tool, max_concurrency=2),
        evidence_enrichment=EvidenceEnrichmentService(catalog),
        item_resolution=InputItemResolutionService(
            search_tool,
            metadata_repository=catalog,
        ),
        evaluation=PlaceEvaluationService(),
        scoring=CandidateScoringService(
            allowed_tags_provider=lambda: tag_catalog.definitions().keys()
        ),
        targeted_retrieval=TargetedRetrievalService(
            gap_source,
            metadata_repository=catalog,
            verified_target_per_gap=5,
            external_call_budget=0,
            # Add one catalog query for each deficient optional entity pool.
            expand_pool=True,
            # Keep TravelPlace and Accommodation targets independent as well.
            ensure_core_pools=True,
        ),
        food_selection=FoodRestaurantSelectionService(catalog),
    )


def build_postgres_place_search_tool(
    database_url: str,
) -> tuple[SearchPlacesTool, PostgresPlaceCatalog]:
    """Build the read-only search used by manual itinerary additions."""
    tag_catalog = YamlTagCatalog()
    catalog = PostgresPlaceCatalog(
        database_url,
        tag_filter=tag_catalog.resolve,
    )
    return SearchPlacesTool(catalog), catalog
