import asyncio
from types import SimpleNamespace

from fastapi import FastAPI

from app.modules.place_checker.manual_search import (
    list_subplaces_for_plan,
    router,
    search_places_for_manual_plan,
)
from app.modules.place_checker.subplaces.contract import SubplaceGroup, SubplaceSummary
from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places import PlaceSearchMatch, PlaceSearchResult


def test_manual_place_search_defaults_to_five_results() -> None:
    app = FastAPI()
    app.include_router(router)

    operation = app.openapi()["paths"]["/v1/plans/places/search"]["get"]
    top_k = next(
        parameter
        for parameter in operation["parameters"]
        if parameter["name"] == "topK"
    )

    assert top_k["schema"]["default"] == 5


def test_subplace_lookup_uses_a_bounded_repeated_parent_query() -> None:
    app = FastAPI()
    app.include_router(router)

    operation = app.openapi()["paths"]["/v1/plans/places/subplaces"]["get"]
    parent_ids = next(
        parameter
        for parameter in operation["parameters"]
        if parameter["name"] == "parentPlaceIds"
    )

    assert parent_ids["required"] is True
    assert parent_ids["schema"]["minItems"] == 1
    assert parent_ids["schema"]["maxItems"] == 50


def test_manual_search_returns_planning_metadata_for_catalog_matches() -> None:
    class FakeTool:
        async def search(self, request):
            assert request.top_k == 5
            return PlaceSearchResult(
                status="resolved",
                query=request.query,
                normalized_query="lang bac",
                search_mode="named_place",
                top_matches=[
                    PlaceSearchMatch(
                        place_id="kg:mausoleum",
                        provider="knowledge_graph",
                        name="Ho Chi Minh's Mausoleum",
                        coordinates=Coordinates(latitude=21.0368, longitude=105.8346),
                        score=0.95,
                    )
                ],
                resolution_reason="ranked",
            )

    class FakeCatalog:
        async def resolve(self, destination):
            return SimpleNamespace(
                adm_id="adm:hanoi",
                canonical_name=destination,
                country_code="VN",
            )

        async def get_many(self, place_ids):
            assert place_ids == ["kg:mausoleum"]
            return {
                "kg:mausoleum": SimpleNamespace(
                    typical_duration_minutes=90,
                    opening_hours=["08:00-17:00"],
                    typical_cost=30_000,
                )
            }

    suggestions = asyncio.run(
        search_places_for_manual_plan(
            query="lăng bác",
            destination="Hà Nội",
            top_k=5,
            _=None,
            dependencies=(FakeTool(), FakeCatalog()),
        )
    )

    assert suggestions[0]["durationMinutes"] == 90
    assert suggestions[0]["openingHours"] == ["08:00-17:00"]
    assert suggestions[0]["costPerPerson"] == 30_000


def test_subplaces_endpoint_keeps_children_informational() -> None:
    class FakeCatalog:
        async def list_subplaces(self, parent_place_ids, *, per_parent_limit):
            assert parent_place_ids == ["kg:old-quarter"]
            assert per_parent_limit == 50
            return [
                SubplaceGroup(
                    parent_place_id="kg:old-quarter",
                    total_count=1,
                    items=[
                        SubplaceSummary(
                            place_id="kg:hang-gai",
                            name="Phố Hàng Gai",
                            latitude=21.0321,
                            longitude=105.8501,
                        )
                    ],
                )
            ]

    groups = asyncio.run(
        list_subplaces_for_plan(
            parent_place_ids=["kg:old-quarter"],
            _=None,
            catalog=FakeCatalog(),
        )
    )

    assert groups[0].items[0].name == "Phố Hàng Gai"
    assert groups[0].total_count == 1
