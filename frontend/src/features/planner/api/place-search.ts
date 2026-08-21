import { apiFetch } from "@/shared/api/client";

export type PlaceSuggestion = {
  name: string;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  placeId?: string | null;
  imageUrl?: string | null;
  rating?: number | null;
  reviewCount?: number | null;
  priceLevel?: number | null;
  placeType?: string | null;
  phone?: string | null;
  website?: string | null;
  openingHours?: string[] | null;
  durationMinutes?: number | null;
  costPerPerson?: number | null;
  isVerified?: boolean;
  source?: "knowledge_graph" | "google_maps_scraper" | string | null;
};

export type SubplaceSummary = {
  placeId: string;
  name: string;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  imageUrl?: string | null;
  description?: string | null;
  durationMinutes?: number | null;
  costPerPerson?: number | null;
  rating?: number | null;
  reviewCount?: number | null;
};

export type SubplaceGroup = {
  parentPlaceId: string;
  totalCount: number;
  items: SubplaceSummary[];
};

export const PLACE_SEARCH_TOP_K = 5;

export async function searchPlaces(
  query: string,
  destination?: string,
  topK = PLACE_SEARCH_TOP_K
): Promise<PlaceSuggestion[]> {
  const params = new URLSearchParams({ query, topK: String(topK) });
  if (destination) params.append("destination", destination);
  return apiFetch<PlaceSuggestion[]>(
    `/v1/plans/places/search?${params.toString()}`
  );
}

export async function listSubplaces(
  parentPlaceIds: string[],
  options: { signal?: AbortSignal } = {}
): Promise<SubplaceGroup[]> {
  const uniqueIds = [...new Set(parentPlaceIds.map((id) => id.trim()).filter(Boolean))];
  if (uniqueIds.length === 0) return [];
  const params = new URLSearchParams();
  uniqueIds.slice(0, 50).forEach((id) => params.append("parentPlaceIds", id));
  return apiFetch<SubplaceGroup[]>(
    `/v1/plans/places/subplaces?${params.toString()}`,
    { signal: options.signal }
  );
}
