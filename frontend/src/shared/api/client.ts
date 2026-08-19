import {
  networkAPIError,
  parseAPIError,
  jsonRequestHeaders
} from "@travelplanner/api-client";

export { APIError } from "@travelplanner/api-client";
export type { APIErrorBody } from "@travelplanner/api-client";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const ACCESS_TOKEN_KEY = "travelplanner_access_token";
const REFRESH_TOKEN_KEY = "travelplanner_refresh_token";

let accessToken: string | null = null;

function readAccessToken(): string | null {
  if (accessToken) return accessToken;
  if (typeof window === "undefined") return null;
  accessToken = window.localStorage.getItem(ACCESS_TOKEN_KEY);
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(ACCESS_TOKEN_KEY, token);
  else window.localStorage.removeItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(access: string | null, refresh: string | null): void {
  setAccessToken(access);
  if (typeof window === "undefined") return;
  if (refresh) window.localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
  else window.localStorage.removeItem(REFRESH_TOKEN_KEY);
}

let refreshSessionPromise: Promise<boolean> | null = null;

type NavigatorWithLocks = Navigator & {
  locks?: {
    request<T>(
      name: string,
      callback: () => Promise<T>
    ): Promise<T>;
  };
};

async function performSessionRefresh(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  try {
    const response = await fetch(`${apiBase}/auth/refresh`, {
      method: "POST",
      credentials: "omit",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refreshToken })
    });
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) setTokens(null, null);
      return false;
    }
    const body = await response.json() as { accessToken?: string; refreshToken?: string };
    if (!body.accessToken || !body.refreshToken) return false;
    setTokens(body.accessToken, body.refreshToken);
    return true;
  } catch {
    return false;
  }
}

async function refreshSession(): Promise<boolean> {
  if (refreshSessionPromise) return refreshSessionPromise;

  refreshSessionPromise = (async () => {
    const locks = typeof navigator !== "undefined"
      ? (navigator as NavigatorWithLocks).locks
      : undefined;
    if (locks) {
      return locks.request("travelplanner-auth-refresh", () =>
        performSessionRefresh()
      );
    }
    return performSessionRefresh();
  })().finally(() => {
    refreshSessionPromise = null;
  });

  return refreshSessionPromise;
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  retryAuth = true
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = jsonRequestHeaders(init);
  const token = readAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      ...init,
      credentials: "omit",
      headers
    });
  } catch {
    throw networkAPIError(
      "Không thể kết nối tới máy chủ. Vui lòng kiểm tra backend đang chạy."
    );
  }

  const isAuthRoute = path.startsWith("/auth/");
  if (
    response.status === 401 &&
    retryAuth &&
    !isAuthRoute &&
    await refreshSession()
  ) {
    return apiFetch<T>(path, init, false);
  }
  if (!response.ok) throw await parseAPIError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
