from __future__ import annotations

from types import SimpleNamespace

from app.modules.plans.domain.entities import PlaceSelectionDay, PlaceSelectionBlueprint, TravelIntent
from app.modules.plans.domain.enums import BudgetLevel, TravelPace
from app.modules.plans.place_selector.service import PlaceSelectorService
from app.modules.plans.place_selector.place_tool import RepositoryPlaceSelectionTool


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
                group="Restaurant",
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
    tool = RepositoryPlaceSelectionTool(repository)

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


def test_structured_reranking_prefers_reviewed_place_over_alphabetic_noise() -> None:
    repository = FakeFinderRepository(
        [
            _place(
                "alphabetic-noise",
                "A Generic Museum",
                "museum",
                "vn,ha-noi",
                description="Culture museum in Hanoi.",
                group="attraction",
                tags=["culture", "museum"],
                rating=3.5,
                review_count=2,
            ),
            _place(
                "reviewed-museum",
                "Vietnam History Museum",
                "museum",
                "vn,ha-noi",
                description="Culture museum in Hanoi.",
                group="attraction",
                tags=["culture", "museum"],
                rating=4.6,
                review_count=10_000,
                image_urls=["https://images.example/history-museum.jpg"],
            ),
        ]
    )

    results = RepositoryPlaceSelectionTool(repository).search(
        region_key="vn,ha-noi",
        target_tags=["culture", "museum"],
        excluded_place_ids=set(),
        limit=2,
    )

    assert [place.place_id for place in results] == [
        "reviewed-museum",
        "alphabetic-noise",
    ]
    assert results[0].rating == 4.6
    assert results[0].review_count == 10_000
    assert results[0].image_urls == [
        "https://images.example/history-museum.jpg"
    ]


def test_offers_activity_enriches_finder_candidate_without_category_dependency() -> None:
    repository = FakeFinderRepository(
        [
            _place(
                "cocktail-bar",
                "Rooftop Bar",
                "bar",
                "vn,ha-noi",
                description="Không gian ngắm thành phố về đêm.",
                group="DrinkDessert",
                tags=["nightlife"],
            )
        ]
    )

    class _Graph:
        def list_activity_place_candidates(self, region_key: str, *, limit: int):
            assert region_key == "vn,ha-noi"
            return [
                SimpleNamespace(
                    placeId="cocktail-bar",
                    activityId="activity-cocktail",
                    activityName="Uống cocktail ngắm thành phố",
                )
            ]

    results = RepositoryPlaceSelectionTool(
        repository,
        graph_repository=_Graph(),
    ).search(
        region_key="vn,ha-noi",
        target_tags=["cocktail"],
        excluded_place_ids=set(),
        limit=3,
    )

    assert len(results) == 1
    assert results[0].activity_id == "activity-cocktail"
    assert results[0].source_activity == "Uống cocktail ngắm thành phố"
    assert results[0].selection_method == "offers_activity_graph"


def test_place_selector_softly_prefers_a_new_activity_id_within_the_day() -> None:
    repository = FakeFinderRepository(
        [
            _place("walk-a", "A Walk", "museum", "vn,ha-noi", description="culture", group="attraction", tags=["culture"]),
            _place("walk-b", "B Walk", "museum", "vn,ha-noi", description="culture", group="attraction", tags=["culture"]),
            _place("photo", "C Photo", "museum", "vn,ha-noi", description="culture", group="attraction", tags=["culture"]),
        ]
    )

    class _Graph:
        def list_activity_place_candidates(self, region_key: str, **kwargs):
            return [
                SimpleNamespace(placeId="walk-a", activityId="activity-walk", activityName="Đi dạo"),
                SimpleNamespace(placeId="walk-b", activityId="activity-walk", activityName="Đi dạo"),
                SimpleNamespace(placeId="photo", activityId="activity-photo", activityName="Chụp ảnh"),
            ]

    selector = PlaceSelectorService(
        RepositoryPlaceSelectionTool(repository, graph_repository=_Graph())
    )
    result = selector.fill_main_plan(
        PlaceSelectionBlueprint(
            title="Hà Nội",
            destination="Hà Nội",
            regionKey="vn,ha-noi",
            selectionDays=[
                PlaceSelectionDay(
                    day=1,
                    theme="Culture",
                    targetArea="Hà Nội",
                    targetRegionKey="vn,ha-noi",
                    focusTags=["culture"],
                    pace=TravelPace.balanced,
                )
            ],
        ),
        TravelIntent(
            destination="Hà Nội",
            days=1,
            budget=BudgetLevel.medium,
            travelStyle="local",
            pace=TravelPace.balanced,
            interests=["culture"],
        ),
        [],
    )

    activities = [
        item for item in result.days[0].items if item.timeline_category == "activity"
    ]
    assert [item.activity_id for item in activities[:2]] == [
        "activity-walk",
        "activity-photo",
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
                group="Restaurant",
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
    finder = PlaceSelectorService(RepositoryPlaceSelectionTool(repository))
    macro_plan = PlaceSelectionBlueprint(
        title="Khám phá Hải Phòng",
        destination="Hải Phòng",
        regionKey="vn,hai-phong",
        journeyStyle="multi_base",
        selectionDays=[
            PlaceSelectionDay(
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
    national_park_item = next(
        item
        for item in result.days[0].items
        if item.place_id == "national-park"
    )
    assert national_park_item.notes is not None
    assert "khám phá thiên nhiên" in national_park_item.notes


class FakeFinderRepository:
    def __init__(self, places: list[Place]) -> None:
        self.places = places
        self.requested_scopes: list[str] = []

    def get(self, place_id: str) -> Place | None:
        return next(
            (place for place in self.places if place.id == place_id),
            None,
        )

    def list_for_place_selection(
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
    rating: float | None = None,
    review_count: int = 0,
    image_urls: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=place_id,
        name=name,
        place_type=place_type,
        address=None,
        region_key=region_key,
        status="active",
        latitude=20.72,
        longitude=107.05,
        typical_duration_minutes=60,
        data_confidence="high",
        opening_hours=[],
        rating=rating,
        review_count=review_count,
        source_platform="google_maps",
        source_link=None,
        metadata_json={
            "description": description,
            "placeGroup": group,
            "tags": tags,
            "activityIntensity": "light",
        },
        images=[SimpleNamespace(image_url=image_url) for image_url in (image_urls or [])],
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
