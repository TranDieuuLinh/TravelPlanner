"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useAuth } from "@/components/AuthProvider";
import { BackgroundUrlJobs } from "@/components/BackgroundUrlJobs";
import { GlobalPlannerAssistant } from "@/components/GlobalPlannerAssistant";

type NavItem = {
  href: string;
  label: string;
};

const nav: NavItem[] = [
  { href: "/reels", label: "Khám phá" },
  { href: "/planner", label: "AI Planner" },
  { href: "/profile", label: "Hồ sơ" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { loading, logout, user } = useAuth();
  const landingRoute = pathname === "/";
  const plannerRoute = pathname.startsWith("/planner");

  const dynamicNav = landingRoute
    ? [
        { href: "#how-it-works", label: "Cách hoạt động" },
        { href: "/explore", label: "Khám phá" },
        { href: "#for-creators", label: "Dành cho creator" },
      ]
    : [...nav];
  if (!landingRoute && user?.role === "creator") {
    dynamicNav.splice(1, 0, { href: "/creator/listings", label: "Creator Studio" });
  } else if (!landingRoute && user?.role === "admin") {
    dynamicNav.splice(1, 0, { href: "/admin/listings", label: "Admin Duyệt" });
  }

  const mobileNav = dynamicNav.map((item) =>
    item.href === "/profile" && !user ? { ...item, href: "/login", label: "Đăng nhập" } : item
  );

  return (
    <>
      <a className="skipLink" href="#main-content">Bỏ qua điều hướng</a>
      <header className={landingRoute ? "topbar is-landing" : plannerRoute ? "topbar is-planner" : "topbar"}>
        <div className="topbarInner">
          <div className="brandCluster">
            <Link aria-label="VSF Travel" className="brand" href={landingRoute ? "/" : "/reels"}>
              <h2>
                <span>VSF</span> Travel
              </h2>
            </Link>
          </div>
          <div className="shellActions">
            <nav aria-label="Điều hướng chính" className="desktopNav">
              {dynamicNav.map((item) => (
                <Link
                  aria-current={pathname.startsWith(item.href) ? "page" : undefined}
                  className={pathname.startsWith(item.href) ? "navItem active" : "navItem"}
                  href={item.href}
                  key={item.href}
                >
                  <span>{item.label}</span>
                </Link>
              ))}
            </nav>
            <BackgroundUrlJobs authenticated={Boolean(user)} enabled={!loading} />
            {landingRoute ? (
              <div className="landingHeaderActions">
                {!loading && !user ? (
                  <Link className="accountLink" href="/login">
                    Đăng nhập
                  </Link>
                ) : null}
                <Link className="landingHeaderCta" href={user ? "/planner" : "/login?next=%2Fplanner"}>
                  {user ? "Mở Planner" : "Lên lịch trình"}
                </Link>
                {!loading && user ? (
                  <details className="accountMenu">
                    <summary aria-label={`Mở menu tài khoản của ${user.fullName}`} className="accountMenuTrigger">
                      <span className="shellAccountAvatar">{user.fullName.charAt(0).toUpperCase()}</span>
                      <svg aria-hidden="true" className="accountMenuChevron" viewBox="0 0 24 24">
                        <path d="m8 10 4 4 4-4" />
                      </svg>
                    </summary>
                    <div className="accountMenuPopover">
                      <div className="accountMenuIdentity">
                        <span className="shellAccountAvatar">{user.fullName.charAt(0).toUpperCase()}</span>
                        <strong>{user.fullName}</strong>
                      </div>
                      <Link className="accountMenuItem" href="/profile">
                        Hồ sơ
                      </Link>
                      <button className="accountMenuItem accountMenuLogout" onClick={() => void logout()} type="button">
                        <span>Đăng xuất</span>
                        <svg aria-hidden="true" viewBox="0 0 24 24">
                          <path d="M14.25 8.25V5.5A2.5 2.5 0 0 0 11.75 3h-5.5a2.5 2.5 0 0 0-2.5 2.5v13a2.5 2.5 0 0 0 2.5 2.5h5.5a2.5 2.5 0 0 0 2.5-2.5v-2.75M10 12h10.25m0 0-3.5-3.5m3.5 3.5-3.5 3.5" />
                        </svg>
                      </button>
                    </div>
                  </details>
                ) : null}
              </div>
            ) : null}
            {!landingRoute && !loading && !user ? (
              <Link className="accountLink" href="/login">
                Đăng nhập
              </Link>
            ) : null}
            {!landingRoute && !loading && user ? (
              <details className="accountMenu">
                <summary aria-label={`Mở menu tài khoản của ${user.fullName}`} className="accountMenuTrigger">
                  <span className="shellAccountAvatar">{user.fullName.charAt(0).toUpperCase()}</span>
                  <svg aria-hidden="true" className="accountMenuChevron" viewBox="0 0 24 24">
                    <path d="m8 10 4 4 4-4" />
                  </svg>
                </summary>
                <div className="accountMenuPopover">
                  <div className="accountMenuIdentity">
                    <span className="shellAccountAvatar">{user.fullName.charAt(0).toUpperCase()}</span>
                    <strong>{user.fullName}</strong>
                  </div>
                  <Link className="accountMenuItem" href="/profile">
                    Hồ sơ
                  </Link>
                  <button className="accountMenuItem accountMenuLogout" onClick={() => void logout()} type="button">
                    <span>Đăng xuất</span>
                    <svg aria-hidden="true" viewBox="0 0 24 24">
                      <path d="M14.25 8.25V5.5A2.5 2.5 0 0 0 11.75 3h-5.5a2.5 2.5 0 0 0-2.5 2.5v13a2.5 2.5 0 0 0 2.5 2.5h5.5a2.5 2.5 0 0 0 2.5-2.5v-2.75M10 12h10.25m0 0-3.5-3.5m3.5 3.5-3.5 3.5" />
                    </svg>
                  </button>
                </div>
              </details>
            ) : null}
          </div>
        </div>
      </header>
      <div className="appBody" id="main-content">{children}</div>
      <GlobalPlannerAssistant />
      <nav aria-label="Điều hướng di động" className={landingRoute ? "mobileNav landingMobileNav" : "mobileNav"}>
        {mobileNav.map((item) => (
          <Link
            aria-current={pathname.startsWith(item.href) ? "page" : undefined}
            className={pathname.startsWith(item.href) ? "mobileItem active" : "mobileItem"}
            href={item.href}
            key={item.href}
          >
            <span className="mobileItemLabel">{item.label}</span>
          </Link>
        ))}
      </nav>
    </>
  );
}
