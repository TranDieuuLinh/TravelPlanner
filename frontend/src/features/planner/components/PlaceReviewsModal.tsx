"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  getPlaceReviews,
  type PlaceReview,
  type PlaceReviewPage,
} from "@/features/planner/api/plans";

export type PlaceReviewsModalPlace = {
  placeId: string;
  name: string;
  address?: string | null;
  rating?: number | null;
  reviewCount?: number | null;
  sourceLink?: string | null;
};

type PlaceReviewsModalProps = {
  place: PlaceReviewsModalPlace;
  onClose: () => void;
};

const PAGE_SIZE = 20;
const STAR_FILTERS: Array<number | null> = [null, 5, 4, 3, 2, 1];

export function PlaceReviewsModal({ place, onClose }: PlaceReviewsModalProps) {
  const [ratingFilter, setRatingFilter] = useState<number | null>(null);
  const [reviews, setReviews] = useState<PlaceReview[]>([]);
  const [page, setPage] = useState<PlaceReviewPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setReviews([]);
    setPage(null);
    getPlaceReviews(place.placeId, {
      rating: ratingFilter,
      limit: PAGE_SIZE,
      offset: 0,
    })
      .then((response) => {
        if (cancelled) return;
        setPage(response);
        setReviews(response.items);
      })
      .catch((requestError: unknown) => {
        if (cancelled) return;
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Không thể tải đánh giá lúc này."
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [place.placeId, ratingFilter]);

  const storedReviewCount = useMemo(
    () => Object.values(page?.ratingCounts ?? {}).reduce((sum, count) => sum + count, 0),
    [page?.ratingCounts]
  );
  const maxRatingCount = Math.max(
    1,
    ...Object.values(page?.ratingCounts ?? {}).map((count) => Number(count))
  );
  const googleMapsUrl = googleMapsReviewUrl(place);

  async function loadMore() {
    if (!page?.hasMore || loadingMore) return;
    setLoadingMore(true);
    setError(null);
    try {
      const response = await getPlaceReviews(place.placeId, {
        rating: ratingFilter,
        limit: PAGE_SIZE,
        offset: reviews.length,
      });
      setReviews((current) => [...current, ...response.items]);
      setPage(response);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Không thể tải thêm đánh giá."
      );
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <div
      aria-labelledby="place-reviews-title"
      aria-modal="true"
      className="placeReviewsBackdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      role="dialog"
    >
      <section className="placeReviewsModal">
        <header className="placeReviewsHeader">
          <div>
            <h2 id="place-reviews-title">{place.name}</h2>
          </div>
          <button
            aria-label="Đóng đánh giá"
            className="placeReviewsClose"
            onClick={onClose}
            ref={closeButtonRef}
            type="button"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="m7 7 10 10M17 7 7 17" />
            </svg>
          </button>
        </header>

        <div className="placeReviewsSummary">
          <div className="placeReviewsScore">
            <strong>{place.rating?.toFixed(1) ?? "—"}</strong>
            <span aria-label={`${place.rating ?? 0} trên 5 sao`}>
              {renderStars(place.rating ?? 0)}
            </span>
            <small>
              {place.reviewCount != null
                ? `${formatCount(place.reviewCount)} lượt đánh giá trên Google`
                : `${formatCount(storedReviewCount)} đánh giá đã lưu`}
            </small>
          </div>
          <div className="placeReviewsDistribution" aria-label="Phân bố đánh giá đã lưu">
            {[5, 4, 3, 2, 1].map((star) => {
              const count = page?.ratingCounts[String(star)] ?? 0;
              return (
                <div key={star}>
                  <span>{star}</span>
                  <i><b style={{ width: `${(count / maxRatingCount) * 100}%` }} /></i>
                  <small>{count}</small>
                </div>
              );
            })}
          </div>
        </div>

        <div aria-label="Lọc đánh giá theo số sao" className="placeReviewsFilters" role="group">
          {STAR_FILTERS.map((star) => (
            <button
              aria-pressed={ratingFilter === star}
              className={ratingFilter === star ? "isActive" : ""}
              key={star ?? "all"}
              onClick={() => setRatingFilter(star)}
              type="button"
            >
              {star == null ? "Tất cả" : `${star} ★`}
              {page ? (
                <small>
                  {star == null ? storedReviewCount : page.ratingCounts[String(star)] ?? 0}
                </small>
              ) : null}
            </button>
          ))}
        </div>

        <div className="placeReviewsList" aria-live="polite">
          {loading ? <ReviewListSkeleton /> : null}
          {!loading && error && reviews.length === 0 ? (
            <div className="placeReviewsState">
              <strong>Chưa tải được đánh giá</strong>
              <span>{error}</span>
            </div>
          ) : null}
          {!loading && !error && reviews.length === 0 ? (
            <div className="placeReviewsState">
              <strong>Chưa có đánh giá {ratingFilter ? `${ratingFilter} sao` : "chi tiết"}</strong>
              <span>Thử chọn mức sao khác hoặc xem nguồn trên Google Maps.</span>
            </div>
          ) : null}
          {reviews.map((review) => <ReviewCard key={review.id} review={review} />)}
          {error && reviews.length > 0 ? <p className="placeReviewsInlineError">{error}</p> : null}
          {page?.hasMore ? (
            <button className="placeReviewsMore" disabled={loadingMore} onClick={loadMore} type="button">
              {loadingMore ? "Đang tải…" : `Xem thêm (${page.total - reviews.length})`}
            </button>
          ) : null}
        </div>

        <footer className="placeReviewsFooter">
          <a href={googleMapsUrl} rel="noreferrer" target="_blank">
            {place.reviewCount != null
              ? `Xem toàn bộ ${formatCount(place.reviewCount)} đánh giá trên Google Maps ↗`
              : "Xem trên Google Maps ↗"}
          </a>
        </footer>
      </section>
    </div>
  );
}

function ReviewCard({ review }: { review: PlaceReview }) {
  const name = review.authorName?.trim() || "Người dùng Google";
  return (
    <article className="placeReviewCard">
      <div className="placeReviewAvatar" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</div>
      <div>
        <header>
          <strong>{name}</strong>
          <span>{review.whenText || formatReviewDate(review.publishedAt)}</span>
        </header>
        <div className="placeReviewStars" aria-label={`${review.rating ?? 0} trên 5 sao`}>
          {renderStars(review.rating ?? 0)}
        </div>
        {review.reviewText ? <p>{review.reviewText}</p> : <p className="isEmpty">Không có nội dung viết.</p>}
      </div>
    </article>
  );
}

function ReviewListSkeleton() {
  return <div className="placeReviewsSkeleton" aria-label="Đang tải đánh giá"><i /><i /><i /></div>;
}

function renderStars(rating: number): string {
  const rounded = Math.max(0, Math.min(5, Math.round(rating)));
  return `${"★".repeat(rounded)}${"☆".repeat(5 - rounded)}`;
}

function formatCount(value: number): string {
  return new Intl.NumberFormat("vi-VN").format(value);
}

function formatReviewDate(value?: string | null): string {
  if (!value) return "Không rõ thời điểm";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Không rõ thời điểm";
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium" }).format(date);
}

function googleMapsReviewUrl(place: PlaceReviewsModalPlace): string {
  if (place.sourceLink && isGoogleMapsUrl(place.sourceLink)) {
    return place.sourceLink;
  }
  const query = [place.name, place.address].filter(Boolean).join(", ");
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

function isGoogleMapsUrl(value: string): boolean {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    return (
      host === "maps.app.goo.gl" ||
      host === "maps.google.com" ||
      ((host === "google.com" || host === "www.google.com") &&
        url.pathname.startsWith("/maps"))
    );
  } catch {
    return false;
  }
}
