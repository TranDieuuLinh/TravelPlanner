"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { logout, type AdminUser } from "../../lib/shared/auth";

type NavLink = {
  href: string;
  label: string;
  icon: string;
  description: string;
  external?: boolean;
};

const KNOWLEDGE_GRAPH_ENABLED = process.env.NEXT_PUBLIC_KNOWLEDGE_GRAPH_ENABLED !== "false";

const NAV_LINKS: NavLink[] = [
  {
    href: "/observability",
    label: "Observability",
    icon: "⌁",
    description: "Langfuse traces, sessions, playground"
  },
  {
    href: "/knowledge-graph",
    label: "Knowledge Graph",
    icon: "⌘",
    description: "Catalog entity, alias và relationship"
  },
  {
    href: "/knowledge-graph/auto-attach",
    label: "Auto Attach",
    icon: "AA",
    description: "Manage Style keyword attachment rules"
  }
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/observability") {
    return pathname === "/observability" || pathname.startsWith("/observability/");
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

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
    fetch("/api/admin-session", {
      credentials: "include"
    })
      .then((response) => {
        if (!response.ok) {
          setAuthenticated(false);
          router.push("/login");
          return null;
        }
        return response.json();
      })
      .then((payload: AdminUser | null) => {
        if (!payload) return;
        if (payload.role !== "admin") {
          setAuthenticated(false);
          router.push("/login");
          return;
        }
        setUser(payload);
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
    return null;
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
        <Link href="/observability" className="topbarNavBrand" aria-label="TravelPlanner home">
          <span className="topbarNavBrandMark">TP</span>
          <div>
            <b>TravelPlanner</b>
            <small>Planning control</small>
          </div>
        </Link>
        <nav className="topbarNavLinks" aria-label="Primary">
          {NAV_LINKS.filter((link) => KNOWLEDGE_GRAPH_ENABLED || link.href !== "/knowledge-graph").map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={isActive(pathname ?? "", link.href) ? "active" : ""}
              title={link.description}
            >
              <span aria-hidden="true">{link.icon}</span>
              <span>{link.label}</span>
            </Link>
          ))}
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
