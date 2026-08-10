const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type AgentInvokeRequest = {
  threadId: string;
  message: string;
  suppliedCandidates?: unknown[];
  existingItinerary?: unknown;
  editOperation?: unknown;
};

export type AgentInvokeResponse = {
  request_id: string;
  route: string;
  response: string;
  itinerary: unknown | null;
  clarification_question: string | null;
  warnings: string[];
};

export async function invokeAgent(
  input: AgentInvokeRequest
): Promise<AgentInvokeResponse> {
  return apiFetch<AgentInvokeResponse>("/v1/agent/invoke", {
    method: "POST",
    body: JSON.stringify({
      thread_id: input.threadId,
      message: input.message,
      supplied_candidates: input.suppliedCandidates ?? [],
      existing_itinerary: input.existingItinerary,
      edit_operation: input.editOperation,
    }),
  });
}

export type APIErrorBody = {
  code?: string;
  message?: string;
  detail?: string | { message?: string };
  details?: Record<string, unknown>;
  fieldErrors?: Record<string, string>;
  requestId?: string;
};

export class APIError extends Error {
  status: number;
  code: string;
  fieldErrors: Record<string, string>;
  details: Record<string, unknown>;
  requestId?: string;

  constructor(status: number, body: APIErrorBody) {
    super(body.message ?? "Không thể hoàn thành yêu cầu.");
    this.name = "APIError";
    this.status = status;
    this.code = body.code ?? "REQUEST_FAILED";
    this.fieldErrors = body.fieldErrors ?? {};
    this.details = body.details ?? {};
    this.requestId = body.requestId;
  }
}

function networkError(): APIError {
  return new APIError(0, {
    code: "NETWORK_ERROR",
    message: "Không thể kết nối tới máy chủ. Vui lòng kiểm tra backend đang chạy."
  });
}

function getCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const prefix = `${encodeURIComponent(name)}=`;
  return document.cookie
    .split("; ")
    .find((item) => item.startsWith(prefix))
    ?.slice(prefix.length);
}

async function parseError(response: Response): Promise<APIError> {
  let body: APIErrorBody = {};
  try {
    body = await response.json() as APIErrorBody;
    if (!body.message && body.detail) {
      body.message = typeof body.detail === "string"
        ? body.detail
        : body.detail.message;
    }
  } catch {
    body = { message: "Backend không trả về phản hồi hợp lệ." };
  }
  return new APIError(response.status, body);
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
  const headers = new Headers(init.headers);
  const bodyNeedsJsonContentType = (
    init.body
    && !(typeof FormData !== "undefined" && init.body instanceof FormData)
    && !(typeof URLSearchParams !== "undefined" && init.body instanceof URLSearchParams)
    && !(typeof Blob !== "undefined" && init.body instanceof Blob)
  );
  if (bodyNeedsJsonContentType && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
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
    throw networkError();
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
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
