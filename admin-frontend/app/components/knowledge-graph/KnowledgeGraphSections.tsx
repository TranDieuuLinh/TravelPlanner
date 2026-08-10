"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

const KG_COLLAPSED_SECTIONS_STORAGE_KEY = "vsf.admin.kg.section.collapsed";

// Inspector section IDs that are collapsed by default when no persisted
// preference exists yet. Users can still expand individually; their choice is
// then stored in localStorage and reused on subsequent visits.
export const KG_DEFAULT_COLLAPSED_SECTIONS: readonly string[] = [
  "information",
  "aliases",
  "properties",
  "relationships",
];

// Property pagination is disabled in the inspector; we always ask the backend
// for the full set so editors can see every property without paging. The
// backend cap is set to KG_DETAIL_PROPERTY_FETCH_LIMIT.
export const KG_DETAIL_PROPERTY_FETCH_LIMIT = 500;

type CollapsedSectionsState = {
  collapsed: ReadonlySet<string>;
  isCollapsed: (sectionId: string) => boolean;
  toggle: (sectionId: string) => void;
};

export function useCollapsedSections(defaultCollapsed: readonly string[] = []): CollapsedSectionsState {
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set(defaultCollapsed));
  const hydratedRef = useRef(false);

  // Restore persisted collapse state once on mount.
  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    try {
      const raw = window.localStorage.getItem(KG_COLLAPSED_SECTIONS_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          setCollapsed(new Set(parsed.filter((value): value is string => typeof value === "string")));
        }
      }
    } catch {
      // ignore malformed storage entry
    }
    hydratedRef.current = true;
  }, []);

  // Persist collapse state whenever it changes (skip the initial render before hydration).
  useEffect(() => {
    if (!hydratedRef.current || typeof window === "undefined") {
      return;
    }
    try {
      window.localStorage.setItem(
        KG_COLLAPSED_SECTIONS_STORAGE_KEY,
        JSON.stringify(Array.from(collapsed))
      );
    } catch {
      // ignore storage failures (e.g. quota, private mode)
    }
  }, [collapsed]);

  const isCollapsed = useCallback((sectionId: string) => collapsed.has(sectionId), [collapsed]);

  const toggle = useCallback((sectionId: string) => {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(sectionId)) {
        next.delete(sectionId);
      } else {
        next.add(sectionId);
      }
      return next;
    });
  }, []);

  return { collapsed, isCollapsed, toggle };
}

export function InspectorSection({
  sectionId,
  title,
  count,
  headerExtras,
  isCollapsed,
  onToggle,
  children,
}: {
  sectionId: string;
  title: string;
  count?: number;
  headerExtras?: ReactNode;
  isCollapsed: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <section
      className={`kgInspectorSection${isCollapsed ? " kgInspectorSectionCollapsed" : ""}`}
      data-section-id={sectionId}
    >
      <header className="kgSectionHeaderActions">
        <button
          type="button"
          className="kgSectionToggle"
          onClick={onToggle}
          aria-expanded={!isCollapsed}
          aria-label={isCollapsed ? `Expand ${title} section` : `Collapse ${title} section`}
          title={isCollapsed ? `Expand ${title}` : `Collapse ${title}`}
        >
          <span className={`kgSectionChevron${isCollapsed ? " kgSectionChevronCollapsed" : ""}`} aria-hidden="true">
            ▾
          </span>
          <h3>{title}</h3>
          {typeof count === "number" && <span className="kgSectionCount">{count}</span>}
        </button>
        {headerExtras}
      </header>
      {children}
    </section>
  );
}

// Force-graph 2D visualization for an entity's direct relationships.
// Lazy-loaded with ssr:false because the underlying library touches `window`
// at module load time.
