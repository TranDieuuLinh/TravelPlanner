import { apiFetch } from "@/shared/api/client";

export type PlaceReview = {
  id: string;
  authorName?: string | null;
  rating?: number | null;
  publishedAt?: string | null;
  whenText?: string | null;
  language?: string | null;
  reviewText?: string | null;
};

export type PlaceReviewPage = {
  items: PlaceReview[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
  ratingCounts: Record<string, number>;
};

export function getPlaceReviews(
  placeId: string,
  options: { rating?: number | null; limit?: number; offset?: number } = {}
): Promise<PlaceReviewPage> {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 20),
    offset: String(options.offset ?? 0),
  });
  if (options.rating != null) {
    params.set("rating", String(options.rating));
  }
  return apiFetch<PlaceReviewPage>(
    `/places/${encodeURIComponent(placeId)}/reviews?${params.toString()}`
  );
}
