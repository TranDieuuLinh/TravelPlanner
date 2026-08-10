from __future__ import annotations

import re
import unicodedata


NON_TOURISM_PLACE_TYPES = frozenset(
    {
        "accounting",
        "administrative_office",
        "bank",
        "car_dealer",
        "car_repair",
        "cemetery",
        "community_center",
        "congregation",
        "consultant",
        "courthouse",
        "doctor",
        "dentist",
        "education_center",
        "education_consultant",
        "embassy",
        "employment_agency",
        "fire_station",
        "funeral_home",
        "health_consultant",
        "hospital",
        "insurance_agency",
        "lawyer",
        "local_government_office",
        "medical_center",
        "medical_clinic",
        "police",
        "post_office",
        "real_estate_agency",
        "school",
        "university",
        "village_hall",
    }
)

_NON_VISIT_NAME_MARKERS = (
    "phong kham",
    "medical clinic",
    "dental clinic",
    "tu van giao duc",
    "education consultant",
    "real estate",
    "van phong cong ty",
    "company office",
    "employment agency",
)


def normalize_place_type(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", (value or "").casefold())
    ascii_value = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9]+", "_", ascii_value).strip("_")


def is_default_travel_eligible(
    *,
    name: str,
    place_type: str | None,
    tags: list[str],
) -> bool:
    """Reject operational/service venues from automatic gap filling.

    Explicitly selected places bypass this policy at the caller, allowing a
    user to request practical stops such as a clinic without making them
    eligible as unsolicited itinerary activities.
    """

    structured_types = {
        normalize_place_type(place_type),
        *(normalize_place_type(tag) for tag in tags),
    }
    if structured_types.intersection(NON_TOURISM_PLACE_TYPES):
        return False
    normalized_name = normalize_place_type(name).replace("_", " ")
    return not any(marker in normalized_name for marker in _NON_VISIT_NAME_MARKERS)
