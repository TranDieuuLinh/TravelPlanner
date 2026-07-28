"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode
} from "react";
import { APIError, apiFetch } from "@/lib/api";

export type UserRole = "traveler" | "host" | "creator" | "admin";
export type UserStatus = "active" | "inactive" | "banned";
export type CreatorStatus = "none" | "pending" | "verified" | "rejected";

export type CurrentUser = {
  id: number;
  email: string;
  fullName: string;
  role: UserRole;
  status: UserStatus;
  avatarUrl: string | null;
  bio: string | null;
  travelPreferences: string[];
  creatorStatus: CreatorStatus;
  creatorPortfolioUrls: string[];
  createdAt: string;
};

type ProfileInput = {
  fullName?: string;
  avatarUrl?: string | null;
  bio?: string | null;
  travelPreferences?: string[];
};

type AuthContextValue = {
  user: CurrentUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (fullName: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (input: ProfileInput) => Promise<CurrentUser>;
  submitCreatorApplication: (bio: string, portfolioUrls: string[]) => Promise<CurrentUser>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  const loadUser = useCallback(async () => {
    try {
      setUser(await apiFetch<CurrentUser>("/me"));
    } catch (error) {
      if (!(error instanceof APIError) || ![401, 403].includes(error.status)) throw error;
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadUser();
  }, [loadUser]);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    async login(email, password) {
      const response = await apiFetch<{ user: CurrentUser }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password })
      }, false);
      setUser(response.user);
    },
    async register(fullName, email, password) {
      const response = await apiFetch<{ user: CurrentUser }>("/auth/register", {
        method: "POST",
        body: JSON.stringify({ fullName, email, password })
      }, false);
      setUser(response.user);
    },
    async logout() {
      await apiFetch<void>("/auth/logout", { method: "POST" }, false);
      setUser(null);
    },
    async updateProfile(input) {
      const updated = await apiFetch<CurrentUser>("/me/profile", {
        method: "PATCH",
        body: JSON.stringify(input)
      });
      setUser(updated);
      return updated;
    },
    async submitCreatorApplication(bio, portfolioUrls) {
      const updated = await apiFetch<CurrentUser>("/me/creator-application", {
        method: "POST",
        body: JSON.stringify({ bio, portfolioUrls })
      });
      setUser(updated);
      return updated;
    }
  }), [loading, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
