from __future__ import annotations

from app.modules.places.model import Place
from app.modules.plans.domain.entities import DayBrief, MacroPlan, TravelIntent
from app.modules.plans.domain.enums import BudgetLevel, TravelPace
from app.modules.plans.finder.finder_service import FinderService
from app.modules.plans.finder.place_tool import RepositoryFinderPlaceTool


def test_description_retrieval_then_structured_reranking_prefers_nature() -> None:
    repository = FakeFinderRepository(
        [
            _place(
                "cat-ba-hotel",
                "Cat Ba Love Hotel",
                "hotel",
                "vn,hai-phong,cat-hai,cat-ba",
                description="Khách sạn tại trung tâm Cát Bà.",
                group="accommodation",
                tags=["accommodation", "hotel"],
            ),
            _place(
                "cat-ba-restaurant",
                "Aroma Cat Ba Restaurant",
                "restaurant",
                "vn,hai-phong,cat-hai,cat-ba",
                description=(
                    "Nhà hàng gần thiên nhiên Cát Bà, phù hợp sau chuyến hiking."
                ),
                group="food_drink",
                tags=["food", "restaurant"],
            ),
            _place(
                "cat-ba-national-park",
                "Vườn quốc gia Cát Bà",
                "nature_reserve",
                "vn,hai-phong",
                description=(
                    "Vườn quốc gia Cát Bà có rừng, núi và tuyến hiking "
                    "khám phá thiên nhiên."
                ),
                group="attraction",
                tags=["attraction", "nature", "hiking", "park"],
            ),
        ]
    )
    tool = RepositoryFinderPlaceTool(repository)

    results = tool.search(
        region_key="vn,hai-phong,cat-hai,cat-ba",
        target_tags=["Thiên nhiên Cát Bà", "nature", "hiking"],
        excluded_place_ids=set(),
        limit=3,
    )

    assert [place.place_id for place in results] == [
        "cat-ba-national-park",
    ]
    assert repository.requested_scopes == [
        "vn,hai-phong,cat-hai,cat-ba",
        "vn,hai-phong,cat-hai",
        "vn,hai-phong",
    ]


def test_nature_day_keeps_hotel_and_restaurant_out_of_activity_slots() -> None:
    repository = FakeFinderRepository(
        [
            _place(
                "hotel",
                "Phuong Mai Family Hotel",
                "hotel",
                "vn,hai-phong,cat-ba-town",
                description="Khách sạn lưu trú tại Cát Bà.",
                group="accommodation",
                tags=["accommodation", "hotel"],
            ),
            _place(
                "restaurant",
                "Aroma Cat Ba seafood restaurant",
                "restaurant",
                "vn,hai-phong,cat-ba-town",
                description="Nhà hàng hải sản tại Cát Bà.",
                group="food_drink",
                tags=["food", "restaurant", "seafood"],
            ),
            _place(
                "national-park",
                "Vườn quốc gia Cát Bà",
                "nature_reserve",
                "vn,hai-phong",
                description=(
                    "Đi bộ xuyên rừng và khám phá thiên nhiên tại "
                    "Vườn quốc gia Cát Bà."
                ),
                group="attraction",
                tags=["attraction", "nature", "hiking"],
            ),
        ]
    )
    finder = FinderService(RepositoryFinderPlaceTool(repository))
    macro_plan = MacroPlan(
        title="Khám phá Hải Phòng",
        destination="Hải Phòng",
        regionKey="vn,hai-phong",
        journeyStyle="multi_base",
        dayBriefs=[
            DayBrief(
                day=1,
                theme="Thiên nhiên Cát Bà",
                targetArea="Cát Bà",
                targetRegionKey="vn,hai-phong,cat-ba-town",
                focusTags=["nature", "hiking"],
                pace=TravelPace.balanced,
            )
        ],
    )

    result = finder.fill_main_plan(macro_plan, _intent(), [])

    scheduled_place_ids = [
        item.place_id
        for item in result.days[0].items
        if item.place_id is not None
    ]
    assert scheduled_place_ids == ["national-park", "restaurant"]
    assert "hotel" not in scheduled_place_ids
    restaurant_item = next(
        item
        for item in result.days[0].items
        if item.place_id == "restaurant"
    )
    assert restaurant_item.role == "lunch_meal"


class FakeFinderRepository:
    def __init__(self, places: list[Place]) -> None:
        self.places = places
        self.requested_scopes: list[str] = []

    def get(self, place_id: str) -> Place | None:
        return next(
            (place for place in self.places if place.id == place_id),
            None,
        )

    def list_for_finder(
        self,
        region_key: str,
        *,
        limit: int = 10000,
    ) -> list[Place]:
        self.requested_scopes.append(region_key)
        return [
            place
            for place in self.places
            if (
                place.region_key == region_key
                or place.region_key.startswith(f"{region_key},")
            )
        ][:limit]


def _place(
    place_id: str,
    name: str,
    place_type: str,
    region_key: str,
    *,
    description: str,
    group: str,
    tags: list[str],
) -> Place:
    return Place(
        id=place_id,
        name=name,
        place_type=place_type,
        region_key=region_key,
        status="active",
        latitude=20.72,
        longitude=107.05,
        typical_duration_minutes=60,
        data_confidence="high",
        opening_hours=[],
        metadata_json={
            "description": description,
            "placeGroup": group,
            "tags": tags,
            "activityIntensity": "light",
        },
    )


def _intent() -> TravelIntent:
    return TravelIntent(
        destination="Hải Phòng",
        days=1,
        budget=BudgetLevel.medium,
        travelStyle="local",
        pace=TravelPace.balanced,
        interests=["nature", "hiking"],
    )
