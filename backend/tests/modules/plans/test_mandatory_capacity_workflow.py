from app.modules.plans.dto.agent_contracts import PlaceSelectionInput
from app.modules.plans.itinerary_optimizer import RouteFirstItineraryOptimizer
from app.modules.plans.place_selector.place_tool import SelectablePlace
from app.modules.plans.place_selector.service import PlaceSelectorService
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer
from app.modules.plans.solver.candidate_pool import build_selected_place_pool


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


def test_route_first_gap_fill_keeps_small_candidate_pool_per_window() -> None:
    selector = PlaceSelectorService(
        _RequiredPlaceTool(),
        max_candidates_per_block=5,
        route_optimizer=RouteFirstItineraryOptimizer(GeographicRouteOptimizer()),
    )

    assert selector.max_candidates_per_block == 5
    assert selector.candidate_selector.max_candidates_per_block == 5
