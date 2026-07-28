"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { APIError } from "@/lib/api";
import {
  addFavorite,
  getMarketplaceCategories,
  removeFavorite,
  searchListings
} from "@/lib/marketplace";
import type { ListingSummary } from "@/types/marketplace";

const categoryLabels: Record<string, string> = {
  budget: "Tiết kiệm",
  medium: "Cân bằng",
  high: "Cao cấp",
  food: "Ẩm thực",
  nature: "Thiên nhiên",
  family: "Gia đình",
  "creator-picks": "Gợi ý Creator"
};

const sortOptions = [
  { id: "newest", label: "Mới nhất" },
  { id: "priceAsc", label: "Giá tăng dần" },
  { id: "priceDesc", label: "Giá giảm dần" },
];

export default function ExplorePage() {
  const router = useRouter();
  const { user } = useAuth();

  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("Tất cả");
  const [categories, setCategories] = useState<string[]>([]);
  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);

  const [listings, setListings] = useState<ListingSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [selected, setSelected] = useState<ListingSummary | null>(null);

  useEffect(() => {
    fetchListings();
  }, [category, page, sort, user]);

  useEffect(() => {
    void getMarketplaceCategories()
      .then(setCategories)
      .catch(() => setCategories([]));
  }, []);

  async function fetchListings() {
    setLoading(true);
    setError("");
    try {
      const data = await searchListings({
        page,
        pageSize: 12,
        query: query.trim() || undefined,
        category: category !== "Tất cả" ? category : undefined,
        sort,
      });
      setListings(data.items);
      setTotal(data.total);
      setTotalPages(data.totalPages);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Không thể tải danh sách chuyến đi.");
    } finally {
      setLoading(false);
    }
  }

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    setPage(1);
    fetchListings();
  }

  async function toggleFavorite(item: ListingSummary) {
    if (!user) {
      router.push(`/login?next=/explore`);
      return;
    }

    const currentFav = item.isFavorited;
    // Optimistic update
    setListings((prev) =>
      prev.map((l) => (l.id === item.id ? { ...l, isFavorited: !currentFav } : l))
    );

    try {
      if (currentFav) {
        await removeFavorite(item.id);
      } else {
        await addFavorite(item.id);
      }
    } catch (err) {
      // Revert on error
      setListings((prev) =>
        prev.map((l) => (l.id === item.id ? { ...l, isFavorited: currentFav } : l))
      );
    }
  }

  return (
    <main>
      <section className="exploreHero">
        <div className="pageWidth heroGrid">
          <div>
            <span className="eyebrow light">Marketplace du lịch</span>
            <h1>Đi đâu tiếp theo?</h1>
            <p>Khám phá plan từ creator địa phương, rồi dùng AI để biến nó thành chuyến đi của riêng bạn.</p>
          </div>
          <form className="heroSearch" onSubmit={handleSearchSubmit}>
            <span>⌕</span>
            <input
              aria-label="Tìm plan"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Tìm Đà Nẵng, food tour, biển..."
              value={query}
            />
            <button type="submit">Tìm kiếm</button>
          </form>
        </div>
      </section>

      <section className="pageWidth exploreContent">
        <div className="filterRow" aria-label="Bộ lọc">
          <div>
            {["Tất cả", ...categories].map((item) => (
              <button
                className={category === item ? "filter active" : "filter"}
                key={item}
                onClick={() => {
                  setCategory(item);
                  setPage(1);
                }}
                type="button"
              >
                {item === "Tất cả" ? item : (categoryLabels[item] ?? item)}
              </button>
            ))}
          </div>

          <div className="sortSelectBox">
            <label htmlFor="sort-select">Sắp xếp:</label>
            <select
              id="sort-select"
              onChange={(e) => {
                setSort(e.target.value);
                setPage(1);
              }}
              value={sort}
            >
              {sortOptions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="sectionTitle">
          <div>
            <span className="eyebrow">Khám phá hành trình</span>
            <h2>{total} hành trình khả thi từ Creator</h2>
          </div>
          <Link href="/planner">Tạo plan mới với AI <span>→</span></Link>
        </div>

        {loading ? (
          <div className="routeLoading">Đang tải danh sách hành trình...</div>
        ) : error ? (
          <div className="errorBanner">{error}</div>
        ) : listings.length === 0 ? (
          <div className="emptyState">
            <h2>Chưa tìm thấy hành trình phù hợp</h2>
            <p>Thử tìm kiếm với từ khóa khác hoặc bỏ các bộ lọc danh mục.</p>
          </div>
        ) : (
          <div className="planGrid">
            {listings.map((plan) => {
              const ver = plan.currentVersion;
              const creatorName = plan.creator?.fullName || "Creator";
              const coverUrl = ver.mediaUrls?.[0] || "";

              return (
                <article className="planCard" key={plan.id}>
                  <Link className="planCoverLink" href={`/listings/${plan.id}`}>
                    <div className="planCover flexCover">
                      {coverUrl ? (
                        <img alt={ver.title} className="coverImg" src={coverUrl} />
                      ) : (
                        <span className="coverPlace">{ver.destination}</span>
                      )}
                      <span className="planTag">{ver.category}</span>
                      <span className="coverDays">{ver.durationDays} ngày</span>
                    </div>
                  </Link>

                  <div className="planInfo">
                    <div className="creatorLine">
                      <span className="creatorAvatar">{creatorName.charAt(0)}</span>
                      <span>{creatorName}</span>
                      <span className="verified">✓</span>
                    </div>
                    <Link className="planTitle textLink" href={`/listings/${plan.id}`}>
                      {ver.title}
                    </Link>
                    <p>{ver.description}</p>

                    <div className="planMeta">
                      <span>{ver.destination}</span>
                      <strong>{ver.priceAmount.toLocaleString("vi-VN")} {ver.priceCurrency}</strong>
                    </div>

                    <div className="cardActions">
                      <button
                        className={plan.isFavorited ? "saveButton saved" : "saveButton"}
                        onClick={() => void toggleFavorite(plan)}
                        type="button"
                      >
                        {plan.isFavorited ? "♥ Đã lưu" : "♡ Lưu"}
                      </button>
                      <Link className="viewButton" href={`/listings/${plan.id}`}>
                        Xem chi tiết
                      </Link>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}

        {totalPages > 1 ? (
          <div className="paginationRow">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} type="button">
              ← Trang trước
            </button>
            <span>
              Trang {page} / {totalPages}
            </span>
            <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} type="button">
              Trang sau →
            </button>
          </div>
        ) : null}

        <section className="creatorCallout">
          <div>
            <span className="eyebrow light">Dành cho creator</span>
            <h2>Chia sẻ hành trình.<br />Tạo thêm giá trị.</h2>
          </div>
          <div>
            <p>Biến trải nghiệm thật thành plan có cấu trúc và quản lý listing trong Creator Studio.</p>
            {user?.role === "creator" ? (
              <Link href="/creator/listings">Vào Creator Studio →</Link>
            ) : (
              <Link href="/profile">Đăng ký thành Creator →</Link>
            )}
          </div>
        </section>
      </section>
    </main>
  );
}
