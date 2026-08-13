"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getLangfuseRecords,
  getLangfuseStatus,
  getTrace,
  type LangfusePageResponse,
  type LangfuseRecord,
  type LangfuseResource,
  type LangfuseStatus
} from "../lib/langfuse-api";
import type { LangfusePage } from "../lib/langfuse-config";

const RESOURCE_BY_PAGE: Partial<Record<LangfusePage, LangfuseResource>> = {
  traces: "traces",
  observations: "observations",
  sessions: "sessions"
};

const COLUMNS: Record<LangfuseResource, { label: string; keys: string[]; timestamp?: boolean }[]> = {
  traces: [
    { label: "Request", keys: ["id"] },
    { label: "Route", keys: ["route"] },
    { label: "Status", keys: ["status"] },
    { label: "Duration", keys: ["durationMs"] },
    { label: "Started", keys: ["startedAt"], timestamp: true },
    { label: "Error", keys: ["errorCode"] }
  ],
  observations: [
    { label: "Step", keys: ["name"] },
    { label: "Kind", keys: ["kind"] },
    { label: "Status", keys: ["status"] },
    { label: "Duration", keys: ["durationMs"] },
    { label: "Input", keys: ["inputPreview"] },
    { label: "Output", keys: ["outputPreview"] },
    { label: "Started", keys: ["startTime"], timestamp: true }
  ],
  sessions: [
    { label: "Thread", keys: ["id"] },
    { label: "Requests", keys: ["traceCount"] },
    { label: "Errors", keys: ["errorCount"] },
    { label: "First request", keys: ["firstTimestamp"], timestamp: true },
    { label: "Last request", keys: ["lastTimestamp"], timestamp: true }
  ]
};

function valueOf(record: LangfuseRecord, keys: string[]): string {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" || typeof value === "number") return String(value);
    if (typeof value === "boolean") return value ? "Yes" : "No";
  }
  return "—";
}

function display(value: string, timestamp = false): string {
  if (!timestamp || value === "—") return value;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("vi-VN");
}

function Preview({ value, open = false }: { value: string; open?: boolean }) {
  if (value === "—") return <span className="localNoPayload">—</span>;
  return (
    <details className="localPreview" open={open}>
      <summary>{value.slice(0, 72)}{value.length > 72 ? "…" : ""}</summary>
      <pre>{value}</pre>
    </details>
  );
}

function payloadSummary(value: string): string {
  if (value === "—") return "Không có dữ liệu";
  try {
    const payload = JSON.parse(value) as unknown;
    if (Array.isArray(payload)) return `${payload.length} phần tử`;
    if (payload && typeof payload === "object") {
      const record = payload as Record<string, unknown>;
      const content = record.content ?? record.response ?? record.message;
      const details: string[] = [];
      if (typeof content === "string" && content) details.push(content);
      if (typeof record.route === "string") details.push(`route: ${record.route}`);
      if (Array.isArray(record.warnings)) details.push(`${record.warnings.length} warning`);
      if (Array.isArray(record.sources)) details.push(`${record.sources.length} source`);
      if (details.length) return details.join(" · ");
      return `${Object.keys(record).length} trường: ${Object.keys(record).slice(0, 5).join(", ")}`;
    }
    return String(payload);
  } catch {
    return value.length > 180 ? `${value.slice(0, 180)}…` : value;
  }
}

function SummaryPayload({ value }: { value: string }) {
  const [open, setOpen] = useState(false);
  if (value === "—") return <span className="localNoPayload">—</span>;
  return <div className="localPreview"><div className="localPayloadSummary">{payloadSummary(value)}</div><button type="button" className="localRawToggle" onClick={() => setOpen((current) => !current)}>{open ? "Ẩn JSON" : "Xem JSON"}</button>{open && <pre>{value}</pre>}</div>;
}

