export interface CheckoutSession {
  orderId: string;
  status: string;
  amount: number;
  currency: string;
  paymentUrl: string;
  expiresAt?: string | null;
}

export interface OrderItem {
  id: string;
  orderId: string;
  marketplacePlanId: string;
  marketplacePlanVersionId: string;
  unitAmount: number;
  currency: string;
  quantity: number;
}

export interface OrderDetail {
  id: string;
  buyerId: number;
  totalAmount: number;
  currency: string;
  status: string;
  items: OrderItem[];
  createdAt: string;
  paidAt?: string | null;
  refundedAt?: string | null;
}

export interface PlanCopyResult {
  planId: string;
  planVersionId: string;
  sourcePlanVersionId: string;
  sourceListingVersionId: string;
}
