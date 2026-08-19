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
  isVerified?: boolean;
  source?: "knowledge_graph" | "google_maps_scraper" | string | null;
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
