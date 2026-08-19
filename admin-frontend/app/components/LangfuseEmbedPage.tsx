"use client";

import { LangfuseConsole, LangfuseNav } from "../features/observability/components";
import type { LangfusePage } from "../features/observability/lib";

export function LangfuseEmbedPage({ page, pathPrefix }: { page: LangfusePage; pathPrefix: string }) {
  return <section className="langfusePage"><header className="topbar"><div><p className="eyebrow">TravelPlanner backend</p><h1>Observability</h1><p className="langfuseLead">Đọc request, lỗi, thời gian chạy và input/output của tool trong console nhẹ tích hợp sẵn.</p></div></header><LangfuseNav activePage={page} pathPrefix={pathPrefix} /><LangfuseConsole page={page} /></section>;
}
