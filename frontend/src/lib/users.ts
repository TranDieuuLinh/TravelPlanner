import { apiFetch } from "@/lib/api";
import type { CurrentUser } from "@/components/AuthProvider";

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
