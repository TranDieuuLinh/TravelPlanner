import { apiFetch } from "@/shared/api/client";

export type PlaceDedupeRecord = {
  entityId: string;
  name: string;
  aliases: string[];
  placeType: string;
  category: string;
  address: string;
  regionKey: string;
  latitude: number;
  longitude: number;
  reviewCount: number;
  revision: number;
};

export type PlaceReviewGroup = {
  groupId: string;
  reasonCodes: string[];
  records: PlaceDedupeRecord[];
};

export type PlaceReviewResponse = {
  schemaVersion: number;
  generatedAt: string;
  groupCount: number;
  groups: PlaceReviewGroup[];
};

export type PlaceReviewDecisionResponse = {
  groupId: string;
  decision: "merged" | "not_merged";
};

export function getPlaceReviewGroups({
  offset = 0,
  limit = 50,
  query = "",
}: {
  offset?: number;
  limit?: number;
  query?: string;
} = {}): Promise<PlaceReviewResponse> {
  const params = new URLSearchParams({
    offset: String(offset),
    limit: String(limit),
  });
  if (query.trim()) params.set("query", query.trim());
  return apiFetch<PlaceReviewResponse>(
    `/admin/knowledge-graph/place-dedupe/review?${params.toString()}`,
  );
}

export function approvePlaceMerge(
  groupId: string,
  canonicalEntityId: string,
): Promise<PlaceReviewDecisionResponse> {
  return apiFetch<PlaceReviewDecisionResponse>(
    `/admin/knowledge-graph/place-dedupe/review/${encodeURIComponent(groupId)}/merge`,
    {
      method: "POST",
      body: JSON.stringify({ canonicalEntityId }),
    },
  );
}

export function dismissPlaceMerge(groupId: string): Promise<PlaceReviewDecisionResponse> {
  return apiFetch<PlaceReviewDecisionResponse>(
    `/admin/knowledge-graph/place-dedupe/review/${encodeURIComponent(groupId)}/dismiss`,
    { method: "POST" },
  );
}
