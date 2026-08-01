from __future__ import annotations

from collections.abc import Sequence

from app.modules.places.model import Place
from app.modules.places.semantic import (
    build_place_embedding_text,
    place_embedding_content_hash,
)
from app.modules.plans.finder.place_tool import RepositoryFinderPlaceTool


class FakeEmbeddingClient:
    model = "gemini-embedding-2"
    dimensions = 3

    def embed_query(self, text: str) -> list[float]:
        assert "local food" in text
        return [1.0, 0.0, 0.0]

    def embed_document(self, text: str, *, title: str | None = None) -> list[float]:
        return [1.0, 0.0, 0.0]


class FakeSemanticRepository:
    def __init__(self, places: list[Place], scores: dict[str, float]) -> None:
        self.places = places
        self.scores = scores
        self.semantic_candidate_ids: list[str] = []

    def get(self, place_id: str) -> Place | None:
        return next((place for place in self.places if place.id == place_id), None)

    def list_for_finder(self, region_key: str, *, limit: int = 10_000) -> list[Place]:
        return [
            place
            for place in self.places
            if place.region_key == region_key
            or place.region_key.startswith(f"{region_key},")
        ][:limit]

    def rank_place_ids_by_embedding(
        self,
        place_ids: Sequence[str],
        query_embedding: list[float],
        *,
        embedding_model: str,
        limit: int,
    ) -> list[tuple[str, float]]:
        self.semantic_candidate_ids = list(place_ids)
        assert embedding_model == "gemini-embedding-2"
        return sorted(
            ((place_id, self.scores[place_id]) for place_id in place_ids),
            key=lambda item: -item[1],
        )[:limit]

    def has_place_embeddings(
        self,
        region_key: str,
        *,
        embedding_model: str,
    ) -> bool:
        return True


def test_embedding_shortlist_precedes_popularity_reranking() -> None:
    repository = FakeSemanticRepository(
        [
            _place(
                "local-noodles",
                "Bún chả gia truyền Hà Nội",
                "restaurant",
                rating=4.5,
                review_count=500,
            ),
            _place(
                "popular-pizza",
                "International Pizza",
                "restaurant",
                rating=4.9,
                review_count=20_000,
            ),
            _place(
                "hotel",
                "Hotel Hà Nội",
                "hotel",
                rating=4.9,
                review_count=30_000,
            ),
        ],
        scores={"local-noodles": 0.91, "popular-pizza": 0.62},
    )
    tool = RepositoryFinderPlaceTool(repository, FakeEmbeddingClient())

    results = tool.search(
        region_key="vn,ha-noi,hoan-kiem",
        target_tags=["local food", "traditional Hanoi cuisine"],
        excluded_place_ids=set(),
        limit=2,
    )

    assert [place.place_id for place in results] == [
        "local-noodles",
        "popular-pizza",
    ]
    assert set(repository.semantic_candidate_ids) == {
        "local-noodles",
        "popular-pizza",
    }


def test_place_embedding_hash_changes_with_semantic_content() -> None:
    place = _place("place", "Quán Hà Nội", "restaurant")
    original_hash = place_embedding_content_hash(place)
    original_text = build_place_embedding_text(place)

    place.metadata_json = {
        **place.metadata_json,
        "description": "Traditional Hanoi breakfast and local noodles.",
    }

    assert "Quán Hà Nội" in original_text
    assert place_embedding_content_hash(place) != original_hash


def test_no_embedding_coverage_uses_fallback_without_provider_call() -> None:
    class NoCoverageRepository(FakeSemanticRepository):
        def has_place_embeddings(
            self,
            region_key: str,
            *,
            embedding_model: str,
        ) -> bool:
            return False

    class FailingIfCalledEmbeddingClient(FakeEmbeddingClient):
        def embed_query(self, text: str) -> list[float]:
            raise AssertionError("provider must not be called without vector coverage")

    repository = NoCoverageRepository(
        [_place("local", "Bún chả Hà Nội", "restaurant")],
        scores={"local": 0.9},
    )

    results = RepositoryFinderPlaceTool(
        repository,
        FailingIfCalledEmbeddingClient(),
    ).search(
        region_key="vn,ha-noi,hoan-kiem",
        target_tags=["local food"],
        excluded_place_ids=set(),
        limit=1,
    )

    assert results[0].place_id == "local"


def _place(
    place_id: str,
    name: str,
    place_type: str,
    *,
    rating: float | None = None,
    review_count: int = 0,
) -> Place:
    group = "accommodation" if place_type == "hotel" else "food_drink"
    return Place(
        id=place_id,
        name=name,
        place_type=place_type,
        region_key="vn,ha-noi,hoan-kiem",
        status="active",
        rating=rating,
        review_count=review_count,
        data_confidence="high",
        opening_hours=[],
        metadata_json={
            "placeGroup": group,
            "description": "Tourism venue in Hanoi.",
            "tags": [group],
        },
    )
