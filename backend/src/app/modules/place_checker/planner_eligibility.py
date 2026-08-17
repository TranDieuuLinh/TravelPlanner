from app.modules.place_checker.checked_output_contract import CheckedPlace
from app.modules.place_checker.enums import VerificationStatus
from app.modules.place_checker.planning_time_windows import (
    meals_for_hours,
    parse_planner_windows,
)
from app.modules.place_checker.planner_category import planner_category
from app.modules.place_checker.price_policy import has_planner_cost


def is_planner_eligible(checked: CheckedPlace) -> bool:
    base_eligible = bool(
        checked.place_id
        and checked.canonical_name
        and checked.coordinates
        and checked.duration.typical_minutes
        and has_planner_cost(
            category=planner_category(checked.category),
            minimum=checked.cost.minimum,
            typical=checked.cost.typical,
            maximum=checked.cost.maximum,
            tier=checked.cost.tier,
        )
        and checked.evaluation.planner_eligible
        and (checked.mandatory or not checked.evaluation.avoid_conflicts)
        and checked.verification.status
        in {VerificationStatus.verified_kg, VerificationStatus.verified_external}
    )
    if not base_eligible:
        return False
    if planner_category(checked.category) not in {"restaurant", "drink_dessert"}:
        return True
    return bool(
        checked.opening.hours
        and parse_planner_windows(checked.opening.hours)
        and meals_for_hours(checked.opening.hours)
    )
