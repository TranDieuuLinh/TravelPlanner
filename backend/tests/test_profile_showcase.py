from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.places.model import Place
from app.modules.profiles.model import UserPost, UserVisitedPlace
from app.modules.users.model import User
from tests.helpers import csrf_headers


def _place(place_id: str, name: str = "Phố cổ Hội An") -> Place:
    return Place(
        id=place_id,
        name=name,
        place_type="historic_area",
        address="Phường Minh An, Hội An",
        city="Hội An",
        country="Việt Nam",
        country_code="VN",
        region_key="vn:quang-nam:hoi-an",
        primary_area="Hội An",
        latitude=Decimal("15.8800584"),
        longitude=Decimal("108.3380469"),
        status="active",
        opening_hours=[],
        data_confidence="high",
        metadata_json={},
    )


def test_profile_showcase_returns_only_authenticated_users_content(
    registered_client: TestClient,
    db_session: Session,
) -> None:
    current_user = db_session.query(User).filter_by(email="traveler@example.com").one()
    other_user = User(
        email="other@example.com",
        full_name="Người dùng khác",
        role="traveler",
        status="active",
    )
    place = _place("profile-place-hoi-an")
    other_place = _place("profile-place-private", "Địa điểm của người khác")
    db_session.add_all([other_user, place, other_place])
    db_session.flush()
    db_session.add_all(
        [
            UserVisitedPlace(
                id="profile-visit-current",
                user_id=current_user.id,
                place_id=place.id,
                visited_at=date(2026, 6, 14),
                note="Một buổi chiều ở Hội An.",
            ),
            UserVisitedPlace(
                id="profile-visit-other",
                user_id=other_user.id,
                place_id=other_place.id,
                visited_at=date(2026, 5, 1),
            ),
            UserPost(
                id="profile-post-current",
                user_id=current_user.id,
                caption="Kỷ niệm Hội An",
                media_url="https://images.example.com/hoi-an.jpg",
                location_name="Hội An",
                created_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            ),
            UserPost(
                id="profile-post-other",
                user_id=other_user.id,
                caption="Nội dung riêng",
                media_url="https://images.example.com/private.jpg",
            ),
        ]
    )
    db_session.commit()

    response = registered_client.get("/api/me/showcase")

    assert response.status_code == 200
    payload = response.json()
    assert [place["name"] for place in payload["visitedPlaces"]] == ["Phố cổ Hội An"]
    assert payload["visitedPlaces"][0]["latitude"] == 15.8800584
    assert [post["caption"] for post in payload["posts"]] == ["Kỷ niệm Hội An"]
    assert "userId" not in payload["posts"][0]


def test_user_can_mark_resolved_place_as_visited(
    registered_client: TestClient,
    db_session: Session,
) -> None:
    place = _place("profile-place-mark")
    db_session.add(place)
    db_session.commit()

    response = registered_client.post(
        "/api/me/visited-places",
        headers=csrf_headers(registered_client),
        json={
            "placeId": place.id,
            "visitedAt": "2026-07-20",
            "note": "Đã hoàn thành chuyến đi.",
        },
    )

    assert response.status_code == 201
    assert response.json()["placeId"] == place.id
    assert response.json()["visitedAt"] == "2026-07-20"
    assert db_session.query(UserVisitedPlace).filter_by(place_id=place.id).count() == 1
