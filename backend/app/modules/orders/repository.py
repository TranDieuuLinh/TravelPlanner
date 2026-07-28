from typing import Sequence

from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.modules.marketplace.model import (
    Entitlement,
    Order,
    OrderItem,
    Payment,
    PaymentEvent,
)


class OrderRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_order(self, order: Order) -> Order:
        self.db.add(order)
        self.db.flush()
        return order

    def update_order(self, order: Order) -> Order:
        self.db.flush()
        return order

    def get_order_by_id(self, order_id: str) -> Order | None:
        return self.db.scalar(select(Order).where(Order.id == order_id))

    def get_order_by_idempotency_key(self, key: str) -> Order | None:
        return self.db.scalar(select(Order).where(Order.idempotency_key == key))

    def get_orders_by_buyer(self, buyer_id: int) -> Sequence[Order]:
        return self.db.scalars(
            select(Order).where(Order.buyer_id == buyer_id).order_by(desc(Order.created_at))
        ).all()

    def create_order_item(self, item: OrderItem) -> OrderItem:
        self.db.add(item)
        self.db.flush()
        return item

    def get_order_items(self, order_id: str) -> Sequence[OrderItem]:
        return self.db.scalars(select(OrderItem).where(OrderItem.order_id == order_id)).all()

    def create_payment(self, payment: Payment) -> Payment:
        self.db.add(payment)
        self.db.flush()
        return payment

    def update_payment(self, payment: Payment) -> Payment:
        self.db.flush()
        return payment

    def get_payment_by_request_id(self, request_id: str) -> Payment | None:
        return self.db.scalar(select(Payment).where(Payment.request_id == request_id))

    def get_payment_by_order_id(self, order_id: str) -> Payment | None:
        return self.db.scalar(select(Payment).where(Payment.order_id == order_id))

    def create_payment_event(self, event: PaymentEvent) -> PaymentEvent:
        self.db.add(event)
        self.db.flush()
        return event

    def get_payment_event_by_provider_event(self, provider: str, event_id: str) -> PaymentEvent | None:
        return self.db.scalar(
            select(PaymentEvent).where(
                PaymentEvent.provider == provider,
                PaymentEvent.provider_event_id == event_id,
            )
        )

    def create_entitlement(self, entitlement: Entitlement) -> Entitlement:
        self.db.add(entitlement)
        self.db.flush()
        return entitlement

    def update_entitlement(self, entitlement: Entitlement) -> Entitlement:
        self.db.flush()
        return entitlement

    def get_entitlement_by_order_item_id(self, order_item_id: str) -> Entitlement | None:
        return self.db.scalar(select(Entitlement).where(Entitlement.order_item_id == order_item_id))

    def get_entitlements_by_user(self, user_id: int) -> Sequence[Entitlement]:
        return self.db.scalars(
            select(Entitlement).where(Entitlement.user_id == user_id).order_by(desc(Entitlement.created_at))
        ).all()
