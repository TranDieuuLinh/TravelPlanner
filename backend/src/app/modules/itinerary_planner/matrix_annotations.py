from app.modules.itinerary_planner.contract import FoodVenueType
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.routing_models import MatrixCell, TravelMatrix


def annotate_food_to_food(
    matrix: TravelMatrix,
    node_to_candidates: dict[str, tuple[str, ...]],
    problem: PreparedPlanningProblem,
) -> TravelMatrix:
    restaurant_ids = {
        candidate.place_id
        for candidate in problem.valid_food
        if candidate.venue_type == FoodVenueType.restaurant
    }
    rows = []
    for origin_index, row in enumerate(matrix.cells):
        origin_ids = node_to_candidates[matrix.node_ids[origin_index]]
        parsed_row = []
        for destination_index, cell in enumerate(row):
            destination_ids = node_to_candidates[matrix.node_ids[destination_index]]
            food_to_food = any(
                origin_id in restaurant_ids and destination_id in restaurant_ids
                for origin_id in origin_ids
                for destination_id in destination_ids
            )
            parsed_row.append(
                MatrixCell(
                    cell.duration_seconds,
                    cell.distance_meters,
                    cell.reachable,
                    food_to_food,
                )
            )
        rows.append(tuple(parsed_row))
    return TravelMatrix(
        node_ids=matrix.node_ids,
        cells=tuple(rows),
        profile=matrix.profile,
        provider=matrix.provider,
        provider_version=matrix.provider_version,
        cache_key=matrix.cache_key,
    )
