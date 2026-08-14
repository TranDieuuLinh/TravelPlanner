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
]


def create_checkpointer() -> InMemorySaver:
    """Development checkpointer; replace this provider for production storage."""
    serializer = JsonPlusSerializer(allowed_msgpack_modules=_ALLOWED_MSGPACK_TYPES)
    return InMemorySaver(serde=serializer)
