from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.modules.marketplace.model import (
    AuditEvent,
    Entitlement,
    Order,
    OrderItem,
    Payment,
    PaymentEvent,
)
from app.modules.marketplace.repository import MarketplaceRepository
from app.modules.orders.repository import OrderRepository
from app.modules.orders.schema import (
    CheckoutSessionCreateRequest,
    CheckoutSessionResponse,
    MoMoIPNPayload,
    OrderItemResponse,
    OrderResponse,
    PlanCopyResponse,
)
from app.modules.payments.momo_adapter import MoMoAdapter
from app.modules.users.model import User
from app.shared.contracts.plan_marketplace import PlanMarketplaceGateway
from app.shared.errors import AppError


class OrderService:
    def __init__(
        self,
        db: Session,
        repo: OrderRepository,
        marketplace_repo: MarketplaceRepository,
        momo_adapter: MoMoAdapter,
        plan_gateway: PlanMarketplaceGateway,
    ) -> None:
        self.db = db
        self.repo = repo
        self.marketplace_repo = marketplace_repo
        self.momo_adapter = momo_adapter
        self.plan_gateway = plan_gateway

    def create_checkout_session(
        self,
        buyer: User,
        payload: CheckoutSessionCreateRequest,
        idempotency_key: str | None = None,
    ) -> CheckoutSessionResponse:
        if idempotency_key:
            existing = self.repo.get_order_by_idempotency_key(idempotency_key)
            if existing:
                payment = self.repo.get_payment_by_order_id(existing.id)
                return CheckoutSessionResponse(
                    orderId=existing.id,
                    status=existing.status,
                    amount=existing.total_amount,
                    currency=existing.currency,
                    paymentUrl=payment.payment_url if payment else "",
                    expiresAt=None,
                )

        version = self.marketplace_repo.get_version_by_id(payload.listing_version_id)
        if not version or version.marketplace_plan_id != payload.listing_id:
            raise AppError(404, "LISTING_VERSION_NOT_FOUND", "Không tìm thấy phiên bản listing cần mua.")

        plan = self.marketplace_repo.get_plan_by_id(payload.listing_id)
        if not plan or plan.status != "published":
            raise AppError(400, "LISTING_NOT_AVAILABLE", "Sản phẩm không khả dụng để thanh toán.")

        order_id = f"order_{uuid4().hex[:12]}"
        request_id = f"req_{uuid4().hex[:12]}"
        item_id = f"item_{uuid4().hex[:12]}"

        order = Order(
            id=order_id,
            buyer_id=buyer.id,
            total_amount=version.price_amount,
            currency=version.price_currency,
            status="pending",
            idempotency_key=idempotency_key,
            provider_request_id=request_id,
        )
        self.repo.create_order(order)

        order_item = OrderItem(
            id=item_id,
            order_id=order.id,
            marketplace_plan_id=plan.id,
            marketplace_plan_version_id=version.id,
            unit_amount=version.price_amount,
            currency=version.price_currency,
            quantity=1,
        )
        self.repo.create_order_item(order_item)

        momo_res = self.momo_adapter.create_payment_session(
            order_id=order.id,
            request_id=request_id,
            amount=version.price_amount,
            order_info=f"Thanh toan plan {version.title[:50]}",
        )

        payment = Payment(
            id=f"pay_{uuid4().hex[:12]}",
            order_id=order.id,
            provider="momo",
            method="momo_wallet",
            request_id=request_id,
            amount=version.price_amount,
            currency=version.price_currency,
            status="pending",
            payment_url=momo_res.get("payUrl", ""),
        )
        self.repo.create_payment(payment)

        self.db.commit()

        return CheckoutSessionResponse(
            orderId=order.id,
            status=order.status,
            amount=order.total_amount,
            currency=order.currency,
            paymentUrl=payment.payment_url or "",
            expiresAt=None,
        )

    def process_momo_ipn(self, payload_data: MoMoIPNPayload | dict) -> dict[str, str]:
        if isinstance(payload_data, MoMoIPNPayload):
            payload_dict = payload_data.model_dump(by_alias=True)
        else:
            payload_dict = payload_data

        if not self.momo_adapter.verify_ipn_signature(payload_dict):
            raise AppError(400, "INVALID_SIGNATURE", "Chữ ký MoMo IPN không hợp lệ.")

        trans_id = str(payload_dict.get("transId") or payload_dict.get("requestId"))
        existing_event = self.repo.get_payment_event_by_provider_event("momo", trans_id)
        if existing_event:
            return {"status": "ok", "message": "Already processed"}

        order_id = payload_dict.get("orderId")
        order = self.repo.get_order_by_id(order_id)
        if not order:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng tương ứng với IPN.")

        payment = self.repo.get_payment_by_order_id(order.id)

        event = PaymentEvent(
            id=f"pevt_{uuid4().hex[:12]}",
            payment_id=payment.id if payment else None,
            order_id=order.id,
            provider="momo",
            provider_event_id=trans_id,
            request_id=payload_dict.get("requestId"),
            transaction_id=trans_id,
            event_type="ipn_received",
            payload=payload_dict,
        )
        self.repo.create_payment_event(event)

        now = datetime.now(timezone.utc)
        result_code = payload_dict.get("resultCode", -1)

        if result_code == 0:
            if payment:
                payment.status = "success"
                payment.paid_at = now
                payment.transaction_id = trans_id
                self.repo.update_payment(payment)

            order.status = "paid"
            order.paid_at = now
            self.repo.update_order(order)

            items = self.repo.get_order_items(order.id)
            for item in items:
                existing_entitlement = self.repo.get_entitlement_by_order_item_id(item.id)
                if not existing_entitlement:
                    entitlement = Entitlement(
                        id=f"ent_{uuid4().hex[:12]}",
                        user_id=order.buyer_id,
                        order_id=order.id,
                        order_item_id=item.id,
                        marketplace_plan_id=item.marketplace_plan_id,
                        marketplace_plan_version_id=item.marketplace_plan_version_id,
                        status="active",
                    )
                    self.repo.create_entitlement(entitlement)

            audit = AuditEvent(
                id=f"evt_{uuid4().hex[:12]}",
                actor_id=order.buyer_id,
                action="payment.success",
                resource_type="order",
                resource_id=order.id,
                metadata_={"trans_id": trans_id, "amount": order.total_amount},
            )
            self.db.add(audit)
        else:
            if payment:
                payment.status = "failed"
                self.repo.update_payment(payment)
            order.status = "failed"
            self.repo.update_order(order)

        self.db.commit()
        return {"status": "ok"}

    def get_order_detail(self, user: User, order_id: str) -> OrderResponse:
        order = self.repo.get_order_by_id(order_id)
        if not order:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")

        if order.buyer_id != user.id and user.role != "admin":
            raise AppError(403, "ACCESS_DENIED", "Bạn không có quyền truy cập đơn hàng này.")

        items = self.repo.get_order_items(order.id)
        item_responses = [OrderItemResponse.model_validate(it) for it in items]

        return OrderResponse(
            id=order.id,
            buyerId=order.buyer_id,
            totalAmount=order.total_amount,
            currency=order.currency,
            status=order.status,
            items=item_responses,
            createdAt=order.created_at,
            paidAt=order.paid_at,
            refundedAt=order.refunded_at,
        )

    def get_user_orders(self, buyer: User) -> list[OrderResponse]:
        orders = self.repo.get_orders_by_buyer(buyer.id)
        responses = []
        for order in orders:
            items = self.repo.get_order_items(order.id)
            item_responses = [OrderItemResponse.model_validate(it) for it in items]
            responses.append(
                OrderResponse(
                    id=order.id,
                    buyerId=order.buyer_id,
                    totalAmount=order.total_amount,
                    currency=order.currency,
                    status=order.status,
                    items=item_responses,
                    createdAt=order.created_at,
                    paidAt=order.paid_at,
                    refundedAt=order.refunded_at,
                )
            )
        return responses

    def copy_plan_for_buyer(self, buyer: User, order_id: str) -> PlanCopyResponse:
        order = self.repo.get_order_by_id(order_id)
        if not order:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")

        if order.buyer_id != buyer.id:
            raise AppError(403, "ACCESS_DENIED", "Bạn không sở hữu đơn hàng này.")

        if order.status != "paid":
            raise AppError(400, "ORDER_NOT_PAID", "Đơn hàng chưa được thanh toán thành công.")

        items = self.repo.get_order_items(order.id)
        if not items:
            raise AppError(404, "ORDER_ITEM_NOT_FOUND", "Không tìm thấy sản phẩm trong đơn hàng.")

        target_item = items[0]
        entitlement = self.repo.get_entitlement_by_order_item_id(target_item.id)
        if not entitlement or entitlement.status != "active":
            raise AppError(403, "ENTITLEMENT_NOT_ACTIVE", "Quyền truy cập sản phẩm không còn hiệu lực.")

        if entitlement.copied_plan_id:
            return PlanCopyResponse(
                planId=entitlement.copied_plan_id,
                planVersionId=entitlement.copied_plan_version_id or "",
                sourcePlanVersionId=target_item.marketplace_plan_version_id,
                sourceListingVersionId=target_item.marketplace_plan_version_id,
            )

        copy_result = self.plan_gateway.clone_for_buyer(
            plan_version_id=target_item.marketplace_plan_version_id,
            buyer_id=buyer.id,
            source_listing_version_id=target_item.marketplace_plan_version_id,
        )

        entitlement.copied_plan_id = copy_result.plan_id
        entitlement.copied_plan_version_id = copy_result.plan_version_id
        self.repo.update_entitlement(entitlement)

        self.db.commit()

        return PlanCopyResponse(
            planId=copy_result.plan_id,
            planVersionId=copy_result.plan_version_id,
            sourcePlanVersionId=copy_result.source_plan_version_id,
            sourceListingVersionId=copy_result.source_listing_version_id,
        )
