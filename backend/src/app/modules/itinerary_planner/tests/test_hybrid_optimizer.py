import asyncio

from dataclasses import replace
from types import MappingProxyType

import pytest

from app.modules.itinerary_planner.adapters.transport_cost import (
    XanhSmTransportCostEstimator,
)
from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.hybrid import optimize_hybrid_itinerary
from app.modules.itinerary_planner.hybrid.heuristic import (
    _improve_activity_order,
    _route_cost,
    build_day_shortlist,
)
from app.modules.itinerary_planner.preprocessing import prepare_planning_problem
from app.modules.itinerary_planner.optimizer import optimize_itinerary
from app.modules.itinerary_planner.optimizer.solver import OptimizationError
from app.modules.itinerary_planner.routing import build_routing_problem
from app.modules.itinerary_planner.routing_models import SafeTravel
from app.modules.itinerary_planner.tests.optimizer_fixtures import (
    FAST_CONFIG,
    base_payload,
    meal_candidates,
)
from app.modules.itinerary_planner.tests.factories import candidate, food, payload
from app.modules.itinerary_planner.tests.routing_fakes import GeneratedMatrixProvider


def _hybrid_result(days: int = 2):
    problem = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(base_payload(days=days))
    )
    routing = asyncio.run(
        build_routing_problem(
            problem,
            GeneratedMatrixProvider(asymmetric=True),
            XanhSmTransportCostEstimator(),
        )
    )
    return optimize_hybrid_itinerary(
        problem,
        routing,
        config=FAST_CONFIG,
    )


def test_hybrid_repairs_each_day_and_never_reuses_candidate() -> None:
    result = _hybrid_result(days=2)

    assert (
        result.objective_policy_version
        == "hybrid-activity-corridor-v16-dense-activities"
    )
    assert [item.name for item in result.passes] == [
        "day_1:priority",
        "day_1:activity_count",
        "day_1:utility",
        "day_2:priority",
        "day_2:activity_count",
        "day_2:utility",
    ]
    scheduled = [stop.place_id for stop in result.scheduled_stops]
    assert len(scheduled) == len(set(scheduled))
    assert {stop.day for stop in result.scheduled_stops} == {1, 2}


def test_hybrid_distributes_popular_places_across_trip_days() -> None:
    landmarks = [candidate(f"landmark_{index}") for index in range(6)]
    for index, item in enumerate(landmarks):
        item.update({"rating": 4.8, "reviewCount": 20_000 - index})
        item["sourceKind"] = "generic"
    problem = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(
            base_payload(days=3, places=landmarks)
        )
    )
    routing = asyncio.run(
        build_routing_problem(
            problem,
            GeneratedMatrixProvider(),
            XanhSmTransportCostEstimator(),
        )
    )

    result = optimize_hybrid_itinerary(problem, routing, config=FAST_CONFIG)
    popular_by_day = {
        day: sum(
            stop.place_id.startswith("landmark_")
            for stop in result.scheduled_stops
            if stop.day == day
        )
        for day in range(1, 4)
    }

    assert sum(popular_by_day.values()) >= 4, popular_by_day
    assert sum(count > 0 for count in popular_by_day.values()) >= 2


def test_hybrid_reserves_two_special_places_for_each_trip_day() -> None:
    specials = [candidate(f"special_{index}") for index in range(6)]
    for item in specials:
        item["sourceKind"] = "special_experience"
    problem = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(
            base_payload(days=3, places=specials)
        )
    )
    routing = asyncio.run(
        build_routing_problem(
            problem,
            GeneratedMatrixProvider(),
            XanhSmTransportCostEstimator(),
        )
    )

    result = optimize_hybrid_itinerary(problem, routing, config=FAST_CONFIG)
    special_by_day = {
        day: sum(
            stop.place_id.startswith("special_")
            for stop in result.scheduled_stops
            if stop.day == day
        )
        for day in range(1, 4)
    }

    assert sum(special_by_day.values()) >= 4
    assert sum(count > 0 for count in special_by_day.values()) >= 2


def test_two_opt_and_swap_reduce_route_cost() -> None:
    problem = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(base_payload())
    )
    routing = asyncio.run(
        build_routing_problem(
            problem,
            GeneratedMatrixProvider(),
            XanhSmTransportCostEstimator(),
        )
    )
    cheap = SafeTravel(1, 1, 1, 0)
    expensive = SafeTravel(100, 100, 1, 0)
    routing.travel_by_candidate_pair.update(
        {
            ("continuity_1_1", "continuity_1_2"): expensive,
            ("continuity_1_2", "continuity_1_3"): expensive,
            ("continuity_1_1", "continuity_1_3"): cheap,
            ("continuity_1_3", "continuity_1_2"): cheap,
        }
    )

    initial = ("continuity_1_1", "continuity_1_2", "continuity_1_3")
    improved = _improve_activity_order(initial, routing)

    assert _route_cost(improved, routing) < _route_cost(initial, routing)


