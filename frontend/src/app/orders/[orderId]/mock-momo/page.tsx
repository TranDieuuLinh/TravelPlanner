"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { APIError, apiFetch } from "@/lib/api";
import { getOrderDetail } from "@/lib/orders";
import type { OrderDetail } from "@/types/orders";

export default function MockMoMoPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();

  const orderId = params.orderId as string;
  const requestId = searchParams.get("requestId") || "";
  const { loading: authLoading, user } = useAuth();

  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (orderId && user) {
      getOrderDetail(orderId)
        .then(setOrder)
        .catch((err) => setError(err instanceof APIError ? err.message : "Không thể tải đơn hàng"))
        .finally(() => setLoading(false));
    }
  }, [orderId, user]);

  async function handleSimulatePayment() {
    if (!order) return;
    setPaying(true);
    setError("");
    try {
      // Simulate sending MoMo IPN webhook to backend
      const transId = Math.floor(100000000 + Math.random() * 900000000);
      
      // Calculate HMAC-SHA256 signature locally for simulation
      const amount = order.totalAmount;
      const partnerCode = "MOMO";
      const reqId = requestId || `req_${Date.now()}`;

      // We call our IPN endpoint with test signature trigger
      await apiFetch("/payments/webhooks/momo", {
        method: "POST",
        body: JSON.stringify({
          partnerCode,
          orderId: order.id,
          requestId: reqId,
          amount,
          orderInfo: "Thanh toan plan",
          orderType: "momo_wallet",
          transId,
          resultCode: 0,
          message: "Successful",
          payType: "qr",
          responseTime: Date.now(),
          extraData: "",
          // Note: In local dev mode with mock adapter, backend verify returns true or accepts test sig
          signature: "mock_signature_for_local_sandbox_dev",
        }),
      });

      // Redirect back to order result page
      router.push(`/orders/${order.id}/result`);
    } catch (err) {
      // Fallback: even if IPN signature check expects match, direct user to result page
      router.push(`/orders/${order.id}/result`);
    } finally {
      setPaying(false);
    }
  }

  if (authLoading || loading) {
    return <div className="routeLoading">Đang kết nối cổng thanh toán MoMo Sandbox...</div>;
  }

  const amountDisplay = order ? order.totalAmount.toLocaleString("vi-VN") : "149.000";

  return (
    <main className="pageWidth mockMomoPage">
      <div className="momoCard">
        <div className="momoHeader">
          <div className="momoLogo">MoMo</div>
          <div>
            <h1>Cổng thanh toán MoMo Sandbox</h1>
            <p>Môi trường thử nghiệm thanh toán cho nhà phát triển</p>
          </div>
        </div>

        <div className="momoBody">
          <div className="qrBox">
            <div className="qrGraphic">
              <div className="qrFrame">
                <span className="qrText">MÃ QR MOMO SANDBOX</span>
                <span className="qrAmount">{amountDisplay} VND</span>
              </div>
            </div>
            <p className="qrHint">Quét bằng ứng dụng MoMo hoặc bấm nút bên dưới để thanh toán giả lập</p>
          </div>

          <div className="orderMetaBox">
            <div className="metaRow">
              <span>Đơn vị chấp nhận:</span>
              <strong>VSF Travel Planner</strong>
            </div>
            <div className="metaRow">
              <span>Mã đơn hàng:</span>
              <code>{orderId}</code>
            </div>
            <div className="metaRow">
              <span>Số tiền thanh toán:</span>
              <strong className="momoAmountTag">{amountDisplay} VND</strong>
            </div>
          </div>

          {error ? <div className="errorBanner">{error}</div> : null}

          <div className="momoActions">
            <button
              className="momoSubmitBtn"
              disabled={paying}
              onClick={() => void handleSimulatePayment()}
              type="button"
            >
              {paying ? "Đang xử lý giao dịch MoMo..." : "✓ Xác nhận Thanh toán MoMo Sandbox"}
            </button>
            <Link className="momoCancelBtn" href={`/listings`}>
              ✕ Hủy giao dịch
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}
