"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/features/auth/components/AuthProvider";
import { APIError } from "@/shared/api/client";
import { createListing, getPublishablePlans } from "@/features/marketplace/api";
import type { PublishablePlan } from "@/features/marketplace/types";

const categories = [
  { value: "food", label: "Ẩm thực & Văn hóa" },
  { value: "nature", label: "Thiên nhiên & Mạo hiểm" },
  { value: "family", label: "Gia đình & Nối kết" },
  { value: "budget", label: "Tiết kiệm" },
  { value: "balanced", label: "Cân bằng" },
  { value: "comfortable", label: "Nghỉ dưỡng & Thoải mái" },
  { value: "creator-picks", label: "Gợi ý Creator" },
];

export default function NewListingPage() {
  const router = useRouter();
  const { loading: authLoading, sessionUnavailable, user } = useAuth();

  const [plans, setPlans] = useState<PublishablePlan[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [category, setCategory] = useState("food");
  const [priceAmount, setPriceAmount] = useState(150000);
  const [mediaUrl, setMediaUrl] = useState("https://images.unsplash.com/photo-1559592413-7cec4d0cae2b");

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!authLoading && !sessionUnavailable && (!user || user.role !== "creator")) {
      router.replace("/profile");
      return;
    }
    if (user && user.role === "creator") {
      fetchPlans();
    }
  }, [authLoading, router, sessionUnavailable, user]);

  async function fetchPlans() {
    setLoading(true);
    setError("");
    try {
      const data = await getPublishablePlans();
      setPlans(data);
      if (data.length > 0) {
        const firstValid = data.find((p) => p.status === "locked" && p.checkStatus === "valid") || data[0];
        setSelectedPlanId(firstValid.planId);
        setTitle(firstValid.title);
      }
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Không thể tải danh sách plan.");
    } finally {
      setLoading(false);
    }
  }

  function handleSelectPlan(id: string) {
    setSelectedPlanId(id);
    const target = plans.find((p) => p.planId === id);
    if (target) {
      setTitle(target.title);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedPlanId) return;

    setSubmitting(true);
    setError("");
    try {
      const created = await createListing({
        planId: selectedPlanId,
        title,
        summary,
        category,
        priceAmount: Number(priceAmount),
        mediaUrls: mediaUrl.trim() ? [mediaUrl.trim()] : [],
      });
      router.push(`/creator/listings/${created.id}/edit`);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Tạo listing thất bại.");
      setSubmitting(false);
    }
  }

  if (authLoading || loading) {
    return <div className="routeLoading">Đang chuẩn bị danh sách plan...</div>;
  }

  return (
    <main className="pageWidth creatorFormPage">
      <header className="pageHeader">
        <div>
          <span className="eyebrow">Creator Studio</span>
          <h1>Tạo Listing mới</h1>
          <p>Chọn plan khả thi từ Planner để đóng gói thành sản phẩm xuất bản lên Marketplace.</p>
        </div>
        <Link className="secondaryBtn" href="/creator/listings">
          ← Quay lại danh sách
        </Link>
      </header>

      {error ? <div className="errorBanner">{error}</div> : null}

      <form className="listingForm" onSubmit={handleSubmit}>
        <section className="formSection">
          <h2>1. Chọn Plan xuất bản</h2>
          <p className="formHint">Chỉ plan ở trạng thái Đã khóa (locked) và Hợp lệ (valid) mới có thể chọn.</p>

          <div className="planSelectionGrid">
            {plans.map((p) => {
              const isValid = p.status === "locked" && p.checkStatus === "valid";
              return (
                <div
                  className={`planSelectCard ${selectedPlanId === p.planId ? "selected" : ""} ${!isValid ? "disabled" : ""}`}
                  key={p.planId}
                  onClick={() => isValid && handleSelectPlan(p.planId)}
                  role="button"
                  tabIndex={0}
                >
                  <div className="planCardHead">
                    <strong>{p.title}</strong>
                    <span className={`badge ${isValid ? "valid" : "invalid"}`}>
                      {isValid ? "Hợp lệ" : p.status !== "locked" ? "Chưa khóa" : "Chưa kiểm tra"}
                    </span>
                  </div>
                  <div className="planCardBody">
                    <span>Điểm đến: {p.destination}</span>
                    <span>Số ngày: {p.days} ngày</span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="formSection">
          <h2>2. Thông tin thương mại</h2>

          <label htmlFor="title">Tiêu đề Listing</label>
          <input
            id="title"
            minLength={5}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Ví dụ: Đà Nẵng & Hội An 4N3Đ ẩm thực trọn vẹn"
            required
            value={title}
          />

          <label htmlFor="summary">Mô tả / Tóm tắt hành trình</label>
          <textarea
            id="summary"
            minLength={10}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="Giới thiệu điểm đặc sắc của chuyến đi, đối tượng phù hợp và trải nghiệm đáng chú ý..."
            required
            rows={4}
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
            placeholder="https://..."
            type="url"
            value={mediaUrl}
          />
        </section>

        <div className="formActions">
          <Link className="secondaryBtn" href="/creator/listings">
            Hủy
          </Link>
          <button className="primaryBtn" disabled={submitting || !selectedPlanId} type="submit">
            {submitting ? "Đang tạo nháp..." : "Tạo bản nháp →"}
          </button>
        </div>
      </form>
    </main>
  );
}
