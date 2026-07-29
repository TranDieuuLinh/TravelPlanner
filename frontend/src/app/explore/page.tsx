"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { PenguinMascot } from "@/components/PenguinMascot";
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
  "creator-picks": "Creator chọn"
};

const sortOptions = [
  { id: "newest", label: "Mới cập nhật" },
  { id: "priceAsc", label: "Giá thấp trước" },
  { id: "priceDesc", label: "Giá cao trước" },
];

const coverTones = ["sunset", "forest", "berry", "mist", "lime", "ocean"];

function SearchIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="m16 16 4 4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 20 20">
      <path d="M4 10h12m-4.5-4.5L16 10l-4.5 4.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}

function HeartIcon({ filled = false }: { filled?: boolean }) {
  return (
    <svg aria-hidden="true" fill={filled ? "currentColor" : "none"} viewBox="0 0 24 24">
      <path d="M20.8 4.7a5.6 5.6 0 0 0-7.9 0L12 5.6l-.9-.9a5.6 5.6 0 0 0-7.9 7.9l.9.9L12 21.4l7.9-7.9.9-.9a5.6 5.6 0 0 0 0-7.9Z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}

function getCoverTone(id: string) {
  const score = Array.from(id).reduce((total, character) => total + character.charCodeAt(0), 0);
  return coverTones[score % coverTones.length];
}

function formatUpdatedAt(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Mới cập nhật";
  return `Cập nhật ${new Intl.DateTimeFormat("vi-VN", {
    month: "short",
    year: "numeric"
  }).format(date)}`;
}

function formatPrice(amount: number, currency: string) {
  try {
    return new Intl.NumberFormat("vi-VN", {
      style: "currency",
      currency,
      maximumFractionDigits: 0
    }).format(amount);
  } catch {
    return `${amount.toLocaleString("vi-VN")} ${currency}`;
  }
}

export default function ExplorePage() {
  const router = useRouter();
  const { user } = useAuth();

  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [category, setCategory] = useState("Tất cả");
  const [categories, setCategories] = useState<string[]>([]);
  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);
  const [refreshKey, setRefreshKey] = useState(0);

  const [listings, setListings] = useState<ListingSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function fetchListings() {
      setLoading(true);
      setError("");
      try {
        const data = await searchListings({
          page,
          pageSize: 12,
          query: appliedQuery || undefined,
          category: category !== "Tất cả" ? category : undefined,
          sort,
        });
        if (!cancelled) {
          setListings(data.items);
          setTotal(data.total);
          setTotalPages(data.totalPages);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof APIError ? err.message : "Không thể tải danh sách chuyến đi.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void fetchListings();
    return () => {
      cancelled = true;
    };
  }, [appliedQuery, category, page, refreshKey, sort, user]);

  useEffect(() => {
    void getMarketplaceCategories()
      .then(setCategories)
      .catch(() => setCategories([]));
  }, []);

  function handleSearchSubmit(event: React.FormEvent) {
    event.preventDefault();
    setPage(1);
    setAppliedQuery(query.trim());
  }

  function clearFilters() {
    setQuery("");
    setAppliedQuery("");
    setCategory("Tất cả");
    setPage(1);
  }

  async function toggleFavorite(item: ListingSummary) {
    if (!user) {
      router.push("/login?next=/explore");
      return;
    }

    const currentFavorite = Boolean(item.isFavorited);
    setListings((current) =>
      current.map((listing) =>
        listing.id === item.id ? { ...listing, isFavorited: !currentFavorite } : listing
      )
    );

    try {
      if (currentFavorite) {
        await removeFavorite(item.id);
      } else {
        await addFavorite(item.id);
      }
    } catch {
      setListings((current) =>
        current.map((listing) =>
          listing.id === item.id ? { ...listing, isFavorited: currentFavorite } : listing
        )
      );
    }
  }

  return (
    <main className="explorePage">
      <section className="exploreHero">
        <div className="heroGlow heroGlowOne" />
        <div className="heroGlow heroGlowTwo" />
        <div className="pageWidth heroGrid">
          <div className="heroCopy">
            <span className="eyebrow light">Marketplace hành trình</span>
            <h1>Một chuyến đi hay bắt đầu từ một plan tốt.</h1>
            <p>
              Khám phá lịch trình từ creator, nhận bản sao của riêng bạn và tiếp tục
              cá nhân hóa cùng AI Planner.
            </p>

            <form className="heroSearch" onSubmit={handleSearchSubmit}>
              <SearchIcon />
              <input
                aria-label="Tìm theo điểm đến hoặc phong cách"
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Bạn muốn đi đâu?"
                value={query}
              />
              <button type="submit">
                Khám phá
                <ArrowIcon />
              </button>
            </form>

            <div className="heroSuggestions" aria-label="Tìm kiếm gợi ý">
              <span>Gợi ý:</span>
              {["Đà Nẵng", "Food tour", "Cuối tuần"].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => {
                    setQuery(suggestion);
                    setAppliedQuery(suggestion);
                    setPage(1);
                  }}
                  type="button"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>

          <div className="heroJourney" aria-label="Cách Marketplace hoạt động">
            <div className="journeyStamp">
              <span>VSF</span>
              <small>TRAVEL<br />PLANS</small>
            </div>
            <p className="journeyQuote">“Đi theo trải nghiệm thật, nhưng vẫn là chuyến đi của bạn.”</p>
            <ol>
              <li>
                <span>01</span>
                <div><strong>Chọn cảm hứng</strong><small>Xem preview trước khi quyết định</small></div>
              </li>
              <li>
                <span>02</span>
                <div><strong>Nhận plan cá nhân</strong><small>Bản creator luôn được giữ nguyên</small></div>
              </li>
              <li>
                <span>03</span>
                <div><strong>Tinh chỉnh với AI</strong><small>Đổi ngày, ngân sách và sở thích</small></div>
              </li>
            </ol>
          </div>
        </div>
      </section>

      <section className="pageWidth exploreContent">
        <div className="exploreToolbar">
          <div className="filterScroll" aria-label="Danh mục hành trình">
            {["Tất cả", ...categories].map((item) => (
              <button
                aria-pressed={category === item}
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
            <label htmlFor="sort-select">Sắp xếp</label>
            <select
              id="sort-select"
              onChange={(event) => {
                setSort(event.target.value);
                setPage(1);
              }}
              value={sort}
            >
              {sortOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="sectionTitle exploreTitle">
          <div>
            <span className="eyebrow">Tuyển chọn cho bạn</span>
            <h2>
              {appliedQuery
                ? `Kết quả cho “${appliedQuery}”`
                : "Những hành trình đáng khám phá"}
            </h2>
            {!loading && !error ? <p>{total} plan đang sẵn sàng để xem preview</p> : null}
          </div>
          <Link className="plannerTextLink" href="/planner">
            <span>Không thấy plan phù hợp?</span>
            Tạo chuyến đi mới
            <ArrowIcon />
          </Link>
        </div>

        {loading ? (
          <div aria-label="Đang tải danh sách hành trình" className="planGrid">
            {Array.from({ length: 6 }).map((_, index) => (
              <div aria-hidden="true" className="planCard planSkeleton" key={index}>
                <div className="skeletonCover" />
                <div className="skeletonBody">
                  <span /><strong /><p /><p />
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="exploreFeedback errorBanner" role="alert">
            <div>
              <strong>Chưa tải được hành trình</strong>
              <span>{error}</span>
            </div>
            <button onClick={() => setRefreshKey((key) => key + 1)} type="button">Thử lại</button>
          </div>
        ) : listings.length === 0 ? (
          <div className="emptyState exploreEmpty">
            <PenguinMascot className="emptyPenguin" size={180} variant="search" />
            <h2>Chưa có hành trình khớp với bạn</h2>
            <p>Thử một điểm đến khác hoặc xem lại toàn bộ plan đang có.</p>
            <button onClick={clearFilters} type="button">Xem tất cả hành trình</button>
          </div>
        ) : (
          <div className="planGrid">
            {listings.map((plan) => {
              const version = plan.currentVersion;
              const creatorName = plan.creator?.fullName || "Creator";
              const coverUrl = version.mediaUrls?.[0] || "";
              const categoryName = categoryLabels[version.category] ?? version.category;

              return (
                <article className="planCard" key={plan.id}>
                  <Link
                    aria-label={`Xem ${version.title}`}
                    className="planCoverLink"
                    href={`/listings/${plan.id}`}
                  >
                    <div className={`planCover flexCover ${getCoverTone(plan.id)}`}>
                      {coverUrl ? (
                        <img alt="" className="coverImg" src={coverUrl} />
                      ) : (
                        <div className="coverFallback">
                          <span>{version.destination.slice(0, 2).toUpperCase()}</span>
                        </div>
                      )}
                      <div className="coverShade" />
                      <span className="planTag">{categoryName}</span>
                      <span className="coverDays">{version.durationDays} ngày</span>
                      <div className="coverDestination">
                        <small>Điểm đến</small>
                        <strong>{version.destination}</strong>
                      </div>
                    </div>
                  </Link>

                  <div className="planInfo">
                    <div className="creatorLine">
                      {plan.creator?.avatarUrl ? (
                        <img alt="" className="creatorAvatar image" src={plan.creator.avatarUrl} />
                      ) : (
                        <span className="creatorAvatar">{creatorName.charAt(0).toUpperCase()}</span>
                      )}
                      <span>Plan bởi <strong>{creatorName}</strong></span>
                      <span className="freshness">{formatUpdatedAt(version.updatedAt)}</span>
                    </div>

                    <Link className="planTitle textLink" href={`/listings/${plan.id}`}>
                      {version.title}
                    </Link>
                    <p>{version.description}</p>

                    <div className="planMeta">
                      <span>
                        <small>Thời lượng</small>
                        <strong>{version.durationDays} ngày</strong>
                      </span>
                      <span>
                        <small>Giá plan</small>
                        <strong>{formatPrice(version.priceAmount, version.priceCurrency)}</strong>
                      </span>
                    </div>

                    <div className="cardActions">
                      <button
                        aria-label={plan.isFavorited ? `Bỏ lưu ${version.title}` : `Lưu ${version.title}`}
                        aria-pressed={Boolean(plan.isFavorited)}
                        className={plan.isFavorited ? "saveButton saved" : "saveButton"}
                        onClick={() => void toggleFavorite(plan)}
                        type="button"
                      >
                        <HeartIcon filled={plan.isFavorited} />
                      </button>
                      <Link className="viewButton" href={`/listings/${plan.id}`}>
                        Xem hành trình
                        <ArrowIcon />
                      </Link>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}

        {totalPages > 1 && !loading ? (
          <nav aria-label="Phân trang" className="paginationRow">
            <button disabled={page <= 1} onClick={() => setPage((current) => current - 1)} type="button">
              <span aria-hidden="true">←</span> Trang trước
            </button>
            <span>
              <strong>{page}</strong> / {totalPages}
            </span>
            <button disabled={page >= totalPages} onClick={() => setPage((current) => current + 1)} type="button">
              Trang sau <span aria-hidden="true">→</span>
            </button>
          </nav>
        ) : null}

        <section className="creatorCallout">
          <div className="creatorCalloutCopy">
            <span className="eyebrow light">Góc dành cho creator</span>
            <h2>Chuyến đi của bạn có thể truyền cảm hứng cho người khác.</h2>
          </div>
          <div className="creatorCalloutAction">
            <p>
              Đóng gói trải nghiệm thành plan có cấu trúc, gửi kiểm duyệt và quản lý
              các phiên bản trong Creator Studio.
            </p>
            {user?.role === "creator" ? (
              <Link href="/creator/listings">Vào Creator Studio <ArrowIcon /></Link>
            ) : (
              <Link href="/profile">Tìm hiểu để trở thành Creator <ArrowIcon /></Link>
            )}
          </div>
          <span aria-hidden="true" className="calloutMark">✦</span>
        </section>
      </section>
    </main>
  );
}
