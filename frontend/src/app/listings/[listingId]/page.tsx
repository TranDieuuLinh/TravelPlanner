"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { APIError } from "@/lib/api";
import { addFavorite, getPublicListingDetail, removeFavorite } from "@/lib/marketplace";
import { createCheckoutSession } from "@/lib/orders";
import type { ListingDetail } from "@/types/marketplace";

export default function ListingDetailPage() {
  const params = useParams();
  const listingId = params.listingId as string;
  const router = useRouter();
  const { loading: authLoading, user } = useAuth();

  const [listing, setListing] = useState<ListingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isFavorited, setIsFavorited] = useState(false);
  const [favBusy, setFavBusy] = useState(false);
  const [checkoutBusy, setCheckoutBusy] = useState(false);

  useEffect(() => {
    if (listingId) {
      fetchDetail();
    }
  }, [listingId, user]);

  async function fetchDetail() {
    setLoading(true);
    setError("");
    try {
      const data = await getPublicListingDetail(listingId);
      setListing(data);
      setIsFavorited(Boolean(data.isFavorited));
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Không thể tải thông tin chuyến đi.");
    } finally {
      setLoading(false);
    }
  }

  async function handleToggleFavorite() {
    if (!user) {
      router.push(`/login?next=/listings/${listingId}`);
      return;
    }
    setFavBusy(true);
    try {
      if (isFavorited) {
        await removeFavorite(listingId);
        setIsFavorited(false);
      } else {
        await addFavorite(listingId);
        setIsFavorited(true);
      }
    } catch (err) {
      alert(err instanceof APIError ? err.message : "Không thể cập nhật yêu thích.");
    } finally {
      setFavBusy(false);
    }
  }

  async function handleBuyMoMo() {
    if (!user) {
      router.push(`/login?next=/listings/${listingId}`);
      return;
    }
    if (!listing || !listing.currentVersion) return;
    setCheckoutBusy(true);
    try {
      const session = await createCheckoutSession(listing.id, listing.currentVersion.id);
      if (session.paymentUrl) {
        window.location.href = session.paymentUrl;
      }
    } catch (err) {
      alert(err instanceof APIError ? err.message : "Không thể khởi tạo phiên thanh toán MoMo.");
      setCheckoutBusy(false);
    }
  }

  if (loading) {
    return <div className="routeLoading">Đang tải thông tin chuyến đi...</div>;
  }

  if (error || !listing || !listing.currentVersion) {
    return (
      <main className="pageWidth emptyState">
        <h2>Không tìm thấy chuyến đi</h2>
        <p>{error || "Listing không tồn tại hoặc đã bị gỡ bỏ."}</p>
        <Link className="primaryBtn" href="/explore">
          ← Quay lại Khám phá
        </Link>
      </main>
    );
  }

  const ver = listing.currentVersion;
  const coverUrl = ver.mediaUrls?.[0] || "https://images.unsplash.com/photo-1559592413-7cec4d0cae2b";
  const snapshot = ver.previewSnapshot;

  return (
    <main className="pageWidth listingDetailPage">
      <div className="breadcrumb">
        <Link href="/explore">Khám phá</Link> &gt; <span>{ver.title}</span>
      </div>

      <div className="detailHeroGrid">
        <div className="mediaColumn">
          <div className="coverContainer">
            <img alt={ver.title} src={coverUrl} />
            <span className="badge category">{ver.category}</span>
          </div>
        </div>

        <div className="infoColumn">
          <div className="creatorLine">
            <span className="creatorAvatar">{listing.creator?.fullName?.charAt(0) || "C"}</span>
            <div>
              <strong>{listing.creator?.fullName || "Creator"}</strong>
              <span className="creatorBadge">✓ Verified Creator</span>
            </div>
          </div>

          <h1>{ver.title}</h1>
          <p className="description">{ver.description}</p>

          <div className="metaFacts">
            <div>
              <span>Điểm đến</span>
              <strong>{ver.destination}</strong>
            </div>
            <div>
              <span>Thời lượng</span>
              <strong>{ver.durationDays} ngày</strong>
            </div>
            <div>
              <span>Giá mua plan</span>
              <strong className="priceTag">{ver.priceAmount.toLocaleString("vi-VN")} {ver.priceCurrency}</strong>
            </div>
          </div>

          <div className="actionRow">
            <button
              className={`saveButton ${isFavorited ? "saved" : ""}`}
              disabled={favBusy}
              onClick={() => void handleToggleFavorite()}
              type="button"
            >
              {isFavorited ? "♥ Đã lưu yêu thích" : "♡ Lưu yêu thích"}
            </button>
            <button
              className="primaryBtn momoBuyBtn"
              disabled={checkoutBusy}
              onClick={() => void handleBuyMoMo()}
              type="button"
            >
              {checkoutBusy ? "Đang chuyển MoMo..." : "💳 Thanh toán qua Ví MoMo →"}
            </button>
          </div>
        </div>
      </div>

      {snapshot ? (
        <section className="itineraryPreviewSection">
          <h2>Bản xem trước Lịch trình (Preview Snapshot)</h2>
          {snapshot.highlights ? (
            <div className="highlightsBox">
              <h3>Highlights chính</h3>
              <div className="tagList">
                {snapshot.highlights.map((h, i) => (
                  <span className="tagChip" key={i}>
                    ✦ {h}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {snapshot.daySummaries ? (
            <div className="daySummaryList">
              <h3>Tóm tắt theo ngày</h3>
              {snapshot.daySummaries.map((ds) => (
                <div className="daySummaryCard" key={ds.day}>
                  <span className="dayNum">Ngày {ds.day}</span>
                  <strong>{ds.theme}</strong>
                </div>
              ))}
            </div>
          ) : null}

          <div className="copyNoteBox">
            <p>
              💡 <em>Sau khi thanh toán thành công qua MoMo, bạn sẽ được tự động tạo **Bản sao Lịch trình riêng** để thỏa sức chỉnh sửa trong AI Planner.</em>
            </p>
          </div>
        </section>
      ) : null}
    </main>
  );
}
