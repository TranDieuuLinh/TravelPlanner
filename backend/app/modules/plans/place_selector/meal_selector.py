from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from app.modules.plans.domain.entities import PlanItem
from app.modules.plans.place_selector.place_tool import (
    SelectablePlace,
    PlaceSelectionTool,
    place_category,
    selection_relevance_score,
)


class MealStopSelector:
    """Choose three food stops after the two daily activities are fixed."""

    candidate_limit = 250
    radius_steps_meters = (1_500, 3_000, 5_000, float("inf"))

    def __init__(self, place_tool: PlaceSelectionTool) -> None:
        self.place_tool = place_tool

    def select_for_day(
        self,
        *,
        region_key: str,
        activities: list[PlanItem],
        excluded_place_ids: set[str],
        bbox_filter: tuple[float, float, float, float] | None = None,
    ) -> dict[str, SelectablePlace | None]:
        if not activities:
            return {"breakfast_meal": None, "lunch_meal": None, "dinner_meal": None}

        first = activities[0]
        second = activities[-1]
        selected: dict[str, SelectablePlace | None] = {}
        used = set(excluded_place_ids)
        for role, terms in (
            ("breakfast_meal", ["breakfast", "bakery", "food"]),
            ("lunch_meal", ["lunch", "local food", "restaurant"]),
            ("dinner_meal", ["dinner", "local food", "restaurant"]),
        ):
            candidates = self._candidates(
                region_key=region_key,
                target_tags=terms,
                excluded_place_ids=used,
                bbox_filter=bbox_filter,
            )
            chosen = self._choose(
                candidates,
                role=role,
                first=first,
                second=second,
                region_key=region_key,
                target_tags=terms,
            )
            selected[role] = chosen
            if chosen is not None:
                used.add(chosen.stable_ref)
                if chosen.place_id is not None:
                    used.add(chosen.place_id)
        return selected

    def _candidates(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        bbox_filter: tuple[float, float, float, float] | None,
    ) -> list[SelectablePlace]:
        candidates = self.place_tool.search(
            region_key=region_key,
            target_tags=target_tags,
            excluded_place_ids=excluded_place_ids,
            limit=self.candidate_limit,
            bbox_filter=bbox_filter,
        )
        if not candidates and bbox_filter is not None:
            candidates = self.place_tool.search(
                region_key=region_key,
                target_tags=target_tags,
                excluded_place_ids=excluded_place_ids,
                limit=self.candidate_limit,
            )
        return [
            candidate
            for candidate in candidates
            if place_category(candidate) == "food_drink"
        ]

    def _choose(
        self,
        candidates: list[SelectablePlace],
        *,
        role: str,
        first: PlanItem,
        second: PlanItem,
        region_key: str,
        target_tags: list[str],
    ) -> SelectablePlace | None:
        located = [
            (rank, candidate)
            for rank, candidate in enumerate(candidates)
            if candidate.latitude is not None and candidate.longitude is not None
        ]
        if not located:
            return candidates[0] if candidates else None

        scored = [
            (
                -selection_relevance_score(
                    candidate,
                    region_key=region_key,
                    target_tags=target_tags,
                ),
                self._route_cost(candidate, role=role, first=first, second=second),
                rank,
                candidate,
            )
            for rank, candidate in located
        ]
        return min(
            scored,
            key=lambda entry: (
                entry[0],
                entry[1],
                entry[2],
                entry[3].name.casefold(),
            ),
        )[3]

    def _route_cost(
        self,
        candidate: SelectablePlace,
        *,
        role: str,
        first: PlanItem,
        second: PlanItem,
    ) -> float:
        candidate_coordinate = self._coordinate(candidate)
        first_coordinate = self._coordinate(first)
        second_coordinate = self._coordinate(second)
        if candidate_coordinate is None:
            return float("inf")
        if role == "breakfast_meal":
            return self._distance(candidate_coordinate, first_coordinate)
        if role == "dinner_meal":
            return self._distance(second_coordinate, candidate_coordinate)
        direct = self._distance(first_coordinate, second_coordinate)
        return max(
            0.0,
            self._distance(first_coordinate, candidate_coordinate)
            + self._distance(candidate_coordinate, second_coordinate)
            - direct,
        )

    @staticmethod
    def _coordinate(value) -> tuple[float, float] | None:
        latitude = getattr(value, "latitude", None)
        longitude = getattr(value, "longitude", None)
        if latitude is None or longitude is None:
            return None
        return float(latitude), float(longitude)

    @staticmethod
    def _distance(
        left: tuple[float, float] | None,
        right: tuple[float, float] | None,
    ) -> float:
        if left is None or right is None:
            return float("inf")
        latitude_1, longitude_1 = map(radians, left)
        latitude_2, longitude_2 = map(radians, right)
        delta_latitude = latitude_2 - latitude_1
        delta_longitude = longitude_2 - longitude_1
        value = (
            sin(delta_latitude / 2) ** 2
            + cos(latitude_1)
            * cos(latitude_2)
            * sin(delta_longitude / 2) ** 2
        )
        return 6_371_000 * 2 * asin(sqrt(value))