def test_greedy_shortlist_does_not_filter_by_total_duration() -> None:
    problem = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(base_payload())
    )
    routing = asyncio.run(
        build_routing_problem(
            problem,
            GeneratedMatrixProvider(),
            XanhSmTransportCostEstimator(),
        )
    )

    shortlist = build_day_shortlist(
        problem,
        routing,
        day=1,
        used_ids=frozenset(),
    )

    assert {f"continuity_1_{index}" for index in range(1, 7)} <= shortlist.candidate_ids


def test_greedy_shortlist_keeps_every_priority_candidate() -> None:
    required = [
        candidate(f"required_{index}", priority="user_input") for index in range(13)
    ]
    problem = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(base_payload(places=required))
    )
    routing = asyncio.run(
        build_routing_problem(
            problem,
            GeneratedMatrixProvider(),
            XanhSmTransportCostEstimator(),
        )
    )

    shortlist = build_day_shortlist(
        problem,
        routing,
        day=1,
        used_ids=frozenset(),
    )

    assert {item["placeId"] for item in required} <= shortlist.candidate_ids


def test_greedy_shortlist_uses_bayesian_review_quality() -> None:
    reliable = candidate("reliable")
    reliable.update({"rating": 4.8, "reviewCount": 2_000})
    sparse = candidate("sparse")
    sparse.update({"rating": 5.0, "reviewCount": 1})
    fillers = [candidate(f"filler_{index}") for index in range(15)]
    problem = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(
            base_payload(places=[reliable, sparse, *fillers])
        )
    )
    routing = asyncio.run(
        build_routing_problem(
            problem,
            GeneratedMatrixProvider(),
            XanhSmTransportCostEstimator(),
        )
    )

    shortlist = build_day_shortlist(
        problem,
        routing,
        day=1,
        used_ids=frozenset(),
    )

    assert "reliable" in shortlist.candidate_ids
    assert "sparse" not in shortlist.candidate_ids


def test_greedy_shortlist_reserves_high_review_popular_places() -> None:
    landmarks = [candidate("landmark_a"), candidate("landmark_b")]
    for index, item in enumerate(landmarks):
        item.update({"rating": 4.7, "reviewCount": 20_000 - index})
        item["sourceKind"] = "generic"
    leisure = [candidate(f"music_box_{index}") for index in range(17)]
    for item in leisure:
        item.update({"rating": 5.0, "reviewCount": 200})
    problem = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(
            base_payload(places=[*landmarks, *leisure])
        )
    )
    routing = asyncio.run(
        build_routing_problem(
            problem,
            GeneratedMatrixProvider(),
            XanhSmTransportCostEstimator(),
        )
    )

    shortlist = build_day_shortlist(
        problem,
        routing,
        day=1,
        used_ids=frozenset(),
    )

    assert {"landmark_a", "landmark_b"} <= shortlist.candidate_ids


def test_popular_places_remain_available_outside_geographic_preferred_day() -> None:
    landmark = candidate("major_landmark")
    landmark.update({"rating": 4.8, "reviewCount": 20_000})
    problem = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(
            base_payload(days=2, places=[landmark, candidate("local_place")])
        )
    )
    problem = replace(
        problem,
        preferred_days=MappingProxyType(
            {**problem.preferred_days, "major_landmark": frozenset({1})}
        ),
    )
    routing = asyncio.run(
        build_routing_problem(
            problem,
            GeneratedMatrixProvider(),
            XanhSmTransportCostEstimator(),
        )
    )

    shortlist = build_day_shortlist(
        problem,
        routing,
        day=2,
        used_ids=frozenset(),
    )

    assert "major_landmark" in shortlist.candidate_ids


def test_greedy_shortlist_allows_sixteen_optional_activities() -> None:
    problem = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(
            base_payload(places=[candidate(f"optional_{index}") for index in range(20)])
        )
    )
    routing = asyncio.run(
        build_routing_problem(
            problem,
            GeneratedMatrixProvider(),
            XanhSmTransportCostEstimator(),
        )
    )

    shortlist = build_day_shortlist(
        problem,
        routing,
        day=1,
        used_ids=frozenset(),
    )

    activity_ids = {item.place_id for item in problem.valid_places}
    assert len(shortlist.candidate_ids & activity_ids) == 16