function RecordsTable({
  resource,
  page,
  onTraceClick
}: {
  resource: LangfuseResource;
  page: LangfusePageResponse;
  onTraceClick?: (id: string) => void;
}) {
  if (!page.items.length) return <div className="langfuseEmpty">Chưa có bản ghi trong bộ nhớ backend.</div>;
  return (
    <div className="langfuseTableWrap">
      <table className="langfuseTable">
        <thead><tr>{COLUMNS[resource].map((column) => <th key={column.label}>{column.label}</th>)}</tr></thead>
        <tbody>
          {page.items.map((record, index) => {
            const id = valueOf(record, ["id"]);
            return (
              <tr key={`${id}-${index}`} className={onTraceClick ? "localClickableRow" : undefined} onClick={() => onTraceClick?.(id)}>
                {COLUMNS[resource].map((column) => (
                  <td key={column.label}>
                    {column.label === "Status" ? <span className={`localStatus localStatus-${valueOf(record, column.keys)}`}>{valueOf(record, column.keys)}</span> : column.label === "Input" || column.label === "Output" ? <SummaryPayload value={valueOf(record, column.keys)} /> : display(valueOf(record, column.keys), column.timestamp)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function PayloadCard({ label, value }: { label: string; value: string }) {
  return <div className="localPayloadCard"><b>{label}</b><SummaryPayload value={value} /></div>;
}

function TraceDetail({ trace, onClose }: { trace: LangfuseRecord; onClose: () => void }) {
  const observations = Array.isArray(trace.observations) ? trace.observations as LangfuseRecord[] : [];
  return (
    <aside className="localTraceDetail">
      <header>
        <div><p className="eyebrow">Request detail</p><h3>{valueOf(trace, ["id"])}</h3></div>
        <button type="button" className="langfuseFrameReload" onClick={onClose}>Đóng</button>
      </header>
      <div className="localDetailGrid">
        <span>Route<strong>{valueOf(trace, ["route"])}</strong></span>
        <span>Status<strong>{valueOf(trace, ["status"])}</strong></span>
        <span>Duration<strong>{valueOf(trace, ["durationMs"])} ms</strong></span>
        <span>Error<strong>{valueOf(trace, ["errorCode"])}</strong></span>
        <span>Thread<strong>{valueOf(trace, ["threadId"])}</strong></span>
        <span>Started<strong>{display(valueOf(trace, ["startedAt"]), true)}</strong></span>
      </div>
      <div className="localPayloadGrid">
        <PayloadCard label="Request input" value={valueOf(trace, ["inputPreview"])} />
        <PayloadCard label="Response output" value={valueOf(trace, ["outputPreview"])} />
      </div>
      <h4>Timeline ({observations.length} steps)</h4>
      <div className="localTimeline">
        {observations.length === 0 && <p className="langfuseEmpty">Request này không có step chi tiết.</p>}
        {observations.map((observation) => (
          <article className="localTimelineItem" key={valueOf(observation, ["id"])}>
            <div className="localTimelineHeading"><b>{valueOf(observation, ["name"])}</b><span>{valueOf(observation, ["kind"])} · {valueOf(observation, ["durationMs"])} ms</span></div>
            <span className={`localStatus localStatus-${valueOf(observation, ["status"])}`}>{valueOf(observation, ["status"])}</span>
            <div className="localStepPayload"><PayloadCard label="Input" value={valueOf(observation, ["inputPreview"])} /><PayloadCard label="Output" value={valueOf(observation, ["outputPreview"])} /></div>
            {valueOf(observation, ["error"]) !== "—" && <label>Error<code>{valueOf(observation, ["error"])}</code></label>}
          </article>
        ))}
      </div>
    </aside>
  );
}

function RecordList({ resource }: { resource: LangfuseResource }) {
  const [data, setData] = useState<LangfusePageResponse | null>(null);
  const [selected, setSelected] = useState<LangfuseRecord | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [pageNumber, setPageNumber] = useState(1);
  const load = useCallback(async () => { setLoading(true); setError(""); try { setData(await getLangfuseRecords(resource, pageNumber)); } catch (caught) { setError(caught instanceof Error ? caught.message : "Không tải được log."); } finally { setLoading(false); } }, [pageNumber, resource]);
  const openTrace = useCallback(async (id: string) => { try { setSelected(await getTrace(id)); } catch (caught) { setError(caught instanceof Error ? caught.message : "Không tải được chi tiết request."); } }, []);
  useEffect(() => { void load(); }, [load]);
  return (
    <section className="langfuseDataPanel">
      <header className="langfusePanelHeader"><div><p className="eyebrow">Local diagnostics</p><h2>{resource === "traces" ? "Requests" : resource === "observations" ? "Steps" : "Threads"}</h2></div><button type="button" className="langfuseFrameReload" onClick={() => void load()}>↻ Tải lại</button></header>
      <p className="langfuseFrameDescription">Bấm request để xem input/output tổng và từng bước xử lý.</p>
      {loading && <div className="langfuseEmpty">Đang tải log…</div>}
      {!loading && error && <div className="langfuseError">{error}</div>}
      {!loading && !error && data && <RecordsTable resource={resource} page={data} onTraceClick={resource === "traces" ? openTrace : undefined} />}
      {selected && <TraceDetail trace={selected} onClose={() => setSelected(null)} />}
      {data && !error && <footer className="langfusePagination"><span>{data.total ?? data.items.length} bản ghi</span><div><button type="button" disabled={pageNumber <= 1 || loading} onClick={() => setPageNumber((value) => value - 1)}>Trước</button><span>Trang {data.page ?? pageNumber}</span><button type="button" disabled={!data.hasMore || loading} onClick={() => setPageNumber((value) => value + 1)}>Sau</button></div></footer>}
    </section>
  );
}

function SummaryCard({ label, value, detail }: { label: string; value: string; detail: string }) { return <article className="langfuseMetricCard"><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>; }

export function LangfuseConsole({ page }: { page: LangfusePage }) {
  const [status, setStatus] = useState<LangfuseStatus | null>(null); const [overview, setOverview] = useState<Record<LangfuseResource, LangfusePageResponse> | null>(null); const [error, setError] = useState(""); const resource = RESOURCE_BY_PAGE[page];
  const loadOverview = useCallback(async () => { setError(""); try { const nextStatus = await getLangfuseStatus(); setStatus(nextStatus); const [traces, observations, sessions] = await Promise.all([getLangfuseRecords("traces", 1, 10), getLangfuseRecords("observations", 1, 10), getLangfuseRecords("sessions", 1, 10)]); setOverview({ traces, observations, sessions }); } catch (caught) { setError(caught instanceof Error ? caught.message : "Không tải được log."); } }, []);
  useEffect(() => { if (page !== "overview") return; void loadOverview(); const timer = window.setInterval(() => void loadOverview(), 10000); return () => window.clearInterval(timer); }, [loadOverview, page]);
  if (resource) return <RecordList resource={resource} />; if (page !== "overview") return <div className="langfuseEmpty">Màn hình này chưa có trong bản observability nhẹ.</div>;
  const successCount = useMemo(() => overview?.traces.items.filter((item) => item.status === "success").length ?? 0, [overview]);
  return <section className="langfuseDataPanel"><header className="langfusePanelHeader"><div><p className="eyebrow">Local diagnostics</p><h2>Request observability</h2><p className="langfuseFrameDescription">Theo dõi request, các bước LangGraph và input/output của tool ngay trong backend.</p></div><button type="button" className="langfuseFrameReload" onClick={() => void loadOverview()}>↻ Tải lại</button></header>{status && <span className="langfuseStatus langfuseStatus-ok">● {status.message}</span>}{error && <div className="langfuseError">{error}</div>}{status && <div className="langfuseMetricGrid"><SummaryCard label="Requests" value={String(status.traceCount)} detail={`giữ tối đa ${status.retentionLimit}`} /><SummaryCard label="Success" value={status.traceCount ? `${Math.round((successCount / Math.max(1, Math.min(status.traceCount, 10))) * 100)}%` : "—"} detail="10 request gần nhất" /><SummaryCard label="Steps" value={String(status.observationCount)} detail="chain, LLM và tool" /><SummaryCard label="Errors" value={String(status.errorCount)} detail="request lỗi" /></div>}{overview?.traces && <RecordsTable resource="traces" page={overview.traces} />}</section>;
}
