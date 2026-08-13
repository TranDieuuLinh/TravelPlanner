import asyncio

from app.modules.place_checker.planning_output import PlaceCheckerPlannerOutputBuilder
from app.modules.place_checker.relationship_contract import PlaceRelationshipEvidence
from app.modules.place_checker.tests.test_pipeline_output import payload, pipeline


def test_compact_output_matches_planner_json_shape_and_relationship_ids() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-compact"))
    first = result.checked_places[0]
    relation = PlaceRelationshipEvidence(
        relationship_type="Special_Near",
        direction="place_to_place",
        scope="anchor",
        from_entity_id=first.place_id,
        to_entity_id="kg:night-market",
        related_entity_id="kg:night-market",
        related_name="Night Market",
        distance_km=0.4,
        threshold_km=5,
        score=0.926,
    )
    result.checked_places[0] = first.model_copy(
        update={"relationship_evidence": [relation]}
    )

    output = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
    ).model_dump(by_alias=True)

    assert set(output) == {"trip", "places", "food"}
    assert output["trip"]["timezone"] == "Asia/Ho_Chi_Minh"
    assert output["trip"]["startDate"] == "2026-08-20"
    assert set(output["trip"]) == {
        "destination", "days", "startDate", "timezone", "people", "budget", "preferences"
    }
    place = next(item for item in output["places"] if item["placeId"] == first.place_id)
    assert set(place) == {
        "placeId", "name", "coordinates", "address", "priority", "notes", "tags",
        "rating", "reviewCount", "durationMinutes", "openingHours",
        "preferredTimeWindows", "price", "relationships",
    }
    assert place["priority"] == "user_input"
    assert place["relationships"] == ["kg:night-market"]
    assert place["openingHours"]["1"] == [
        {"startMinute": 540, "endMinute": 1020}
    ]
    assert set(place["price"]) == {"cost", "currency"}
    food = output["food"][0]
    assert set(food) == {*set(place), "supportedMeals"}
    assert food["supportedMeals"] == ["lunch"]
