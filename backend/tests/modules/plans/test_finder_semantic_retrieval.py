from __future__ import annotations

from app.modules.places.model import Place
from app.modules.places.semantic import (
    build_place_embedding_text,
    place_embedding_content_hash,
)
from app.modules.plans.finder.place_tool import RepositoryFinderPlaceTool
from app.modules.plans.knowledge_graph import get_default_travel_knowledge_tool


class FakePlaceRepository:
    def __init__(self, places: list[Place]) -> None:
        self.places = places

    def get(self, place_id: str) -> Place | None:
        return next((place for place in self.places if place.id == place_id), None)

    def list_for_finder(self, region_key: str, *, limit: int = 10_000) -> list[Place]:
        return [
            place
            for place in self.places
            if place.region_key == region_key
            or place.region_key.startswith(f"{region_key},")
        ][:limit]

def test_graph_terms_and_structured_evidence_precede_popularity() -> None:
    repository = FakePlaceRepository(
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
        ]
    )
    tool = RepositoryFinderPlaceTool(repository)
    expansion = get_default_travel_knowledge_tool().expand(
        ["local food", "traditional Hanoi cuisine"],
        region_key="vn,ha-noi,hoan-kiem",
        category="food_drink",
    )

    results = tool.search(
        region_key="vn,ha-noi,hoan-kiem",
        target_tags=list(expansion.query_terms),
        target_categories=set(expansion.categories),
        excluded_place_ids=set(),
        limit=2,
    )

    assert [place.place_id for place in results] == [
        "local-noodles",
        "popular-pizza",
    ]


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


def test_place_without_description_is_retrieved_from_structured_fields() -> None:
    place = _place("local", "Bún chả Hà Nội", "restaurant")
    place.metadata_json.pop("description", None)
    results = RepositoryFinderPlaceTool(FakePlaceRepository([place])).search(
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
