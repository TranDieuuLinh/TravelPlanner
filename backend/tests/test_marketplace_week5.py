from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.marketplace.model import (
    Entitlement,
    MarketplacePlan,
    MarketplacePlanVersion,
    Order,
    OrderItem,
)
from app.modules.auth.security import hash_password
from app.modules.users.model import User


def setup_paid_listing_and_order(db: Session) -> tuple[MarketplacePlan, MarketplacePlanVersion, User, Order, Entitlement]:
    creator = User(
        email="creator_week5@example.com",
        full_name="Creator Week5",
        role="creator",
        status="active",
        creator_status="verified",
        password_hash=hash_password("Password123!"),
    )
    db.add(creator)
    db.flush()

    plan = MarketplacePlan(
        id="mp_week5_plan",
        creator_id=creator.id,
        status="published",
        current_published_version_id="mpv_week5_v1",
    )
    db.add(plan)

    version = MarketplacePlanVersion(
        id="mpv_week5_v1",
        marketplace_plan_id=plan.id,
        version=1,
        source_plan_id="plan_src_1",
        source_plan_version_id="ver_src_1",
        title="Lịch trình Đà Lạt 3N2Đ",
        description="Khám phá Đà Lạt toàn diện",
        destination="Đà Lạt",
        duration_days=3,
        category="nature",
        price_amount=199000,
        price_currency="VND",
        media_urls=["https://images.unsplash.com/photo-1559592413-7cec4d0cae2b"],
        preview_snapshot={"title": "Đà Lạt", "days": 3},
        moderation_status="published",
    )
    db.add(version)
    db.flush()

    # Create Buyer
    buyer = User(
        email="buyer_week5@example.com",
        full_name="Buyer Week5",
        role="traveler",
        status="active",
        password_hash=hash_password("Password123!"),
    )
    db.add(buyer)
    db.flush()

    # Create Paid Order & Active Entitlement
    order = Order(
        id="order_week5_001",
        buyer_id=buyer.id,
        total_amount=199000,
        currency="VND",
        status="paid",
    )
    db.add(order)
    db.flush()

    order_item = OrderItem(
        id="item_week5_001",
        order_id=order.id,
        marketplace_plan_id=plan.id,
        marketplace_plan_version_id=version.id,
        unit_amount=199000,
    )
    db.add(order_item)
    db.flush()

    entitlement = Entitlement(
        id="ent_week5_001",
        user_id=buyer.id,
        order_id=order.id,
        order_item_id=order_item.id,
        marketplace_plan_id=plan.id,
        marketplace_plan_version_id=version.id,
        status="active",
        copied_plan_id="my_copied_plan_dl_001",
        copied_plan_version_id="ver_001",
    )
    db.add(entitlement)
    db.commit()

    return plan, version, buyer, order, entitlement


def test_buyer_purchased_plans_library(client: TestClient, db_session: Session) -> None:
    plan, version, buyer, order, entitlement = setup_paid_listing_and_order(db_session)

    # Login as buyer
    login_res = client.post(
        "/api/auth/login",
        json={"email": "buyer_week5@example.com", "password": "Password123!"},
    )
    assert login_res.status_code == 200

    # Get buyer plans
    plans_res = client.get("/api/me/plans")
    assert plans_res.status_code == 200
    plans = plans_res.json()
    assert len(plans) == 1
    assert plans[0]["orderId"] == "order_week5_001"
    assert plans[0]["marketplacePlanId"] == plan.id
    assert plans[0]["title"] == "Lịch trình Đà Lạt 3N2Đ"
    assert plans[0]["copiedPlanId"] == "my_copied_plan_dl_001"
    assert plans[0]["status"] == "active"


