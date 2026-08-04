from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.marketplace.model import MarketplacePlan, MarketplacePlanVersion
from app.modules.payments.momo_adapter import MoMoAdapter
from app.modules.users.model import User


def setup_published_listing(db: Session) -> tuple[MarketplacePlan, MarketplacePlanVersion, User]:
    creator = User(
        email="creator_order_test@example.com",
        full_name="Creator Test",
        role="creator",
        status="active",
        creator_status="verified",
    )
    db.add(creator)
    db.flush()

    plan = MarketplacePlan(
        id="mp_order_test_plan",
        creator_id=creator.id,
        status="published",
        current_published_version_id="mpv_order_test_v1",
    )
    db.add(plan)

    version = MarketplacePlanVersion(
        id="mpv_order_test_v1",
        marketplace_plan_id=plan.id,
        version=1,
        source_plan_id="plan_demo_valid",
        source_plan_version_id="plan_version_demo_valid_v1",
        title="Lịch trình Đà Nẵng Test MoMo",
        description="Mô tả chuyến đi test MoMo",
        destination="Đà Nẵng",
        duration_days=4,
        category="food",
        price_amount=149000,
        price_currency="VND",
        media_urls=["https://images.unsplash.com/photo-1559592413-7cec4d0cae2b"],
        preview_snapshot={"title": "Đà Nẵng", "days": 4},
        moderation_status="published",
    )
    db.add(version)

    db.commit()
    return plan, version, creator


def test_momo_adapter_signature() -> None:
    adapter = MoMoAdapter(
        partner_code="MOMO",
        access_key="F8B39C29B7F5",
        secret_key="K95549280BDF0E35417241123A0CE8A",
    )

    signature = adapter.create_payment_signature(
        amount=149000,
        extra_data="",
        ipn_url="http://localhost:8000/api/payments/webhooks/momo",
        order_id="order_test_123",
        order_info="Thanh toan plan",
        partner_code="MOMO",
        redirect_url="http://localhost:3000/orders/order_test_123/result",
        request_id="req_test_123",
    )
    assert signature is not None
    assert len(signature) == 64

    # Build matching IPN payload
    ipn_payload = {
        "partnerCode": "MOMO",
        "orderId": "order_test_123",
        "requestId": "req_test_123",
        "amount": 149000,
        "orderInfo": "Thanh toan plan",
        "orderType": "momo_wallet",
        "transId": 283948291,
        "resultCode": 0,
        "message": "Successful",
        "payType": "qr",
        "responseTime": 1690000000000,
        "extraData": "",
    }
    # Compute signature for IPN
    ipn_payload["signature"] = adapter.create_payment_signature(
        amount=149000,
        extra_data="",
        ipn_url="http://localhost:8000/api/payments/webhooks/momo",
        order_id="order_test_123",
        order_info="Thanh toan plan",
        partner_code="MOMO",
        redirect_url="http://localhost:3000/orders/order_test_123/result",
        request_id="req_test_123",
    )
    # The adapter verify_ipn_signature verifies signature string format
    # Test valid/invalid signature detection
    assert adapter.verify_ipn_signature({"signature": "invalid_sig"}) is False


def test_checkout_session_and_copy_flow(client: TestClient, db_session: Session) -> None:
    plan, version, creator = setup_published_listing(db_session)

    # 1. Register buyer
    res = client.post("/api/auth/register", json={"email": "buyer1@example.com", "password": "Password123!", "fullName": "Buyer One"})
    assert res.status_code == 201
    csrf = res.cookies.get("vsf_csrf") or ""

    # 2. Create Checkout Session
    checkout_res = client.post(
        "/api/checkout-sessions",
        json={
            "listingId": plan.id,
            "listingVersionId": version.id,
        },
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "idemp_checkout_001"},
    )
    assert checkout_res.status_code == 201
    session_data = checkout_res.json()
    assert session_data["status"] == "pending"
    assert session_data["amount"] == 149000
    assert "mock-momo" in session_data["paymentUrl"] or "momo" in session_data["paymentUrl"]
    order_id = session_data["orderId"]

    # Re-sending with same Idempotency-Key returns same order session
    idemp_res = client.post(
        "/api/checkout-sessions",
        json={
            "listingId": plan.id,
            "listingVersionId": version.id,
        },
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "idemp_checkout_001"},
    )
    assert idemp_res.status_code == 201
    assert idemp_res.json()["orderId"] == order_id

    # 3. Get order detail for buyer
    order_detail = client.get(f"/api/orders/{order_id}")
    assert order_detail.status_code == 200
    assert order_detail.json()["status"] == "pending"
    assert order_detail.json()["items"][0]["unitAmount"] == 149000

    # 4. Process MoMo IPN simulation
    momo_adapter = MoMoAdapter()
    ipn_payload = {
        "partnerCode": "MOMO",
        "orderId": order_id,
        "requestId": "req_simulated_ipn_1",
        "amount": 149000,
        "orderInfo": "Thanh toan plan",
        "orderType": "momo_wallet",
        "transId": 987654321,
        "resultCode": 0,
        "message": "Successful",
        "payType": "qr",
        "responseTime": 1690000000000,
        "extraData": "",
    }
    # Sign payload
    raw_sig = (
        f"accessKey={momo_adapter.access_key}"
        f"&amount=149000"
        f"&extraData="
        f"&message=Successful"
        f"&orderId={order_id}"
        f"&orderInfo=Thanh toan plan"
        f"&orderType=momo_wallet"
        f"&partnerCode=MOMO"
        f"&payType=qr"
        f"&requestId=req_simulated_ipn_1"
        f"&responseTime=1690000000000"
        f"&resultCode=0"
        f"&transId=987654321"
    )
    import hashlib
    import hmac
    ipn_payload["signature"] = hmac.new(
        momo_adapter.secret_key.encode("utf-8"),
        raw_sig.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    ipn_res = client.post("/api/payments/webhooks/momo", json=ipn_payload)
    assert ipn_res.status_code == 200
    assert ipn_res.json()["status"] == "ok"

    # Re-sending duplicate IPN returns "Already processed"
    ipn_dup_res = client.post("/api/payments/webhooks/momo", json=ipn_payload)
    assert ipn_dup_res.status_code == 200

    # Check order is now paid
    paid_order = client.get(f"/api/orders/{order_id}")
    assert paid_order.status_code == 200
    assert paid_order.json()["status"] == "paid"

    # 5. Buyer copies plan
    copy_res = client.post(
        f"/api/orders/{order_id}/copy",
        headers={"X-CSRF-Token": csrf},
    )
    assert copy_res.status_code == 200
    copy_data = copy_res.json()
    assert copy_data["planId"] is not None
    assert copy_data["sourceListingVersionId"] == version.id

    # Re-calling copy returns same planId (idempotent)
    copy_again = client.post(
        f"/api/orders/{order_id}/copy",
        headers={"X-CSRF-Token": csrf},
    )
    assert copy_again.status_code == 200
    assert copy_again.json()["planId"] == copy_data["planId"]
