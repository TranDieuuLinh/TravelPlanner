"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LANGFUSE_PAGES, type LangfusePage } from "../lib/langfuse-config";

type Props = {
  activePage: LangfusePage;
  pathPrefix: string;
};

export function LangfuseNav({ activePage, pathPrefix }: Props) {
  const pathname = usePathname();

  return (
    <nav className="langfuseNav" aria-label="Langfuse sections">
      {LANGFUSE_PAGES.map((page) => {
        const href = `${pathPrefix}/${page.id}`;
        const isActive = activePage === page.id;
        return (
          <Link
            key={page.id}
            href={href}
            className={`langfuseNavLink${isActive ? " active" : ""}`}
            aria-current={isActive ? "page" : undefined}
            data-active={pathname === href}
          >
            <b>{page.label}</b>
            <small>{page.description}</small>
          </Link>
        );
      })}
    </nav>
  );
}