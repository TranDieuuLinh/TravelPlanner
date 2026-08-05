import { apiFetch } from "@/lib/api";
import type { CurrentUser } from "@/components/AuthProvider";
import type { ExplorePost, ProfilePost, ProfileShowcase } from "@/types/profile";

export type TravelerPreferenceSignal = {
  id: string;
  dimension: string;
  value: string;
  label: string;
  score: number;
  confidence: number;
  observations: number;
  scope: "global" | "destination";
  destination: string | null;
  origin: "explicit" | "inferred";
  status: "active" | "rejected";
  sourceTypes: string[];
  firstObservedAt: string;
  lastObservedAt: string;
  lastEvidenceIntakeId: string | null;
};

export type TravelerProfile = {
  userId: number;
  explicitPreferences: string[];
  topPreferences: string[];
  observationCount: number;
  signals: TravelerPreferenceSignal[];
  updatedAt: string | null;
};

export async function listUsers(): Promise<CurrentUser[]> {
  return apiFetch<CurrentUser[]>("/users");
}

export async function createUser(input: {
  email: string;
  fullName: string;
  role?: "traveler" | "host" | "creator" | "admin";
  avatarUrl?: string | null;
  travelPreferences?: string[];
}): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/users", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function getPlannerPreview(input: {
  destination: string;
  days?: number;
  budget?: "budget" | "medium" | "high";
}): Promise<{ draft: string }> {
  const search = new URLSearchParams({
    destination: input.destination,
    days: String(input.days ?? 3),
    budget: input.budget ?? "medium"
  });
  return apiFetch<{ draft: string }>(`/me/planner-preview?${search}`, {
    method: "POST"
  });
}

export async function getProfileShowcase(): Promise<ProfileShowcase> {
  return apiFetch<ProfileShowcase>("/me/showcase");
}

export async function getTravelerProfile(): Promise<TravelerProfile> {
  return apiFetch<TravelerProfile>("/me/traveler-profile");
}

export async function deleteTravelerProfile(): Promise<void> {
  return apiFetch<void>("/me/traveler-profile", { method: "DELETE" });
}

export async function createProfilePost(input: {
  contentType: "post" | "reel";
  caption: string;
  media: File;
  locationName: string;
}): Promise<ProfilePost> {
  const body = new FormData();
  body.append("contentType", input.contentType);
  body.append("caption", input.caption);
  body.append("locationName", input.locationName);
  body.append("media", input.media);
  return apiFetch<ProfilePost>("/me/posts", {
    method: "POST",
    body,
  });
}

export async function getExplorePosts(): Promise<ExplorePost[]> {
  return apiFetch<ExplorePost[]>("/posts?limit=30");
}
