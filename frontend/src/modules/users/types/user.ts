export type UserRole = "traveler" | "host" | "creator" | "admin";

export type User = {
  id: number;
  email: string;
  fullName: string;
  role: UserRole;
  avatarUrl?: string | null;
  travelPreferences: string[];
  createdAt: string;
};
