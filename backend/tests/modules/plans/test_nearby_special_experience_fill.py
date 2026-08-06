from types import SimpleNamespace

from app.modules.plans import dependencies
from app.modules.plans.place_selector.area_survey import AreaSurveyService
from app.modules.plans.place_selector.place_tool import SelectablePlace


class FakePlaceTool:
    def __init__(self, places):
        self.places = {place.place_id: place for place in places}

    def get(self, place_id):
        return self.places.get(place_id)

    def search(self, **kwargs):
        return []


def _claim(claim_id, place_id, activity_id, activity_name, predicate="SPECIAL_EXPERIENCE"):
    return SimpleNamespace(
        claimId=claim_id,
        predicate=predicate,
        anchorPlace=SimpleNamespace(id=place_id, name=place_id),
        object=SimpleNamespace(id=activity_id, name=activity_name),
        activity=SimpleNamespace(id=activity_id, name=activity_name),
        evidence=[SimpleNamespace(source=f"kg:{claim_id}")],
    )


def test_nearby_survey_uses_route_cost_and_five_km_bound():
    anchor = SelectablePlace(
        placeId="ho-guom", name="Ho Guom", placeType="attraction",
        regionKey="vn,hanoi", latitude=21.028, longitude=105.852,
    )
    water_puppet = SelectablePlace(
        placeId="water-puppet", name="Mua roi nuoc", placeType="theatre",
        regionKey="vn,hanoi", latitude=21.03, longitude=105.86,
    )
    too_far = water_puppet.model_copy(update={"place_id": "too-far", "name": "Far show"})

    class Graph:
        def discover_nearby_experiences(self, *args, **kwargs):
            return [
                _claim("c1", "water-puppet", "puppet", "Mua roi nuoc"),
                _claim("c2", "too-far", "far", "Far show"),
            ]

    tool = FakePlaceTool([anchor, water_puppet, too_far])
    survey = AreaSurveyService(
        tool,
        graph_repository=Graph(),
        route_cost_provider=lambda origin, destination: (
            2.0 if destination.place_id == "water-puppet" else 6.0
        ),
    ).survey_near_anchor(anchor, radius_km=5.0)

    assert [item.place.name for item in survey.candidates] == ["Mua roi nuoc"]
    assert survey.candidates[0].route_cost_km == 2.0


def test_located_in_child_is_context_only():
    anchor = SelectablePlace(
        placeId="ho-guom", name="Ho Guom", placeType="attraction",
        regionKey="vn,hanoi", latitude=21.028, longitude=105.852,
    )
    landmark = SimpleNamespace(id="thap-rua", canonical_name="Thap Rua")

    class Graph:
        def discover_nearby_experiences(self, *args, **kwargs):
            return []

        def query_located_in_children(self, *args, **kwargs):
            return [SimpleNamespace(from_entity_id="thap-rua")]

        def get_entities_by_ids(self, ids):
            return {landmark.id: landmark}

    result = AreaSurveyService(
        FakePlaceTool([anchor]), graph_repository=Graph()
    ).survey_near_anchor(anchor)

    assert result.candidates == ()
    assert result.context_by_place_id["ho-guom"] == ("Thap Rua",)


def test_production_nearby_route_adapter_returns_provider_distance(monkeypatch):
    class MatrixProvider:
        calls = 0

        def calculate(self, coordinates, *, transport_mode, departure_time):
            self.calls += 1
            assert transport_mode == "pedestrian"
            assert departure_time is None
            assert len(coordinates) == 2
            return SimpleNamespace(
                distances_meters=[[0, 2400], [2400, 0]],
            )

    matrix = MatrixProvider()

    monkeypatch.setattr(
        dependencies,
        "_get_route_optimizer",
        lambda: SimpleNamespace(matrix_provider=matrix),
    )
    provider = dependencies._get_nearby_route_cost_provider()
    origin = SelectablePlace(
        placeId="a", name="A", placeType="attraction", regionKey="vn,hanoi",
        latitude=21.028, longitude=105.852,
    )
    destination = origin.model_copy(update={"place_id": "b", "name": "B"})

    assert provider.calculate_many(origin, [destination]) == [2.4]
    assert matrix.calls == 1


def test_nearby_survey_batches_provider_costs_after_haversine_prefilter():
    anchor = SelectablePlace(
        placeId="anchor", name="Anchor", placeType="attraction",
        regionKey="vn,hanoi", latitude=21.028, longitude=105.852,
    )
    nearby = anchor.model_copy(
        update={"place_id": "nearby", "name": "Nearby", "longitude": 105.86}
    )
    far = anchor.model_copy(
        update={"place_id": "far", "name": "Far", "latitude": 22.0}
    )

    class Graph:
        def discover_nearby_experiences(self, *args, **kwargs):
            return [
                _claim("near", "nearby", "activity-near", "Nearby"),
                _claim("far", "far", "activity-far", "Far"),
            ]

    class BatchCosts:
        calls = 0

        def calculate_many(self, origin, destinations):
            self.calls += 1
            assert [item.place_id for item in destinations] == ["nearby"]
            return [1.2]

    costs = BatchCosts()
    result = AreaSurveyService(
        FakePlaceTool([anchor, nearby, far]),
        graph_repository=Graph(),
        route_cost_provider=costs,
    ).survey_near_anchor(anchor, radius_km=5.0)

    assert [item.place.place_id for item in result.candidates] == ["nearby"]
    assert costs.calls == 1
