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
  const response = await apiRequest<{ user: AdminUser }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });
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
  await apiRequest<void>("/auth/logout", { method: "POST" });
}