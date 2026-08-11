"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getLangfuseRecords,
  getLangfuseStatus,
  type LangfusePageResponse,
  type LangfuseRecord,
  type LangfuseResource,
  type LangfuseStatus
} from "../lib/langfuse-api";
import { langfuseUrlFor, type LangfusePage } from "../lib/langfuse-config";

type Column = { label: string; keys: string[]; timestamp?: boolean };

const RESOURCE_BY_PAGE: Partial<Record<LangfusePage, LangfuseResource>> = {
  traces: "traces",
  observations: "observations",
  sessions: "sessions"
};

const COLUMNS: Record<LangfuseResource, Column[]> = {
  traces: [
    { label: "Name", keys: ["name"] },
    { label: "Trace ID", keys: ["id"] },
    { label: "User", keys: ["userId", "user_id"] },
    { label: "Session", keys: ["sessionId", "session_id"] },
    { label: "Timestamp", keys: ["timestamp", "createdAt"], timestamp: true }
  ],
  observations: [
    { label: "Name", keys: ["name"] },
    { label: "Type", keys: ["type"] },
    { label: "Model", keys: ["model"] },
    { label: "Level", keys: ["level"] },
    { label: "Start", keys: ["startTime", "createdAt"], timestamp: true }
  ],
  sessions: [
    { label: "Session ID", keys: ["id", "sessionId"] },
    { label: "User", keys: ["userId", "user_id"] },
    { label: "Traces", keys: ["traceCount", "trace_count"] },
    { label: "First trace", keys: ["createdAt", "firstTimestamp"], timestamp: true },
    { label: "Last trace", keys: ["lastTimestamp", "updatedAt"], timestamp: true }
  ]
};

function valueOf(record: LangfuseRecord, keys: string[]): string {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" || typeof value === "number") return String(value);
    if (typeof value === "boolean") return value ? "Có" : "Không";
  }
  return "—";
}

function formatValue(value: string, timestamp = false): string {
  if (!timestamp || value === "—") return value;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("vi-VN");
}

function RecordsTable({ resource, page }: { resource: LangfuseResource; page: LangfusePageResponse }) {
  const columns = COLUMNS[resource];
  if (page.items.length === 0) {
    return <div className="langfuseEmpty">Chưa có dữ liệu {resource} trong Langfuse.</div>;
  }
  return (
    <div className="langfuseTableWrap">
      <table className="langfuseTable">
        <thead><tr>{columns.map((column) => <th key={column.label}>{column.label}</th>)}</tr></thead>
        <tbody>
          {page.items.map((record, index) => (
            <tr key={`${valueOf(record, ["id", "traceId", "sessionId"])}-${index}`}>
              {columns.map((column) => (
                <td key={column.label}>{formatValue(valueOf(record, column.keys), column.timestamp)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecordList({ resource }: { resource: LangfuseResource }) {
  const [data, setData] = useState<LangfusePageResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [pageNumber, setPageNumber] = useState(1);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getLangfuseRecords(resource, pageNumber));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không tải được dữ liệu Langfuse.");
    } finally {
      setLoading(false);
    }
  }, [pageNumber, resource]);

  useEffect(() => { void load(); }, [load]);

  return (
    <section className="langfuseDataPanel">
      <header className="langfusePanelHeader">
        <div><p className="eyebrow">Langfuse API</p><h2>{resource[0].toUpperCase() + resource.slice(1)}</h2></div>
        <button type="button" className="langfuseFrameReload" onClick={() => void load()}>↻ Tải lại</button>
      </header>
      {loading && <div className="langfuseEmpty">Đang tải dữ liệu…</div>}
      {!loading && error && <div className="langfuseError">{error}</div>}
      {!loading && !error && data && <RecordsTable resource={resource} page={data} />}
      {data && !error && (
        <footer className="langfusePagination">
          <span>{data.total == null ? `${data.items.length} bản ghi` : `${data.total} bản ghi`}</span>
          <div>
            <button type="button" disabled={pageNumber <= 1 || loading} onClick={() => setPageNumber((value) => value - 1)}>Trước</button>
            <span>Trang {data.page ?? pageNumber}</span>
            <button type="button" disabled={!data.hasMore || loading} onClick={() => setPageNumber((value) => value + 1)}>Sau</button>
          </div>
        </footer>
      )}
    </section>
  );
}

function StatusBadge({ status }: { status: LangfuseStatus }) {
  const tone = status.reachable ? "ok" : status.configured ? "warn" : "muted";
  return <span className={`langfuseStatus langfuseStatus-${tone}`}>{status.message}</span>;
}

function SummaryCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <article className="langfuseMetricCard"><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

export function LangfuseConsole({ page }: { page: LangfusePage }) {
  const [status, setStatus] = useState<LangfuseStatus | null>(null);
  const [overview, setOverview] = useState<Record<LangfuseResource, LangfusePageResponse> | null>(null);
  const [error, setError] = useState("");
  const resource = RESOURCE_BY_PAGE[page];

  const loadOverview = useCallback(async () => {
    setError("");
    try {
      const nextStatus = await getLangfuseStatus();
      setStatus(nextStatus);
      if (!nextStatus.reachable) return;
      const [traces, observations, sessions] = await Promise.all([
        getLangfuseRecords("traces", 1, 10),
        getLangfuseRecords("observations", 1, 10),
        getLangfuseRecords("sessions", 1, 10)
      ]);
      setOverview({ traces, observations, sessions });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không kiểm tra được Langfuse.");
    }
  }, []);

  useEffect(() => { if (page === "overview") void loadOverview(); }, [loadOverview, page]);

  if (resource) return <RecordList resource={resource} />;
  if (page !== "overview") {
    return <div className="langfuseEmpty"><b>{page[0].toUpperCase() + page.slice(1)} chưa có màn hình API tích hợp.</b><p>Mở Langfuse trực tiếp nếu cần tính năng này.</p><a className="langfuseFrameOpen" href={langfuseUrlFor(page)} target="_blank" rel="noreferrer">↗ Mở Langfuse</a></div>;
  }

  const traces = useMemo(() => overview?.traces, [overview]);
  return (
    <section className="langfuseDataPanel">
      <header className="langfusePanelHeader">
        <div><p className="eyebrow">Integrated console</p><h2>Langfuse overview</h2><p className="langfuseFrameDescription">Dữ liệu đọc qua backend proxy và được bảo vệ bởi phiên admin TravelPlanner.</p></div>
        <button type="button" className="langfuseFrameReload" onClick={() => void loadOverview()}>↻ Tải lại</button>
      </header>
      {status && <StatusBadge status={status} />}
      {error && <div className="langfuseError">{error}</div>}
      {status && !status.reachable && <div className="langfuseSetupNotice"><b>Chưa kết nối được Langfuse API</b><p>Cấu hình LANGFUSE_PUBLIC_KEY và LANGFUSE_SECRET_KEY ở backend rồi khởi động lại backend.</p></div>}
      {status?.reachable && overview && <div className="langfuseMetricGrid"><SummaryCard label="Projects" value={status.projectCount == null ? "—" : String(status.projectCount)} detail="Từ Langfuse public API" /><SummaryCard label="Traces" value={overview.traces.total == null ? "—" : String(overview.traces.total)} detail="Trace đã ghi nhận" /><SummaryCard label="Observations" value={overview.observations.total == null ? "—" : String(overview.observations.total)} detail="LLM, tool và span" /><SummaryCard label="Sessions" value={overview.sessions.total == null ? "—" : String(overview.sessions.total)} detail="Session của agent" /></div>}
      {traces && <RecordsTable resource="traces" page={traces} />}
    </section>
  );
}
