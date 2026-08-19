"use client";

import "@/styles/global/explore.css";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/features/auth/components/AuthProvider";
import { PenguinMascot } from "@/components/PenguinMascot";
import { APIError } from "@/shared/api/client";
import {
  addFavorite,
  getMarketplaceCategories,
  removeFavorite,
  searchListings
} from "@/features/marketplace/api";
import type { ListingSummary } from "@/features/marketplace/types";

const defaultCategories = ["food", "nature", "family", "budget", "balanced", "comfortable", "creator-picks"];

const categoryLabels: Record<string, string> = {
  budget: "Tiết kiệm",
  balanced: "Cân bằng",
  medium: "Cân bằng",
  comfortable: "Thoải mái",
  high: "Cao cấp",
  food: "Ẩm thực",
  nature: "Thiên nhiên",
  family: "Gia đình",
  "creator-picks": "Creator chọn"
};

const durationOptions = ["Mọi thời lượng", "1-3 ngày", "4-7 ngày"];

const budgetOptions = [
  { id: "all", label: "Mọi ngân sách" },
  { id: "under100", label: "Dưới 100.000 đ", maxPrice: 99999 },
  { id: "100to200", label: "100.000 - 200.000 đ", minPrice: 100000, maxPrice: 200000 },
  { id: "over200", label: "Trên 200.000 đ", minPrice: 200001 },
];

const coverTones = ["sunset", "forest", "berry", "mist", "lime", "ocean"];

type IconProps = { filled?: boolean };

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

function HeartIcon({ filled = false }: IconProps) {
  return (
    <svg aria-hidden="true" fill={filled ? "currentColor" : "none"} viewBox="0 0 24 24">
      <path d="M20.8 4.7a5.6 5.6 0 0 0-7.9 0L12 5.6l-.9-.9a5.6 5.6 0 0 0-7.9 7.9l.9.9L12 21.4l7.9-7.9.9-.9a5.6 5.6 0 0 0 0-7.9Z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}

function MapPinIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <path d="M12 21s6.5-5.5 6.5-11A6.5 6.5 0 0 0 5.5 10C5.5 15.5 12 21 12 21Z" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="12" cy="10" r="2.2" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 7.5v5l3.2 1.9" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg aria-hidden="true" fill="currentColor" viewBox="0 0 20 20">
      <path d="M6.3 4.7v10.6c0 .8.9 1.2 1.5.8l7.4-5.3a1 1 0 0 0 0-1.6L7.8 3.9c-.6-.4-1.5 0-1.5.8Z" />
    </svg>
  );
}

function SlidersIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <path d="M4 7h9m4 0h3M4 17h3m4 0h9" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
      <circle cx="15" cy="7" r="2" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="9" cy="17" r="2" stroke="currentColor" strokeWidth="1.8" />
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
  return new Intl.DateTimeFormat("vi-VN", {
    month: "short",
    year: "numeric"
  }).format(date);
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

function matchesDuration(item: ListingSummary, duration: string) {
  const days = item.currentVersion.durationDays;
  if (duration === "1-3 ngày") return days <= 3;
  if (duration === "4-7 ngày") return days >= 4 && days <= 7;
  return true;
}

