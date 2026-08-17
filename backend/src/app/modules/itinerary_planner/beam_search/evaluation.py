from __future__ import annotations

from collections import Counter
from statistics import median

from pydantic import Field

from app.modules.itinerary_planner.beam_search.constraints import (
    is_drink_dessert,
    is_entertainment,
    is_restaurant,
    is_travelplace,
)
from app.modules.itinerary_planner.contract import PlannerContractModel
from app.modules.itinerary_planner.optimizer.result import OptimizationResult
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.routing_models import RoutingProblem


class BeamSearchEvaluation(PlannerContractModel):
    rating_min: float | None = None
    rating_max: float | None = None
    rating_median: float | None = None
    review_count_min: int | None = None
    review_count_max: int | None = None
    review_count_median: int | None = None
    distance_meters_min: int | None = None
    distance_meters_max: int | None = None
    distance_meters_median: int | None = None
    tags: dict[str, int] = Field(default_factory=dict)
    styles: dict[str, int] = Field(default_factory=dict)
    items: dict[str, int] = Field(default_factory=dict)
    count_restaurant: int = 0
    count_drink_dessert: int = 0
    count_entertainment: int = 0
    count_travelplace: int = 0
    total_price: int = 0
    score: float = 0.0


def evaluate_plan(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    result: OptimizationResult,
) -> BeamSearchEvaluation:
    # Metrics describe itinerary visits, not only distinct candidate IDs.  A
    # restaurant may now be revisited, so evaluating selected_ids would hide
    # those visits because the aggregate plan stores IDs as a set.
    candidates = [
        problem.candidate_by_id[stop.place_id] for stop in result.scheduled_stops
    ]
    ratings = [item.rating for item in candidates if item.rating is not None]
    reviews = [item.review_count for item in candidates if item.review_count is not None]
    distances = [
        routing.travel_by_candidate_pair[(arc.origin_id, arc.destination_id)].distance_meters
        for arc in result.selected_arcs
        if (arc.origin_id, arc.destination_id) in routing.travel_by_candidate_pair
    ]
    return BeamSearchEvaluation(
        rating_min=min(ratings) if ratings else None,
        rating_max=max(ratings) if ratings else None,
        rating_median=median(ratings) if ratings else None,
        review_count_min=min(reviews) if reviews else None,
        review_count_max=max(reviews) if reviews else None,
        review_count_median=int(round(median(reviews))) if reviews else None,
        distance_meters_min=min(distances) if distances else None,
        distance_meters_max=max(distances) if distances else None,
        distance_meters_median=(
            int(round(median(distances))) if distances else None
        ),
        tags=dict(Counter(tag for item in candidates for tag in item.tags)),
        styles=dict(Counter(style for item in candidates for style in item.styles)),
        items=dict(
            Counter(
                activity_id
                for item in candidates
                for activity_id in item.offered_activity_ids
            )
        ),
        count_restaurant=sum(is_restaurant(item) for item in candidates),
        count_drink_dessert=sum(is_drink_dessert(item) for item in candidates),
        count_entertainment=sum(is_entertainment(item) for item in candidates),
        count_travelplace=sum(is_travelplace(item) for item in candidates),
        total_price=result.total_cost_per_person,
        score=float(result.objective_value),
    )
