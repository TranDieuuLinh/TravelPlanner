"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AdminUser, listRuns, logout } from "../../lib/api";

export default function DashboardLayout({
  children
}: {
  children: React.ReactNode;
}) {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [user, setUser] = useState<AdminUser | null>(null);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    // A quick way to verify if we are logged in
    listRuns({ limit: 1 })
      .then(() => {
        // Assume logged in if it succeeds
        // We don't get the user info from listRuns directly in the old code either
        setAuthenticated(true);
      })
      .catch(() => {
        setAuthenticated(false);
        router.push("/login");
      });
  }, [router]);

  if (authenticated === null) {
    return (
      <main className="bootScreen">
        <div className="bootMark">TravelPlanner</div>
        <p>Đang xác thực Planning Control…</p>
      </main>
    );
  }

  if (!authenticated) {
    return null; // Will redirect
  }

  async function signOut() {
    try {
      await logout();
    } finally {
      router.push("/login");
    }
  }

  return (
    <main className="appShell">
      <header className="topbarNav" role="banner">
        <Link href="/runs" className="topbarNavBrand" aria-label="TravelPlanner home">
          <span className="topbarNavBrandMark">TP</span>
          <div>
            <b>TravelPlanner</b>
            <small>Planning control</small>
          </div>
        </Link>
        <nav className="topbarNavLinks" aria-label="Primary">
          <Link
            href="/runs"
            className={pathname === "/runs" ? "active" : ""}
            title="Planning runs"
          >
            <span aria-hidden="true">⌁</span>
            <span>Planning runs</span>
          </Link>
          <Link
            href="/golden"
            className={pathname === "/golden" ? "active" : ""}
            title="Golden dataset"
          >
            <span aria-hidden="true">◇</span>
            <span>Golden dataset</span>
          </Link>
          <Link
            href="/knowledge-graph"
            className={pathname === "/knowledge-graph" ? "active" : ""}
            title="Knowledge Graph"
          >
            <span aria-hidden="true">⌘</span>
            <span>Knowledge Graph</span>
          </Link>
          <Link
            href="/tools"
            className={pathname === "/tools" ? "active" : ""}
            title="Tools Tester"
          >
            <span aria-hidden="true">⌂</span>
            <span>Tools Tester</span>
          </Link>
        </nav>
        <div className="topbarNavUser">
          <div className="adminAvatar" aria-hidden="true">
            {user?.fullName?.slice(0, 1) ?? "A"}
          </div>
          <div className="topbarNavUserInfo">
            <b>{user?.fullName ?? "TravelPlanner Admin"}</b>
            <small>{user?.email ?? "Authenticated session"}</small>
          </div>
          <button
            type="button"
            className="topbarNavSignout"
            onClick={signOut}
            aria-label="Đăng xuất"
            title="Đăng xuất"
          >
            ↗
          </button>
        </div>
      </header>
      <section className="workspace">{children}</section>
    </main>
  );
}
