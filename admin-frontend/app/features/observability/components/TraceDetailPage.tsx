"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getTrace,
  type TraceDetail,
  type TraceObservation
} from "../lib/langfuse-api";

type ObservationNode = {
  observation: TraceObservation;
  children: ObservationNode[];
};

function formatTimestamp(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("vi-VN");
}

function formatDuration(value?: number | null): string {
  return typeof value === "number" ? `${value.toLocaleString("vi-VN")} ms` : "—";
}

function payloadSummary(value?: string | null): string {
  if (!value) return "Không có dữ liệu";
  try {
    const payload = JSON.parse(value) as unknown;
    if (Array.isArray(payload)) return `${payload.length} phần tử`;
    if (payload && typeof payload === "object") {
      const record = payload as Record<string, unknown>;
      return `${Object.keys(record).length} trường: ${Object.keys(record).slice(0, 6).join(", ")}`;
    }
  } catch {
    return value.length > 160 ? `${value.slice(0, 160)}…` : value;
  }
  return String(value);
}

function PayloadCard({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="localPayloadCard">
      <b>{label}</b>
      <span className="localPayloadSummary">{payloadSummary(value)}</span>
      {value && <details className="localPreview"><summary>Xem JSON</summary><pre>{value}</pre></details>}
    </div>
  );
}

function observationTree(observations: TraceObservation[]): ObservationNode[] {
  const nodes = new Map<string, ObservationNode>();
  observations.forEach((observation) => nodes.set(observation.id, { observation, children: [] }));
  const roots: ObservationNode[] = [];
  nodes.forEach((node) => {
    const parent = node.observation.parentId ? nodes.get(node.observation.parentId) : undefined;
    if (parent && parent !== node) parent.children.push(node);
    else roots.push(node);
  });
  const sort = (items: ObservationNode[]) => {
    items.sort((left, right) => left.observation.startTime.localeCompare(right.observation.startTime));
    items.forEach((item) => sort(item.children));
  };
  sort(roots);
  return roots;
}

function ObservationItem({ node, depth = 0 }: { node: ObservationNode; depth?: number }) {
  const observation = node.observation;
  return (
    <div className="localObservationBranch">
      <details className={`localTimelineItem localTimelineKind-${observation.kind}`} open={depth < 2}>
        <summary className="localTimelineHeading">
          <span><b>{observation.name}</b><small>{observation.kind}</small></span>
          <span><span className={`localStatus localStatus-${observation.status}`}>{observation.status}</span><small>{formatDuration(observation.durationMs)}</small></span>
        </summary>
        <div className="localStepPayload">
          <PayloadCard label="Input" value={observation.inputPreview} />
          <PayloadCard label="Output" value={observation.outputPreview} />
        </div>
        {observation.error && <div className="localObservationError">Error <code>{observation.error}</code></div>}
      </details>
      {node.children.length > 0 && (
        <div className="localObservationChildren">
          {node.children.map((child) => <ObservationItem depth={depth + 1} key={child.observation.id} node={child} />)}
        </div>
      )}
    </div>
  );
}

export function TraceDetailPage() {
  const { traceId } = useParams<{ traceId: string }>();
  const [trace, setTrace] = useState<TraceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setTrace(await getTrace(traceId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không tải được trace.");
    } finally {
      setLoading(false);
    }
  }, [traceId]);
  useEffect(() => { void load(); }, [load]);
  const tree = useMemo(() => observationTree(trace?.observations ?? []), [trace]);

  return (
    <section className="langfuseDataPanel">
      <header className="langfusePanelHeader">
        <div><p className="eyebrow">Trace detail</p><h2>{traceId}</h2><Link className="localBackLink" href="/observability/traces">← Tất cả traces</Link></div>
        <button className="langfuseFrameReload" disabled={loading} onClick={() => void load()} type="button">↻ Tải lại</button>
      </header>
      {loading && <div className="langfuseEmpty">Đang tải trace…</div>}
      {!loading && error && <div className="langfuseError">{error}</div>}
      {!loading && trace && (
        <>
          <div className="localDetailGrid">
            <span>Entry<strong>{trace.entryPoint ?? "—"}</strong></span>
            <span>Route<strong>{trace.route ?? "—"}</strong></span>
            <span>Status<strong><span className={`localStatus localStatus-${trace.status}`}>{trace.status}</span></strong></span>
            <span>Duration<strong>{formatDuration(trace.durationMs)}</strong></span>
            <span>Steps<strong>{trace.observationCount}</strong></span>
            <span>Error<strong>{trace.errorCode ?? "—"}</strong></span>
            <span>Thread<strong>{trace.threadId ?? "—"}</strong></span>
            <span>Started<strong>{formatTimestamp(trace.startedAt)}</strong></span>
            <span>Finished<strong>{formatTimestamp(trace.finishedAt)}</strong></span>
          </div>
          <div className="localPayloadGrid">
            <PayloadCard label="Request summary" value={trace.inputPreview} />
            <PayloadCard label="Response summary" value={trace.outputPreview} />
          </div>
          <div className="localTimelineHeader"><h3>Execution tree</h3><span>{trace.observations.length} spans</span></div>
          <div className="localTimeline">
            {tree.length === 0 && <p className="langfuseEmpty">Trace này chưa có span chi tiết.</p>}
            {tree.map((node) => <ObservationItem key={node.observation.id} node={node} />)}
          </div>
        </>
      )}
    </section>
  );
}
