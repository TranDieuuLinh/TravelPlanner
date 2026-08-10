from __future__ import annotations

import re
import unicodedata

from app.modules.plans.explorer.place_policy import is_meal_place
from app.modules.plans.place_selector.timeline_policy import (
    DEFAULT_ACTIVITY_DURATION_MINUTES,
)
from app.modules.plans.dto.agent_contracts import SelectedPlaceContext
from app.modules.plans.schema import SelectedPlaceCreate
from app.modules.plans.solver.contracts import CandidatePool, PlanningCandidate


CandidatePlace = SelectedPlaceCreate | SelectedPlaceContext


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
            )
        )
    return CandidatePool(tuple(candidates))
