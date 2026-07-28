from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.auth.security import hash_password
from app.modules.marketplace.model import Entitlement, MarketplacePlan, Order
from app.modules.users.model import User


def _set_creator_verified(db: Session, email: str) -> User:
    db.rollback()
    user = db.query(User).filter_by(email=email.strip().lower()).first()
    assert user is not None
    user.role = "creator"
    user.creator_status = "verified"
    db.commit()
    return user


def test_person_c_e2e_acceptance_flow(client: TestClient, db_session: Session) -> None:
    """
    Kiểm thử E2E tổng hợp nghiệm thu cuối cùng (Mục 16 - docs/12-roadmap-person-c.md),
    bao phủ toàn bộ chuỗi nghiệp vụ Marketplace từ Tuần 1 đến Tuần 6.
    """
    # =========================================================================
    # BƯỚC 1: Traveler đăng ký và đăng nhập
    # =========================================================================
    reg_res = client.post(
        "/api/auth/register",
        json={
            "email": "chau_creator@example.com",
            "password": "Password123!",
            "fullName": "Châu Creator",
        },
    )
    assert reg_res.status_code == 201

    login_creator = client.post(
        "/api/auth/login",
        json={"email": "chau_creator@example.com", "password": "Password123!"},
    )
    assert login_creator.status_code == 200
    csrf_creator = login_creator.cookies.get("vsf_csrf") or ""

    # =========================================================================
    # BƯỚC 2: Gửi creator application
    # =========================================================================
    app_res = client.post(
        "/api/me/creator-application",
        json={
            "bio": "Local Creator miền Trung",
            "portfolioUrls": ["https://facebook.com/chau.travel"],
        },
        headers={"X-CSRF-Token": csrf_creator},
    )
    assert app_res.status_code == 200
    assert app_res.json()["creatorStatus"] == "pending"

    # =========================================================================
    # BƯỚC 3: Admin duyệt creator (chuẩn hóa sang verified)
    # =========================================================================
    _set_creator_verified(db_session, "chau_creator@example.com")

    # =========================================================================
    # BƯỚC 4 & 5: Creator chọn plan valid của Người B -> tạo listing draft & submit
    # =========================================================================
    login_creator = client.post(
        "/api/auth/login",
        json={"email": "chau_creator@example.com", "password": "Password123!"},
    )
    csrf_creator = login_creator.cookies.get("vsf_csrf") or ""

    draft_res = client.post(
        "/api/creator/listings",
        json={
            "planId": "plan_demo_valid",
            "title": "Đà Nẵng Hội An 4 Ngày 3 Đêm Chuẩn Bản Địa",
            "summary": "Lịch trình xịn sò đầy đủ quán ngon địa phương.",
            "category": "food",
            "priceAmount": 299000,
            "currency": "VND",
            "mediaUrls": ["https://images.unsplash.com/photo-1559592413-7cec4d0cae2b"],
        },
        headers={"X-CSRF-Token": csrf_creator},
    )
    assert draft_res.status_code == 201
    draft_data = draft_res.json()
    listing_id = draft_data["id"]
    version_v1_id = draft_data["versions"][0]["id"]
    assert draft_data["status"] == "draft"

    submit_res = client.post(
        f"/api/creator/listings/{listing_id}/submit",
        headers={"X-CSRF-Token": csrf_creator},
    )
    assert submit_res.status_code == 200
    assert submit_res.json()["versions"][0]["moderationStatus"] == "pending_review"

    # =========================================================================
    # BƯỚC 6 & 7: Admin approve -> Creator publish
    # =========================================================================
    admin = User(
        email="admin_e2e@example.com",
        full_name="Admin E2E",
        role="admin",
        status="active",
        password_hash=hash_password("Password123!"),
    )
    db_session.add(admin)
    db_session.commit()

    login_admin = client.post(
        "/api/auth/login",
        json={"email": "admin_e2e@example.com", "password": "Password123!"},
    )
    csrf_admin = login_admin.cookies.get("vsf_csrf") or ""

    approve_listing = client.post(
        f"/api/admin/listings/{version_v1_id}/review",
        json={"decision": "approve", "reason": "Hợp lệ tiêu chuẩn E2E"},
        headers={"X-CSRF-Token": csrf_admin},
    )
    assert approve_listing.status_code == 200
    assert approve_listing.json()["moderationStatus"] == "approved"

    # Đăng nhập lại creator -> publish
    login_creator = client.post(
        "/api/auth/login",
        json={"email": "chau_creator@example.com", "password": "Password123!"},
    )
    csrf_creator = login_creator.cookies.get("vsf_csrf") or ""

    publish_res = client.post(
        f"/api/creator/listings/{listing_id}/publish",
        headers={"X-CSRF-Token": csrf_creator},
    )
    assert publish_res.status_code == 200
    assert publish_res.json()["status"] == "published"
    assert publish_res.json()["currentPublishedVersionId"] == version_v1_id

    # =========================================================================
    # BƯỚC 8: Traveler khác tìm listing
    # =========================================================================
    client.post(
        "/api/auth/register",
        json={
            "email": "buyer_e2e@example.com",
            "password": "Password123!",
            "fullName": "Buyer E2E",
        },
    )
    login_buyer = client.post(
        "/api/auth/login",
        json={"email": "buyer_e2e@example.com", "password": "Password123!"},
    )
    assert login_buyer.status_code == 200
    csrf_buyer = login_buyer.cookies.get("vsf_csrf") or ""

    list_public = client.get("/api/listings?query=Đà Nẵng")
    assert list_public.status_code == 200
    assert list_public.json()["total"] >= 1

    detail_res = client.get(f"/api/listings/{listing_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["currentVersion"]["title"] == "Đà Nẵng Hội An 4 Ngày 3 Đêm Chuẩn Bản Địa"

    # =========================================================================
    # BƯỚC 9: Tạo checkout MoMo Sandbox
    # =========================================================================
    checkout_res = client.post(
        "/api/checkout-sessions",
        json={
            "listingId": listing_id,
            "listingVersionId": version_v1_id,
        },
        headers={
            "X-CSRF-Token": csrf_buyer,
            "Idempotency-Key": "e2e_checkout_key_001",
        },
    )
    assert checkout_res.status_code == 201
    checkout_data = checkout_res.json()
    order_id = checkout_data["orderId"]
    assert "paymentUrl" in checkout_data
    assert checkout_data["amount"] == 299000

    # =========================================================================
    # BƯỚC 10: Backend nhận IPN hợp lệ -> order chuyển paid -> entitlement cấp đúng 1 lần
    # =========================================================================
    ipn_payload = {
        "partnerCode": settings.momo_partner_code,
        "orderId": order_id,
        "requestId": f"req_e2e_{order_id}",
        "amount": 299000,
        "orderInfo": "Thanh toan VSF Travel Planner E2E",
        "orderType": "momo_wallet",
        "transId": 246813579,
        "resultCode": 0,
        "message": "Successful.",
        "payType": "qr",
        "responseTime": 1722000000000,
        "extraData": "",
        "signature": "mock_signature_for_local_sandbox_dev",
    }

    # Lần 1: Nhận IPN thành công -> 200 OK
    ipn_res1 = client.post("/api/payments/webhooks/momo", json=ipn_payload)
    assert ipn_res1.status_code == 200

    # Lần 2: lặp lại webhook IPN (Anti-replay test)
    ipn_res2 = client.post("/api/payments/webhooks/momo", json=ipn_payload)
    assert ipn_res2.status_code == 200

    # Kiểm tra Order đã chuyển sang paid và tạo đúng 1 Entitlement duy nhất
    order_in_db = db_session.query(Order).filter_by(id=order_id).first()
    assert order_in_db is not None
    assert order_in_db.status == "paid"

    entitlements = db_session.query(Entitlement).filter_by(order_id=order_id).all()
    assert len(entitlements) == 1
    assert entitlements[0].status == "active"

    # =========================================================================
    # BƯỚC 11: Buyer copy đúng plan version -> mở plan copy trong Planner
    # =========================================================================
    copy_res = client.post(
        f"/api/orders/{order_id}/copy",
        headers={"X-CSRF-Token": csrf_buyer},
    )
    assert copy_res.status_code == 200
    copy_data = copy_res.json()
    assert copy_data["planId"] is not None
    copied_plan_id = copy_data["planId"]
    assert copy_data["sourceListingVersionId"] == version_v1_id

    # Kiểm tra trong thư viện plan của buyer (/api/me/plans - Tuần 5)
    my_plans = client.get("/api/me/plans").json()
    assert len(my_plans) >= 1
    matching_plan = next((p for p in my_plans if p["orderId"] == order_id), None)
    assert matching_plan is not None
    assert matching_plan["copiedPlanId"] == copied_plan_id
    assert matching_plan["status"] == "active"

    # =========================================================================
    # BƯỚC 12: Creator update plan không làm đổi bản buyer đã mua (Bất biến Version)
    # =========================================================================
    login_creator = client.post(
        "/api/auth/login",
        json={"email": "chau_creator@example.com", "password": "Password123!"},
    )
    csrf_creator = login_creator.cookies.get("vsf_csrf") or ""

    # Creator cập nhật listing sang v2
    update_res = client.patch(
        f"/api/creator/listings/{listing_id}",
        json={"title": "Đà Nẵng Hội An 4 Ngày 3 Đêm (Bản Nâng Cấp v2)", "summary": "Thêm ngày tham quan"},
        headers={"X-CSRF-Token": csrf_creator},
    )
    assert update_res.status_code == 200

    # Kiểm tra Entitlement của buyer vẫn trỏ đúng về version v1 cũ
    ent_buyer = db_session.query(Entitlement).filter_by(order_id=order_id).first()
    assert ent_buyer is not None
    assert ent_buyer.marketplace_plan_version_id == version_v1_id  # Version v1 bất biến!

    # =========================================================================
    # BƯỚC 13: Buyer đánh giá plan (Review - Tuần 5)
    # =========================================================================
    login_buyer = client.post(
        "/api/auth/login",
        json={"email": "buyer_e2e@example.com", "password": "Password123!"},
    )
    csrf_buyer = login_buyer.cookies.get("vsf_csrf") or ""

    rev_res = client.post(
        f"/api/listings/{listing_id}/reviews",
        json={"rating": 5, "comment": "Lịch trình rất chuẩn chỉnh, dễ đi theo!"},
        headers={"X-CSRF-Token": csrf_buyer},
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["rating"] == 5

    # Kiểm tra review xuất hiện trên trang listing
    reviews_list = client.get(f"/api/listings/{listing_id}/reviews").json()
    assert len(reviews_list["items"]) >= 1
    assert any(r["comment"] == "Lịch trình rất chuẩn chỉnh, dễ đi theo!" for r in reviews_list["items"])

    # =========================================================================
    # BƯỚC 14: Report vi phạm listing & Admin xử lý (Report - Tuần 5)
    # =========================================================================
    report_res = client.post(
        f"/api/listings/{listing_id}/reports",
        json={"reason": "outdated", "description": "Một vài giá vé điểm tham quan cần cập nhật"},
        headers={"X-CSRF-Token": csrf_buyer},
    )
    assert report_res.status_code == 201
    rep_id = report_res.json()["id"]

    login_admin = client.post(
        "/api/auth/login",
        json={"email": "admin_e2e@example.com", "password": "Password123!"},
    )
    csrf_admin = login_admin.cookies.get("vsf_csrf") or ""

    # Admin chọn dismiss report
    resolve_res = client.post(
        f"/api/admin/reports/{rep_id}/resolve",
        json={"decision": "dismiss", "note": "Đã liên hệ creator xác minh."},
        headers={"X-CSRF-Token": csrf_admin},
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == "dismissed"
    assert resolve_res.json()["resolution"] == "Đã liên hệ creator xác minh."

    # =========================================================================
    # BƯỚC 15: Admin hoàn tiền đơn hàng (Refund) -> thu hồi quyền, giữ bản copy (Tuần 5)
    # =========================================================================
    refund_res = client.post(
        f"/api/admin/orders/{order_id}/refund",
        json={"reason": "Khách hàng yêu cầu đổi lịch trình."},
        headers={"X-CSRF-Token": csrf_admin},
    )
    assert refund_res.status_code == 200
    assert refund_res.json()["status"] == "refunded"

    # Kiểm tra quyền trong thư viện của buyer bị thu hồi nhưng copiedPlanId được bảo toàn
    login_buyer = client.post(
        "/api/auth/login",
        json={"email": "buyer_e2e@example.com", "password": "Password123!"},
    )
    my_plans_after_refund = client.get("/api/me/plans").json()
    matching_plan_refunded = next((p for p in my_plans_after_refund if p["orderId"] == order_id), None)
    assert matching_plan_refunded is not None
    assert matching_plan_refunded["status"] == "revoked"
    assert matching_plan_refunded["copiedPlanId"] == copied_plan_id  # Bảo toàn bản copy!

    # Buyer bị block không gửi được đánh giá sau khi đã refund
    csrf_buyer = login_buyer.cookies.get("vsf_csrf") or ""
    rev_after_refund = client.post(
        f"/api/listings/{listing_id}/reviews",
        json={"rating": 1, "comment": "Đã hoàn tiền"},
        headers={"X-CSRF-Token": csrf_buyer},
    )
    assert rev_after_refund.status_code == 403
    assert "REFUNDED" in rev_after_refund.json()["code"]

    # =========================================================================
    # BƯỚC 16: Admin kiểm tra Nhật ký kiểm toán (Audit Logs - Tuần 5)
    # =========================================================================
    login_admin = client.post(
        "/api/auth/login",
        json={"email": "admin_e2e@example.com", "password": "Password123!"},
    )
    audit_res = client.get("/api/admin/audit-events")
    assert audit_res.status_code == 200
    audit_events = audit_res.json()

    # Xác nhận các action quan trọng đều có mặt trong nhật ký kiểm toán
    actions = [e["action"] for e in audit_events]
    assert "listing_version.approve" in actions
    assert "report.dismiss" in actions
    assert "order.refund" in actions
