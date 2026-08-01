from decimal import Decimal

from app.modules.places.model import Place
from app.modules.plans.planner.tourism_zone_research import (
    RepositoryTourismZoneResearchTool,
)


class FakeRepository:
    def __init__(self, places: list[Place]) -> None:
        self.places = places

    def list_active_for_planner_research(
        self,
        region_key: str | None = None,
        *,
        limit: int = 5000,
    ) -> list[Place]:
        return [
            place
            for place in self.places
            if region_key is None
            or place.region_key == region_key
            or place.region_key.startswith(f"{region_key},")
        ][:limit]


class FakeSemanticRepository(FakeRepository):
    def has_place_embeddings(self, region_key: str, *, embedding_model: str) -> bool:
        return True

    def rank_place_ids_by_embedding(
        self,
        place_ids: list[str],
        query_embedding: list[float],
        *,
        embedding_model: str,
        limit: int,
    ) -> list[tuple[str, float]]:
        scores = {"local-food": 0.93, "pizza": 0.42}
        return sorted(
            ((place_id, scores.get(place_id, 0.0)) for place_id in place_ids),
            key=lambda item: -item[1],
        )[:limit]


class FakeEmbeddingClient:
    model = "test-embedding"
    dimensions = 3

    def embed_query(self, text: str) -> list[float]:
        assert "traditional Hanoi food" in text
        return [1.0, 0.0, 0.0]

    def embed_document(self, text: str, *, title: str | None = None) -> list[float]:
        return [1.0, 0.0, 0.0]


def test_culture_research_builds_zone_around_popular_visitor_anchor() -> None:
    repository = FakeRepository(
        [
            _place(
                "museum",
                "Vietnam Fine Arts Museum",
                "museum",
                "vn,ha-noi,ba-dinh",
                21.0306,
                105.8370,
                ["culture", "museum"],
                rating=4.7,
                reviews=8_000,
            ),
            _place(
                "local-food",
                "Local lunch",
                "restaurant",
                "vn,ha-noi,ba-dinh",
                21.0310,
                105.8380,
                ["food"],
            ),
            _place(
                "far-food",
                "Far restaurant",
                "restaurant",
                "vn,ha-noi,ha-dong",
                20.9710,
                105.7780,
                ["food"],
            ),
        ]
    )

    zones = RepositoryTourismZoneResearchTool(repository).research(
        root_region_key="vn,ha-noi",
        interests=["culture"],
    )

    assert len(zones) == 1
    assert zones[0].region_key == "vn,ha-noi,ba-dinh"
    assert zones[0].anchor_places[0].place_id == "museum"
    assert zones[0].primary_categories == ["attraction", "food_drink"]
    assert zones[0].place_count == 2


def test_food_research_uses_food_place_as_anchor() -> None:
    repository = FakeRepository(
        [
            _place(
                "museum",
                "Museum",
                "museum",
                "vn,ha-noi,ba-dinh",
                21.0306,
                105.8370,
                ["culture"],
                rating=4.9,
                reviews=20_000,
            ),
            _place(
                "pho",
                "Pho restaurant",
                "restaurant",
                "vn,ha-noi,ba-dinh",
                21.0310,
                105.8380,
                ["food"],
                rating=4.6,
                reviews=5_000,
            ),
        ]
    )

    zones = RepositoryTourismZoneResearchTool(repository).research(
        root_region_key="vn,ha-noi",
        interests=["food"],
    )

    assert zones[0].anchor_places[0].place_id == "pho"


def test_natural_language_food_and_coffee_interests_use_food_anchor() -> None:
    repository = FakeRepository(
        [
            _place(
                "museum",
                "Museum",
                "museum",
                "vn,ha-noi,hoan-kiem",
                21.0306,
                105.8370,
                ["culture"],
                rating=4.9,
                reviews=20_000,
            ),
            _place(
                "local-food",
                "Traditional Hanoi restaurant",
                "restaurant",
                "vn,ha-noi,hoan-kiem",
                21.0310,
                105.8380,
                ["food", "coffee"],
                rating=4.7,
                reviews=5_000,
            ),
        ]
    )

    zones = RepositoryTourismZoneResearchTool(repository).research(
        root_region_key="vn,ha-noi",
        interests=["traditional Hanoi food", "egg coffee"],
    )

    assert zones[0].anchor_places[0].place_id == "local-food"


def test_semantic_similarity_beats_raw_popularity_when_selecting_zone_anchor() -> None:
    repository = FakeSemanticRepository(
        [
            _place(
                "pizza",
                "Popular international pizza",
                "restaurant",
                "vn,ha-noi,hoan-kiem",
                21.0306,
                105.8370,
                ["food", "pizza"],
                rating=4.9,
                reviews=30_000,
            ),
            _place(
                "local-food",
                "Hanoi food experience",
                "restaurant",
                "vn,ha-noi,hoan-kiem",
                21.0310,
                105.8380,
                ["food", "Hanoi cuisine"],
                rating=4.6,
                reviews=2_000,
            ),
        ]
    )

    zones = RepositoryTourismZoneResearchTool(
        repository,
        FakeEmbeddingClient(),
    ).research(
        root_region_key="vn,ha-noi",
        interests=["traditional Hanoi food"],
    )

    assert zones[0].anchor_places[0].place_id == "local-food"


def _place(
    place_id: str,
    name: str,
    place_type: str,
    region_key: str,
    latitude: float,
    longitude: float,
    tags: list[str],
    *,
    rating: float = 4.0,
    reviews: int = 100,
) -> Place:
    return Place(
        id=place_id,
        name=name,
        place_type=place_type,
        region_key=region_key,
        status="active",
        latitude=Decimal(str(latitude)),
        longitude=Decimal(str(longitude)),
        rating=Decimal(str(rating)),
        review_count=reviews,
        data_confidence="high",
        opening_hours=[],
        metadata_json={"tags": tags},
    )
