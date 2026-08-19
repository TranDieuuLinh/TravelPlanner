import { NextResponse } from "next/server";
import { headers } from "next/headers";

/**
 * Lightweight session probe used by the admin dashboard layout.
 *
 * Returns the current admin user when the cookie session is valid; otherwise
 * 401 so the client can redirect to /login.
 *
 * The backend exposes the full admin session at /me; we proxy a minimal
 * subset to avoid sending sensitive claims to the browser.
 */
export async function GET() {
  const apiBase =
    process.env.API_BASE_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    "http://localhost:8000";
  try {
    const requestHeaders = await headers();
    const response = await fetch(`${apiBase}/me`, {
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(requestHeaders.get("cookie")
          ? { Cookie: requestHeaders.get("cookie") as string }
          : {})
      }
    });
    if (!response.ok) {
      return NextResponse.json(
        { error: { code: "UNAUTHENTICATED", message: "Chưa đăng nhập." } },
        { status: response.status }
      );
    }
    const payload = (await response.json()) as {
      id: number;
      email: string;
      fullName: string;
      role: "traveler" | "host" | "creator" | "admin";
    };
    if (!payload || payload.role !== "admin") {
      return NextResponse.json(
        { error: { code: "ADMIN_REQUIRED", message: "Không có quyền admin." } },
        { status: 403 }
      );
    }
    return NextResponse.json(payload);
  } catch {
    return NextResponse.json(
      { error: { code: "NETWORK", message: "Không kết nối được backend." } },
      { status: 502 }
    );
  }
}
