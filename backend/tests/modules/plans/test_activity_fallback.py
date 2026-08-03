from __future__ import annotations

from app.modules.plans.domain.entities import PlanDay, PlanItem
from app.modules.plans.explorer.schema import PlaceCandidateReview
from app.modules.plans.finder.place_tool import FinderPlace
from app.modules.plans.place_selector.activity_fallback import (
    RouteAwareActivityFallback,
)


def test_unresolved_activity_recommends_popular_place_near_route() -> None:
    nearby_popular = _cafe(
        "cafe-near",
        "Popular Egg Coffee",
        21.0302,
        105.8402,
        rating=4.8,
        reviews=2400,
    )
    farther = _cafe(
        "cafe-far",
        "Far Egg Coffee",
        21.0600,
        105.8800,
        rating=4.9,
        reviews=9000,
    )
    fallback = RouteAwareActivityFallback(_PlaceTool([farther, nearby_popular]))

    recommendations = fallback.recommend(
        days=[
            PlanDay(
                day=1,
                theme="Old Quarter",
                items=[_activity("route-stop", 21.03, 105.84)],
            )
        ],
        reviews=[
            PlaceCandidateReview(
                candidateId="egg-coffee",
                name="Egg coffee",
                category="cafe",
                status="needs_review",
                resolutionReason="not_found",
                searchRegion="vn,ha-noi",
                sourceUrls=["https://youtube.com/shorts/example"],
                sourceActivity="Drink egg coffee",
                confidence=0.9,
            )
        ],
        region_key="vn,ha-noi",
    )

    assert len(recommendations) == 1
    recommendation = recommendations[0]
    assert recommendation.place_id == "cafe-near"
    assert recommendation.day == 1
    assert recommendation.reason_code == "activity_fallback_recommendation"
    assert "source did not identify a verified venue" in recommendation.reason
    assert "2,400 reviews" in recommendation.reason
    assert recommendation.source_provider == "route_aware_activity_fallback"
    assert recommendation.source_refs == ["https://youtube.com/shorts/example"]


def test_representative_address_anchor_guides_route_compatible_choice() -> None:
    by_address = _cafe("address-cafe", "Address Cafe", 21.031, 105.841)
    other = _cafe("other-cafe", "Other Cafe", 21.029, 105.839)
    fallback = RouteAwareActivityFallback(_PlaceTool([other, by_address]))

    recommendation = fallback.recommend(
        days=[
            PlanDay(
                day=2,
                theme="Centre",
                items=[_activity("route-stop", 21.03, 105.84)],
            )
        ],
        reviews=[
            PlaceCandidateReview(
                candidateId="address-only",
                name="Coffee at this address",
                category="cafe",
                status="needs_review",
                resolutionReason="name_mismatch",
                address="1 Example Street",
                latitude=21.031,
                longitude=105.841,
                hasRepresentativeLocation=True,
                sourceUrls=["https://instagram.com/reel/example"],
                sourceActivity="Egg coffee",
                confidence=0.8,
            )
        ],
        region_key="vn,ha-noi",
    )[0]

    assert recommendation.place_id == "address-cafe"


def _activity(place_id: str, latitude: float, longitude: float) -> PlanItem:
    return PlanItem(
        placeId=place_id,
        name=place_id,
        timeWindow="00:00-00:01",
        placeType="attraction",
        timelineCategory="activity",
        latitude=latitude,
        longitude=longitude,
    )


def _cafe(
    place_id: str,
    name: str,
    latitude: float,
    longitude: float,
    *,
    rating: float | None = None,
    reviews: int = 0,
) -> FinderPlace:
    return FinderPlace(
        placeId=place_id,
        name=name,
        address=f"{name}, Hà Nội",
        placeType="cafe",
        regionKey="vn,ha-noi",
        tags=["coffee", "egg coffee"],
        latitude=latitude,
        longitude=longitude,
        rating=rating,
        reviewCount=reviews,
    )


class _PlaceTool:
    def __init__(self, places: list[FinderPlace]) -> None:
        self.places = places

    def get(self, place_id: str) -> FinderPlace | None:
        return next(
            (place for place in self.places if place.place_id == place_id),
            None,
        )

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        limit: int,
        bbox_filter=None,
    ) -> list[FinderPlace]:
        del region_key, target_tags, bbox_filter
        return [
            place
            for place in self.places
            if place.place_id not in excluded_place_ids
        ][:limit]
