"""Day style classification for the PlaceSelector day skeleton.

The PlaceSelector can build two distinct day-shape strategies. The choice between
them is driven by the average expected duration of the activities the user
explicitly attached to the day (via ``selected_places``).

The ``places`` domain schema no longer exposes the old ``min_duration`` /
``max_duration`` columns, so we infer the expected activity length from the
place's semantic ``category`` (museum / park / cafe / shopping …).

Two styles are produced:

* ``anchor_day``: 1 main activity in the morning, then meals + support
  activities spread around it. Suits "long" places such as museums, parks,
  zoos, theme parks.
* ``scattered_day``: many short stops with meals interleaved. Suits
  cafes, bakeries, street food, shopping, statues.

The decision uses a simple majority rule: when >= 60 % of the
non-meal selected places fall into one bucket, that bucket wins. Ties and
empty inputs default to ``anchor_day`` because it provides a richer skeleton
that the PlaceSelector can downgrade block-by-block.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.modules.plans.place_selector.place_tool import (
    SelectablePlace,
    place_category,
)


class DayStyle(str, Enum):
    """Identifies which day-shape the skeleton builder should emit."""

    anchor_day = "anchor_day"
    scattered_day = "scattered_day"


# ``category -> "anchor" | "scattered"``.
# Anchor categories are venues that typically swallow 2+ hours.
# Scattered categories are short visits (under ~75 minutes).
ANCHOR_CATEGORIES: frozenset[str] = frozenset(
    {
        "attraction",
        "nature",
    }
)
SCATTERED_CATEGORIES: frozenset[str] = frozenset(
    {
        "shopping",
        "entertainment",
    }
)
# Categories whose items default to "meal" (lunch/dinner) treatment. We keep
# them out of the day-style vote because attaching a restaurant to a day
# must not by itself force the day into scattered shape.
MEAL_CATEGORIES: frozenset[str] = frozenset({"Restaurant"})
# Quick stops may be activities (notably cafe/coffee) or short food visits.
# They shape a scattered day without becoming a breakfast/lunch/dinner meal.
QUICK_BITE_PLACE_TYPES: frozenset[str] = frozenset(
    {
        "bakery",
        "cafe",
        "coffee_shop",
        "ice_cream",
        "quan_cafe",
        "quan_coffee",
        "quan_tra",
        "tiem_banh",
        "che",
        "bingsu",
        "tra_sua",
    }
)

MAJORITY_THRESHOLD = 0.60


@dataclass(frozen=True)
class DayStyleDecision:
    """Diagnostic payload returned by :func:`select_day_style`.

    Tests and tooling rely on the breakdown to assert the classifier picked
    the correct style. Production code only needs :attr:`style`.
    """

    style: DayStyle
    anchor_count: int
    scattered_count: int
    excluded_count: int
    total_considered: int


def classify_place(place: SelectablePlace) -> str | None:
    """Return ``"anchor"``, ``"scattered"``, or ``None``.

    ``None`` means the place cannot influence the day-style decision
    (accommodation, transport, regular restaurant, or unknown category).

    ``Restaurant`` places are normally treated as meals and excluded. Quick
    stops such as cafes remain activities but push the day towards
    ``scattered_day``.
    """

    category = place_category(place)
    if category is None:
        return None
    place_type = (place.place_type or "").strip().casefold()
    if place_type in QUICK_BITE_PLACE_TYPES:
        return "scattered"
    if category in ANCHOR_CATEGORIES:
        return "anchor"
    if category in SCATTERED_CATEGORIES:
        return "scattered"
    if category in MEAL_CATEGORIES:
        return None
    return None


def select_day_style(
    selected_places: list[SelectablePlace] | None,
    *,
    area_profile_distribution: dict[str, int] | None = None,
) -> DayStyleDecision:
    """Pick the day style that best fits the attached places.

    ``area_profile_distribution`` is the per-category place count produced by
    :class:`AreaSurveyService`. It is only consulted as a tie-breaker when
    the user's selected places are empty or balanced.
    """

    anchor_count = 0
    scattered_count = 0
    excluded_count = 0

    for place in selected_places or ():
        classification = classify_place(place)
        if classification == "anchor":
            anchor_count += 1
        elif classification == "scattered":
            scattered_count += 1
        else:
            excluded_count += 1

    total_considered = anchor_count + scattered_count

    style = _decide(
        anchor_count=anchor_count,
        scattered_count=scattered_count,
        distribution=area_profile_distribution,
    )

    return DayStyleDecision(
        style=style,
        anchor_count=anchor_count,
        scattered_count=scattered_count,
        excluded_count=excluded_count,
        total_considered=total_considered,
    )


def _decide(
    *,
    anchor_count: int,
    scattered_count: int,
    distribution: dict[str, int] | None,
) -> DayStyle:
    if anchor_count or scattered_count:
        total = anchor_count + scattered_count
        anchor_ratio = anchor_count / total
        scattered_ratio = scattered_count / total
        if anchor_ratio >= MAJORITY_THRESHOLD:
            return DayStyle.anchor_day
        if scattered_ratio >= MAJORITY_THRESHOLD:
            return DayStyle.scattered_day

    # Fallback: ask the area profile. If the area is dominated by short
    # activities (shopping / scattered-type categories outweigh attractions)
    # we lean scattered; otherwise default to anchor (richer skeleton).
    if distribution:
        anchor_pool = sum(
            count
            for category, count in distribution.items()
            if category in ANCHOR_CATEGORIES
        )
        scattered_pool = sum(
            count
            for category, count in distribution.items()
            if category in SCATTERED_CATEGORIES
        )
        if anchor_pool or scattered_pool:
            total = anchor_pool + scattered_pool
            if total:
                scattered_ratio = scattered_pool / total
                if scattered_ratio >= MAJORITY_THRESHOLD:
                    return DayStyle.scattered_day

    return DayStyle.anchor_day
