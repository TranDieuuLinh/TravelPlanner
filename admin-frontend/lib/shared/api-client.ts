import {
  APIError,
  networkAPIError,
  parseAPIError,
  jsonRequestHeaders
} from "@travelplanner/api-client";

export { APIError } from "@travelplanner/api-client";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const ACCESS_TOKEN_KEY = "travelplanner_access_token";
const REFRESH_TOKEN_KEY = "travelplanner_refresh_token";

export const apiBaseUrl = API_BASE;

function token(key: string): string | null {
  if (typeof window === "undefined") return null;
  try { return window.localStorage.getItem(key); } catch { return null; }
}

async function refreshSession(): Promise<boolean> {
  const refreshToken = token(REFRESH_TOKEN_KEY);
  if (!refreshToken) return false;
  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refreshToken })
  });
  if (!response.ok) return false;
  const payload = await response.json() as { accessToken?: string; refreshToken?: string };
  if (!payload.accessToken || !payload.refreshToken) return false;
  window.localStorage.setItem(ACCESS_TOKEN_KEY, payload.accessToken);
  window.localStorage.setItem(REFRESH_TOKEN_KEY, payload.refreshToken);
  return true;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  retry = true
): Promise<T> {
  const headers = jsonRequestHeaders(init);
  const accessToken = token(ACCESS_TOKEN_KEY);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      credentials: "omit"
    });
  } catch {
    throw networkAPIError("Không kết nối được backend TravelPlanner.");
  }
  if (
    response.status === 401 &&
    retry &&
    !path.startsWith("/auth/") &&
    (await refreshSession())
  ) {
    return apiRequest<T>(path, init, false);
  }
  if (!response.ok) {
    throw await parseAPIError(response, "Không thể hoàn thành yêu cầu.", true);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
