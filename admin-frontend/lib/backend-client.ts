const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class BackendRequestError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "BackendRequestError";
  }
}

/** Client nhỏ dùng cho các endpoint của backend modular mới. */
export async function backendFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...init.headers,
      },
    });
  } catch {
    throw new BackendRequestError(0, "Không thể kết nối tới backend.");
  }

  if (!response.ok) {
    let message = `Backend request failed with status ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string; message?: string };
      message = body.message ?? body.detail ?? message;
    } catch {
      // Giữ thông báo mặc định nếu backend không trả JSON.
    }
    throw new BackendRequestError(response.status, message);
  }

  return response.json() as Promise<T>;
}
