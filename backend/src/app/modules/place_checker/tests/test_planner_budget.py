import asyncio
from math import ceil

from app.modules.place_checker.planning_output import PlaceCheckerPlannerOutputBuilder
from app.modules.place_checker.tests.test_pipeline_output import payload, pipeline


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * percentile)]


def test_estimates_non_hanoi_budget_from_adm_candidate_prices() -> None:
    result = asyncio.run(pipeline().check(payload(), request_id="request-adm-budget"))
    sample = result.checked_places[0]
    accommodations = [
        sample.model_copy(
            update={
                "place_id": f"hotel:{index}",
                "canonical_name": f"Hotel {index}",
                "category": "accommodation",
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
        for index, price in enumerate((100_000, 200_000, 300_000, 400_000, 500_000))
    ]
    destination = result.trip_context.destination.model_copy(
        update={
            "adm_id": "adm1_vn_thua_thien_hue",
            "canonical_name": "Huế",
        }
    )
    context = result.trip_context.model_copy(
        update={
            "destination": destination,
            "days": 3,
            "people": result.trip_context.people.model_copy(update={"adults": 2}),
        }
    )
    result = result.model_copy(
        update={
            "trip_context": context,
            "checked_places": [*result.checked_places, *accommodations],
        }
    )

    output = PlaceCheckerPlannerOutputBuilder().build(
        result,
        start_date="2026-08-20",
        timezone="Asia/Ho_Chi_Minh",
    )

    budget = output.trip.budget
    assert budget.source == "estimated_daily_cost"
    assert budget.profile_version is not None
    assert "adm1_vn_thua_thien_hue" in budget.profile_version
    assert budget.daily_estimate is not None
    expected_accommodation = 100_000
    expected_food = ceil(_percentile([item.price.cost for item in output.food], 0.25) * 3)
    expected_activities = ceil(
        _percentile([item.price.cost for item in output.places], 0.25) * 2
    )
    assert budget.daily_estimate.accommodation == expected_accommodation
    assert budget.daily_estimate.food == expected_food
    assert budget.daily_estimate.activities == expected_activities
    assert budget.daily_estimate.local_transport == 171_580
    assert budget.amount == (
        (expected_food + expected_activities + 171_580) * 3
        + expected_accommodation * 2
    )
