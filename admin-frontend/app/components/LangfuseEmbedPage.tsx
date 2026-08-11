"use client";

import { LangfuseConsole, LangfuseNav } from "../features/observability/components";
import type { LangfusePage } from "../features/observability/lib";

type Props = {
  page: LangfusePage;
  pathPrefix: string;
};

export function LangfuseEmbedPage({ page, pathPrefix }: Props) {
  return (
    <section className="langfusePage">
      <header className="topbar">
        <div>
          <p className="eyebrow">Langfuse API</p>
          <h1>Observability console</h1>
          <p className="langfuseLead">
            Theo dõi trace, observation và session của agent qua backend proxy. Màn
            hình này dùng chung phiên admin TravelPlanner, không cần đăng nhập lại.
          </p>
        </div>
      </header>
      <LangfuseNav activePage={page} pathPrefix={pathPrefix} />
      <LangfuseConsole page={page} />
    </section>
  );
}