def test_buyer_review_flow_and_permissions(client: TestClient, db_session: Session) -> None:
    plan, version, buyer, order, entitlement = setup_paid_listing_and_order(db_session)

    # 1. User without entitlement tries to review -> 403 Forbidden
    client.post(
        "/api/auth/register",
        json={"email": "other_traveler@example.com", "password": "Password123!", "fullName": "Other Traveler"},
    )
    login_other = client.post(
        "/api/auth/login",
        json={"email": "other_traveler@example.com", "password": "Password123!"},
    )
    csrf_other = login_other.cookies.get("travelplanner_csrf") or ""

    forbidden_rev = client.post(
        f"/api/listings/{plan.id}/reviews",
        json={"rating": 5, "comment": "Lịch trình rất hay!"},
        headers={"X-CSRF-Token": csrf_other},
    )
    assert forbidden_rev.status_code == 403
    assert "FORBIDDEN_REVIEW" in forbidden_rev.json()["code"]

    # 2. Buyer with active entitlement reviews -> 200 OK
    login_buyer = client.post(
        "/api/auth/login",
        json={"email": "buyer_week5@example.com", "password": "Password123!"},
    )
    csrf_buyer = login_buyer.cookies.get("travelplanner_csrf") or ""

    review_res = client.post(
        f"/api/listings/{plan.id}/reviews",
        json={"rating": 5, "comment": "Lịch trình tuyệt vời, rất đáng mua!"},
        headers={"X-CSRF-Token": csrf_buyer},
    )
    assert review_res.status_code == 200
    rev_data = review_res.json()
    assert rev_data["rating"] == 5
    assert rev_data["comment"] == "Lịch trình tuyệt vời, rất đáng mua!"
    assert rev_data["reviewerName"] == "Buyer Week5"

    # 3. Public lists reviews -> shows the review
    list_res = client.get(f"/api/listings/{plan.id}/reviews")
    assert list_res.status_code == 200
    paginated = list_res.json()
    assert paginated["total"] == 1
    assert paginated["items"][0]["comment"] == "Lịch trình tuyệt vời, rất đáng mua!"

    # 4. Buyer updates existing review -> comment is updated
    update_res = client.post(
        f"/api/listings/{plan.id}/reviews",
        json={"rating": 4, "comment": "Cập nhật đánh giá: 4 sao vì hơi nhiều điểm ăn uống."},
        headers={"X-CSRF-Token": csrf_buyer},
    )
    assert update_res.status_code == 200
    assert update_res.json()["rating"] == 4
    assert update_res.json()["comment"] == "Cập nhật đánh giá: 4 sao vì hơi nhiều điểm ăn uống."

    # Total remains 1
    list_res_2 = client.get(f"/api/listings/{plan.id}/reviews")
    assert list_res_2.json()["total"] == 1


