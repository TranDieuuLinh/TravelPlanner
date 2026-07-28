"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/components/AuthProvider";
import { APIError } from "@/lib/api";
import {
  getCreatorListingDetail,
  publishListing,
  submitListing,
  unpublishListing,
  updateListing,
} from "@/lib/marketplace";
import type { ListingDetail, ListingVersion } from "@/types/marketplace";

const categories = [
  { value: "food", label: "Ẩm thực & Văn hóa" },
  { value: "nature", label: "Thiên nhiên & Mạo hiểm" },
  { value: "family", label: "Gia đình & Nối kết" },
  { value: "budget", label: "Tiết kiệm" },
  { value: "balanced", label: "Cân bằng" },
  { value: "comfortable", label: "Nghỉ dưỡng & Thoải mái" },
  { value: "creator-picks", label: "Gợi ý Creator" },
];

export default function EditListingPage() {
  const params = useParams();
  const listingId = params.listingId as string;
  const router = useRouter();
  const { loading: authLoading, user } = useAuth();

  const [listing, setListing] = useState<ListingDetail | null>(null);
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [category, setCategory] = useState("food");
  const [priceAmount, setPriceAmount] = useState(150000);
  const [mediaUrl, setMediaUrl] = useState("");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [actionMessage, setActionMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!authLoading && (!user || user.role !== "creator")) {
      router.replace("/profile");
      return;
    }
    if (user && user.role === "creator" && listingId) {
      fetchDetail();
    }
  }, [authLoading, listingId, router, user]);

  async function fetchDetail() {
    setLoading(true);
    setError("");
    try {
      const data = await getCreatorListingDetail(listingId);
      setListing(data);
      const activeVer = data.versions[data.versions.length - 1];
      if (activeVer) {
        setTitle(activeVer.title);
        setSummary(activeVer.description);
        setCategory(activeVer.category);
        setPriceAmount(activeVer.priceAmount);
        setMediaUrl(activeVer.mediaUrls?.[0] || "");
      }
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Không thể tải thông tin listing.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!listing) return;

    const latestVer = listing.versions[listing.versions.length - 1];
    setSaving(true);
    setError("");
    setActionMessage("");
    try {
      const updated = await updateListing(listingId, {
        title,
        summary,
        category,
        priceAmount: Number(priceAmount),
        mediaUrls: mediaUrl.trim() ? [mediaUrl.trim()] : [],
        expectedVersion: latestVer?.version,
      });
      setListing(updated);
      setActionMessage("Đã lưu thông tin listing.");
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Lưu listing thất bại.");
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmit() {
    setError("");
    setActionMessage("");
    try {
      const updated = await submitListing(listingId);
      setListing(updated);
      setActionMessage("Đã gửi listing đi nộp duyệt.");
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Nộp duyệt thất bại.");
    }
  }

  async function handlePublish() {
    setError("");
    setActionMessage("");
    try {
      const updated = await publishListing(listingId);
      setListing(updated);
      setActionMessage("Đã phát hành listing lên Marketplace!");
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Phát hành thất bại.");
    }
  }

  async function handleUnpublish() {
    setError("");
    setActionMessage("");
    try {
      const updated = await unpublishListing(listingId);
      setListing(updated);
      setActionMessage("Đã ngừng bán listing.");
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Ngừng bán thất bại.");
    }
  }

  if (authLoading || loading) {
    return <div className="routeLoading">Đang tải thông tin listing...</div>;
  }

  if (!listing) {
    return <div className="routeLoading">Không tìm thấy listing.</div>;
  }

  const latestVer: ListingVersion | undefined = listing.versions[listing.versions.length - 1];
  const modStatus = latestVer?.moderationStatus;
  const isPublished = listing.status === "published";

  return (
    <main className="pageWidth creatorFormPage">
      <header className="pageHeader">
        <div>
          <span className="eyebrow">Creator Studio</span>
          <h1>Chỉnh sửa Listing v{latestVer?.version}</h1>
          <p>
            Trạng thái listing: <strong>{isPublished ? "Đã phát hành" : "Chưa phát hành"}</strong> | Duyệt:{" "}
            <strong>{modStatus}</strong>
          </p>
        </div>
        <div className="headerActions">
          <Link className="secondaryBtn" href="/creator/listings">
            ← Danh sách
          </Link>
          {modStatus === "draft" || modStatus === "rejected" ? (
            <button className="primaryBtn" onClick={() => void handleSubmit()} type="button">
              Nộp duyệt →
            </button>
          ) : null}
          {modStatus === "approved" && !isPublished ? (
            <button className="primaryBtn publish" onClick={() => void handlePublish()} type="button">
              Phát hành ngay ★
            </button>
          ) : null}
          {isPublished ? (
            <button className="secondaryBtn unpublish" onClick={() => void handleUnpublish()} type="button">
              Ngừng bán
            </button>
          ) : null}
        </div>
      </header>

      {error ? <div className="errorBanner">{error}</div> : null}
      {actionMessage ? <div className="successBanner">{actionMessage}</div> : null}

      {modStatus === "rejected" && latestVer?.rejectionReason ? (
        <div className="warningBanner">
          <strong>Phiên bản bị từ chối duyệt:</strong> {latestVer.rejectionReason}
          <p>Hãy chỉnh sửa thông tin bên dưới và bấm "Nộp duyệt" lại.</p>
        </div>
      ) : null}

      {isPublished ? (
        <div className="infoBanner">
          <strong>Listing đang được bán công khai:</strong> Việc chỉnh sửa nội dung bên dưới sẽ tạo một bản nháp phiên bản mới (v
          {(latestVer?.version || 1) + 1}), không ảnh hưởng phiên bản đã xuất bản hiện tại cho tới khi được admin duyệt lại.
        </div>
      ) : null}

      <form className="listingForm" onSubmit={handleSave}>
        <section className="formSection">
          <h2>Thông tin chung</h2>

          <label htmlFor="title">Tiêu đề Listing</label>
          <input
            id="title"
            minLength={5}
            onChange={(e) => setTitle(e.target.value)}
            required
            value={title}
          />

          <label htmlFor="summary">Mô tả / Tóm tắt hành trình</label>
          <textarea
            id="summary"
            minLength={10}
            onChange={(e) => setSummary(e.target.value)}
            required
            rows={5}
            value={summary}
          />

          <div className="formRow">
            <div>
              <label htmlFor="category">Danh mục</label>
              <select id="category" onChange={(e) => setCategory(e.target.value)} value={category}>
                {categories.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="price">Giá bán (VND)</label>
              <input
                id="price"
                min={10000}
                onChange={(e) => setPriceAmount(Number(e.target.value))}
                required
                step={5000}
                type="number"
                value={priceAmount}
              />
            </div>
          </div>

          <label htmlFor="media">URL Hình ảnh bìa</label>
          <input
            id="media"
            onChange={(e) => setMediaUrl(e.target.value)}
            type="url"
            value={mediaUrl}
          />
        </section>

        {latestVer?.previewSnapshot ? (
          <section className="formSection">
            <h2>Preview Snapshot (từ Planner)</h2>
            <div className="snapshotPreview">
              <h3>{latestVer.previewSnapshot.title || latestVer.title}</h3>
              <p>Điểm đến: {latestVer.previewSnapshot.destination} | {latestVer.previewSnapshot.days} ngày</p>
              {latestVer.previewSnapshot.highlights ? (
                <div>
                  <strong>Điểm nổi bật:</strong>
                  <ul>
                    {latestVer.previewSnapshot.highlights.map((h, i) => (
                      <li key={i}>{h}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          </section>
        ) : null}

        <div className="formActions">
          <Link className="secondaryBtn" href="/creator/listings">
            Hủy
          </Link>
          <button className="primaryBtn" disabled={saving} type="submit">
            {saving ? "Đang lưu..." : "Lưu thay đổi"}
          </button>
        </div>
      </form>

      <section className="versionHistorySection">
        <h2>Lịch sử phiên bản</h2>
        <table className="listingTable">
          <thead>
            <tr>
              <th>Version</th>
              <th>Tiêu đề</th>
              <th>Trạng thái duyệt</th>
              <th>Ngày tạo</th>
              <th>Ngày phát hành</th>
            </tr>
          </thead>
          <tbody>
            {listing.versions.map((v) => (
              <tr key={v.id}>
                <td>v{v.version}</td>
                <td>{v.title}</td>
                <td><span className={`badge mod-${v.moderationStatus}`}>{v.moderationStatus}</span></td>
                <td>{new Date(v.createdAt).toLocaleDateString("vi-VN")}</td>
                <td>{v.publishedAt ? new Date(v.publishedAt).toLocaleDateString("vi-VN") : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
