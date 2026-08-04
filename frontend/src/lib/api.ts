const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

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

async function refreshSession(): Promise<boolean> {
  const csrf = getCookie("vsf_csrf");
  if (!csrf) return false;
  const response = await fetch(`${apiBase}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": decodeURIComponent(csrf) }
  });
  return response.ok;
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  retryAuth = true
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
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
    const csrf = getCookie("vsf_csrf");
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
  if (response.status === 401 && retryAuth && !isAuthRoute && await refreshSession()) {
    return apiFetch<T>(path, init, false);
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
