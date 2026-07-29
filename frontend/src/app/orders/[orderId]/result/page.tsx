"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { PenguinMascot } from "@/components/PenguinMascot";
import { APIError } from "@/lib/api";
import { copyPlanForBuyer, getOrderDetail } from "@/lib/orders";
import type { OrderDetail, PlanCopyResult } from "@/types/orders";

export default function OrderResultPage() {
  const params = useParams();
  const orderId = params.orderId as string;
  const { loading: authLoading, user } = useAuth();

  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [copyBusy, setCopyBusy] = useState(false);
  const [copyResult, setCopyResult] = useState<PlanCopyResult | null>(null);
  const [copyError, setCopyError] = useState("");

  useEffect(() => {
    if (orderId && user) {
      fetchOrder();
    }
  }, [orderId, user]);

  async function fetchOrder() {
    setLoading(true);
    setError("");
    try {
      const data = await getOrderDetail(orderId);
      setOrder(data);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Không thể tải thông tin đơn hàng.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCopyPlan() {
    if (!order) return;
    setCopyBusy(true);
    setCopyError("");
    try {
      const res = await copyPlanForBuyer(order.id);
      setCopyResult(res);
    } catch (err) {
      setCopyError(err instanceof APIError ? err.message : "Tạo bản sao plan thất bại.");
    } finally {
      setCopyBusy(false);
    }
  }

  if (authLoading || loading) {
    return <div className="routeLoading">Đang xác minh trạng thái thanh toán từ MoMo...</div>;
  }

  if (error || !order) {
    return (
      <main className="pageWidth emptyState">
        <PenguinMascot className="emptyPenguin" size={160} variant="search" />
        <h2>Không tìm thấy đơn hàng</h2>
        <p>{error || "Đơn hàng không tồn tại."}</p>
        <Link className="primaryBtn" href="/explore">
          ← Về trang Khám phá
        </Link>
      </main>
    );
  }

  const isPaid = order.status === "paid";

  return (
    <main className="pageWidth orderResultPage">
      <section className="resultCard">
        <div className={`statusIcon ${isPaid ? "success" : "pending"}`}>
          {isPaid ? "✓" : "⏳"}
        </div>

        <span className="eyebrow">Kết quả thanh toán</span>
        <h1>{isPaid ? "Thanh toán thành công!" : "Đang chờ xác nhận thanh toán"}</h1>
        <p className="resultDesc">
          {isPaid
            ? "Giao dịch qua ví MoMo đã được xác nhận. Bạn đã có quyền sở hữu trọn vẹn bản sao lịch trình này."
            : "Đơn hàng đang chờ xử lý từ MoMo. Nếu bạn đã hoàn tất thanh toán trên ứng dụng MoMo, vui lòng tải lại trang sau vài giây."}
        </p>

        <div className="orderSummaryBox">
          <div className="summaryRow">
            <span>Mã đơn hàng:</span>
            <strong>{order.id}</strong>
          </div>
          <div className="summaryRow">
            <span>Tổng tiền:</span>
            <strong className="amountTag">{order.totalAmount.toLocaleString("vi-VN")} {order.currency}</strong>
          </div>
          <div className="summaryRow">
            <span>Trạng thái:</span>
            <span className={`badge status-${order.status}`}>
              {isPaid ? "Đã thanh toán" : order.status === "failed" ? "Thất bại" : "Đang xử lý"}
            </span>
          </div>
          {order.paidAt ? (
            <div className="summaryRow">
              <span>Thời gian trả:</span>
              <span>{new Date(order.paidAt).toLocaleString("vi-VN")}</span>
            </div>
          ) : null}
        </div>

        {copyError ? <div className="errorBanner">{copyError}</div> : null}

        {copyResult ? (
          <div className="copySuccessBox">
            <h3>🎉 Đã tạo Bản sao Plan thành công!</h3>
            <p>Bản sao lịch trình cá nhân của bạn có ID: <code>{copyResult.planId}</code></p>
            <div className="copyActions">
              <Link className="primaryBtn" href={`/planner?planId=${copyResult.planId}`}>
                ✦ Mở và chỉnh sửa trong AI Planner →
              </Link>
            </div>
          </div>
        ) : isPaid ? (
          <div className="actionBox">
            <button
              className="primaryBtn copyPlanBtn"
              disabled={copyBusy}
              onClick={() => void handleCopyPlan()}
              type="button"
            >
              {copyBusy ? "Đang tạo bản sao..." : "✦ Tạo bản sao Plan cá nhân ngay →"}
            </button>
          </div>
        ) : (
          <div className="actionBox">
            <button className="secondaryBtn" onClick={() => void fetchOrder()} type="button">
              ↻ Tải lại trang kiểm tra
            </button>
            <Link className="secondaryBtn" href="/explore">
              Về Khám phá
            </Link>
          </div>
        )}
      </section>
    </main>
  );
}
