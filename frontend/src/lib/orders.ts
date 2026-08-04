import { apiFetch } from "@/lib/api";
import type { CheckoutSession, OrderDetail, PlanCopyResult } from "@/types/orders";

export async function createCheckoutSession(
  listingId: string,
  listingVersionId: string
): Promise<CheckoutSession> {
  const idempotencyKey = `chk_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
  return apiFetch<CheckoutSession>("/checkout-sessions", {
    method: "POST",
    headers: {
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({ listingId, listingVersionId }),
  });
}

export async function getOrderDetail(orderId: string): Promise<OrderDetail> {
  return apiFetch<OrderDetail>(`/orders/${orderId}`);
}

export async function getUserOrders(): Promise<OrderDetail[]> {
  return apiFetch<OrderDetail[]>("/orders");
}

export async function copyPlanForBuyer(orderId: string): Promise<PlanCopyResult> {
  return apiFetch<PlanCopyResult>(`/orders/${orderId}/copy`, {
    method: "POST",
  });
}
