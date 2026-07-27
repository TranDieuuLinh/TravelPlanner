"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const nav = [
  { href: "/explore", label: "Khám phá", icon: "⌕" },
  { href: "/planner", label: "AI Planner", icon: "✦" },
  { href: "/profile", label: "Hồ sơ", icon: "○" }
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <>
      <header className="topbar">
        <div className="topbarInner">
          <Link className="brand" href="/explore" aria-label="VSF Travel">
            <span>V</span>
            <strong>VSF Travel</strong>
          </Link>
          <nav className="desktopNav" aria-label="Điều hướng chính">
            {nav.map((item) => (
              <Link className={pathname.startsWith(item.href) ? "navItem active" : "navItem"} href={item.href} key={item.href}>
                {item.label}
              </Link>
            ))}
          </nav>
          <Link className="newTrip" href="/planner"><span>✦</span>Tạo chuyến đi</Link>
        </div>
      </header>
      <div className="appBody">{children}</div>
      <nav className="mobileNav" aria-label="Điều hướng di động">
        {nav.map((item) => (
          <Link className={pathname.startsWith(item.href) ? "mobileItem active" : "mobileItem"} href={item.href} key={item.href}>
            <span>{item.icon}</span>{item.label}
          </Link>
        ))}
      </nav>
    </>
  );
}
