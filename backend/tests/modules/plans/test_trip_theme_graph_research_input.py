from __future__ import annotations

from app.modules.knowledge_graph.research import (
    BudgetLevel as GraphBudgetLevel,
    CheckStatus,
    GraphSnapshot,
    ScopeResolveOutput,
    TransportMode as GraphTransportMode,
    TripResearchBundle,
    TripResearchInput,
)
from app.modules.plans.domain.constraint_policy import ConstraintPolicy
from app.modules.plans.domain.entities import DestinationStay, TravelIntent
from app.modules.plans.domain.enums import BudgetLevel, TravelPace
from app.modules.plans.dto.agent_contracts import (
    PlanningIntent,
    SelectedPlaceContext,
    TransportMode,
    TripPlanningSpec,
)
from app.modules.plans.trip_theme_planner.graph_research import (
    TripThemeGraphResearchService,
    build_trip_research_input,
)
from app.modules.preferences.schema import (
    LongTermPreferenceProfile,
    PreferenceAggregate,
)


def _bundle() -> TripResearchBundle:
    return TripResearchBundle(
        scope=ScopeResolveOutput(),
        graphSnapshot=GraphSnapshot(timestamp="2026-08-04T00:00:00Z"),
    )


def _planning_intent() -> PlanningIntent:
    return PlanningIntent(
        destination="Hà Nội",
        travelStyle="local",
        pace="relaxed",
        interests=["culture"],
        destinationStays=[
            {
                "name": "Hà Nội",
                "durationDays": 2,
                "startDay": 1,
                "endDay": 2,
            }
        ],
        constraints=["avoid long transfers"],
        constraintPolicy=ConstraintPolicy(
            excludedPlaceTypes=["cemetery"],
        ),
    )


def _trip_spec() -> TripPlanningSpec:
    return TripPlanningSpec(
        days=2,
        partySize=3,
        startDate="2026-09-10",
        endDate="2026-09-11",
        budget={
            "level": "high",
            "targetAmount": 12000000,
            "currency": "VND",
        },
        transport={
            "preferredModes": ["walk", "bus"],
            "avoidModes": ["private_car"],
        },
    )


def _profile() -> LongTermPreferenceProfile:
    return LongTermPreferenceProfile(
        explicit=["quiet"],
        scores={
            "category:food": PreferenceAggregate(
                score=0.9,
                confidence=0.8,
            ),
        },
    )


def test_trip_theme_graph_research_input_maps_context_without_private_notes() -> None:
    selected_places = [
        SelectedPlaceContext(
            name="Temple",
            placeId="place-temple",
            personalNotes="Private note must not cross the boundary.",
            notes="Provider context must not cross the boundary.",
        ),
        SelectedPlaceContext(
            name="Unresolved name",
            personalNotes="Another private note.",
        ),
    ]

    result = build_trip_research_input(
        _planning_intent(),
        _trip_spec(),
        selected_places,
        _profile(),
    )

    assert result.destination == "Hà Nội"
    assert result.destinationStays == ["Hà Nội"]
    assert result.selectedPlaceIds == ["place-temple"]
    assert result.interests == ["culture", "quiet", "food"]
    assert result.travelStyle == "local"
    assert result.pace == "relaxed"
    assert result.days == 2
    assert result.partySize == 3
    assert result.startDate == "2026-09-10"
    assert result.endDate == "2026-09-11"
    assert result.budget.level == GraphBudgetLevel.HIGH
    assert result.budget.targetAmount == 12000000
    assert result.budget.currency == "VND"
    assert result.constraints == ["avoid long transfers"]
    assert result.excludedPlaceTypes == ["cemetery"]
    assert result.preferredModes == [
        GraphTransportMode.WALKING,
        GraphTransportMode.PUBLIC_TRANSIT,
    ]
    assert result.avoidModes == [GraphTransportMode.CAR]

    serialized = result.model_dump(mode="json", by_alias=True)
    assert "personalNotes" not in str(serialized)
    assert "Private note" not in str(serialized)
    assert "Provider context" not in str(serialized)


def test_trip_theme_graph_research_input_accepts_travel_intent() -> None:
    intent = TravelIntent(
        destination="Đà Nẵng",
        days=3,
        budget=BudgetLevel.medium,
        travelStyle="local",
        pace=TravelPace.balanced,
        interests=["beach"],
        destinationStays=[
            DestinationStay(
                name="Hội An",
                durationDays=1,
                startDay=3,
                endDay=3,
            )
        ],
    )

    result = build_trip_research_input(intent, TripPlanningSpec(days=3), [])

    assert result.destination == "Đà Nẵng"
    assert result.destinationStays == ["Hội An"]
    assert result.interests == ["beach"]


class _RecordingOrchestrator:
    def __init__(self) -> None:
        self.calls: list[TripResearchInput] = []
        self.bundle = _bundle()

    def research(self, input_data: TripResearchInput) -> TripResearchBundle:
        self.calls.append(input_data)
        return self.bundle


def test_trip_theme_graph_research_service_calls_orchestrator_once() -> None:
    orchestrator = _RecordingOrchestrator()
    service = TripThemeGraphResearchService(orchestrator)

    result = service.research(
        _planning_intent(),
        _trip_spec(),
        [SelectedPlaceContext(name="Temple", placeId="place-temple")],
        _profile(),
    )

    assert result is orchestrator.bundle
    assert len(orchestrator.calls) == 1
    assert orchestrator.calls[0].selectedPlaceIds == ["place-temple"]
    assert orchestrator.calls[0].budget.targetAmount == 12000000
    assert orchestrator.calls[0].preferredModes == [GraphTransportMode.WALKING, GraphTransportMode.PUBLIC_TRANSIT]
    assert orchestrator.calls[0].avoidModes == [GraphTransportMode.CAR]
    assert orchestrator.calls[0].constraints == ["avoid long transfers"]
