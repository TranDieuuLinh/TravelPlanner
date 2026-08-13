import { apiRequest } from "../../../../lib/shared/api-client";

export type LangfuseRecord = Record<string, unknown>;

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
  limit = 25
): Promise<LangfusePageResponse> {
  return apiRequest<LangfusePageResponse>(
    `/admin/observability/${resource}?page=${page}&limit=${limit}`
  );
}

export function getTrace(traceId: string): Promise<LangfuseRecord> {
  return apiRequest<LangfuseRecord>(
    `/admin/observability/traces/${encodeURIComponent(traceId)}`
  );
}
