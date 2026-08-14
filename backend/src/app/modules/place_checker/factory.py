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


def build_postgres_place_checker_pipeline(
    database_url: str,
) -> PlaceCheckerPipeline:
    """Compose the rich PlaceChecker pipeline over the production KG schema."""
    catalog = PostgresPlaceCatalog(database_url)
    search_tool = SearchPlacesTool(catalog)
    gap_source = SearchPlacesGapSource(
        search_tool,
        provider_name=catalog.provider_name,
        source_kind=RetrievalSourceKind.knowledge_graph,
    )
    return PlaceCheckerPipeline(
        context_builder=TripContextBuilder(catalog),
        # Explorer and PlaceChecker share the cloud connection budget. A small
        # bounded resolver pool prevents URL candidates from failing in bursts
        # after Explorer has opened its source/cache pools.
        entity_resolution=EntityResolutionService(search_tool, max_concurrency=4),
        evidence_enrichment=EvidenceEnrichmentService(catalog),
        item_resolution=InputItemResolutionService(
            search_tool,
            metadata_repository=catalog,
        ),
        evaluation=PlaceEvaluationService(),
        targeted_retrieval=TargetedRetrievalService(
            gap_source,
            metadata_repository=catalog,
            verified_target_per_gap=5,
            # Retrieve only for analysis gaps. A broad fixed reserve pool made
            # unrelated KG entities planner-eligible and multiplied latency.
            expand_pool=False,
        ),
        food_selection=FoodRestaurantSelectionService(catalog),
    )
