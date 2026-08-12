from datetime import UTC, datetime, timedelta

from app.modules.place_checker.enums import (
    CostTier,
    PlaceLifecycleState,
)
from app.modules.place_checker.evaluation_contract import (
    DataQualityEvaluation,
    EvaluationFinding,
    PlannerConstraint,
)
from app.modules.place_checker.resolution_contract import EnrichedIdentityPlace
from app.shared.tools.search_places.normalization import normalize_text
from app.modules.place_checker.taxonomy import canonical_label, canonical_labels


STALE_AFTER = timedelta(days=30)
PLANNER_ELIGIBLE_STATES = {
    PlaceLifecycleState.planner_ready,
    PlaceLifecycleState.conditional,
}


def evaluate_data_quality(
    place: EnrichedIdentityPlace,
    now: datetime,
) -> DataQualityEvaluation:
    metadata = place.metadata
    fields = {
        "coordinates": metadata.coordinates if metadata else None,
        "category": metadata.category if metadata else None,
        "duration": metadata.typical_duration_minutes if metadata else None,
        "cost": known_cost(metadata),
        "opening_hours": metadata.opening_hours if metadata else None,
        "operational_status": (
            metadata.operational_status.value
            if metadata and metadata.operational_status.value != "unknown"
            else None
        ),
        "freshness": metadata.fetched_at if metadata else None,
    }
    missing = [name for name, value in fields.items() if value is None]
    completeness = round((len(fields) - len(missing)) / len(fields), 6)
    stale = bool(
        metadata
        and metadata.fetched_at
        and now - as_utc(metadata.fetched_at) > STALE_AFTER
    )
    return DataQualityEvaluation(
        completeness_score=completeness,
        missing_fields=missing,
        stale=stale,
    )


def known_cost(metadata) -> object | None:
    if metadata is None:
        return None
    if metadata.cost_tier != CostTier.unknown:
        return metadata.cost_tier
    return metadata.typical_cost


def destination_compatible(place: EnrichedIdentityPlace) -> bool | None:
    matching = [
        option
        for option in place.match_options
        if place.place_id and option.place.place_id == place.place_id
    ]
    return matching[0].eligible_destination if matching else None


def place_labels(place: EnrichedIdentityPlace) -> set[str]:
    metadata = place.metadata
    values = [
        place.canonical_name or "",
        *place.original_names,
        *place.aliases,
        *(metadata.tags if metadata else []),
        metadata.category if metadata and metadata.category else "",
    ]
    return {normalize_text(value) for value in values if value}


def matching_labels(values: list[str], labels: set[str]) -> list[str]:
    canonical_place_labels = canonical_labels(labels)
    return [
        value
        for value in values
        if canonical_label(value) in canonical_place_labels
    ]


def final_state(
    place: EnrichedIdentityPlace,
    findings: list[EvaluationFinding],
    constraints: list[PlannerConstraint],
    avoid_conflicts: list[str],
) -> PlaceLifecycleState:
    if any(finding.hard for finding in findings):
        return (
            PlaceLifecycleState.blocked
            if place.mandatory
            else PlaceLifecycleState.rejected
        )
    nightlife_conflict = any(
        normalize_text(value) == "nightlife" for value in avoid_conflicts
    )
    if nightlife_conflict and not place.mandatory:
        return PlaceLifecycleState.rejected
    if findings or constraints:
        return PlaceLifecycleState.conditional
    return PlaceLifecycleState.planner_ready


def unique_constraints(
    constraints: list[PlannerConstraint],
) -> list[PlannerConstraint]:
    result: list[PlannerConstraint] = []
    seen: set[tuple[str, str]] = set()
    for constraint in constraints:
        key = (constraint.code, constraint.message)
        if key not in seen:
            seen.add(key)
            result.append(constraint)
    return result


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
