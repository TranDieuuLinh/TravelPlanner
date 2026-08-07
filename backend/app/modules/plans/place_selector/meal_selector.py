from __future__ import annotations

from math import asin, cos, log10, radians, sin, sqrt
import re

from app.modules.plans.domain.entities import PlanItem
from app.modules.plans.place_selector.place_tool import (
    SelectablePlace,
    PlaceSelectionTool,
    is_coffee_place,
    selection_relevance_score,
)
from app.modules.plans.explorer.place_policy import is_meal_place
from app.modules.plans.place_selector.meal_node_planner import MealNodePlanner, MealNodeSelection


class MealStopSelector:
    """Choose three food stops after the two daily activities are fixed."""

    candidate_limit = 250
    radius_steps_meters = (1_500, 3_000, 5_000, float("inf"))

    def __init__(
        self,
        place_tool: PlaceSelectionTool,
        *,
        graph_repository=None,
        meal_node_planner: MealNodePlanner | None = None,
    ) -> None:
        self.place_tool = place_tool
        self.graph_repository = graph_repository
        self.meal_node_planner = meal_node_planner

    def select_for_day(
        self,
        *,
        region_key: str,
        activities: list[PlanItem],
        excluded_place_ids: set[str],
        bbox_filter: tuple[float, float, float, float] | None = None,
        interests: list[str] | None = None,
    ) -> dict[str, SelectablePlace | None]:
        if not activities:
            return {"breakfast_meal": None, "lunch_meal": None, "dinner_meal": None}

        first = activities[0]
        second = activities[-1]
        selected: dict[str, SelectablePlace | None] = {}
        used = set(excluded_place_ids)
        coffee_used = any(is_coffee_place(activity) for activity in activities)
        node_by_slot: dict[str, MealNodeSelection] = {}
        if self.meal_node_planner is not None:
            try:
                selections = self.meal_node_planner.select_for_day(
                    activities=[
                        item.model_dump(mode="json", by_alias=True)
                        for item in activities
                    ],
                    interests=interests or [],
                    used_node_names=set(),
                )
                node_by_slot = {selection.slot: selection for selection in selections}
            except (RuntimeError, ValueError, TypeError):
                node_by_slot = {}
        for role, terms in (
            ("breakfast_meal", ["breakfast", "bakery", "food"]),
            ("lunch_meal", ["lunch", "local food", "restaurant"]),
            ("dinner_meal", ["dinner", "local food", "restaurant"]),
        ):
            anchor = self._anchor_for_role(role, first, second)
            node = node_by_slot.get(role.removesuffix("_meal"))
            candidates: list[SelectablePlace] = []
            unavailable_node_ids: set[str] = set()
            for _ in range(3):
                if node is None:
                    break
                candidates = self._nearby_graph_candidates(
                    node=node,
                    target_tags=terms,
                    excluded_place_ids=used,
                    anchor=anchor,
                )
                if candidates or self.meal_node_planner is None:
                    break
                unavailable_node_ids.add(node.node_id)
                try:
                    replacement = self.meal_node_planner.select_for_day(
                        activities=[
                            item.model_dump(mode="json", by_alias=True)
                            for item in activities
                        ],
                        interests=interests or [],
                        used_node_names={node.node_name},
                        unavailable_node_ids=unavailable_node_ids,
                    )
                except (RuntimeError, ValueError, TypeError):
                    replacement = []
                node = next(
                    (
                        item
                        for item in replacement
                        if item.slot == role.removesuffix("_meal")
                    ),
                    None,
                )
            if not candidates:
                candidates = self._nearby_candidates(
                    region_key=region_key,
                    target_tags=terms,
                    excluded_place_ids=used,
                    anchor=anchor,
                    bbox_filter=bbox_filter,
                )
            if coffee_used:
                candidates = [
                    candidate
                    for candidate in candidates
                    if not is_coffee_place(candidate)
                ]
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
                coffee_used = coffee_used or is_coffee_place(chosen)
                used.add(chosen.stable_ref)
                if chosen.place_id is not None:
                    used.add(chosen.place_id)
        return selected

    def _nearby_graph_candidates(
        self,
        *,
        node: MealNodeSelection,
        target_tags: list[str],
        excluded_place_ids: set[str],
        anchor: tuple[float, float] | None,
    ) -> list[SelectablePlace]:
        if self.graph_repository is None:
            return []
        entities = self.graph_repository.list_places_offering_items([node.node_id])
        candidates = [
            place
            for entity in entities
            if (place := self.place_tool.get(entity.id)) is not None
            and place.stable_ref not in excluded_place_ids
            and self._is_meal_candidate(place)
        ]
        if anchor is None:
            return candidates
        for radius_meters in self.radius_steps_meters:
            scoped = [
                place
                for place in candidates
                if self._distance(anchor, self._coordinate(place)) <= radius_meters
            ]
            if scoped:
                return scoped
        return []

    def _nearby_candidates(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        anchor: tuple[float, float] | None,
        bbox_filter: tuple[float, float, float, float] | None,
    ) -> list[SelectablePlace]:
        """Search meals around the activity anchor before widening the radius."""
        if anchor is None:
            return self._candidates(
                region_key=region_key,
                target_tags=target_tags,
                excluded_place_ids=excluded_place_ids,
                bbox_filter=bbox_filter,
            )

        for radius_meters in self.radius_steps_meters:
            radius_km = radius_meters / 1000 if radius_meters != float("inf") else None
            local_bbox = self._bbox_for_radius(anchor, radius_km)
            candidates = self._candidates(
                region_key=region_key,
                target_tags=target_tags,
                excluded_place_ids=excluded_place_ids,
                bbox_filter=local_bbox,
            )
            candidates = [
                candidate
                for candidate in candidates
                if self._distance(anchor, self._coordinate(candidate))
                <= radius_meters
            ]
            if candidates:
                return candidates
        return []

    @staticmethod
    def _anchor_for_role(
        role: str,
        first: PlanItem,
        second: PlanItem,
    ) -> tuple[float, float] | None:
        first_coordinate = MealStopSelector._coordinate(first)
        second_coordinate = MealStopSelector._coordinate(second)
        if role == "breakfast_meal":
            return first_coordinate
        if role == "dinner_meal":
            return second_coordinate
        if first_coordinate is None:
            return second_coordinate
        if second_coordinate is None:
            return first_coordinate
        return (
            (first_coordinate[0] + second_coordinate[0]) / 2,
            (first_coordinate[1] + second_coordinate[1]) / 2,
        )

    @staticmethod
    def _bbox_for_radius(
        center: tuple[float, float],
        radius_km: float | None,
    ) -> tuple[float, float, float, float] | None:
        if radius_km is None:
            return None
        latitude, longitude = center
        latitude_delta = radius_km / 111.0
        longitude_delta = radius_km / (111.0 * max(cos(radians(latitude)), 0.01))
        return (
            latitude - latitude_delta,
            longitude - longitude_delta,
            latitude + latitude_delta,
            longitude + longitude_delta,
        )

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
        return [candidate for candidate in candidates if self._is_meal_candidate(candidate)]

    @staticmethod
    def _is_meal_candidate(candidate: SelectablePlace) -> bool:
        """Keep actual food venues out of supplier, retail, and school results."""
        text = " ".join(
            [candidate.name, candidate.place_type, *candidate.tags]
        ).casefold()
        if any(
            re.search(rf"\b{term}\b", text)
            for term in ("supplier", "store", "supermarket", "school", "market")
        ):
            return False
        return is_meal_place(
            tags=[candidate.place_type, *candidate.tags],
            source_activity=candidate.name,
        )

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
                -self._quality_score(candidate),
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
                entry[4].name.casefold(),
            ),
        )[4]

    @staticmethod
    def _quality_score(candidate: SelectablePlace) -> float:
        """Prefer trusted public feedback after semantic meal relevance."""
        rating_score = (candidate.rating or 0.0) * 20.0
        review_score = log10(max(candidate.review_count, 0) + 1) * 4.0
        return rating_score + review_score

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
