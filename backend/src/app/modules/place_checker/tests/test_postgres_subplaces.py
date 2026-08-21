import asyncio

from app.modules.place_checker.adapters.postgres_catalog_mapping import (
    PostgresCatalogMappingMixin,
)
from app.modules.place_checker.adapters.postgres_subplaces import (
    SUBPLACES_BY_PARENT_SQL,
    PostgresSubplaceMixin,
)
from app.modules.place_checker.adapters.postgres_generic_ranking_sql import (
    GENERIC_TRAVEL_RANKING_CTES,
)
from app.modules.place_checker.adapters.postgres_named_place_query import (
    NAMED_PLACE_SEARCH_SQL,
)
from app.modules.place_checker.adapters.postgres_search_query import PLACE_SEARCH_SQL


class FakeSubplaceCatalog(PostgresSubplaceMixin, PostgresCatalogMappingMixin):
    def __init__(self) -> None:
        self.arguments = None

    async def _fetch(self, query, *arguments):
        self.arguments = arguments
        assert query == SUBPLACES_BY_PARENT_SQL
        return [
            {
                "parent_place_id": "kg:old-quarter",
                "place_id": "kg:hang-gai",
                "name": "Phố Hàng Gai",
                "total_count": 2,
                "child_order": 1,
                "address": "Hàng Gai, Hoàn Kiếm",
                "latitude": "21.032100",
                "longitude": "105.850100",
                "image": '["https://example.test/hang-gai.jpg"]',
                "description": "Phố nghề truyền thống",
                "time_duration": "PT45M",
                "price_min": "30000",
                "rating": "4.6",
                "review_count": "125",
            },
            {
                "parent_place_id": "kg:old-quarter",
                "place_id": "kg:hang-ma",
                "name": "Phố Hàng Mã",
                "total_count": 2,
                "child_order": 2,
                "address": None,
                "latitude": "not-a-coordinate",
                "longitude": "999",
                "image": None,
                "description": None,
                "time_duration": "invalid",
                "price_min": "invalid",
                "rating": "9",
                "review_count": None,
            },
        ]


def test_subplace_read_projection_is_bounded_and_tolerates_partial_metadata() -> None:
    catalog = FakeSubplaceCatalog()

    groups = asyncio.run(
        catalog.list_subplaces(
            ["kg:old-quarter", "kg:old-quarter"],
            per_parent_limit=500,
        )
    )

    assert catalog.arguments == (["kg:old-quarter"], 50)
    assert len(groups) == 1
    assert groups[0].total_count == 2
    assert groups[0].items[0].image_url == "https://example.test/hang-gai.jpg"
    assert groups[0].items[0].latitude == 21.0321
    assert groups[0].items[0].description == "Phố nghề truyền thống"
    assert groups[0].items[0].duration_minutes == 45
    assert groups[0].items[0].cost_per_person == 30000
    assert groups[0].items[0].rating == 4.6
    assert groups[0].items[0].review_count == 125
    assert groups[0].items[1].latitude is None
    assert groups[0].items[1].longitude is None
    assert groups[0].items[1].duration_minutes is None
    assert groups[0].items[1].cost_per_person is None
    assert groups[0].items[1].rating is None


def test_subplace_query_keeps_children_out_of_planner_relationships() -> None:
    assert "relationship.relationship_type = 'Has_Subplace'" in SUBPLACES_BY_PARENT_SQL
    assert "child.entity_type = 'SubPlace'" in SUBPLACES_BY_PARENT_SQL
    assert "parent.entity_type = 'TravelPlace'" in SUBPLACES_BY_PARENT_SQL


def test_planner_catalog_queries_do_not_read_or_project_subplaces() -> None:
    for planner_sql in (
        GENERIC_TRAVEL_RANKING_CTES,
        NAMED_PLACE_SEARCH_SQL,
        PLACE_SEARCH_SQL,
    ):
        assert "Has_Subplace" not in planner_sql
        assert "SubPlace" not in planner_sql
