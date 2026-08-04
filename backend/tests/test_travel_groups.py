from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.travel_groups.model import TravelGroup


def add_groups(db: Session) -> None:
    db.add_all(
        [
            TravelGroup(
                country_code="VN", country_name="Việt Nam",
                name="Cộng đồng du lịch Việt Nam",
                photo_url="https://example.com/default.jpg", visibility="public",
            ),
            TravelGroup(
                country_code="JP", country_name="Nhật Bản",
                name="Cộng đồng du lịch Nhật Bản",
                photo_url="https://example.com/default.jpg", visibility="public",
            ),
            TravelGroup(
                country_code="FR", country_name="Pháp", name="Nhóm nội bộ",
                photo_url="https://example.com/default.jpg", visibility="private",
            ),
        ]
    )
    db.commit()


def test_public_groups_are_searchable_and_hide_private_groups(
    client: TestClient, db_session: Session
) -> None:
    add_groups(db_session)
    response = client.get("/api/travel-groups")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["countryCode"] for item in body["items"]} == {"JP", "VN"}
    assert all(item["isPublic"] is True for item in body["items"])
    assert all(item["isMember"] is False for item in body["items"])

    filtered = client.get("/api/travel-groups", params={"query": "Việt"})
    assert filtered.status_code == 200
    assert [item["countryName"] for item in filtered.json()["items"]] == ["Việt Nam"]


def test_join_is_authenticated_csrf_protected_and_idempotent(
    registered_client: TestClient, db_session: Session
) -> None:
    add_groups(db_session)
    group_id = registered_client.get("/api/travel-groups", params={"query": "Nhật"}).json()["items"][0]["id"]
    assert registered_client.put(f"/api/travel-groups/{group_id}/membership").status_code == 403

    csrf = registered_client.cookies.get("vsf_csrf")
    headers = {"X-CSRF-Token": csrf}
    joined = registered_client.put(f"/api/travel-groups/{group_id}/membership", headers=headers)
    assert joined.status_code == 200
    assert joined.json() == {"groupId": group_id, "isMember": True, "memberCount": 1}

    joined_again = registered_client.put(f"/api/travel-groups/{group_id}/membership", headers=headers)
    assert joined_again.status_code == 200
    assert joined_again.json()["memberCount"] == 1
    groups = registered_client.get("/api/travel-groups", params={"query": "Nhật"}).json()
    assert groups["items"][0]["isMember"] is True


def test_anonymous_user_cannot_join(client: TestClient, db_session: Session) -> None:
    add_groups(db_session)
    group_id = client.get("/api/travel-groups").json()["items"][0]["id"]
    response = client.put(f"/api/travel-groups/{group_id}/membership")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_public_group_detail_is_readable_and_signed_in_users_can_post(
    registered_client: TestClient, db_session: Session
) -> None:
    add_groups(db_session)
    group_id = registered_client.get(
        "/api/travel-groups", params={"query": "Việt"}
    ).json()["items"][0]["id"]

    empty_detail = registered_client.get(f"/api/travel-groups/{group_id}")
    assert empty_detail.status_code == 200
    assert empty_detail.json()["group"]["countryCode"] == "VN"
    assert empty_detail.json()["posts"] == []
    assert empty_detail.json()["totalPosts"] == 0

    csrf = registered_client.cookies.get("vsf_csrf")
    created = registered_client.post(
        f"/api/travel-groups/{group_id}/posts",
        headers={"X-CSRF-Token": csrf},
        json={"content": "  Mọi người có gợi ý quán ăn ngon ở Hà Nội không?  "},
    )
    assert created.status_code == 201
    assert created.json()["content"] == "Mọi người có gợi ý quán ăn ngon ở Hà Nội không?"
    assert created.json()["author"]["fullName"] == "Nguyễn Minh Tuấn"

    detail = registered_client.get(f"/api/travel-groups/{group_id}").json()
    assert detail["totalPosts"] == 1
    assert [post["id"] for post in detail["posts"]] == [created.json()["id"]]


def test_group_posting_requires_authentication_csrf_and_non_blank_content(
    client: TestClient, registered_client: TestClient, db_session: Session
) -> None:
    add_groups(db_session)
    group_id = registered_client.get("/api/travel-groups").json()["items"][0]["id"]

    assert registered_client.post(
        f"/api/travel-groups/{group_id}/posts", json={"content": "Xin chào"}
    ).status_code == 403

    csrf = registered_client.cookies.get("vsf_csrf")
    blank = registered_client.post(
        f"/api/travel-groups/{group_id}/posts",
        headers={"X-CSRF-Token": csrf},
        json={"content": "   "},
    )
    assert blank.status_code == 422
    assert blank.json()["fieldErrors"]["content"] == "Bài viết cần có nội dung."

    client.cookies.clear()
    anonymous = client.post(
        f"/api/travel-groups/{group_id}/posts", json={"content": "Xin chào"}
    )
    assert anonymous.status_code == 401


def test_private_or_missing_group_detail_is_not_exposed(
    client: TestClient, db_session: Session
) -> None:
    add_groups(db_session)
    private_group = next(
        group for group in db_session.query(TravelGroup).all() if group.visibility == "private"
    )
    response = client.get(f"/api/travel-groups/{private_group.id}")
    assert response.status_code == 404
    assert response.json()["code"] == "TRAVEL_GROUP_NOT_FOUND"
