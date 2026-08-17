from app.modules.place_checker.checked_output_contract import CheckedPlace
from app.modules.place_checker.enums import SourceTier, VerificationStatus
from app.modules.place_checker.output_contract import PlannerExcludedCandidate
from app.modules.place_checker.price_policy import has_planner_cost


def build_excluded_candidate(checked: CheckedPlace) -> PlannerExcludedCandidate:
    if not checked.place_id or not checked.canonical_name:
        code = "missing_canonical_identity"
        message = "The requested place could not be resolved to a canonical identity."
    elif checked.coordinates is None:
        code = "missing_coordinates"
        message = "The requested place has no usable coordinates."
    elif not checked.duration.typical_minutes:
        code = "missing_duration"
        message = "The requested place has no usable visit duration."
    elif not has_planner_cost(
        category=checked.category,
        minimum=checked.cost.minimum,
        typical=checked.cost.typical,
        maximum=checked.cost.maximum,
        tier=checked.cost.tier,
    ):
        code = "missing_cost"
        message = "The requested place has no usable cost estimate."
    elif not checked.evaluation.planner_eligible:
        code = f"place_checker_{checked.evaluation.state.value}"
        message = next(
            (item.message for item in checked.evaluation.findings if item.message),
            "The requested place is not eligible for itinerary planning.",
        )
    elif checked.verification.status not in {
        VerificationStatus.verified_kg,
        VerificationStatus.verified_external,
    }:
        code = "verification_required"
        message = "The requested place must be verified before itinerary planning."
    else:
        code = "place_checker_excluded"
        message = "The requested place was excluded before itinerary optimization."
    name = checked.canonical_name or next(iter(checked.original_names), "Requested place")
    return PlannerExcludedCandidate(
        place_id=checked.place_id or f"unresolved:{name}",
        name=name,
        priority="url" if checked.source_tier == SourceTier.url else "user_input",
        reason_code=code,
        message=message,
    )
