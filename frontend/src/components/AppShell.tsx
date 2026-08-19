"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useAuth } from "@/features/auth/components/AuthProvider";

const BackgroundUrlJobs = dynamic(
  () => import("@/features/planner/components/BackgroundUrlJobs").then(
    (module) => module.BackgroundUrlJobs
  ),
  { ssr: false }
);
const GlobalPlannerAssistant = dynamic(
  () => import("@/features/planner/components/GlobalPlannerAssistant").then(
    (module) => module.GlobalPlannerAssistant
  ),
  { ssr: false }
);

type NavItem = {
  href: string;
  label: string;
};

function MobileNavIcon({ href }: Pick<NavItem, "href">) {
  if (href === "/reels" || href === "/explore") {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="8.5" />
        <path d="m14.9 9.1-1.7 4.1-4.1 1.7 1.7-4.1 4.1-1.7Z" />
      </svg>
    );
  }

  if (href === "/planner") {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M12 3.5c.5 3.1 2.4 5 5.5 5.5-3.1.5-5 2.4-5.5 5.5-.5-3.1-2.4-5-5.5-5.5 3.1-.5 5-2.4 5.5-5.5Z" />
        <path d="M18.2 14.8c.2 1.5 1.1 2.4 2.6 2.6-1.5.2-2.4 1.1-2.6 2.6-.2-1.5-1.1-2.4-2.6-2.6 1.5-.2 2.4-1.1 2.6-2.6Z" />
      </svg>
    );
  }

  if (href.startsWith("/creator")) {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M4.5 9.5h15v10h-15zM3.5 9.5l1.4-5h14.2l1.4 5" />
        <path d="M9.5 19.5v-5h5v5M3.5 9.5c0 1.4 1.1 2.5 2.5 2.5s2.5-1.1 2.5-2.5c0 1.4 1.1 2.5 2.5 2.5s2.5-1.1 2.5-2.5c0 1.4 1.1 2.5 2.5 2.5s2.5-1.1 2.5-2.5" />
      </svg>
    );
  }

  if (href.startsWith("/admin")) {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M12 3.5 19 6v5.2c0 4.3-2.8 7.6-7 9.3-4.2-1.7-7-5-7-9.3V6l7-2.5Z" />
        <path d="m8.8 12 2.1 2.1 4.4-4.4" />
      </svg>
    );
  }

  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5.5 20c.4-4 2.7-6 6.5-6s6.1 2 6.5 6" />
    </svg>
  );
}

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
            <Link aria-label="TravelPlanner" className="brand" href={landingRoute ? "/" : "/reels"}>
              <h2>
                <span>Travel</span>Planner
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
            <span className="mobileItemIcon">
              <MobileNavIcon href={item.href} />
            </span>
            <span className="mobileItemLabel">{item.label}</span>
          </Link>
        ))}
      </nav>
    </>
  );
}
