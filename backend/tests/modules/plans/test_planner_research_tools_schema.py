from decimal import Decimal

from app.modules.places.model import Place
from app.modules.plans.planner.constraint_tool import (
    ConstraintResearchTool,
    calculate_constraint_research,
)
from app.modules.plans.planner.research_tools_schema import (
    CategoryStat,
    ConstraintResearchInput,
    Festival,
)


def test_constraint_research_accepts_internal_snake_case_models() -> None:
    place = Place(
        id="local-restaurant",
        name="Quán ăn địa phương",
        place_type="restaurant",
        region_key="vn,ha-noi,hoan-kiem",
        status="active",
        latitude=Decimal("21.0285"),
        longitude=Decimal("105.8542"),
        rating=Decimal("4.7"),
        review_count=850,
        data_confidence="high",
        opening_hours=[],
        metadata_json={
            "tags": ["food", "local"],
            "finance": {"dailyBudget": 100_000},
        },
    )
    input_data = ConstraintResearchInput(
        mode="coordinates",
        center_lat=21.0285,
        center_lng=105.8542,
        radius_km=5,
        budget=500_000,
        duration=2,
    )

    result = calculate_constraint_research([place], input_data)

    assert result.spatial_stats.total_zones_in_radius == 1
    assert result.spatial_stats.total_places_in_radius == 1
    assert result.spatial_stats.zones[0].zone_id.startswith("zone_")
    assert result.spatial_stats.zones[0].place_count == 1
    assert result.category_stats.food is not None
    assert result.category_stats.food.count_with_price == 1
    assert result.budget_compatibility is not None
    assert result.budget_compatibility.within_budget is True
    assert result.model_dump(by_alias=True)["spatialStats"]["zones"][0][
        "placeCount"
    ] == 1


def test_nested_research_schemas_preserve_snake_case_values_and_camel_aliases() -> None:
    category = CategoryStat(
        count=3,
        count_with_price=2,
        avg_rating=4.6,
        avg_review_count=125.0,
        price_distribution={"$$": 2},
        avg_daily_cost=150_000,
    )
    festival = Festival(
        name="Lễ hội địa phương",
        date="tháng 8",
        region_keys=["vn,ha-noi"],
        region_names=["Hà Nội"],
        scale="dia-phuong",
    )

    assert category.count_with_price == 2
    assert category.model_dump(by_alias=True)["avgReviewCount"] == 125.0
    assert festival.region_keys == ["vn,ha-noi"]
    assert festival.model_dump(by_alias=True)["regionNames"] == ["Hà Nội"]


def test_text_constraint_research_uses_resolved_region_boundary() -> None:
    hanoi = Place(
        id="hanoi-museum",
        name="Hanoi Museum",
        place_type="museum",
        region_key="vn,ha-noi,nam-tu-liem",
        status="active",
        latitude=Decimal("21.011"),
        longitude=Decimal("105.785"),
        data_confidence="high",
        opening_hours=[],
        metadata_json={"tags": ["culture"]},
    )

    class Repository:
        requested_region: str | None = None

        def list_active_for_region(self, region_key: str) -> list[Place]:
            self.requested_region = region_key
            return [hanoi]

        def list_all_active(self) -> list[Place]:
            raise AssertionError("text-mode Planner research must not scan every region")

        def list_within_radius(self, *args) -> list[Place]:
            return []

    repository = Repository()
    result = ConstraintResearchTool(repository).execute(
        ConstraintResearchInput(
            mode="text",
            query="Hà Nội",
            region_key="vn,ha-noi",
        )
    )

    assert repository.requested_region == "vn,ha-noi"
    assert result.spatial_stats.total_places_in_radius == 1
