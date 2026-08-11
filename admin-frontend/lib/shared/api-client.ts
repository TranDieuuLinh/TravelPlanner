import {
  APIError,
  networkAPIError,
  parseAPIError,
  jsonRequestHeaders
} from "@travelplanner/api-client";

export { APIError } from "@travelplanner/api-client";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const apiBaseUrl = API_BASE;

function cookie(name: string): string | undefined {
  const prefix = `${encodeURIComponent(name)}=`;
  return document.cookie
    .split("; ")
    .find((item) => item.startsWith(prefix))
    ?.slice(prefix.length);
}

async function refreshSession(): Promise<boolean> {
  const csrf = cookie("travelplanner_csrf");
  if (!csrf) return false;
  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": decodeURIComponent(csrf) }
  });
  return response.ok;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  retry = true
): Promise<T> {
  const headers = jsonRequestHeaders(init);
  if (!["GET", "HEAD"].includes((init.method ?? "GET").toUpperCase())) {
    const csrf = cookie("travelplanner_csrf");
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      credentials: "include"
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