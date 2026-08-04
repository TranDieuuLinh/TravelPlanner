import { apiFetch } from "@/lib/api";
import type {
  FavoriteResponse,
  AuditEvent,
  BuyerPlan,
  ListingDetail,
  ListingPaginated,
  ListingSummary,
  ListingVersion,
  PendingListingVersion,
  PublishablePlan,
  MarketplaceReport,
  Review,
  ReviewPaginated,
} from "@/types/marketplace";

export async function getMarketplaceCategories(): Promise<string[]> {
  return apiFetch<string[]>("/marketplace/categories");
}

export async function getPublishablePlans(): Promise<PublishablePlan[]> {
  return apiFetch<PublishablePlan[]>("/creator/publishable-plans");
}

export async function createListing(data: {
  planId: string;
  title: string;
  summary: string;
  category: string;
  priceAmount: number;
  currency?: string;
  mediaUrls?: string[];
}): Promise<ListingDetail> {
  return apiFetch<ListingDetail>("/creator/listings", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getCreatorListings(): Promise<ListingDetail[]> {
  return apiFetch<ListingDetail[]>("/creator/listings");
}

export async function getCreatorListingDetail(listingId: string): Promise<ListingDetail> {
  return apiFetch<ListingDetail>(`/creator/listings/${listingId}`);
}

export async function updateListing(
  listingId: string,
  data: {
    title?: string;
    summary?: string;
    category?: string;
    priceAmount?: number;
    currency?: string;
    mediaUrls?: string[];
    expectedVersion?: number;
  }
): Promise<ListingDetail> {
  return apiFetch<ListingDetail>(`/creator/listings/${listingId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function submitListing(listingId: string): Promise<ListingDetail> {
  return apiFetch<ListingDetail>(`/creator/listings/${listingId}/submit`, {
    method: "POST",
  });
}

export async function publishListing(listingId: string): Promise<ListingDetail> {
  return apiFetch<ListingDetail>(`/creator/listings/${listingId}/publish`, {
    method: "POST",
  });
}

export async function unpublishListing(listingId: string): Promise<ListingDetail> {
  return apiFetch<ListingDetail>(`/creator/listings/${listingId}/unpublish`, {
    method: "POST",
  });
}

export async function searchListings(params: {
  page?: number;
  pageSize?: number;
  query?: string;
  category?: string;
  minPrice?: number;
  maxPrice?: number;
  sort?: string;
}): Promise<ListingPaginated> {
  const search = new URLSearchParams();
  if (params.page) search.set("page", params.page.toString());
  if (params.pageSize) search.set("pageSize", params.pageSize.toString());
  if (params.query) search.set("query", params.query);
  if (params.category) search.set("category", params.category);
  if (params.minPrice !== undefined) search.set("minPrice", params.minPrice.toString());
  if (params.maxPrice !== undefined) search.set("maxPrice", params.maxPrice.toString());
  if (params.sort) search.set("sort", params.sort);

  const queryString = search.toString();
  return apiFetch<ListingPaginated>(`/listings${queryString ? `?${queryString}` : ""}`);
}

export async function getPublicListingDetail(listingId: string): Promise<ListingDetail> {
  return apiFetch<ListingDetail>(`/listings/${listingId}`);
}

export async function addFavorite(listingId: string): Promise<FavoriteResponse> {
  return apiFetch<FavoriteResponse>(`/listings/${listingId}/favorite`, {
    method: "PUT",
  });
}

export async function removeFavorite(listingId: string): Promise<FavoriteResponse> {
  return apiFetch<FavoriteResponse>(`/listings/${listingId}/favorite`, {
    method: "DELETE",
  });
}

export async function getUserFavorites(): Promise<ListingSummary[]> {
  return apiFetch<ListingSummary[]>("/me/favorites");
}

export async function getPurchasedPlans(): Promise<BuyerPlan[]> {
  return apiFetch<BuyerPlan[]>("/me/plans");
}

export async function getListingReviews(
  listingId: string,
  page = 1,
  pageSize = 10
): Promise<ReviewPaginated> {
  return apiFetch<ReviewPaginated>(
    `/listings/${listingId}/reviews?page=${page}&pageSize=${pageSize}`
  );
}

export async function saveListingReview(
  listingId: string,
  rating: number,
  comment: string
): Promise<Review> {
  return apiFetch<Review>(`/listings/${listingId}/reviews`, {
    method: "POST",
    body: JSON.stringify({ rating, comment })
  });
}

export async function reportListing(
  listingId: string,
  reason: string,
  description: string
): Promise<MarketplaceReport> {
  return apiFetch<MarketplaceReport>(`/listings/${listingId}/reports`, {
    method: "POST",
    body: JSON.stringify({ reason, description })
  });
}

export async function getAdminPendingListings(): Promise<PendingListingVersion[]> {
  return apiFetch<PendingListingVersion[]>("/admin/listings/pending");
}

export async function reviewListingVersion(
  versionId: string,
  decision: "approve" | "reject",
  reason?: string
): Promise<ListingVersion> {
  return apiFetch<ListingVersion>(`/admin/listings/${versionId}/review`, {
    method: "POST",
    body: JSON.stringify({ decision, reason }),
  });
}

export async function getAdminReports(filters: {
  status?: string;
  reason?: string;
} = {}): Promise<MarketplaceReport[]> {
  const search = new URLSearchParams();
  if (filters.status) search.set("status", filters.status);
  if (filters.reason) search.set("reason", filters.reason);
  return apiFetch<MarketplaceReport[]>(
    `/admin/reports${search.size ? `?${search}` : ""}`
  );
}

export async function resolveAdminReport(
  reportId: string,
  decision: "dismiss" | "unpublish" | "requestChanges",
  note?: string
): Promise<MarketplaceReport> {
  return apiFetch<MarketplaceReport>(`/admin/reports/${reportId}/resolve`, {
    method: "POST",
    body: JSON.stringify({ decision, note })
  });
}

export async function refundOrder(
  orderId: string,
  reason?: string
): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(`/admin/orders/${orderId}/refund`, {
    method: "POST",
    body: JSON.stringify({ reason })
  });
}

export async function getAdminAuditEvents(filters: {
  actorId?: number;
  action?: string;
  resourceType?: string;
  resourceId?: string;
} = {}): Promise<AuditEvent[]> {
  const search = new URLSearchParams();
  if (filters.actorId !== undefined) search.set("actorId", String(filters.actorId));
  if (filters.action) search.set("action", filters.action);
  if (filters.resourceType) search.set("resourceType", filters.resourceType);
  if (filters.resourceId) search.set("resourceId", filters.resourceId);
  return apiFetch<AuditEvent[]>(
    `/admin/audit-events${search.size ? `?${search}` : ""}`
  );
}
