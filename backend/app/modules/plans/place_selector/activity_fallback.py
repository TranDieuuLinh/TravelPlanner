from __future__ import annotations

from math import asin, cos, log1p, radians, sin, sqrt

from app.modules.plans.domain.entities import PlanDay, UnscheduledPlace
from app.modules.plans.explorer.schema import PlaceCandidateReview
from app.modules.plans.place_selector.place_tool import SelectablePlace, PlaceSelectionTool
from app.modules.plans.trip_theme_planner.region_context import normalize_search_region_key


class RouteAwareActivityFallback:
    """Recommend a real POI for an evidenced activity with no resolved venue.

    This runs after the itinerary route has been selected.  It never promotes
    an unresolved source candidate or claims that the recommended venue was in
    the source; it returns a separate, draggable recommendation instead.
    """

    candidate_limit = 250

    def __init__(self, place_tool: PlaceSelectionTool) -> None:
        self.place_tool = place_tool

    def recommend(
        self,
        *,
        days: list[PlanDay],
        reviews: list[PlaceCandidateReview],
        region_key: str,
    ) -> list[UnscheduledPlace]:
        scheduled_refs = {
            ref
            for day in days
            for item in day.items
            for ref in (item.place_id, item.name.casefold())
            if ref
        }
        route_points = [
            (day.day, float(item.latitude), float(item.longitude))
            for day in days
            for item in day.items
            if item.latitude is not None and item.longitude is not None
        ]
        recommendations: list[UnscheduledPlace] = []
        used = set(scheduled_refs)

        for review in reviews:
            if review.status != "needs_review" or not review.source_urls:
                continue
            activity = (review.source_activity or review.name).strip()
            if not activity:
                continue
            region_parts = region_key.split(",", maxsplit=2)
            destination_root = (
                region_parts[1] if len(region_parts) > 1 else region_key
            )
            search_region = (
                normalize_search_region_key(
                    review.search_region,
                    destination_root,
                )
                if review.search_region
                else region_key
            )
            terms = list(
                dict.fromkeys(
                    value
                    for value in (activity, review.name, review.category.value)
                    if value
                )
            )
            candidates = self.place_tool.search(
                region_key=search_region,
                target_tags=terms,
                excluded_place_ids={value for value in used if value},
                limit=self.candidate_limit,
            )
            candidates = [
                candidate
                for candidate in candidates
                if candidate.latitude is not None
                and candidate.longitude is not None
                and candidate.name.casefold() not in used
            ]
            if not candidates:
                continue

            ranked = [
                (
                    *self._score(
                        candidate,
                        route_points=route_points,
                        address_anchor=(
                            (float(review.latitude), float(review.longitude))
                            if review.has_representative_location
                            and review.latitude is not None
                            and review.longitude is not None
                            else None
                        ),
                        catalog_rank=rank,
                    ),
                    candidate,
                )
                for rank, candidate in enumerate(candidates)
            ]
            chosen = min(ranked, key=lambda entry: entry[:3])[3]
            # Recompute the human-facing route facts for the selected candidate.
            closest_day, route_distance = self._closest_route_point(
                chosen,
                route_points,
            )
            reason_parts = [
                f"Recommended for the source activity ‘{activity}’; the source did not identify a verified venue."
            ]
            if closest_day is not None and route_distance is not None:
                reason_parts.append(
                    f"Closest to day {closest_day}'s route (about {round(route_distance / 100) * 100:.0f} m)."
                )
            if chosen.rating is not None:
                popularity = f"Rated {chosen.rating:.1f}/5"
                if chosen.review_count:
                    popularity += f" from {chosen.review_count:,} reviews"
                reason_parts.append(popularity + ".")

            recommendations.append(
                UnscheduledPlace(
                    placeId=chosen.place_id,
                    name=chosen.name,
                    day=closest_day,
                    reasonCode="activity_fallback_recommendation",
                    reason=" ".join(reason_parts),
                    address=chosen.address,
                    latitude=chosen.latitude,
                    longitude=chosen.longitude,
                    placeType=chosen.place_type,
                    tags=chosen.tags,
                    sourceRefs=review.source_urls,
                    sourceProvider="route_aware_activity_fallback",
                    sourceActivity=activity,
                    rating=chosen.rating,
                    reviewCount=chosen.review_count,
                )
            )
            used.add(chosen.stable_ref)
            used.add(chosen.name.casefold())

        return recommendations

    def _score(
        self,
        candidate: SelectablePlace,
        *,
        route_points: list[tuple[int, float, float]],
        address_anchor: tuple[float, float] | None,
        catalog_rank: int,
    ) -> tuple[float, int, float]:
        day, route_distance = self._closest_route_point(candidate, route_points)
        route_cost = route_distance if route_distance is not None else 50_000.0
        address_cost = (
            self._distance(
                (float(candidate.latitude), float(candidate.longitude)),
                address_anchor,
            )
            if address_anchor is not None
            else 0.0
        )
        # Popularity can break a nearby tie, but cannot pull the user across a
        # city.  Repository rank already carries semantic/category relevance.
        popularity_bonus = min(
            1_200.0,
            (candidate.rating or 0.0) * 100.0
            + log1p(max(0, candidate.review_count)) * 90.0,
        )
        score = (
            route_cost
            + address_cost * 0.6
            + catalog_rank * 20
            - popularity_bonus
        )
        return score, day or 99, route_cost

    def _closest_route_point(
        self,
        candidate: SelectablePlace,
        route_points: list[tuple[int, float, float]],
    ) -> tuple[int | None, float | None]:
        if not route_points:
            return None, None
        coordinate = (float(candidate.latitude), float(candidate.longitude))
        day, distance = min(
            [
                (
                    day,
                    self._distance(coordinate, (latitude, longitude)),
                )
                for day, latitude, longitude in route_points
            ],
            key=lambda value: (value[1], value[0]),
        )
        return day, distance

    @staticmethod
    def _distance(
        left: tuple[float, float],
        right: tuple[float, float],
    ) -> float:
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
