import logging

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


# Root graph state contains validated domain models, not services or secrets.
# Keep the checkpoint deserializer explicit so strict MsgPack mode can restore
# a thread without permitting arbitrary application classes.
_ALLOWED_MSGPACK_TYPES = [
    ("app.modules.conversation_memory.contract", name)
    for name in ("WorkingMemoryState", "MemoryReference", "MemoryFact", "FactProvenance")
] + [
    ("app.modules.supervisor.contract", "SupervisorDecision"),
    ("app.modules.information_finder.contract", "InformationFinderOutput"),
    ("app.modules.explorer.contract", "ExplorerOutput"),
    ("app.shared.contracts.trip", "TripIntent"),
    ("app.modules.place_checker.contract", "PlaceCheckerOutput"),
    ("app.modules.place_checker.output_contract", "PlaceCheckerResult"),
    ("app.modules.itinerary_planner.contract", "ItineraryPlannerInput"),
    ("app.modules.itinerary_planner.contract", "ItineraryPlannerOutput"),
] + [
    ("app.modules.place_checker.enums", name)
    for name in (
        "PlaceLifecycleState", "VerificationStatus", "SourceTier",
        "IssueSeverity", "PlaceCheckerStatus", "EvidenceOrigin",
        "AdmResolutionStatus", "BudgetMode", "TravelPace",
        "IdentityResolutionStatus", "SimilarityMethod", "OperationalStatus",
        "CostTier", "ItemResolutionStatus", "EvaluationDimension",
        "BudgetAssessmentStatus", "CapacityLoadStatus", "CoverageLevel",
        "GeographicSpread", "GapType", "GapStatus", "RetrievalSourceKind",
        "PromotionEventStatus", "UnresolvedEntityType",
    )
]


def create_checkpointer(database_url: str | None = None):
    """Create a durable saver when configured, otherwise use development memory."""
    serializer = JsonPlusSerializer(allowed_msgpack_modules=_ALLOWED_MSGPACK_TYPES)
    if database_url:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # noqa: F401
        except ImportError:
            logging.warning(
                "Postgres checkpointer dependency is unavailable; using InMemorySaver."
            )
            return InMemorySaver(serde=serializer)
        from app.shared.persistence.postgres_checkpointer import (
            LazyAsyncPostgresCheckpointer,
        )

        logging.info("Using lazy PostgreSQL LangGraph checkpointer.")
        return LazyAsyncPostgresCheckpointer(database_url, serde=serializer)
    logging.warning("Using InMemorySaver; LangGraph state is not durable.")
    return InMemorySaver(serde=serializer)