def test_listing_report_and_admin_moderation(client: TestClient, db_session: Session) -> None:
    plan, version, buyer, order, entitlement = setup_paid_listing_and_order(db_session)

    # 1. Any user reports listing
    login_buyer = client.post(
        "/api/auth/login",
        json={"email": "buyer_week5@example.com", "password": "Password123!"},
    )
    csrf_buyer = login_buyer.cookies.get("travelplanner_csrf") or ""

    report_res = client.post(
        f"/api/listings/{plan.id}/reports",
        json={"reason": "outdated", "description": "Giá vé trong lịch trình không còn đúng."},
        headers={"X-CSRF-Token": csrf_buyer},
    )
    assert report_res.status_code == 201
    rep_data = report_res.json()
    assert rep_data["status"] == "pending"
    assert rep_data["reason"] == "outdated"
    report_id = rep_data["id"]

    # 2. Create Admin user
    admin = User(
        email="admin_week5@example.com",
        full_name="Admin Week5",
        role="admin",
        status="active",
        password_hash=hash_password("Password123!"),
    )
    db_session.add(admin)
    db_session.commit()

    login_admin = client.post(
        "/api/auth/login",
        json={"email": "admin_week5@example.com", "password": "Password123!"},
    )
    csrf_admin = login_admin.cookies.get("travelplanner_csrf") or ""

    # 3. Admin queries reports
    admin_rep_res = client.get("/api/admin/reports")
    assert admin_rep_res.status_code == 200
    reps = admin_rep_res.json()
    assert len(reps) >= 1
    assert any(r["id"] == report_id for r in reps)

    # 4. Admin resolves report -> unpublish
    resolve_res = client.post(
        f"/api/admin/reports/{report_id}/resolve",
        json={"decision": "unpublish", "note": "Gỡ bài vì thông tin giá lỗi thời."},
        headers={"X-CSRF-Token": csrf_admin},
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == "resolved"
    assert resolve_res.json()["resolution"] == "Gỡ bài vì thông tin giá lỗi thời."

    # Verify plan status is unpublished
    detail_res = client.get(f"/api/listings/{plan.id}")
    assert detail_res.status_code == 404  # Public cannot see unpublished listing


def test_admin_order_refund_and_audit_events(client: TestClient, db_session: Session) -> None:
    plan, version, buyer, order, entitlement = setup_paid_listing_and_order(db_session)

    # Admin setup
    admin = User(
        email="admin_refund@example.com",
        full_name="Admin Refund",
        role="admin",
        status="active",
        password_hash=hash_password("Password123!"),
    )
    db_session.add(admin)
    db_session.commit()

    login_admin = client.post(
        "/api/auth/login",
        json={"email": "admin_refund@example.com", "password": "Password123!"},
    )
    csrf_admin = login_admin.cookies.get("travelplanner_csrf") or ""

    # 1. Admin refunds order
    refund_res = client.post(
        f"/api/admin/orders/{order.id}/refund",
        json={"reason": "Khách hàng yêu cầu hoàn tiền do mua nhầm."},
        headers={"X-CSRF-Token": csrf_admin},
    )
    assert refund_res.status_code == 200
    assert refund_res.json()["status"] == "refunded"

    # 2. Check Entitlement is revoked but copied_plan_id is preserved
    login_buyer = client.post(
        "/api/auth/login",
        json={"email": "buyer_week5@example.com", "password": "Password123!"},
    )
    plans_buyer = client.get("/api/me/plans").json()
    assert len(plans_buyer) == 1
    assert plans_buyer[0]["status"] == "revoked"
    assert plans_buyer[0]["copiedPlanId"] == "my_copied_plan_dl_001"  # Copied plan preserved!

    # 3. Buyer cannot review after refund
    csrf_buyer = login_buyer.cookies.get("travelplanner_csrf") or ""
    rev_after_refund = client.post(
        f"/api/listings/{plan.id}/reviews",
        json={"rating": 5, "comment": "Thử đánh giá sau khi hoàn tiền."},
        headers={"X-CSRF-Token": csrf_buyer},
    )
    assert rev_after_refund.status_code == 403
    assert "REFUNDED" in rev_after_refund.json()["code"]

    # 4. Idempotency test: refund second time returns success (log back in as admin)
    login_admin = client.post(
        "/api/auth/login",
        json={"email": "admin_refund@example.com", "password": "Password123!"},
    )
    csrf_admin = login_admin.cookies.get("travelplanner_csrf") or ""

    refund_again = client.post(
        f"/api/admin/orders/{order.id}/refund",
        json={"reason": "Hoàn tiền lần 2"},
        headers={"X-CSRF-Token": csrf_admin},
    )
    assert refund_again.status_code == 200
    assert refund_again.json()["status"] == "refunded"
    assert "trước đó" in refund_again.json()["message"]

    # 5. Verify Audit Logs
    audit_res = client.get("/api/admin/audit-events")
    assert audit_res.status_code == 200
    events = audit_res.json()
    assert any(e["action"] == "order.refund" and e["resourceId"] == order.id for e in events)
    # Ensure no sensitive keys in metadata
    for ev in events:
        for k in ev.get("metadata", {}).keys():
            assert "password" not in str(k).lower()
            assert "jwt" not in str(k).lower()
            assert "secret" not in str(k).lower()
