import {
  networkAPIError,
  parseAPIError,
  jsonRequestHeaders
} from "@travelplanner/api-client";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export { APIError as BackendRequestError } from "@travelplanner/api-client";

/** Client nhỏ dùng cho các endpoint của backend modular mới. */
export async function backendFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: jsonRequestHeaders(init, { "Content-Type": "application/json" }),
    });
  } catch {
    throw networkAPIError("Không thể kết nối tới backend.");
  }

  if (!response.ok) throw await parseAPIError(response);

  return response.json() as Promise<T>;
}
