import { httpClient } from "@/lib/http-client";
import type { User } from "@/modules/users/types/user";

type CreateUserPayload = {
  email: string;
  fullName: string;
  role: User["role"];
  travelPreferences: string[];
};

export const userApi = {
  list() {
    return httpClient<User[]>("/users");
  },
  create(payload: CreateUserPayload) {
    return httpClient<User>("/users", {
      method: "POST",
      body: payload
    });
  }
};
