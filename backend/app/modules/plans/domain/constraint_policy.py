from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class GeographicScopeType(StrEnum):
    unrestricted = "unrestricted"
    coastal = "coastal"


class GeographicScopePolicy(BaseModel):
    type: GeographicScopeType = GeographicScopeType.unrestricted


class ConstraintPolicy(BaseModel):
    excluded_place_types: Annotated[
        list[str],
        Field(default_factory=list, alias="excludedPlaceTypes"),
    ]
    geographic_scope: Annotated[
        GeographicScopePolicy,
        Field(default_factory=GeographicScopePolicy, alias="geographicScope"),
    ]

    model_config = {"populate_by_name": True}

    @field_validator("excluded_place_types")
    @classmethod
    def normalize_excluded_place_types(cls, values: list[str]) -> list[str]:
        return list(
            dict.fromkeys(
                normalized
                for value in values
                if (normalized := normalize_constraint_value(value))
            )
        )


_EXCLUDED_TYPE_ALIASES: dict[str, set[str]] = {
    "cemetery": {
        "cemetery",
        "graveyard",
        "grave_yard",
        "burial_ground",
        "nghia_trang",
    },
}

_COASTAL_EVIDENCE_TERMS = {
    "beach",
    "beachfront",
    "bo_bien",
    "coast",
    "coastal",
    "dao",
    "island",
    "marina",
    "seaside",
    "ven_bien",
    "waterfront",
}


def normalize_constraint_value(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "_", without_marks).strip("_")


def constraint_policy_rejection(
    policy: ConstraintPolicy,
    *,
    name: str,
    place_type: str,
    tags: list[str],
    region_key: str | None,
) -> tuple[str, str] | None:
    evidence_values = {
        normalize_constraint_value(value)
        for value in (name, place_type, *tags)
        if value
    }
    for excluded_type in policy.excluded_place_types:
        aliases = _EXCLUDED_TYPE_ALIASES.get(
            excluded_type,
            {excluded_type},
        )
        if any(
            _contains_term(evidence, alias)
            for evidence in evidence_values
            for alias in aliases
        ):
            return (
                "excluded_place_type",
                f"Place matches the excluded type '{excluded_type}'.",
            )

    if policy.geographic_scope.type == GeographicScopeType.coastal:
        geographic_evidence = {
            normalize_constraint_value(value)
            for value in (place_type, *tags, region_key or "")
            if value
        }
        if not any(
            _contains_term(evidence, marker)
            for evidence in geographic_evidence
            for marker in _COASTAL_EVIDENCE_TERMS
        ):
            return (
                "outside_geographic_scope",
                "Place has no structured evidence that it is in a coastal area.",
            )
    return None


def _contains_term(value: str, term: str) -> bool:
    return value == term or value.startswith(f"{term}_") or value.endswith(
        f"_{term}"
    ) or f"_{term}_" in value
