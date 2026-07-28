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
            <span>V</span>
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
            <Link className="newTrip" href="/planner">
              <span>✦</span>Tạo chuyến đi
            </Link>
            {!loading && !user ? (
              <Link className="accountLink" href="/login">
                Đăng nhập
              </Link>
            ) : null}
            {!loading && user ? (
              <>
                <Link aria-label={`Hồ sơ của ${user.fullName}`} className="accountLink signedIn" href="/profile">
                  <span>{user.fullName.charAt(0).toUpperCase()}</span>
                  <strong>{user.fullName}</strong>
                </Link>
                <button className="logoutButton" onClick={() => void logout()} type="button">
                  Đăng xuất
                </button>
              </>
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
