import asyncio

from app.modules.place_checker.enums import CostTier
from app.modules.place_checker.selection.food.contract import SelectedFoodRestaurant
from app.modules.place_checker.planning.builder import PlaceCheckerPlannerOutputBuilder
from app.modules.place_checker.planning.place_projection import PlannerPlaceProjector
from app.modules.place_checker.relationship_contract import PlaceRelationshipEvidence
from app.modules.place_checker.tests.test_pipeline_output import (
    metadata,
    payload,
    pipeline,
)


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
        update={
            "relationship_evidence": [relation],
            "image_urls": ["https://example.test/place.jpg"],
        }
    )

    output = (
        PlaceCheckerPlannerOutputBuilder()
        .build(
            result,
            start_date="2026-08-20",
            timezone="Asia/Ho_Chi_Minh",
        )
        .model_dump(by_alias=True)
    )

    assert set(output) == {
        "trip",
        "places",
        "food",
        "entertainment",
        "foodCoverage",
        "accommodations",
        "excludedCandidates",
    }
    assert output["trip"]["timezone"] == "Asia/Ho_Chi_Minh"
    assert output["trip"]["startDate"] == "2026-08-20"
    assert output["trip"]["preferences"] == {
        "tags": ["nature"],
        "avoidTags": ["nightlife"],
        "styles": [],
    }
    assert output["trip"]["party"] == {"adults": 1, "kids": 0}
    assert set(output["trip"]) == {
        "destination",
        "days",
        "startDate",
        "timezone",
        "people",
        "party",
        "budget",
        "preferences",
    }
    place = next(item for item in output["places"] if item["placeId"] == first.place_id)
    assert place["imageUrls"] == ["https://example.test/place.jpg"]
    assert set(place) == {
        "placeId",
        "name",
        "coordinates",
        "address",
        "priority",
        "notes",
        "tags",
        "styles",
        "audience",
        "imageUrls",
        "rating",
        "reviewCount",
        "durationMinutes",
        "openingHours",
        "preferredTimeWindows",
        "sourceKind",
        "offeredActivityIds",
        "timeSource",
        "price",
        "relationships",
    }
    assert place["priority"] == "user_input"
    assert place["relationships"] == ["kg:night-market"]
    assert place["sourceKind"] == "generic"
    assert place["offeredActivityIds"] == []
    assert place["openingHours"]["1"] == [{"startMinute": 540, "endMinute": 1020}]
    assert set(place["price"]) == {"cost", "currency"}
    food = output["food"][0]
    assert set(food) == {*set(place), "venueType", "supportedMeals"}
    assert food["placeId"] == "kg:pho"
    assert food["priority"] == "user_input"
    assert food["venueType"] == "restaurant"
    assert food["supportedMeals"] == ["lunch"]
    assert output["foodCoverage"]["days"] == result.trip_context.days
    assert set(output["foodCoverage"]) == {
        "days",
        "hardComplete",
        "reserveComplete",
        "hardAssignments",
        "hardMissingSlots",
        "reserveAssignments",
        "reserveMissingSlots",
    }


def test_food_projection_accepts_provider_generic_travel_place_category() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-generic-food"))
    checked = result.checked_places[0].model_copy(
        update={"category": "travel_place", "pool_category": "restaurant"}
    )

    food = PlannerPlaceProjector.food(checked, result.trip_context.days, ["lunch"])

    assert food.venue_type == "restaurant"
    assert food.supported_meals == ["lunch"]


