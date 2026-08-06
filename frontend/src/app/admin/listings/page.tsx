"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { PenguinMascot } from "@/components/PenguinMascot";
import { APIError } from "@/lib/api";
import { getAdminPendingListings, reviewListingVersion } from "@/lib/marketplace";
import type { PendingListingVersion } from "@/types/marketplace";

export default function AdminListingsPage() {
  const router = useRouter();
  const { loading: authLoading, user } = useAuth();

  const [pendingListings, setPendingListings] = useState<PendingListingVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionMessage, setActionMessage] = useState("");

  const [selectedItem, setSelectedItem] = useState<PendingListingVersion | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [reviewing, setReviewing] = useState(false);

  useEffect(() => {
    if (!authLoading && (!user || user.role !== "admin")) {
      router.replace("/");
      return;
    }
    if (user && user.role === "admin") {
      fetchPending();
    }
  }, [authLoading, router, user]);

  async function fetchPending() {
    setLoading(true);
    setError("");
    try {
      const data = await getAdminPendingListings();
      setPendingListings(data);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Không thể tải danh sách duyệt.");
    } finally {
      setLoading(false);
    }
  }

  async function handleReview(decision: "approve" | "reject") {
    if (!selectedItem) return;
    if (decision === "reject" && !rejectReason.trim()) {
      setError("Vui lòng nhập lý do từ chối.");
      return;
    }

    setReviewing(true);
    setError("");
    setActionMessage("");
    try {
      await reviewListingVersion(selectedItem.listingVersionId, decision, rejectReason);
      setActionMessage(
        decision === "approve"
          ? `Đã duyệt thành công listing "${selectedItem.title}".`
          : `Đã từ chối listing "${selectedItem.title}".`
      );
      setSelectedItem(null);
      setRejectReason("");
      await fetchPending();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Xử lý duyệt thất bại.");
    } finally {
      setReviewing(false);
    }
  }

  if (authLoading || loading) {
    return <div className="routeLoading">Đang tải danh sách chờ duyệt Admin...</div>;
  }

  return (
    <main className="pageWidth adminModerationPage">
      <header className="pageHeader">
        <div>
          <span className="eyebrow">Quản trị Admin</span>
          <h1>Duyệt Listing Marketplace ({pendingListings.length})</h1>
          <p>Khai thác và kiểm duyệt chất lượng nội dung trước khi creator phát hành công khai.</p>
        </div>
        <div className="shellActions">
          <Link className="secondaryBtn" href="/admin/places">Duyệt địa điểm</Link>
          <Link className="secondaryBtn" href="/profile">← Về Hồ sơ</Link>
        </div>
      </header>

      {error ? <div className="errorBanner">{error}</div> : null}
      {actionMessage ? <div className="successBanner">{actionMessage}</div> : null}

      {pendingListings.length === 0 ? (
        <section className="emptyState">
          <PenguinMascot className="emptyPenguin" size={160} variant="search" />
          <h2>Không có listing nào đang chờ duyệt</h2>
          <p>Tất cả sản phẩm gửi lên đã được xử lý.</p>
        </section>
      ) : (
        <div className="pendingGrid">
          {pendingListings.map((item) => (
            <article className="pendingCard" key={item.listingVersionId}>
              <div className="cardHeader">
                <span className="badge category">{item.category}</span>
                <span className="badge version">v{item.version}</span>
              </div>
              <div className="cardBody">
                <h2>{item.title}</h2>
                <p className="description">{item.description}</p>
                <div className="metaRow">
                  <span>Creator: <strong>{item.creator.fullName}</strong></span>
                  <span>Điểm đến: <strong>{item.destination}</strong> ({item.durationDays} ngày)</span>
                  <span>Giá: <strong>{item.priceAmount.toLocaleString("vi-VN")} VND</strong></span>
                </div>

                {item.previewSnapshot ? (
                  <div className="snapshotBox">
                    <strong>Preview Snapshot:</strong>
                    {item.previewSnapshot.highlights ? (
                      <ul>
                        {item.previewSnapshot.highlights.map((h, i) => (
                          <li key={i}>{h}</li>
                        ))}
                      </ul>
                    ) : null}
                    {item.previewSnapshot.daySummaries ? (
                      <div className="daySummaries">
                        {item.previewSnapshot.daySummaries.map((ds) => (
                          <div className="daySummaryItem" key={ds.day}>
                            Ngày {ds.day}: {ds.theme}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <div className="cardFooter">
                <button
                  className="primaryBtn approveBtn"
                  onClick={() => setSelectedItem(item)}
                  type="button"
                >
                  Xem & Duyệt
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      {selectedItem ? (
        <div className="modalBackdrop" onMouseDown={() => setSelectedItem(null)} role="presentation">
          <section
            aria-modal="true"
            className="planModal moderationModal"
            onMouseDown={(e) => e.stopPropagation()}
            role="dialog"
          >
            <button aria-label="Đóng" className="modalClose" onClick={() => setSelectedItem(null)} type="button">
              ×
            </button>
            <div className="modalBody">
              <span className="eyebrow">Xác nhận duyệt Listing</span>
              <h2>{selectedItem.title}</h2>
              <p>{selectedItem.description}</p>

              <div className="modalFacts">
                <div>
                  <span>Creator</span>
                  <strong>{selectedItem.creator.fullName}</strong>
                </div>
                <div>
                  <span>Điểm đến</span>
                  <strong>{selectedItem.destination}</strong>
                </div>
                <div>
                  <span>Giá bán</span>
                  <strong>{selectedItem.priceAmount.toLocaleString("vi-VN")} VND</strong>
                </div>
              </div>

              <div className="moderationForm">
                <label htmlFor="reject-reason">Lý do từ chối (nếu Chọn Từ chối):</label>
                <textarea
                  id="reject-reason"
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="Nhập chi tiết lý do từ chối nếu nội dung chưa đạt..."
                  rows={3}
                  value={rejectReason}
                />

                <div className="modalActions">
                  <button
                    className="rejectBtn"
                    disabled={reviewing}
                    onClick={() => void handleReview("reject")}
                    type="button"
                  >
                    {reviewing ? "Đang xử lý..." : "✕ Từ chối"}
                  </button>
                  <button
                    className="approveBtn"
                    disabled={reviewing}
                    onClick={() => void handleReview("approve")}
                    type="button"
                  >
                    {reviewing ? "Đang xử lý..." : "✓ Duyệt chấp nhận"}
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}
