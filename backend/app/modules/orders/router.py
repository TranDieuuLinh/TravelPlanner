from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, status

from app.modules.auth.dependencies import require_active_user, require_csrf
from app.modules.orders.dependencies import get_order_service
from app.modules.orders.schema import (
    CheckoutSessionCreateRequest,
    CheckoutSessionResponse,
    OrderResponse,
    PlanCopyResponse,
)
from app.modules.orders.service import OrderService
from app.modules.users.model import User

router = APIRouter(prefix="", tags=["orders-and-payments"])


@router.post("/checkout-sessions", response_model=CheckoutSessionResponse, status_code=status.HTTP_201_CREATED)
def create_checkout_session(
    payload: CheckoutSessionCreateRequest,
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[OrderService, Depends(get_order_service)],
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CheckoutSessionResponse:
    return service.create_checkout_session(user, payload, idempotency_key)


@router.post("/payments/webhooks/momo")
async def momo_ipn_webhook(
    request: Request,
    service: Annotated[OrderService, Depends(get_order_service)],
) -> dict[str, Any]:
    payload_data = await request.json()
    return service.process_momo_ipn(payload_data)


@router.get("/orders", response_model=list[OrderResponse])
def get_user_orders(
    user: Annotated[User, Depends(require_active_user)],
    service: Annotated[OrderService, Depends(get_order_service)],
) -> list[OrderResponse]:
    return service.get_user_orders(user)


@router.get("/orders/{order_id}", response_model=OrderResponse)
def get_order_detail(
    order_id: str,
    user: Annotated[User, Depends(require_active_user)],
    service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderResponse:
    return service.get_order_detail(user, order_id)


@router.post("/orders/{order_id}/copy", response_model=PlanCopyResponse)
def copy_plan_for_buyer(
    order_id: str,
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[OrderService, Depends(get_order_service)],
) -> PlanCopyResponse:
    return service.copy_plan_for_buyer(user, order_id)
