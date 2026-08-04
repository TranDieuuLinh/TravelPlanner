import { apiFetch } from "@/lib/api";
import type { CurrentUser } from "@/components/AuthProvider";
import type { ExplorePost, ProfilePost, ProfileShowcase } from "@/types/profile";

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
