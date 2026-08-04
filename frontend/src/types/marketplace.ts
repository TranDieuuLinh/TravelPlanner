export type ListingStatus = "draft" | "published" | "unpublished";
export type ModerationStatus = "draft" | "pending_review" | "approved" | "rejected" | "published";

export interface PublishablePlan {
  planId: string;
  planVersionId: string;
  ownerId: number;
  title: string;
  destination: string;
  days: number;
  status: string;
  checkStatus: string;
}

export interface ListingVersion {
  id: string;
  marketplacePlanId: string;
  version: number;
  sourcePlanId: string;
  sourcePlanVersionId: string;
  title: string;
  description: string;
  destination: string;
  durationDays: number;
  category: string;
  priceAmount: number;
  priceCurrency: string;
  mediaUrls: string[];
  previewSnapshot: {
    title?: string;
    destination?: string;
    days?: number;
    highlights?: string[];
    daySummaries?: Array<{ day: number; theme: string }>;
  };
  moderationStatus: ModerationStatus;
  rejectionReason?: string | null;
  createdAt: string;
  updatedAt: string;
  publishedAt?: string | null;
}

export interface CreatorInfo {
  id: number;
  fullName: string;
  avatarUrl?: string | null;
}

export interface ListingDetail {
  id: string;
  creatorId: number;
  creator?: CreatorInfo | null;
  status: ListingStatus;
  currentPublishedVersionId?: string | null;
  currentVersion?: ListingVersion | null;
  versions: ListingVersion[];
  isFavorited?: boolean;
  stats?: {
    views?: number;
    orders?: number;
    grossRevenue?: number;
  };
  createdAt: string;
  updatedAt: string;
}

export interface ListingSummary {
  id: string;
  creatorId: number;
  creator?: CreatorInfo | null;
  status: ListingStatus;
  currentVersion: ListingVersion;
  isFavorited?: boolean;
  createdAt: string;
}

export interface ListingPaginated {
  items: ListingSummary[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface FavoriteResponse {
  marketplacePlanId: string;
  isFavorited: boolean;
}

export interface PendingListingVersion {
  listingVersionId: string;
  listingId: string;
  version: number;
  title: string;
  description: string;
  destination: string;
  durationDays: number;
  category: string;
  priceAmount: number;
  priceCurrency: string;
  mediaUrls: string[];
  previewSnapshot: {
    title?: string;
    destination?: string;
    days?: number;
    highlights?: string[];
    daySummaries?: Array<{ day: number; theme: string }>;
  };
  creator: CreatorInfo;
  createdAt: string;
  updatedAt: string;
}

export interface Review {
  id: string;
  reviewerId: number;
  reviewerName: string;
  reviewerAvatarUrl?: string | null;
  marketplacePlanId: string;
  rating: number;
  comment: string;
  status: string;
  createdAt: string;
  updatedAt: string;
}

export interface ReviewPaginated {
  items: Review[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface MarketplaceReport {
  id: string;
  reporterId: number;
  reporterName?: string | null;
  marketplacePlanId: string;
  reason: string;
  description: string;
  status: string;
  resolution?: string | null;
  createdAt: string;
}

export interface AuditEvent {
  id: string;
  actorId?: number | null;
  action: string;
  resourceType: string;
  resourceId?: string | null;
  requestId?: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
}

export interface BuyerPlan {
  orderId: string;
  entitlementId: string;
  marketplacePlanId: string;
  marketplacePlanVersionId: string;
  title: string;
  destination: string;
  durationDays: number;
  copiedPlanId?: string | null;
  status: string;
  createdAt: string;
}
