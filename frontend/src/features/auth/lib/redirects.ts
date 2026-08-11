import type { CurrentUser } from "@/features/auth/components/AuthProvider";

export function safeNextPath(next: string | null | undefined): string | null {
  if (!next || !next.startsWith("/") || next.startsWith("//")) return null;
  if (next === "/login" || next === "/register") return null;
  return next;
}

export function defaultRouteForUser(user: Pick<CurrentUser, "role">): string {
  if (user.role === "admin") return "/admin/places";
  if (user.role === "creator") return "/creator/listings";
  return "/profile";
}

export function postAuthRoute(
  user: Pick<CurrentUser, "role">,
  next: string | null | undefined,
): string {
  return safeNextPath(next) ?? defaultRouteForUser(user);
}