def test_shortlist_prefers_a_new_experience_group_across_trip_days() -> None:
    spiritual = [candidate(f"temple_{index}") for index in range(16)]
    for item in spiritual:
        item["tags"] = ["temple", "culture"]
    museum = candidate("museum")
    museum["tags"] = ["museum", "culture"]
    museum["rating"] = 1.0
    museum["reviewCount"] = 2_000
    museum["sourceKind"] = "generic"
    problem = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(
            base_payload(places=[*spiritual, museum])
        )
    )
    routing = asyncio.run(
        build_routing_problem(
            problem,
            GeneratedMatrixProvider(),
            XanhSmTransportCostEstimator(),
        )
    )

    baseline = build_day_shortlist(
        problem,
        routing,
        day=1,
        used_ids=frozenset(),
    )
    diversified = build_day_shortlist(
        problem,
        routing,
        day=1,
        used_ids=frozenset(),
        trip_tag_counts={"spiritual": 2},
    )

    assert "museum" not in baseline.candidate_ids
    assert "museum" in diversified.candidate_ids


def test_meal_placeholder_prefers_food_on_the_activity_corridor() -> None:
    raw = base_payload()
    raw["food"].append(
        food(
            "corridor_lunch",
            supported_meals=["lunch"],
            opening_hours={"1": [{"startMinute": 480, "endMinute": 1230}]},
        )
    )
    problem = prepare_planning_problem(ItineraryPlannerInput.model_validate(raw))
    routing = asyncio.run(
        build_routing_problem(
            problem,
            GeneratedMatrixProvider(),
            XanhSmTransportCostEstimator(),
        )
    )
    cheap = SafeTravel(1, 1, 1, 0)
    expensive = SafeTravel(100, 100, 1, 0)
    for activity in problem.valid_places:
        routing.travel_by_candidate_pair.update(
            {
                (activity.place_id, "corridor_lunch"): cheap,
                ("corridor_lunch", activity.place_id): cheap,
                (activity.place_id, "lunch_1"): expensive,
                ("lunch_1", activity.place_id): expensive,
            }
        )

    shortlist = build_day_shortlist(
        problem,
        routing,
        day=1,
        used_ids=frozenset(),
    )

    assert "corridor_lunch" in shortlist.hinted_order
    assert "lunch_1" not in shortlist.hinted_order


def test_hybrid_relaxes_hard_wait_only_after_strict_full_day_is_infeasible() -> None:
    activities = [
        candidate(
            "morning",
            opening_hours={"1": [{"startMinute": 600, "endMinute": 660}]},
        ),
        candidate(
            "afternoon",
            opening_hours={"1": [{"startMinute": 840, "endMinute": 900}]},
        ),
    ]
    problem = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(
            payload(places=activities, foods=meal_candidates())
        )
    )
    routing = asyncio.run(
        build_routing_problem(
            problem,
            GeneratedMatrixProvider(),
            XanhSmTransportCostEstimator(),
        )
    )

    with pytest.raises(OptimizationError, match="INFEASIBLE"):
        optimize_itinerary(problem, routing, config=FAST_CONFIG)

    result = optimize_hybrid_itinerary(problem, routing, config=FAST_CONFIG)

    assert {stop.place_id for stop in result.scheduled_stops} == {
        "breakfast_1",
        "morning",
        "lunch_1",
        "afternoon",
        "dinner_1",
    }


def test_hybrid_reuses_only_food_when_later_day_has_no_unique_meal_matching() -> None:
    activities = []
    for day in (1, 2):
        opening_hours = {
            "1": [] if day == 2 else [{"startMinute": 600, "endMinute": 660}],
            "2": [] if day == 1 else [{"startMinute": 600, "endMinute": 660}],
        }
        activities.append(candidate(f"morning_{day}", opening_hours=opening_hours))
        opening_hours = {
            "1": [] if day == 2 else [{"startMinute": 840, "endMinute": 900}],
            "2": [] if day == 1 else [{"startMinute": 840, "endMinute": 900}],
        }
        activities.append(candidate(f"afternoon_{day}", opening_hours=opening_hours))
    meal_hours = {
        "1": [{"startMinute": 480, "endMinute": 1230}],
        "2": [{"startMinute": 480, "endMinute": 1230}],
    }
    foods = [
        food(
            f"shared_{meal}",
            supported_meals=[meal],
            opening_hours=meal_hours,
        )
        for meal in ("breakfast", "lunch", "dinner")
    ]
    problem = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(
            payload(days=2, places=activities, foods=foods)
        )
    )
    routing = asyncio.run(
        build_routing_problem(
            problem,
            GeneratedMatrixProvider(),
            XanhSmTransportCostEstimator(),
        )
    )

    result = optimize_hybrid_itinerary(problem, routing, config=FAST_CONFIG)

    activity_stops = [
        stop.place_id
        for stop in result.scheduled_stops
        if not stop.place_id.startswith("shared_")
    ]
    food_stops = [
        stop.place_id
        for stop in result.scheduled_stops
        if stop.place_id.startswith("shared_")
    ]
    assert len(activity_stops) == len(set(activity_stops)) == 4
    assert sorted(food_stops) == sorted(
        f"shared_{meal}" for meal in ("breakfast", "lunch", "dinner") for _ in range(2)
    )
