import { LangfuseNav, TraceDetailPage } from "../../../../features/observability/components";

export default function ObservabilityTraceDetailPage() {
  return (
    <section className="langfusePage">
      <header className="topbar"><div><p className="eyebrow">TravelPlanner backend</p><h1>Observability</h1><p className="langfuseLead">Một request, các module và tool/provider spans thuộc riêng request đó.</p></div></header>
      <LangfuseNav activePage="traces" pathPrefix="/observability" />
      <TraceDetailPage />
    </section>
  );
}
