from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, log10, radians, sin, sqrt
import logging
import re
import unicodedata

from app.modules.knowledge_graph.research.schema import SpecialtyMealCandidate
from app.modules.plans.domain.entities import PlanItem
from app.modules.plans.place_selector.place_tool import (
    SelectablePlace,
    PlaceSelectionTool,
    is_coffee_place,
    selection_relevance_score,
)
from app.modules.plans.explorer.place_policy import is_meal_place


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _TripMealOption:
    place: SelectablePlace
    selection_path: str = "catalog"
    meal_key: str = ""
    best_time_slots: tuple[str, ...] = ()
    item_id: str | None = None
    item_name: str | None = None
    preferred_slots: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class _MealSlot:
    day: int
    role: str
    first: PlanItem
    second: PlanItem


class MealStopSelector:
    """Choose three food stops after the two daily activities are fixed."""

    candidate_limit = 250
    radius_steps_meters = (1_500, 3_000, 5_000, float("inf"))

    def __init__(
        self,
        place_tool: PlaceSelectionTool,
        *,
        graph_repository=None,
        meal_node_planner=None,
    ) -> None:
        self.place_tool = place_tool
        self.graph_repository = graph_repository
        self.meal_node_planner = meal_node_planner

    def select_for_trip(
        self,
        *,
        region_key: str,
        activities_by_day: dict[int, list[PlanItem]],
        excluded_place_ids: set[str],
        interests: list[str] | None = None,
    ) -> dict[int, dict[str, SelectablePlace | None]]:
        """Select all meal venues from one bounded trip-wide candidate pool."""
        interests = interests or []
        slots = [
            _MealSlot(day=day, role=role, first=activities[0], second=activities[-1])
            for day, activities in sorted(activities_by_day.items())
            if activities
            for role in ("breakfast_meal", "lunch_meal", "dinner_meal")
        ]
        result = {
            day: {
                "breakfast_meal": None,
                "lunch_meal": None,
                "dinner_meal": None,
            }
            for day in activities_by_day
        }
        if not slots:
            return result

        meal_node_selections = []
        if self.meal_node_planner is not None:
            try:
                meal_node_selections = self.meal_node_planner.select_for_trip(
                    activities_by_day={
                        day: [
                            {
                                "name": activity.name,
                                "timeWindow": activity.time_window,
                                "activityId": activity.activity_id,
                                "sourceActivity": activity.source_activity,
                            }
                            for activity in activities
                        ]
                        for day, activities in activities_by_day.items()
                    },
                    interests=interests,
                )
            except (RuntimeError, TypeError, ValueError) as exc:
                # Meal-node selection is an enhancement. The deterministic
                # specialty/catalog selector remains the fail-open path.
                logger.warning("Meal node planning was skipped: %s", exc)

        specialty_rows: list[SpecialtyMealCandidate] = []
        loader = getattr(self.graph_repository, "list_specialty_meal_candidates", None)
        if callable(loader):
            specialty_rows = loader(region_key, limit=self.candidate_limit)

        fallback = self._candidates(
            region_key=region_key,
            target_tags=["breakfast", "lunch", "dinner", "local food", "restaurant"],
            excluded_place_ids=excluded_place_ids,
            bbox_filter=None,
        )
        fallback_by_id = {
            place.place_id: place for place in fallback if place.place_id is not None
        }
        options_by_key: dict[tuple[str, str, tuple[tuple[int, str], ...]], _TripMealOption] = {
            (place.stable_ref, self._meal_key(place.name, place.name), ()): _TripMealOption(
                place=place,
                meal_key=self._meal_key(place.name, place.name),
                best_time_slots=self._place_time_slots(place),
            )
            for place in fallback
        }
        for row in specialty_rows:
            place = fallback_by_id.get(row.placeId) or self.place_tool.get(row.placeId)
            if place is None or not self._is_meal_candidate(place):
                continue
            option = _TripMealOption(
                place=place,
                selection_path=row.selectionPath,
                meal_key=self._meal_key(row.itemName or row.activityName, place.name),
                best_time_slots=tuple(row.bestTimeSlots),
                item_id=row.itemId,
                item_name=row.itemName or row.activityName,
            )
            options_by_key[(place.stable_ref, option.meal_key, ())] = option

        item_venue_loader = getattr(
            self.graph_repository,
            "list_places_offering_items",
            None,
        )
        if callable(item_venue_loader):
            for selection in meal_node_selections:
                preferred_slot = (selection.day, f"{selection.slot}_meal")
                for entity in item_venue_loader([selection.node_id], limit=self.candidate_limit):
                    place = self.place_tool.get(entity.id)
                    if (
                        place is None
                        or not self._is_meal_candidate(place)
                        or not self._in_region(place, region_key)
                    ):
                        continue
                    option = _TripMealOption(
                        place=place,
                        selection_path="meal_node",
                        meal_key=self._meal_key(selection.node_name, place.name),
                        item_id=selection.node_id,
                        item_name=selection.node_name,
                        preferred_slots=(preferred_slot,),
                    )
                    options_by_key[
                        (place.stable_ref, option.meal_key, option.preferred_slots)
                    ] = option

        used_refs = set(excluded_place_ids)
        used_meal_keys: set[str] = set()
        pending = list(slots)
        while pending:
            ranked_slots: list[tuple[int, tuple, _MealSlot, list[tuple[tuple, _TripMealOption]]]] = []
            for slot in pending:
                ranked_options = self._rank_trip_options(
                    list(options_by_key.values()),
                    slot=slot,
                    region_key=region_key,
                    used_refs=used_refs,
                    used_meal_keys=used_meal_keys,
                )
                ranked_slots.append(
                    (
                        len(ranked_options),
                        ranked_options[0][0] if ranked_options else (float("inf"),),
                        slot,
                        ranked_options,
                    )
                )
            _, _, slot, ranked_options = min(
                ranked_slots,
                key=lambda entry: (entry[0], entry[1], entry[2].day, entry[2].role),
            )
            if ranked_options:
                chosen = ranked_options[0][1]
                result[slot.day][slot.role] = self._materialize_option(chosen)
                used_refs.add(chosen.place.stable_ref)
                if chosen.place.place_id is not None:
                    used_refs.add(chosen.place.place_id)
                if chosen.meal_key:
                    used_meal_keys.add(chosen.meal_key)
            pending.remove(slot)
        return result

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
        del interests
        for role, terms in (
            ("breakfast_meal", ["breakfast", "bakery", "food"]),
            ("lunch_meal", ["lunch", "local food", "restaurant"]),
            ("dinner_meal", ["dinner", "local food", "restaurant"]),
        ):
            anchor = self._anchor_for_role(role, first, second)
            candidates = self._nearby_candidates(
                region_key=region_key,
                target_tags=terms,
                excluded_place_ids=used,
                anchor=anchor,
                bbox_filter=bbox_filter,
            )
            candidates = [
                candidate
                for candidate in candidates
                if not candidate.preferred_time_windows
                or self._matches_role(self._place_time_slots(candidate), role)
            ]
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

    def _rank_trip_options(
        self,
        options: list[_TripMealOption],
        *,
        slot: _MealSlot,
        region_key: str,
        used_refs: set[str],
        used_meal_keys: set[str],
    ) -> list[tuple[tuple, _TripMealOption]]:
        available = [
            option
            for option in options
            if option.place.stable_ref not in used_refs
            and (option.place.place_id is None or option.place.place_id not in used_refs)
            and (not option.meal_key or option.meal_key not in used_meal_keys)
            and (
                not option.preferred_slots
                or (slot.day, slot.role) in option.preferred_slots
            )
            and (
                not option.best_time_slots
                or self._matches_role(option.best_time_slots, slot.role)
            )
        ]
        if not available:
            return []
        anchor = self._anchor_for_role(slot.role, slot.first, slot.second)
        for radius in self.radius_steps_meters:
            scoped = [
                option
                for option in available
                if self._distance(anchor, self._coordinate(option.place)) <= radius
            ]
            if scoped:
                available = scoped
                break
        target_tags = {
            "breakfast_meal": ["breakfast", "local food", "restaurant"],
            "lunch_meal": ["lunch", "local food", "restaurant"],
            "dinner_meal": ["dinner", "local food", "restaurant"],
        }[slot.role]
        ranked = [
            (
                (
                    -self._path_priority(option.selection_path),
                    -int(self._matches_role(option.best_time_slots, slot.role)),
                    -selection_relevance_score(
                        option.place,
                        region_key=region_key,
                        target_tags=target_tags,
                    ),
                    -self._quality_score(option.place),
                    self._route_cost(
                        option.place,
                        role=slot.role,
                        first=slot.first,
                        second=slot.second,
                    ),
                    option.place.name.casefold(),
                ),
                option,
            )
            for option in available
        ]
        return sorted(ranked, key=lambda entry: entry[0])

    @staticmethod
    def _path_priority(path: str) -> int:
        return {"meal_node": 3, "target_place": 2, "offers_item": 1}.get(path, 0)

    @staticmethod
    def _materialize_option(option: _TripMealOption) -> SelectablePlace:
        if option.item_id is None:
            return option.place
        return option.place.model_copy(
            update={
                "candidate_entity_ids": list(
                    dict.fromkeys(
                        [*option.place.candidate_entity_ids, option.item_id]
                    )
                ),
                "source_activity": option.item_name or option.place.source_activity,
                "selection_method": (
                    "meal_node_graph"
                    if option.selection_path == "meal_node"
                    else option.place.selection_method or option.selection_path
                ),
            }
        )

    @staticmethod
    def _in_region(place: SelectablePlace, region_key: str) -> bool:
        place_region = (place.region_key or "").strip().casefold()
        requested = region_key.strip().casefold()
        return (
            place_region == requested
            or place_region.startswith(f"{requested},")
            or requested.startswith(f"{place_region},")
        )

    @staticmethod
    def _place_time_slots(place: SelectablePlace) -> tuple[str, ...]:
        return tuple(
            f"{window.start}-{window.end}"
            for window in place.preferred_time_windows
        )

    @staticmethod
    def _matches_role(time_slots: tuple[str, ...], role: str) -> bool:
        if not time_slots:
            return True
        role_ranges = {
            "breakfast_meal": (7 * 60, 9 * 60 + 30),
            "lunch_meal": (11 * 60 + 30, 14 * 60),
            "dinner_meal": (17 * 60 + 30, 20 * 60),
        }
        role_start, role_end = role_ranges[role]
        for value in time_slots:
            try:
                start, end = value.split("-", maxsplit=1)
                start_hour, start_minute = map(int, start.split(":"))
                end_hour, end_minute = map(int, end.split(":"))
            except (TypeError, ValueError):
                continue
            if max(role_start, start_hour * 60 + start_minute) < min(
                role_end, end_hour * 60 + end_minute
            ):
                return True
        return False

    @staticmethod
    def _meal_key(label: str, venue_name: str) -> str:
        normalized = unicodedata.normalize("NFKC", label).casefold().strip()
        normalized = re.sub(r"^(ăn|uong|uống)\s+", "", normalized)
        normalized = re.split(r"\s+(?:ở|tại|buổi|kiểu|sau khi)\s+", normalized)[0]
        for prefix in ("bún chả", "bún bò", "bánh cuốn", "bánh mì", "phở cuốn"):
            if normalized.startswith(prefix):
                return prefix
        if normalized.startswith("phở"):
            return "phở"
        return normalized or venue_name.casefold()

    def _nearby_graph_candidates(
        self,
        *,
        node,
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
            for term in (
                "supplier",
                "store",
                "supermarket",
                "school",
                "market",
                "distributor",
                "exporter",
                "showroom",
                "wholesaler",
                "factory",
            )
        ):
            return False
        return is_meal_place(
            tags=[candidate.place_type, *candidate.tags],
            source_activity=candidate.name,
            ontology_type=candidate.ontology_type,
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