def test_compact_output_adds_selected_special_food_near_anchor() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-special-food"))
    anchor = result.checked_places[0]
    restaurant_metadata = metadata(
        "restaurant:bun-cha",
        category="restaurant",
        cost_tier=CostTier.low,
        latitude=21.032,
    ).model_copy(update={"rating": 4.7, "review_count": 2_500})
    selection = SelectedFoodRestaurant(
        anchor_place_id=anchor.place_id,
        anchor_name=anchor.canonical_name,
        food_item_id="food:bun-cha",
        food_item_name="Bún chả",
        offered_food_item_id="food:bun-cha",
        offered_food_item_name="Bún chả",
        food_match_type="special_experience",
        food_match_confidence=1,
        restaurant_id="restaurant:bun-cha",
        restaurant_name="Bún Chả Hương Liên",
        distance_km=0.8,
        rating=4.7,
        review_count=2_500,
        bayesian_rating=4.68,
        pair_score=0.91,
        selection_reason="sole_candidate_for_food",
        metadata=restaurant_metadata,
    )
    result = result.model_copy(update={"food_restaurant_selections": [selection]})

    output = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    )
    selected = next(
        food for food in output.food if food.place_id == "restaurant:bun-cha"
    )

    assert selected.priority == "special_near"
    assert selected.relationships == [anchor.place_id]
    assert selected.tags == ["restaurant"]
    assert not any(tag.startswith("food-item:") for tag in selected.tags)
    assert selected.notes is not None
    assert "Bún chả" in selected.notes.text
    assert "Bayesian rating" not in selected.notes.text


def test_compact_output_projects_drink_dessert_as_entertainment_not_meal() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-drink-place"))
    anchor = result.checked_places[0]
    drink_metadata = metadata(
        "drink:cafe",
        category="drink_dessert",
        cost_tier=CostTier.low,
        latitude=21.031,
    ).model_copy(update={"rating": 4.5, "review_count": 100})
    selection = SelectedFoodRestaurant(
        anchor_place_id=anchor.place_id,
        anchor_name=anchor.canonical_name,
        food_item_id="drink:coffee",
        food_item_name="Cà phê",
        offered_food_item_id="drink:coffee",
        offered_food_item_name="Cà phê",
        food_match_type="special_experience",
        food_match_confidence=1,
        restaurant_id="drink:cafe",
        restaurant_name="Cafe Test",
        distance_km=0.2,
        rating=4.5,
        review_count=100,
        pair_score=0.8,
        selection_reason="food_item_diversity",
        metadata=drink_metadata,
    )
    result = result.model_copy(update={"food_restaurant_selections": [selection]})

    output = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    )

    assert output.entertainment is not None
    assert "drink:cafe" in {place.place_id for place in output.entertainment}
    assert "drink:cafe" not in {place.place_id for place in output.places}
    assert "drink:cafe" not in {food.place_id for food in output.food}


def test_drink_selection_reclassifies_an_existing_food_candidate() -> None:
    result = asyncio.run(
        pipeline().check(payload(), request_id="request-drink-overlap")
    )
    checked = result.checked_places[0].model_copy(
        update={"category": "restaurant", "canonical_name": "Cafe Test"}
    )
    result.checked_places[0] = checked
    selection = SelectedFoodRestaurant(
        anchor_place_id=checked.place_id,
        anchor_name=checked.canonical_name,
        food_item_id="drink:coffee",
        food_item_name="Cà phê",
        offered_food_item_id="drink:coffee",
        offered_food_item_name="Cà phê",
        food_match_type="special_experience",
        food_match_confidence=1,
        restaurant_id=checked.place_id,
        restaurant_name=checked.canonical_name,
        distance_km=0.2,
        rating=4.5,
        review_count=100,
        pair_score=0.8,
        selection_reason="food_item_diversity",
        metadata=metadata(
            checked.place_id,
            category="drink_dessert",
            cost_tier=CostTier.low,
            latitude=21.031,
        ),
    )
    result = result.model_copy(update={"food_restaurant_selections": [selection]})

    output = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    )

    assert checked.place_id not in {food.place_id for food in output.food}
    drink = next(
        place
        for place in output.entertainment or []
        if place.place_id == checked.place_id
    )
    assert drink.entity_type == "drink_dessert"


