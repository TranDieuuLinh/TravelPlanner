import { APIError, apiRequest } from "./api-client";

export type AdminUser = {
  id: number;
  email: string;
  fullName: string;
  role: "traveler" | "host" | "creator" | "admin";
};

export async function login(
  email: string,
  password: string
): Promise<AdminUser> {
  const response = await apiRequest<{ user: AdminUser; accessToken: string; refreshToken: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });
  window.localStorage.setItem("travelplanner_access_token", response.accessToken);
  window.localStorage.setItem("travelplanner_refresh_token", response.refreshToken);
  if (response.user.role !== "admin") {
    await logout();
    throw new APIError(403, {
      code: "ADMIN_REQUIRED",
      message: "Tài khoản này không có quyền quản trị."
    });
  }
  return response.user;
}

export async function logout(): Promise<void> {
  try {
    await apiRequest<void>("/auth/logout", {
      method: "POST",
      body: JSON.stringify({ refreshToken: window.localStorage.getItem("travelplanner_refresh_token") })
    });
  } finally {
    window.localStorage.removeItem("travelplanner_access_token");
    window.localStorage.removeItem("travelplanner_refresh_token");
  }
}
