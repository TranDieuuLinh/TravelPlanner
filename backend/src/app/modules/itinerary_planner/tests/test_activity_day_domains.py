from app.modules.itinerary_planner.activity_day_domains import project_activity_days
from app.modules.itinerary_planner.contract import PlannerCandidate
from app.modules.itinerary_planner.tests.factories import candidate


def test_dense_balanced_projection_does_not_use_isolated_outlier_as_center() -> None:
    raw_places = [candidate(f"city_{index:02d}") for index in range(41)]
    for index, item in enumerate(raw_places):
        item["coordinates"] = {
            "latitude": 21.02 + index / 100_000,
            "longitude": 105.84 + index / 100_000,
        }
    outlier = candidate("zz_ba_vi")
    outlier["coordinates"] = {"latitude": 21.13, "longitude": 105.38}
    places = [PlannerCandidate.model_validate(item) for item in [*raw_places, outlier]]
    original_days = {item.place_id: frozenset({1, 2, 3}) for item in places}

    projection = project_activity_days(
        days=3,
        places=places,
        feasible_days=original_days,
    )

    assert all(center.place_id != "zz_ba_vi" for center in projection.center_by_day.values())
    assert [
        sum(day in projection.feasible_days[item.place_id] for item in places)
        for day in range(1, 4)
    ] == [14, 14, 14]
