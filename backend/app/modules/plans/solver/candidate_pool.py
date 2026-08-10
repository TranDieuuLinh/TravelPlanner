from __future__ import annotations

import re
import unicodedata

from app.modules.plans.explorer.place_policy import is_meal_place
from app.modules.plans.place_selector.timeline_policy import (
    DEFAULT_ACTIVITY_DURATION_MINUTES,
)
from app.modules.plans.dto.agent_contracts import SelectedPlaceContext
from app.modules.plans.schema import SelectedPlaceCreate
from app.modules.plans.solver.contracts import (
    CandidatePool,
    PlanningCandidate,
    REQUIRED_EXPERIENCE_TIER,
    URL_SOURCE_TIER,
    USER_INTENT_TIER,
)


CandidatePlace = SelectedPlaceCreate | SelectedPlaceContext


def selected_place_priority_tier(place: CandidatePlace) -> int:
    """Return the user-visible commitment order for a selected Place.

    ``source_order`` only orders stops within a source itinerary. It must not
    outrank an explicit user choice. Required-experience markers are added by
    TripThemePlanner and therefore sit behind user and URL commitments.
    """

    refs = [ref.casefold() for ref in place.source_refs]
    is_required = any(ref.startswith("required_experience:") for ref in refs)
    is_url_source = bool(place.source_order) or any(
        ref.startswith(("http://", "https://")) or ref == "ocr" for ref in refs
    )
    if is_required:
        # Required-experience evidence commonly contains an HTTP claim URL;
        # only a real source-itinerary order proves that this was already a
        # URL stop before ThemePlanner attached the requirement marker.
        return URL_SOURCE_TIER if place.source_order else REQUIRED_EXPERIENCE_TIER
    if place.must_visit or not is_url_source:
        return USER_INTENT_TIER
    return URL_SOURCE_TIER


def selected_place_identity(place: CandidatePlace) -> str:
    if place.place_id:
        return f"place:{place.place_id}"
    normalized = unicodedata.normalize("NFKD", place.name.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return f"name:{slug or place.name.casefold()}"


def build_selected_place_pool(
    selected_places: list[CandidatePlace],
) -> CandidatePool:
    """Build only the pool that Planner owes to the user.

    URL/user-selected Places and resolved required experiences enter this
    pool. Catalog candidates considered later for gap filling deliberately do
    not: optional suggestions must never expand the trip or appear as unmet
    user commitments.
    """

    candidates: list[PlanningCandidate] = []
    seen: set[str] = set()
    for place in selected_places:
        candidate_id = selected_place_identity(place)
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        kind = (
            "meal"
            if is_meal_place(
                tags=place.tags,
                source_activity=place.source_activity,
                ontology_type=place.ontology_type,
            )
            else "activity"
        )
        candidates.append(
            PlanningCandidate(
                candidate_id=candidate_id,
                name=place.name,
                kind=kind,
                duration_minutes=(
                    place.source_duration_minutes
                    or DEFAULT_ACTIVITY_DURATION_MINUTES
                ),
                mandatory=True,
                latitude=place.latitude,
                longitude=place.longitude,
                source_order=place.source_order,
                source_day=place.source_day,
                priority_tier=selected_place_priority_tier(place),
            )
        )
    return CandidatePool(tuple(candidates))
