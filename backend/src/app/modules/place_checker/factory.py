from app.modules.place_checker.adapters.postgres_catalog import PostgresPlaceCatalog
from app.modules.place_checker.adapters.search_places_gap_source import (
    SearchPlacesGapSource,
)
from app.modules.place_checker.enums import RetrievalSourceKind
from app.modules.place_checker.evaluation import PlaceEvaluationService
from app.modules.place_checker.evidence import EvidenceEnrichmentService
from app.modules.place_checker.food_selection import FoodRestaurantSelectionService
from app.modules.place_checker.item_resolution import InputItemResolutionService
from app.modules.place_checker.pipeline import PlaceCheckerPipeline
from app.modules.place_checker.resolution import EntityResolutionService
from app.modules.place_checker.retrieval import TargetedRetrievalService
from app.modules.place_checker.service import TripContextBuilder
from app.shared.tools.search_places import SearchPlacesTool
from app.shared.tools.search_places.ports import ExternalPlaceSearch


def build_postgres_place_checker_pipeline(
    database_url: str,
    *,
    external_place_search: ExternalPlaceSearch | None = None,
) -> PlaceCheckerPipeline:
    """Compose the rich PlaceChecker pipeline over the production KG schema."""
    catalog = PostgresPlaceCatalog(database_url)
    search_tool = SearchPlacesTool(catalog, external_place_search)
    gap_source = SearchPlacesGapSource(
        search_tool,
        provider_name=catalog.provider_name,
        source_kind=RetrievalSourceKind.knowledge_graph,
        max_anchor_queries=1,
    )
    external_gap_source = (
        SearchPlacesGapSource(
            search_tool,
            provider_name=external_place_search.provider_name,
            source_kind=RetrievalSourceKind.external,
            max_anchor_queries=1,
        )
        if external_place_search is not None
        else None
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
        targeted_retrieval=TargetedRetrievalService(
            gap_source,
            external_sources=(
                [external_gap_source] if external_gap_source is not None else []
            ),
            metadata_repository=catalog,
            verified_target_per_gap=5,
            # Bound browser-backed fallbacks per PlaceChecker request. This is
            # separate from the global concurrency limit of two searches.
            external_call_budget=2,
            # Fill the activity reserve from independent theme/style queries
            # instead of letting the generic TravelPlace ranking dominate it.
            expand_pool=True,
            # Keep independent TravelPlace and Restaurant pools for Planner.
            ensure_core_pools=True,
        ),
        food_selection=FoodRestaurantSelectionService(catalog),
    )


def build_postgres_place_search_tool(
    database_url: str,
) -> tuple[SearchPlacesTool, PostgresPlaceCatalog]:
    """Build the read-only search used by manual itinerary additions."""
    catalog = PostgresPlaceCatalog(database_url)
    return SearchPlacesTool(catalog), catalog
