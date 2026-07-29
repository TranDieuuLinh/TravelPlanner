"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { PenguinMascot } from "@/components/PenguinMascot";
import { APIError } from "@/lib/api";
import {
  getCreatorListings,
  publishListing,
  submitListing,
  unpublishListing,
} from "@/lib/marketplace";
import type { ListingDetail } from "@/types/marketplace";

export default function CreatorListingsPage() {
  const router = useRouter();
  const { loading: authLoading, user } = useAuth();
  const [listings, setListings] = useState<ListingDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionMessage, setActionMessage] = useState("");

  useEffect(() => {
    if (!authLoading && (!user || user.role !== "creator")) {
      router.replace("/profile");
      return;
    }
    if (user && user.role === "creator") {
      fetchListings();
    }
  }, [authLoading, router, user]);

  async function fetchListings() {
    setLoading(true);
    setError("");
    try {
      const data = await getCreatorListings();
      setListings(data);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Không thể tải danh sách listing.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(id: string) {
    setActionMessage("");
    try {
      await submitListing(id);
      setActionMessage("Đã nộp duyệt listing thành công.");
      await fetchListings();
    } catch (err) {
      setActionMessage(err instanceof APIError ? err.message : "Gửi duyệt thất bại.");
    }
  }

  async function handlePublish(id: string) {
    setActionMessage("");
    try {
      await publishListing(id);
      setActionMessage("Đã phát hành listing lên Marketplace.");
      await fetchListings();
    } catch (err) {
      setActionMessage(err instanceof APIError ? err.message : "Phát hành thất bại.");
    }
  }

  async function handleUnpublish(id: string) {
    setActionMessage("");
    try {
      await unpublishListing(id);
      setActionMessage("Đã ẩn listing khỏi Marketplace.");
      await fetchListings();
    } catch (err) {
      setActionMessage(err instanceof APIError ? err.message : "Ngừng bán thất bại.");
    }
  }

  if (authLoading || loading) {
    return <div className="routeLoading">Đang tải Creator Studio...</div>;
  }

  return (
    <main className="pageWidth creatorStudio">
      <header className="pageHeader">
        <div>
          <span className="eyebrow">Creator Studio</span>
          <h1>Quản lý Listing của bạn</h1>
          <p>Tạo mới, chỉnh sửa nội dung và theo dõi trạng thái duyệt listing trên Marketplace.</p>
        </div>
        <Link className="newTrip" href="/creator/listings/new">
          <span>+</span> Tạo Listing mới
        </Link>
      </header>

      {error ? <div className="errorBanner">{error}</div> : null}
      {actionMessage ? <div className="successBanner">{actionMessage}</div> : null}

      {listings.length === 0 ? (
        <section className="emptyState">
          <PenguinMascot className="emptyPenguin" size={160} variant="search" />
          <h2>Bạn chưa có listing nào</h2>
          <p>Hãy bắt đầu bằng cách chọn một plan hợp lệ từ Planner để xuất bản lên Marketplace.</p>
          <Link className="newTrip" href="/creator/listings/new">
            + Tạo listing đầu tiên
          </Link>
        </section>
      ) : (
        <div className="listingTableWrapper">
          <table className="listingTable">
            <thead>
              <tr>
                <th>Tên Listing</th>
                <th>Danh mục</th>
                <th>Giá bán</th>
                <th>Trạng thái</th>
                <th>Phiên bản hiện tại</th>
                <th>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {listings.map((item) => {
                const latestVersion = item.versions[item.versions.length - 1];
                const status = item.status;
                const modStatus = latestVersion?.moderationStatus;

                return (
                  <tr key={item.id}>
                    <td>
                      <strong>{latestVersion?.title || "Chưa có tiêu đề"}</strong>
                      <span className="tableSubtext">{latestVersion?.destination} ({latestVersion?.durationDays} ngày)</span>
                    </td>
                    <td><span className="badge category">{latestVersion?.category}</span></td>
                    <td><strong>{latestVersion?.priceAmount?.toLocaleString("vi-VN")} VND</strong></td>
                    <td>
                      <span className={`badge status-${status}`}>
                        {status === "published" ? "Đã phát hành" : status === "unpublished" ? "Ngừng bán" : "Bản nháp"}
                      </span>
                    </td>
                    <td>
                      <span className={`badge mod-${modStatus}`}>
                        v{latestVersion?.version} ({modStatus === "pending_review" ? "Đang chờ duyệt" : modStatus === "approved" ? "Đã duyệt" : modStatus === "rejected" ? "Từ chối" : modStatus === "published" ? "Đã xuất bản" : "Nháp"})
                      </span>
                      {modStatus === "rejected" && latestVersion?.rejectionReason ? (
                        <p className="rejectReason">Lý do: {latestVersion.rejectionReason}</p>
                      ) : null}
                    </td>
                    <td>
                      <div className="tableActions">
                        <Link className="actionLink" href={`/creator/listings/${item.id}/edit`}>
                          Chỉnh sửa
                        </Link>
                        {modStatus === "draft" || modStatus === "rejected" ? (
                          <button className="actionBtn" onClick={() => void handleSubmit(item.id)} type="button">
                            Nộp duyệt
                          </button>
                        ) : null}
                        {modStatus === "approved" && status !== "published" ? (
                          <button className="actionBtn publish" onClick={() => void handlePublish(item.id)} type="button">
                            Phát hành
                          </button>
                        ) : null}
                        {status === "published" ? (
                          <button className="actionBtn unpublish" onClick={() => void handleUnpublish(item.id)} type="button">
                            Ngừng bán
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
