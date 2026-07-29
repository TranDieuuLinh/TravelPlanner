"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useAuth } from "@/components/AuthProvider";

const nav = [
  { href: "/explore", label: "Khám phá", icon: "⌕" },
  { href: "/planner", label: "AI Planner", icon: "✦" },
  { href: "/profile", label: "Hồ sơ", icon: "○" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { loading, logout, user } = useAuth();

  const dynamicNav = [...nav];
  if (user?.role === "creator") {
    dynamicNav.splice(2, 0, { href: "/creator/listings", label: "Creator Studio", icon: "✎" });
  } else if (user?.role === "admin") {
    dynamicNav.splice(2, 0, { href: "/admin/listings", label: "Admin Duyệt", icon: "✓" });
  }

  const mobileNav = dynamicNav.map((item) =>
    item.href === "/profile" && !user ? { ...item, href: "/login", label: "Đăng nhập" } : item
  );

  return (
    <>
      <header className="topbar">
        <div className="topbarInner">
          <Link aria-label="VSF Travel" className="brand" href="/explore">
            <span aria-hidden="true" className="brandPenguin" />
            <strong>VSF Travel</strong>
          </Link>
          <nav aria-label="Điều hướng chính" className="desktopNav">
            {dynamicNav.map((item) => (
              <Link
                className={pathname.startsWith(item.href) ? "navItem active" : "navItem"}
                href={item.href}
                key={item.href}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="shellActions">
            {!loading && !user ? (
              <Link className="accountLink" href="/login">
                Đăng nhập
              </Link>
            ) : null}
            {!loading && user ? (
              <div className="accountMenu">
                <Link aria-label={`Hồ sơ của ${user.fullName}`} className="accountLink signedIn" href="/profile">
                  <span className="shellAccountAvatar">{user.fullName.charAt(0).toUpperCase()}</span>
                  <span className="accountCopy">
                    <strong>{user.fullName}</strong>
                  </span>
                </Link>
                <button aria-label="Đăng xuất" className="logoutButton" onClick={() => void logout()} title="Đăng xuất" type="button">
                  <svg aria-hidden="true" viewBox="0 0 24 24">
                    <path d="M14.25 8.25V5.5A2.5 2.5 0 0 0 11.75 3h-5.5a2.5 2.5 0 0 0-2.5 2.5v13a2.5 2.5 0 0 0 2.5 2.5h5.5a2.5 2.5 0 0 0 2.5-2.5v-2.75M10 12h10.25m0 0-3.5-3.5m3.5 3.5-3.5 3.5" />
                  </svg>
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>
      <div className="appBody">{children}</div>
      <nav aria-label="Điều hướng di động" className="mobileNav">
        {mobileNav.map((item) => (
          <Link
            className={pathname.startsWith(item.href) ? "mobileItem active" : "mobileItem"}
            href={item.href}
            key={item.href}
          >
            <span>{item.icon}</span>
            {item.label}
          </Link>
        ))}
      </nav>
    </>
  );
}
