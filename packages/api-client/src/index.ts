export type APIErrorBody = {
  code?: string;
  message?: string;
  detail?: string | { message?: string };
  details?: Record<string, unknown>;
  fieldErrors?: Record<string, string>;
  field_errors?: Record<string, string>;
  requestId?: string;
};

export class APIError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fieldErrors: Record<string, string>;
  readonly details: Record<string, unknown>;
  readonly requestId?: string;

  constructor(status: number, body: APIErrorBody) {
    super(body.message ?? "Không thể hoàn thành yêu cầu.");
    this.name = "APIError";
    this.status = status;
    this.code = body.code ?? "REQUEST_FAILED";
    this.fieldErrors = body.fieldErrors ?? body.field_errors ?? {};
    this.details = body.details ?? {};
    this.requestId = body.requestId;
  }
}

export function networkAPIError(message: string): APIError {
  return new APIError(0, {
    code: "NETWORK_ERROR",
    message
  });
}

export async function parseAPIError(
  response: Response,
  fallbackMessage = "Backend không trả về phản hồi hợp lệ.",
  includeFieldErrorsInMessage = false
): Promise<APIError> {
  let body: APIErrorBody = {};

  try {
    body = await response.json() as APIErrorBody;
    if (!body.message && body.detail) {
      body.message = typeof body.detail === "string"
        ? body.detail
        : body.detail.message;
    }
  } catch {
    body = { message: fallbackMessage };
  }

  if (includeFieldErrorsInMessage) {
    const fieldErrors = body.fieldErrors ?? body.field_errors;
    if (fieldErrors && Object.keys(fieldErrors).length > 0) {
      const details = Object.entries(fieldErrors)
        .map(([field, reason]) => `${field}: ${reason}`)
        .join("; ");
      if (details) body.message = `${body.message ?? fallbackMessage} (${details})`;
    }
  }

  return new APIError(response.status, body);
}

export function jsonRequestHeaders(
  init: RequestInit,
  extraHeaders: HeadersInit = {}
): Headers {
  const headers = new Headers(init.headers);
  const bodyNeedsJsonContentType = Boolean(
    init.body
    && !(typeof FormData !== "undefined" && init.body instanceof FormData)
    && !(typeof URLSearchParams !== "undefined" && init.body instanceof URLSearchParams)
    && !(typeof Blob !== "undefined" && init.body instanceof Blob)
  );

  if (bodyNeedsJsonContentType && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  new Headers(extraHeaders).forEach((value, key) => headers.set(key, value));
  return headers;
}
