from __future__ import annotations

import re

from app.modules.itinerary_planner.contract import (
    PlannerCandidate,
    PlannerFoodCandidate,
    PlannerTrip,
)


Candidate = PlannerCandidate | PlannerFoodCandidate


def normalize_tag(value: str) -> str:
    normalized = re.sub(r"[^\w]+", "_", value.strip().casefold(), flags=re.UNICODE)
    return normalized.strip("_")


def normalize_tags(values: list[str]) -> list[str]:
    normalized = (normalize_tag(value) for value in values)
    return list(dict.fromkeys(value for value in normalized if value))


def normalize_candidate(candidate: Candidate) -> Candidate:
    return candidate.model_copy(
        update={
            "tags": normalize_tags(candidate.tags),
            "styles": normalize_tags(candidate.styles),
        }
    )


def normalize_trip(trip: PlannerTrip) -> PlannerTrip:
    preferences = trip.preferences.model_copy(
        update={
            "tags": normalize_tags(trip.preferences.tags),
            "avoid_tags": normalize_tags(trip.preferences.avoid_tags),
            "styles": normalize_tags(trip.preferences.styles),
        }
    )
    return trip.model_copy(update={"preferences": preferences})


def eligibility_failure(
    candidate: Candidate,
    trip: PlannerTrip,
) -> tuple[str, str] | None:
    avoided = sorted(set(candidate.tags) & set(trip.preferences.avoid_tags))
    if avoided:
        return (
            "avoided_tag",
            "Candidate matches avoided tags: " + ", ".join(avoided),
        )
    kids = trip.party.kids if trip.party is not None else 0
    if kids and candidate.audience.adult_only is True:
        return "adult_only", "Candidate is adult-only but the trip includes kids."
    if kids and candidate.audience.kid_suitable is False:
        return (
            "not_kid_suitable",
            "Candidate is not suitable for a trip that includes kids.",
        )
    return None