export default function ExplorePage() {
  const router = useRouter();
  const { user } = useAuth();

  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [category, setCategory] = useState("Tất cả");
  const [categories, setCategories] = useState<string[]>(defaultCategories);
  const [duration, setDuration] = useState(durationOptions[0]);
  const [budget, setBudget] = useState(budgetOptions[0].id);
  const [page, setPage] = useState(1);
  const [refreshKey, setRefreshKey] = useState(0);

  const [listings, setListings] = useState<ListingSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const selectedBudget = budgetOptions.find((option) => option.id === budget) ?? budgetOptions[0];

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
          minPrice: selectedBudget.minPrice,
          maxPrice: selectedBudget.maxPrice,
          sort: "newest",
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
  }, [appliedQuery, category, page, refreshKey, selectedBudget.maxPrice, selectedBudget.minPrice, user]);

  useEffect(() => {
    void getMarketplaceCategories()
      .then((items) => setCategories(items.length ? items : defaultCategories))
      .catch(() => setCategories(defaultCategories));
  }, []);

  const visibleListings = useMemo(
    () => listings.filter((listing) => matchesDuration(listing, duration)),
    [duration, listings]
  );

  function handleSearchSubmit(event: React.FormEvent) {
    event.preventDefault();
    setPage(1);
    setAppliedQuery(query.trim());
  }

  function clearFilters() {
    setQuery("");
    setAppliedQuery("");
    setCategory("Tất cả");
    setDuration(durationOptions[0]);
    setBudget(budgetOptions[0].id);
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
    <main className="explorePage marketExplorePage">
      <section className="pageWidth marketExploreHero">
        <div>
          <h1>Khám phá hành trình từ Creator</h1>
          <p>Xem các plan được chia sẻ, lấy cảm hứng và tiếp tục tùy chỉnh theo chuyến đi của bạn.</p>

          <form className="marketHeroSearch" onSubmit={handleSearchSubmit}>
            <SearchIcon />
            <input
              aria-label="Tìm địa điểm hoặc hành trình"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Phú Quốc, chụp ảnh, đi gia đình..."
              value={query}
            />
            <button type="submit">Tìm kiếm</button>
          </form>
        </div>
      </section>

      <section className="pageWidth marketExploreContent">
        <div className="marketCategoryRow" aria-label="Danh mục hành trình">
          {["Tất cả", ...categories].map((item) => (
            <button
              aria-pressed={category === item}
              className={category === item ? "marketChip active" : "marketChip"}
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

        <div className="marketFilterBar">
          <span className="marketFilterLabel"><SlidersIcon /> Bộ lọc</span>
          <select
            aria-label="Lọc theo thời lượng"
            onChange={(event) => {
              setDuration(event.target.value);
              setPage(1);
            }}
            value={duration}
          >
            {durationOptions.map((option) => <option key={option}>{option}</option>)}
          </select>
          <select
            aria-label="Lọc theo ngân sách"
            onChange={(event) => {
              setBudget(event.target.value);
              setPage(1);
            }}
            value={budget}
          >
            {budgetOptions.map((option) => (
              <option key={option.id} value={option.id}>{option.label}</option>
            ))}
          </select>
          <button className="marketRatingChip" disabled title="Danh sách hiện chưa trả điểm đánh giá để lọc chính xác" type="button">
            Đánh giá 4.7★ trở lên
          </button>
          <span className="marketResultCount">
            {loading ? "Đang tải..." : `${duration === durationOptions[0] ? total : visibleListings.length} kết quả`}
          </span>
        </div>

        {loading ? (
          <div aria-label="Đang tải danh sách hành trình" className="marketPlanGrid">
            {Array.from({ length: 6 }).map((_, index) => (
              <div aria-hidden="true" className="marketPlanCard marketSkeleton" key={index}>
                <div className="marketSkeletonCover" />
                <div className="marketSkeletonBody">
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
        ) : visibleListings.length === 0 ? (
          <div className="emptyState exploreEmpty">
            <PenguinMascot className="emptyPenguin" size={180} variant="search" />
            <h2>Chưa có hành trình khớp với bạn</h2>
            <p>Thử một điểm đến khác hoặc xem lại toàn bộ plan đang có.</p>
            <button onClick={clearFilters} type="button">Xem tất cả hành trình</button>
          </div>
        ) : (
          <div className="marketPlanGrid">
            {visibleListings.map((plan) => {
              const version = plan.currentVersion;
              const creatorName = plan.creator?.fullName || "Creator";
              const coverUrl = version.mediaUrls?.[0] || "";
              const categoryName = categoryLabels[version.category] ?? version.category;

              return (
                <article className="marketPlanCard" key={plan.id}>
                  <Link aria-label={`Xem ${version.title}`} className="marketCoverLink" href={`/listings/${plan.id}`}>
                    <div className={`marketCover ${getCoverTone(plan.id)}`}>
                      {coverUrl ? (
                        <img alt={version.title} loading="lazy" src={coverUrl} />
                      ) : (
                        <div className="marketCoverFallback">
                          <span>{version.destination.slice(0, 2).toUpperCase()}</span>
                        </div>
                      )}
                      <span className="marketCategoryBadge">{categoryName}</span>
                      {coverUrl ? (
                        <span className="marketPreviewBadge"><PlayIcon /> Có preview</span>
                      ) : null}
                    </div>
                  </Link>

                  <button
                    aria-label={plan.isFavorited ? `Bỏ lưu ${version.title}` : `Lưu ${version.title}`}
                    aria-pressed={Boolean(plan.isFavorited)}
                    className={plan.isFavorited ? "marketFavorite saved" : "marketFavorite"}
                    onClick={() => void toggleFavorite(plan)}
                    type="button"
                  >
                    <HeartIcon filled={plan.isFavorited} />
                  </button>

                  <div className="marketCardBody">
                    <Link className="marketCardTitle" href={`/listings/${plan.id}`}>{version.title}</Link>
                    <div className="marketMetaRow">
                      <span><MapPinIcon /> {version.destination}</span>
                      <span><ClockIcon /> {version.durationDays} ngày</span>
                      <span>Cập nhật {formatUpdatedAt(version.updatedAt)}</span>
                    </div>
                    <p>{version.description}</p>
                    <div className="marketCardFooter">
                      <span className="marketPrice">{formatPrice(version.priceAmount, version.priceCurrency)}</span>
                      <Link className="marketDetailLink" href={`/listings/${plan.id}`}>
                        Xem chi tiết <ArrowIcon />
                      </Link>
                    </div>
                    <div className="marketCreatorLine">Plan bởi <strong>{creatorName}</strong></div>
                  </div>
                </article>
              );
            })}
          </div>
        )}

        {totalPages > 1 && !loading ? (
          <nav aria-label="Phân trang" className="paginationRow marketPagination">
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

        <section className="creatorCallout marketCreatorCallout">
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
