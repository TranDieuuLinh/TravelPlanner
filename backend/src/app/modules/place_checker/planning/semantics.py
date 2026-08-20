from __future__ import annotations

import re

from app.modules.place_checker.relationship_contract import PlaceRelationshipEvidence


KNOWN_TRIP_STYLES = frozenset(
    {
        "adventure",
        "cultural_immersion",
        "local_life",
        "luxury",
        "night_owl",
        "relaxed",
        "romantic",
        "slow_travel",
    }
)
TECHNICAL_TAG_PREFIXES = (
    "food-item:",
    "food:",
    "item:",
    "pool_category:",
    "relationship:",
    "retrieval:",
    "style:",
)


def normalize_label(value: str) -> str:
    normalized = re.sub(r"[^\w]+", "_", value.strip().casefold(), flags=re.UNICODE)
    return normalized.strip("_")


def split_trip_preferences(
    preferences: list[str], avoids: list[str]
) -> tuple[list[str], list[str], list[str]]:
    tags: list[str] = []
    styles: list[str] = []
    for value in preferences:
        is_prefixed_style = value.casefold().startswith("style:")
        raw_value = value.split(":", 1)[1] if is_prefixed_style else value
        normalized = normalize_label(raw_value)
        target = (
            styles if is_prefixed_style or normalized in KNOWN_TRIP_STYLES else tags
        )
        if normalized and normalized not in target:
            target.append(normalized)
    avoid_tags = list(
        dict.fromkeys(
            normalize_label(value) for value in avoids if normalize_label(value)
        )
    )
    return tags, avoid_tags, styles


def candidate_semantics(
    tags: list[str], relationships: list[PlaceRelationshipEvidence]
) -> tuple[list[str], list[str]]:
    semantic_tags = list(
        dict.fromkeys(
            value
            for value in tags
            if value.strip()
            and not value.casefold().startswith(TECHNICAL_TAG_PREFIXES)
            and value.casefold() != "experience:special_experience"
        )
    )
    del relationships  # Has_Style is metadata inheritance, not planner semantics.
    return semantic_tags, []


def audience_values(
    *, adults: bool | None, children: bool | None, infants: bool | None
) -> tuple[bool | None, bool | None]:
    if children is True or infants is True:
        kid_suitable = True
    elif children is False and infants is False:
        kid_suitable = False
    else:
        kid_suitable = None
    adult_only = (
        True
        if adults is True and kid_suitable is False
        else (False if kid_suitable is True else None)
    )
    return adult_only, kid_suitable
