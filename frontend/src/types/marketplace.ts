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
