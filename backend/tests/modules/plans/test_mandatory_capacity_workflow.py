from app.modules.plans.dto.agent_contracts import PlaceSelectionInput
from app.modules.plans.itinerary_optimizer import RouteFirstItineraryOptimizer
from app.modules.plans.place_selector.place_tool import SelectablePlace
from app.modules.plans.place_selector.service import PlaceSelectorService
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer
from app.modules.plans.solver.candidate_pool import build_selected_place_pool
from app.modules.plans.solver.candidate_pool import selected_place_priority_tier
from app.modules.plans.dto.agent_contracts import SelectedPlaceContext


class _RequiredPlaceTool:
    def get(self, place_id: str):
        if place_id != "required-place":
            return None
        return SelectablePlace(
            placeId=place_id,
            name="Required experience venue",
            placeType="attraction",
            regionKey="vn,ha-noi",
            latitude=21.03,
            longitude=105.84,
        )

    def search(self, **kwargs):
        return []


def test_required_experience_enters_mandatory_pool_before_capacity() -> None:
    selector = PlaceSelectorService(_RequiredPlaceTool())
    planning_input = PlaceSelectionInput.model_validate(
        {
            "intent": {"destination": "Hà Nội"},
            "tripSpec": {"days": 1},
            "regionKey": "vn,ha-noi",
            "selectedPlaces": [
                {
                    "placeId": "source-place",
                    "name": "Source place",
                    "sourceRefs": ["https://example.com/reel"],
                }
            ],
            "requiredExperiences": [
                {
                    "requirementId": "required-experience",
                    "theme": "A characteristic experience",
                    "selectionPolicy": "required_anchor",
                    "anchorPlaceIds": ["required-place"],
                    "minimumRequired": 1,
                    "priority": "must",
                    "reason": "Graph-backed highlight.",
                    "evidenceClaimIds": ["claim-required"],
                    "sourceRefs": ["https://example.com/claim"],
                }
            ],
        }
    )

    prepared, unresolved = selector.prepare_mandatory_candidates(planning_input)
    pool = build_selected_place_pool(list(prepared.selected_places))

    assert unresolved == []
    assert {candidate.candidate_id for candidate in pool.candidates} == {
        "place:source-place",
        "place:required-place",
    }
    assert all(candidate.mandatory for candidate in pool.candidates)
    by_id = {candidate.candidate_id: candidate for candidate in pool.candidates}
    assert by_id["place:source-place"].priority_tier == 1
    assert by_id["place:required-place"].priority_tier == 2


def test_route_first_gap_fill_keeps_small_candidate_pool_per_window() -> None:
    selector = PlaceSelectorService(
        _RequiredPlaceTool(),
        max_candidates_per_block=5,
        route_optimizer=RouteFirstItineraryOptimizer(GeographicRouteOptimizer()),
    )

    assert selector.max_candidates_per_block == 5
    assert selector.candidate_selector.max_candidates_per_block == 5


def test_selected_place_priority_is_user_then_url_then_required() -> None:
    user_place = SelectedPlaceContext(name="User choice", mustVisit=True)
    url_place = SelectedPlaceContext(
        name="URL choice",
        sourceRefs=["https://example.com/reel"],
        sourceOrder=1,
    )
    required_place = SelectedPlaceContext(
        name="Required choice",
        mustVisit=True,
        sourceRefs=["required_experience:req-1", "https://example.com/claim"],
    )

    assert [
        selected_place_priority_tier(place)
        for place in (user_place, url_place, required_place)
    ] == [0, 1, 2]
