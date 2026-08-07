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
      <aside className="sidebar">
        <div className="sidebarBrand">
          <span>TravelPlanner</span>
          <div>
            <b>Planning</b>
            <small>Control room</small>
          </div>
        </div>
        <nav>
          <Link href="/runs" className={pathname === "/runs" ? "active" : ""}>
            <span>⌁</span> Planning runs
          </Link>
          <Link href="/golden" className={pathname === "/golden" ? "active" : ""}>
            <span>◇</span> Golden dataset
          </Link>
          <Link
            href="/knowledge-graph"
            className={pathname === "/knowledge-graph" ? "active" : ""}
          >
            <span>⌘</span> Knowledge Graph
          </Link>
          <Link href="/tools" className={pathname === "/tools" ? "active" : ""}>
            <span>⌂</span> Tools Tester
          </Link>
        </nav>
        <div className="sidebarFoot">
          <div className="adminAvatar">{user?.fullName?.slice(0, 1) ?? "A"}</div>
          <div>
            <b>{user?.fullName ?? "TravelPlanner Admin"}</b>
            <small>{user?.email ?? "Authenticated session"}</small>
          </div>
          <button type="button" onClick={signOut} aria-label="Đăng xuất">
            ↗
          </button>
        </div>
      </aside>
      <section className="workspace">
        {children}
      </section>
    </main>
  );
}