def test_drink_selection_reclassifies_an_existing_place_candidate() -> None:
    result = asyncio.run(
        pipeline().check(payload(), request_id="request-drink-place-overlap")
    )
    checked = result.checked_places[0].model_copy(
        update={"category": "travel_place", "canonical_name": "Cafe Test"}
    )
    result.checked_places[0] = checked
    selection = SelectedFoodRestaurant(
        anchor_place_id=checked.place_id,
        anchor_name=checked.canonical_name,
        food_item_id="drink:coffee",
        food_item_name="Cà phê",
        offered_food_item_id="drink:coffee",
        offered_food_item_name="Cà phê",
        food_match_type="special_experience",
        food_match_confidence=1,
        restaurant_id=checked.place_id,
        restaurant_name=checked.canonical_name,
        distance_km=0.2,
        rating=4.5,
        review_count=100,
        pair_score=0.8,
        selection_reason="food_item_diversity",
        metadata=metadata(
            checked.place_id,
            category="drink_dessert",
            cost_tier=CostTier.low,
            latitude=21.031,
        ),
    )
    result = result.model_copy(update={"food_restaurant_selections": [selection]})

    output = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    )

    assert checked.place_id not in {place.place_id for place in output.places}
    assert checked.place_id not in {food.place_id for food in output.food}
    drink = next(
        place
        for place in output.entertainment or []
        if place.place_id == checked.place_id
    )
    assert drink.entity_type == "drink_dessert"


def test_compact_output_reclassifies_mislabeled_music_box_as_entertainment() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-music-box"))
    first = result.checked_places[0]
    result.checked_places[0] = first.model_copy(
        update={
            "canonical_name": "ON TOP MUSIC BOX",
            "category": "travel_place",
        }
    )

    output = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    )

    assert first.place_id not in {place.place_id for place in output.places}
    reclassified = next(
        place
        for place in output.entertainment or []
        if place.place_id == first.place_id
    )
    assert reclassified.entity_type == "entertainment"
    assert reclassified.priority == "user_input"


def test_resolved_item_promotes_duplicate_pool_candidate_to_user_input() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-item-overlap"))
    optional = next(place for place in result.checked_places if not place.mandatory)
    resolved = result.resolved_items[0]
    result.resolved_items[0] = resolved.model_copy(
        update={
            "selected": resolved.selected.model_copy(
                update={"place_id": optional.place_id}
            )
        }
    )

    output = PlaceCheckerPlannerOutputBuilder().build(
        result, start_date="2026-08-20", timezone="Asia/Ho_Chi_Minh"
    )
    promoted = next(
        place for place in output.places if place.place_id == optional.place_id
    )

    assert promoted.priority == "user_input"


def test_resolved_drink_duplicate_is_moved_to_entertainment_pool() -> None:
    result = asyncio.run(
        pipeline().check(payload(), request_id="request-item-drink-overlap")
    )
    checked = result.checked_places[0]
    resolved = result.resolved_items[0]
    result.resolved_items[0] = resolved.model_copy(
        update={
            "selected": resolved.selected.model_copy(
                update={
                    "place_id": checked.place_id,
                    "name": "Cafe Test",
                    "category": "drink_dessert",
                    "tags": ["drink_dessert"],
                }
            )
        }
    )

    output = PlaceCheckerPlannerOutputBuilder().build(
        result, start_date="2026-08-20", timezone="Asia/Ho_Chi_Minh"
    )

    assert checked.place_id not in {place.place_id for place in output.places}
    drink = next(
        place
        for place in output.entertainment or []
        if place.place_id == checked.place_id
    )
    assert drink.entity_type == "drink_dessert"


def test_food_pool_cap_prefers_required_then_paired_candidates() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-food-cap"))
    output = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    )
    sample = output.food[0]
    foods = [
        sample.model_copy(update={"place_id": f"food:{index}"}) for index in range(14)
    ]

    limited = PlaceCheckerPlannerOutputBuilder._limit_food_pool(
        foods,
        limit=12,
        required_ids={"food:13"},
        paired_ids={"food:12"},
    )

    assert len(limited) == 12
    assert {food.place_id for food in limited} >= {"food:12", "food:13"}


