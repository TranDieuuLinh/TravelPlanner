from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CheckoutSessionCreateRequest(BaseModel):
    listing_id: str = Field(alias="listingId")
    listing_version_id: str = Field(alias="listingVersionId")

    model_config = ConfigDict(populate_by_name=True)


class CheckoutSessionResponse(BaseModel):
    order_id: str = Field(alias="orderId")
    status: str
    amount: int
    currency: str
    payment_url: str = Field(alias="paymentUrl")
    expires_at: datetime | None = Field(default=None, alias="expiresAt")

    model_config = ConfigDict(populate_by_name=True)


class OrderItemResponse(BaseModel):
    id: str
    order_id: str = Field(alias="orderId")
    marketplace_plan_id: str = Field(alias="marketplacePlanId")
    marketplace_plan_version_id: str = Field(alias="marketplacePlanVersionId")
    unit_amount: int = Field(alias="unitAmount")
    currency: str
    quantity: int

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class OrderResponse(BaseModel):
    id: str
    buyer_id: int = Field(alias="buyerId")
    total_amount: int = Field(alias="totalAmount")
    currency: str
    status: str
    items: list[OrderItemResponse] = Field(default_factory=list)
    created_at: datetime = Field(alias="createdAt")
    paid_at: datetime | None = Field(default=None, alias="paidAt")
    refunded_at: datetime | None = Field(default=None, alias="refundedAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class EntitlementResponse(BaseModel):
    id: str
    user_id: int = Field(alias="userId")
    order_id: str = Field(alias="orderId")
    order_item_id: str = Field(alias="orderItemId")
    marketplace_plan_id: str = Field(alias="marketplacePlanId")
    marketplace_plan_version_id: str = Field(alias="marketplacePlanVersionId")
    status: str
    copied_plan_id: str | None = Field(default=None, alias="copiedPlanId")
    copied_plan_version_id: str | None = Field(default=None, alias="copiedPlanVersionId")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class PlanCopyResponse(BaseModel):
    plan_id: str = Field(alias="planId")
    plan_version_id: str = Field(alias="planVersionId")
    source_plan_version_id: str = Field(alias="sourcePlanVersionId")
    source_listing_version_id: str = Field(alias="sourceListingVersionId")

    model_config = ConfigDict(populate_by_name=True)


class MoMoIPNPayload(BaseModel):
    partner_code: str = Field(alias="partnerCode")
    order_id: str = Field(alias="orderId")
    request_id: str = Field(alias="requestId")
    amount: int
    order_info: str | None = Field(default=None, alias="orderInfo")
    order_type: str | None = Field(default=None, alias="orderType")
    trans_id: Any | None = Field(default=None, alias="transId")
    result_code: int = Field(alias="resultCode")
    message: str | None = Field(default=None)
    pay_type: str | None = Field(default=None, alias="payType")
    response_time: Any | None = Field(default=None, alias="responseTime")
    extra_data: str | None = Field(default="", alias="extraData")
    signature: str

    model_config = ConfigDict(populate_by_name=True)
