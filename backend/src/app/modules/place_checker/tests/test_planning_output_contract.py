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
        timezone="Asia/Ho_Chi_Minh",
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


def test_compact_output_preserves_overnight_window() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-overnight"))
    first = result.checked_places[0]
    result.checked_places[0] = first.model_copy(
        update={"opening": first.opening.model_copy(update={"hours": ["22:00-03:00"]})}
    )

    output = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    ).model_dump(by_alias=True)

    place = next(item for item in output["places"] if item["placeId"] == first.place_id)
    assert place["openingHours"]["1"] == [
        {"startMinute": 1320, "endMinute": 180}
    ]


def test_compact_output_keeps_conflicting_user_input_but_drops_optional() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-avoids"))
    mandatory = next(place for place in result.checked_places if place.mandatory)
    optional = next(place for place in result.checked_places if not place.mandatory)
    for checked in (mandatory, optional):
        index = result.checked_places.index(checked)
        result.checked_places[index] = checked.model_copy(
            update={
                "evaluation": checked.evaluation.model_copy(
                    update={"avoid_conflicts": ["alcohol"]}
                )
            }
        )

    output = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    )
    output_ids = {place.place_id for place in [*output.places, *output.food]}

    assert mandatory.place_id in output_ids
    assert optional.place_id not in output_ids
