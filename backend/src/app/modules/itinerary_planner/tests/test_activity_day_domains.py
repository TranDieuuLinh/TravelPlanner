from app.modules.itinerary_planner.activity_day_domains import (
    _normalized_knn_density,
    project_activity_days,
)
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
    daily_counts = [
        sum(day in projection.preferred_days[item.place_id] for item in places)
        for day in range(1, 4)
    ]
    assert all(count >= 14 for count in daily_counts)
    assert all(
        1 <= len(projection.preferred_days[item.place_id]) <= 2
        for item in places
    )


def test_knn_density_scores_compact_cluster_above_outlier() -> None:
    raw_places = [candidate(f"cluster_{index}") for index in range(11)]
    for index, item in enumerate(raw_places):
        item["coordinates"] = {
            "latitude": 21.02 + index / 10_000,
            "longitude": 105.84,
        }
    outlier = candidate("outlier")
    outlier["coordinates"] = {"latitude": 21.2, "longitude": 105.4}
    places = [
        PlannerCandidate.model_validate(item)
        for item in [*raw_places, outlier]
    ]

    density = _normalized_knn_density(places)

    assert density["outlier"] == 0
    assert min(density[item.place_id] for item in places[:-1]) > 0
