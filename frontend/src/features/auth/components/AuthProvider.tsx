"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode
} from "react";
import { authLoadFailureAction } from "@/features/auth/lib/session-recovery";
import { APIError, apiFetch } from "@/shared/api/client";

const SESSION_RETRY_DELAY_MS = 3_000;
const SESSION_REQUEST_TIMEOUT_MS = 5_000;

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
  sessionUnavailable: boolean;
  login: (email: string, password: string) => Promise<CurrentUser>;
  register: (fullName: string, email: string, password: string) => Promise<CurrentUser>;
  logout: () => Promise<void>;
  updateProfile: (input: ProfileInput) => Promise<CurrentUser>;
  submitCreatorApplication: (bio: string, portfolioUrls: string[]) => Promise<CurrentUser>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionUnavailable, setSessionUnavailable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let requestController: AbortController | undefined;

    const scheduleRetry = () => {
      if (cancelled || retryTimer) return;
      retryTimer = setTimeout(() => {
        retryTimer = undefined;
        void loadUser();
      }, SESSION_RETRY_DELAY_MS);
    };

    const loadUser = async () => {
      requestController?.abort();
      const controller = new AbortController();
      requestController = controller;
      const timeout = setTimeout(
        () => controller.abort(),
        SESSION_REQUEST_TIMEOUT_MS
      );
      try {
        const currentUser = await apiFetch<CurrentUser>("/me", {
          signal: controller.signal,
        });
        if (cancelled) return;
        setUser(currentUser);
        setSessionUnavailable(false);
        setLoading(false);
      } catch (error) {
        if (cancelled) return;
        const action = authLoadFailureAction(
          error instanceof APIError ? error.status : undefined
        );
        if (action === "retry") {
          setSessionUnavailable(true);
          setLoading(false);
          scheduleRetry();
          return;
        }
        if (action === "clear-session") {
          setUser(null);
          setSessionUnavailable(false);
          setLoading(false);
          return;
        }
        setLoading(false);
        throw error;
      } finally {
        clearTimeout(timeout);
        if (requestController === controller) requestController = undefined;
      }
    };

    const retryNow = () => {
      if (retryTimer) {
        clearTimeout(retryTimer);
        retryTimer = undefined;
      }
      void loadUser();
    };

    window.addEventListener("online", retryNow);
    void loadUser();

    return () => {
      cancelled = true;
      requestController?.abort();
      if (retryTimer) clearTimeout(retryTimer);
      window.removeEventListener("online", retryNow);
    };
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    sessionUnavailable,
    async login(email, password) {
      const response = await apiFetch<{ user: CurrentUser }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password })
      }, false);
      setUser(response.user);
      return response.user;
    },
    async register(fullName, email, password) {
      const response = await apiFetch<{ user: CurrentUser }>("/auth/register", {
        method: "POST",
        body: JSON.stringify({ fullName, email, password })
      }, false);
      setUser(response.user);
      return response.user;
    },
    async logout() {
      try {
        await apiFetch<void>("/auth/logout", { method: "POST" }, false);
      } finally {
        setUser(null);
      }
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
  }), [loading, sessionUnavailable, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
