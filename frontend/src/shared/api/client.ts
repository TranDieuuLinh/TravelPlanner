import {
  networkAPIError,
  parseAPIError,
  jsonRequestHeaders
} from "@travelplanner/api-client";

export { APIError } from "@travelplanner/api-client";
export type { APIErrorBody } from "@travelplanner/api-client";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function getCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const prefix = `${encodeURIComponent(name)}=`;
  return document.cookie
    .split("; ")
    .find((item) => item.startsWith(prefix))
    ?.slice(prefix.length);
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

async function performSessionRefresh(observedCsrf?: string): Promise<boolean> {
  const csrf = getCookie("travelplanner_csrf");
  if (!csrf) return false;

  // Another tab may have refreshed while this request was waiting for the
  // browser-wide lock. Its new cookies are already available to this tab, so
  // retry the original request instead of rotating the token a second time.
  if (observedCsrf && csrf !== observedCsrf) return true;

  try {
    const response = await fetch(`${apiBase}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRF-Token": decodeURIComponent(csrf) }
    });
    return response.ok;
  } catch {
    return false;
  }
}

async function refreshSession(observedCsrf?: string): Promise<boolean> {
  if (refreshSessionPromise) return refreshSessionPromise;

  refreshSessionPromise = (async () => {
    const locks = typeof navigator !== "undefined"
      ? (navigator as NavigatorWithLocks).locks
      : undefined;
    if (locks) {
      return locks.request("travelplanner-auth-refresh", () =>
        performSessionRefresh(observedCsrf)
      );
    }
    return performSessionRefresh(observedCsrf);
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
  const observedCsrf = getCookie("travelplanner_csrf");
  const headers = jsonRequestHeaders(init);
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = getCookie("travelplanner_csrf");
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }

  let response: Response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      ...init,
      credentials: "include",
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
    await refreshSession(observedCsrf)
  ) {
    return apiFetch<T>(path, init, false);
  }
  if (!response.ok) throw await parseAPIError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
