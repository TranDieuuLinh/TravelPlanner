from collections.abc import Mapping

from app.modules.itinerary_planner.routing_models import CandidatePair, SafeTravel


MEAL_ACCESS_NEIGHBOR_LIMIT = 6


def meal_access_pairs(
    feasible: Mapping[CandidatePair, frozenset[int]],
    travel: Mapping[CandidatePair, SafeTravel],
    feasible_days_by_id: Mapping[str, frozenset[int]],
    food_ids: set[str],
    activity_ids: set[str],
) -> frozenset[CandidatePair]:
    selected: set[CandidatePair] = set()
    for origin_ids, destination_ids in (
        (activity_ids, food_ids),
        (food_ids, activity_ids),
    ):
        for origin_id in origin_ids:
            for day in feasible_days_by_id[origin_id]:
                _select_nearest(
                    selected,
                    feasible,
                    travel,
                    day=day,
                    origin_ids={origin_id},
                    destination_ids=destination_ids,
                )

    # Every meal candidate needs activity access in both directions per day.
    # The origin-oriented loop above alone can leave a lunch/dinner node with
    # no incoming activity arc after sparse neighbor pruning.
    for food_id in food_ids:
        for day in feasible_days_by_id[food_id]:
            _select_nearest(
                selected,
                feasible,
                travel,
                day=day,
                origin_ids={food_id},
                destination_ids=activity_ids,
                limit=MEAL_ACCESS_NEIGHBOR_LIMIT,
            )
            _select_nearest(
                selected,
                feasible,
                travel,
                day=day,
                origin_ids=activity_ids,
                destination_ids={food_id},
                limit=MEAL_ACCESS_NEIGHBOR_LIMIT,
            )
    return frozenset(selected)


def _select_nearest(
    selected: set[CandidatePair],
    feasible: Mapping[CandidatePair, frozenset[int]],
    travel: Mapping[CandidatePair, SafeTravel],
    *,
    day: int,
    origin_ids: set[str],
    destination_ids: set[str],
    limit: int = 1,
) -> None:
    options = [
        pair
        for pair, feasible_days in feasible.items()
        if pair[0] in origin_ids
        and pair[1] in destination_ids
        and day in feasible_days
    ]
    if options:
        selected.update(
            sorted(
                options,
                key=lambda pair: (travel[pair].safe_minutes, pair),
            )[:limit]
        )
