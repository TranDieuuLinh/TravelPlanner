from app.modules.place_checker.avoid_policy import has_avoid_conflict
from app.modules.place_checker.contract import TripEvaluationContext
from app.modules.place_checker.enums import IssueSeverity, OperationalStatus
from app.modules.place_checker.price_policy import has_planner_cost
from app.modules.place_checker.retrieval_contract import RetrievedCandidate

SEVERITY_VALUE = {
    IssueSeverity.critical: 1.0,
    IssueSeverity.high: 0.85,
    IssueSeverity.medium: 0.65,
    IssueSeverity.low: 0.45,
}


def hard_violations(
    candidate: RetrievedCandidate,
    context: TripEvaluationContext,
    labels: set[str],
) -> list[str]:
    reasons: list[str] = []
    if not candidate.planner_eligible:
        reasons.append("identity_not_verified")
    if candidate.adm_id and candidate.adm_id != context.destination.adm_id:
        reasons.append("destination_mismatch")
    if has_avoid_conflict(context.avoids, labels):
        reasons.append("avoid_conflict")
    metadata = candidate.metadata
    if metadata is not None and not has_planner_cost(
        category=candidate.category,
        minimum=metadata.minimum_cost,
        typical=metadata.typical_cost,
        maximum=metadata.maximum_cost,
        tier=metadata.cost_tier,
    ):
        reasons.append("missing_cost")
    if (
        candidate.category != "accommodation"
        and (metadata is None or metadata.typical_duration_minutes is None)
    ):
        reasons.append("missing_duration")
    if metadata and metadata.operational_status == OperationalStatus.permanently_closed:
        reasons.append("permanently_closed")
    if metadata and context.people.children and metadata.children_suitable is False:
        reasons.append("children_unsuitable")
    if metadata and context.people.infants and metadata.infants_suitable is False:
        reasons.append("infants_unsuitable")
    return reasons