def test_compact_output_preserves_overnight_window() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-overnight"))
    first = result.checked_places[0]
    result.checked_places[0] = first.model_copy(
        update={"opening": first.opening.model_copy(update={"hours": ["22:00-03:00"]})}
    )

    output = (
        PlaceCheckerPlannerOutputBuilder()
        .build(
            result,
            start_date="2026-08-20",
            timezone="Asia/Ho_Chi_Minh",
        )
        .model_dump(by_alias=True)
    )

    place = next(item for item in output["places"] if item["placeId"] == first.place_id)
    assert place["openingHours"]["1"] == [{"startMinute": 1320, "endMinute": 180}]


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


def test_compact_output_defaults_checked_place_without_price_to_free() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-no-price"))
    first = result.checked_places[0]
    result.checked_places[0] = first.model_copy(
        update={
            "cost": first.cost.model_copy(
                update={
                    "tier": "unknown",
                    "currency": None,
                    "minimum": None,
                    "typical": None,
                    "maximum": None,
                    "known": False,
                }
            )
        }
    )

    output = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    )

    projected = next(
        place for place in output.places if place.place_id == first.place_id
    )
    assert projected.price.cost == 0
    assert projected.price.currency == "VND"
    assert output.excluded_candidates == []


def test_compact_output_calculates_typical_cost_from_range() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-price-range"))
    first = result.checked_places[0]
    result.checked_places[0] = first.model_copy(
        update={
            "cost": first.cost.model_copy(
                update={"minimum": 20_000, "typical": 999_999, "maximum": 80_000}
            )
        }
    )

    output = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    )
    place = next(item for item in output.places if item.place_id == first.place_id)

    assert place.price.cost == 50_000


def test_compact_output_selects_three_priced_accommodations_around_budget_percentile() -> (
    None
):
    result = asyncio.run(pipeline().check(payload(), request_id="request-hotel"))
    sample = result.checked_places[0]
    accommodations = []
    for index, price in enumerate((100_000, 200_000, 300_000, 400_000, 500_000)):
        latitude_offset = {0: 0.0, 1: 1.0, 2: 0.1}.get(index, 2.0 + index)
        accommodations.append(
            sample.model_copy(
                update={
                    "place_id": f"hotel:{index}",
                    "canonical_name": f"Hotel {index}",
                    "category": "accommodation",
                    "coordinates": sample.coordinates.model_copy(
                        update={
                            "latitude": sample.coordinates.latitude + latitude_offset
                        }
                    ),
                    "cost": sample.cost.model_copy(
                        update={
                            "currency": "VND",
                            "minimum": price,
                            "typical": price,
                            "maximum": price,
                            "known": True,
                        }
                    ),
                }
            )
        )
    zero_price = accommodations[0].model_copy(
        update={
            "place_id": "hotel:free",
            "cost": accommodations[0].cost.model_copy(
                update={"minimum": 0, "typical": 0, "maximum": 0}
            ),
        }
    )
    result = result.model_copy(
        update={"checked_places": [*result.checked_places, zero_price, *accommodations]}
    )

    output = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    )

    assert [item.place_id for item in output.accommodations] == [
        "hotel:0",
        "hotel:2",
        "hotel:1",
    ]
    assert output.accommodations[0].price_per_night.cost == 100_000
    assert output.accommodations[0].coordinates == accommodations[0].coordinates
    assert all(
        item.place_id not in {place.place_id for place in output.places}
        for item in output.accommodations
    )


def test_compact_output_preserves_explicit_per_person_budget() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-budget-exact"))
    context = result.trip_context.model_copy(
        update={
            "budget": result.trip_context.budget.model_copy(
                update={
                    "target_amount": 2_000_000,
                    "basis": "per_person",
                }
            )
        }
    )
    result = result.model_copy(update={"trip_context": context})

    output = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    )

    assert output.trip.budget.amount == 2_000_000
    assert output.trip.budget.source == "explicit"
    assert output.trip.budget.daily_estimate is None
