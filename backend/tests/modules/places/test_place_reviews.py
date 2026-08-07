from datetime import datetime, timezone

from app.modules.knowledge_graph.model import KnowledgeEntity
from app.modules.places.model import PlaceReview


def test_place_reviews_can_be_filtered_and_paginated(client, db_session):
    entity = KnowledgeEntity(
        id="place-che-loc-tai",
        canonical_name="Chè Lộc Tài",
        normalized_name="che loc tai",
        entity_type="place",
        status="active",
    )
    db_session.add(entity)
    db_session.add_all(
        [
            PlaceReview(
                id="review-5",
                entity_id=entity.id,
                author_name="An",
                rating=5,
                published_at=datetime(2026, 8, 5, tzinfo=timezone.utc),
                when_text="2 ngày trước",
                language="vi",
                review_text="Chè ngon, phục vụ nhanh.",
            ),
            PlaceReview(
                id="review-2",
                entity_id=entity.id,
                author_name="Bình",
                rating=2,
                published_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                review_text="Hơi ngọt.",
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        f"/api/places/{entity.id}/reviews",
        params={"rating": 5, "limit": 1, "offset": 0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["hasMore"] is False
    assert payload["ratingCounts"] == {
        "1": 0,
        "2": 1,
        "3": 0,
        "4": 0,
        "5": 1,
    }
    assert payload["items"][0]["authorName"] == "An"
    assert payload["items"][0]["reviewText"] == "Chè ngon, phục vụ nhanh."


def test_place_reviews_returns_empty_page_for_unknown_entity(client):
    response = client.get("/api/places/not-in-the-graph/reviews")

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0
