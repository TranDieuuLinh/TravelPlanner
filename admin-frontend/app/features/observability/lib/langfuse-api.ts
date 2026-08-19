import { apiRequest } from "../../../../lib/shared/api-client";

export type LangfuseRecord = Record<string, unknown>;

export type TraceObservation = LangfuseRecord & {
  id: string;
  traceId: string;
  parentId?: string | null;
  name: string;
  kind: string;
  status: string;
  startTime: string;
  endTime?: string | null;
  durationMs?: number | null;
  error?: string | null;
  inputPreview?: string | null;
  outputPreview?: string | null;
};

export type TraceSummary = LangfuseRecord & {
  id: string;
  requestId: string;
  entryPoint?: string;
  threadId?: string | null;
  route?: string | null;
  status: string;
  startedAt: string;
  finishedAt?: string | null;
  durationMs?: number | null;
  errorCode?: string | null;
  observationCount: number;
  inputPreview?: string | null;
  outputPreview?: string | null;
};

export type TraceDetail = TraceSummary & {
  observations: TraceObservation[];
};

export type LangfusePageResponse = {
  items: LangfuseRecord[];
  page: number | null;
  limit: number;
  total: number | null;
  hasMore: boolean | null;
};

export type LangfuseStatus = {
  configured: boolean;
  reachable: boolean;
  message: string;
  traceCount: number;
  observationCount: number;
  errorCount: number;
  retentionLimit: number;
};

export type LangfuseResource = "traces" | "observations" | "sessions";

export function getLangfuseStatus(): Promise<LangfuseStatus> {
  return apiRequest<LangfuseStatus>("/admin/observability/status");
}

export function getLangfuseRecords(
  resource: LangfuseResource,
  page = 1,
  limit = 25,
  traceId?: string
): Promise<LangfusePageResponse> {
  const traceFilter = traceId ? `&traceId=${encodeURIComponent(traceId)}` : "";
  return apiRequest<LangfusePageResponse>(
    `/admin/observability/${resource}?page=${page}&limit=${limit}${traceFilter}`
  );
}

export function getTrace(traceId: string): Promise<TraceDetail> {
  return apiRequest<TraceDetail>(
    `/admin/observability/traces/${encodeURIComponent(traceId)}`
  );
}
