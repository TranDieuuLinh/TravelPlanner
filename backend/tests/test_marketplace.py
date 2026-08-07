import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.users.model import User


def set_user_role(db_session: Session, email: str, role: str) -> User:
    db_session.rollback()
    user = db_session.query(User).filter_by(email=email.strip().lower()).first()
    assert user is not None, f"User with email {email} not found"
    user.role = role
    if role == "creator":
        user.creator_status = "verified"
    db_session.commit()
    return user


def test_traveler_cannot_create_listing(client: TestClient, db_session: Session) -> None:
    # Register a traveler
    res = client.post("/api/auth/register", json={"email": "traveler1@example.com", "password": "Password123!", "fullName": "Traveler One"})
    assert res.status_code == 201
    csrf = res.cookies.get("travelplanner_csrf") or ""

    # Try creating listing
    create_res = client.post(
        "/api/creator/listings",
        json={
            "planId": "plan_demo_valid",
            "title": "Đà Nẵng 4 ngày",
            "summary": "Mô tả hành trình",
            "category": "food",
            "priceAmount": 100000,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert create_res.status_code == 403
    assert create_res.json()["code"] == "CREATOR_REQUIRED"


def test_creator_listing_full_workflow(client: TestClient, db_session: Session) -> None:
    # 1. Register user and make them creator
    creator_res = client.post("/api/auth/register", json={"email": "creator1@example.com", "password": "Password123!", "fullName": "Creator One"})
    assert creator_res.status_code == 201
    creator_csrf = creator_res.cookies.get("travelplanner_csrf") or ""

    creator_user = set_user_role(db_session, "creator1@example.com", "creator")

    # 2. Creator creates draft listing from plan_demo_valid
    create_res = client.post(
        "/api/creator/listings",
        json={
            "planId": "plan_demo_valid",
            "title": "Đà Nẵng & Hội An Đậm Chất",
            "summary": "Chuyến đi 4 ngày trải nghiệm trọn vẹn miền Trung.",
            "category": "food",
            "priceAmount": 150000,
            "currency": "VND",
            "mediaUrls": ["https://cdn.example.com/danang.jpg"],
        },
        headers={"X-CSRF-Token": creator_csrf},
    )
    assert create_res.status_code == 201
    listing = create_res.json()
    assert listing["status"] == "draft"
    listing_id = listing["id"]
    assert listing["versions"][0]["moderationStatus"] == "draft"

    # 3. Draft/invalid plan cannot be submitted
    invalid_create_res = client.post(
        "/api/creator/listings",
        json={
            "planId": "plan_demo_invalid",
            "title": "Sapa lỗi",
            "summary": "Plan chưa valid",
            "category": "nature",
            "priceAmount": 100000,
        },
        headers={"X-CSRF-Token": creator_csrf},
    )
    assert invalid_create_res.status_code == 201
    invalid_listing_id = invalid_create_res.json()["id"]

    submit_invalid_res = client.post(
        f"/api/creator/listings/{invalid_listing_id}/submit",
        headers={"X-CSRF-Token": creator_csrf},
    )
    assert submit_invalid_res.status_code == 400
    assert submit_invalid_res.json()["code"] == "PLAN_NOT_ELIGIBLE"

    # 4. Submit valid draft listing -> pending_review
    submit_res = client.post(
        f"/api/creator/listings/{listing_id}/submit",
        headers={"X-CSRF-Token": creator_csrf},
    )
    assert submit_res.status_code == 200
    submitted_listing = submit_res.json()
    version_id = submitted_listing["versions"][0]["id"]
    assert submitted_listing["versions"][0]["moderationStatus"] == "pending_review"

    # 5. Non-admin cannot view pending listings or review
    admin_pending_fail = client.get("/api/admin/listings/pending")
    assert admin_pending_fail.status_code == 403

    # Upgrade user role to admin to test admin moderation
    set_user_role(db_session, "creator1@example.com", "admin")

    # 6. Admin lists pending listings & approves version
    admin_pending = client.get("/api/admin/listings/pending")
    assert admin_pending.status_code == 200
    pending_list = admin_pending.json()
    assert len(pending_list) >= 1
    assert pending_list[0]["listingVersionId"] == version_id

    review_res = client.post(
        f"/api/admin/listings/{version_id}/review",
        json={"decision": "approve", "reason": "Hợp lệ"},
        headers={"X-CSRF-Token": creator_csrf},
    )
    assert review_res.status_code == 200
    assert review_res.json()["moderationStatus"] == "approved"

    # Set user role back to creator for publishing
    set_user_role(db_session, "creator1@example.com", "creator")

    # 7. Creator publishes approved listing
    pub_res = client.post(
        f"/api/creator/listings/{listing_id}/publish",
        headers={"X-CSRF-Token": creator_csrf},
    )
    assert pub_res.status_code == 200
    pub_listing = pub_res.json()
    assert pub_listing["status"] == "published"
    assert pub_listing["currentPublishedVersionId"] == version_id

    # 8. Search public listings - should find the published listing
    search_res = client.get("/api/listings?query=Đà Nẵng")
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["total"] >= 1
    assert search_data["items"][0]["id"] == listing_id

    # 9. Editing published listing creates new draft version with version=2
    update_res = client.patch(
        f"/api/creator/listings/{listing_id}",
        json={"title": "Đà Nẵng Mới v2", "summary": "Cập nhật mô tả v2"},
        headers={"X-CSRF-Token": creator_csrf},
    )
    assert update_res.status_code == 200
    updated_listing = update_res.json()

    # Should have 2 versions now
    assert len(updated_listing["versions"]) == 2
    version_v2 = [v for v in updated_listing["versions"] if v["version"] == 2][0]
    assert version_v2["title"] == "Đà Nẵng Mới v2"
    assert version_v2["moderationStatus"] == "draft"

    # Public detail still shows version v1 (current published version)
    detail_res = client.get(f"/api/listings/{listing_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["currentVersion"]["title"] == "Đà Nẵng & Hội An Đậm Chất"

    # 10. Favorite PUT/DELETE idempotency
    fav_put1 = client.put(f"/api/listings/{listing_id}/favorite", headers={"X-CSRF-Token": creator_csrf})
    assert fav_put1.status_code == 200
    assert fav_put1.json()["isFavorited"] is True

    fav_put2 = client.put(f"/api/listings/{listing_id}/favorite", headers={"X-CSRF-Token": creator_csrf})
    assert fav_put2.status_code == 200
    assert fav_put2.json()["isFavorited"] is True

    my_favs = client.get("/api/me/favorites")
    assert my_favs.status_code == 200
    assert len(my_favs.json()) == 1

    fav_del1 = client.delete(f"/api/listings/{listing_id}/favorite", headers={"X-CSRF-Token": creator_csrf})
    assert fav_del1.status_code == 200
    assert fav_del1.json()["isFavorited"] is False

    fav_del2 = client.delete(f"/api/listings/{listing_id}/favorite", headers={"X-CSRF-Token": creator_csrf})
    assert fav_del2.status_code == 200
    assert fav_del2.json()["isFavorited"] is False


def test_cannot_edit_other_creator_listing(client: TestClient, db_session: Session) -> None:
    # Creator A
    res_a = client.post("/api/auth/register", json={"email": "creatorA@example.com", "password": "Password123!", "fullName": "Creator A"})
    assert res_a.status_code == 201, f"res_a status: {res_a.status_code}, body: {res_a.text}"
    csrf_a = res_a.cookies.get("travelplanner_csrf") or ""
    set_user_role(db_session, "creatorA@example.com", "creator")

    create_res = client.post(
        "/api/creator/listings",
        json={"planId": "plan_demo_valid", "title": "Listing A", "summary": "Mô tả", "category": "food", "priceAmount": 100000},
        headers={"X-CSRF-Token": csrf_a},
    )
    listing_id = create_res.json()["id"]

    # Creator B
    res_b = client.post("/api/auth/register", json={"email": "creatorB@example.com", "password": "Password123!", "fullName": "Creator B"})
    csrf_b = res_b.cookies.get("travelplanner_csrf") or ""
    set_user_role(db_session, "creatorB@example.com", "creator")

    # Creator B tries to update listing A
    update_res = client.patch(
        f"/api/creator/listings/{listing_id}",
        json={"title": "Hacked Title"},
        headers={"X-CSRF-Token": csrf_b},
    )
    assert update_res.status_code == 404
