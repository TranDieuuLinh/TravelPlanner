from decimal import Decimal

from app.modules.places.model import Place
from app.modules.plans.trip_theme_planner.constraint_tool import calculate_constraint_research
from app.modules.plans.trip_theme_planner.research_tools_schema import ConstraintResearchInput


def test_constraint_research_accepts_internal_snake_case_and_exports_camel_case() -> None:
    place = Place(
        id="hanoi-attraction",
        name="Hanoi attraction",
        place_type="attraction",
        region_key="vn,ha-noi",
        status="active",
        latitude=Decimal("21.0285"),
        longitude=Decimal("105.8542"),
        data_confidence="high",
        opening_hours=[],
        metadata_json={"tags": ["sightseeing"], "dailyCost": 100_000},
    )
    input_data = ConstraintResearchInput(
        mode="coordinates",
        center_lat=21.0285,
        center_lng=105.8542,
        radius_km=10,
        budget=1_000_000,
        duration=2,
    )

    result = calculate_constraint_research([place], input_data)
    payload = result.model_dump(by_alias=True)

    assert payload["spatialStats"]["totalZonesInRadius"] == 1
    assert payload["spatialStats"]["zones"][0]["zoneId"].startswith("zone_")
    populated_categories = [
        stat for stat in payload["categoryStats"].values() if stat is not None
    ]
    assert populated_categories[0]["count"] == 1
    assert payload["budgetCompatibility"]["withinBudget"] is True
