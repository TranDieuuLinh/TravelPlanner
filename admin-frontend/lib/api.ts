const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

export type AdminUser = {
  id: number;
  email: string;
  fullName: string;
  role: "traveler" | "host" | "creator" | "admin";
};

export type PlanningRunSummary = {
  id: string;
  userId: number | null;
  intakeId: string | null;
  source: string;
  mode: string;
  destination: string;
  status: string;
  currentStage: string | null;
  stageCount: number;
  errorCode: string | null;
  summary: Record<string, unknown>;
  createdAt: string;
  completedAt: string | null;
};

export type PlanningRunStage = {
  id: string;
  sequence: number;
  stage: string;
  status: string;
  durationMs: number | null;
  input: unknown;
  output: unknown;
  error: Record<string, unknown>;
  metadata: Record<string, unknown>;
  createdAt: string;
};

export type PlanningRunDetail = PlanningRunSummary & {
  errorMessage: string | null;
  stages: PlanningRunStage[];
};

export type GoldenCase = {
  module: string;
  datasetVersion: string;
  id: string;
  scenarioName: string;
  scenarioPurpose: string;
  category: string;
  input: unknown;
  goldenOutput: unknown;
  assertions: string[];
  validation: {
    status: "valid" | "warning" | "invalid";
    errorCount: number;
    warningCount: number;
    issues: Array<{
      path: string;
      message: string;
      severity: "error" | "warning";
    }>;
  };
};

export type GoldenCaseExecution = {
  runId: string;
  caseId: string;
  module: string;
  status: "completed" | "failed";
  durationMs: number;
  effectiveInput: unknown;
  actualOutput: unknown | null;
  adaptations: string[];
  comparison: {
    matchedFieldCount: number;
    mismatchCount: number;
    matchesGoldenProjection: boolean;
    mismatches: Array<{
      path: string;
      expected: unknown;
      actual: unknown;
    }>;
  } | null;
  error: {
    code: string;
    message: string;
    details: unknown[];
  } | null;
};

type RunList = {
  items: PlanningRunSummary[];
  total: number;
  limit: number;
  offset: number;
};

export class APIError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string
  ) {
    super(message);
  }
}

function cookie(name: string): string | undefined {
  const prefix = `${encodeURIComponent(name)}=`;
  return document.cookie
    .split("; ")
    .find((item) => item.startsWith(prefix))
    ?.slice(prefix.length);
}

async function parseError(response: Response): Promise<APIError> {
  let body: { code?: string; message?: string; detail?: string } = {};
  try {
    body = await response.json();
  } catch {
    // Use the stable fallback below.
  }
  return new APIError(
    response.status,
    body.code ?? "REQUEST_FAILED",
    body.message ?? body.detail ?? "Không thể hoàn thành yêu cầu."
  );
}

async function refreshSession(): Promise<boolean> {
  const csrf = cookie("vsf_csrf");
  if (!csrf) return false;
  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": decodeURIComponent(csrf) }
  });
  return response.ok;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  retry = true
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD"].includes((init.method ?? "GET").toUpperCase())) {
    const csrf = cookie("vsf_csrf");
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      credentials: "include"
    });
  } catch {
    throw new APIError(
      0,
      "NETWORK_ERROR",
      "Không kết nối được backend VSF Travel."
    );
  }
  if (
    response.status === 401 &&
    retry &&
    !path.startsWith("/auth/") &&
    (await refreshSession())
  ) {
    return request<T>(path, init, false);
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function login(
  email: string,
  password: string
): Promise<AdminUser> {
  const response = await request<{ user: AdminUser }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });
  if (response.user.role !== "admin") {
    await logout();
    throw new APIError(
      403,
      "ADMIN_REQUIRED",
      "Tài khoản này không có quyền quản trị."
    );
  }
  return response.user;
}

export async function logout(): Promise<void> {
  await request<void>("/auth/logout", { method: "POST" });
}

export function listRuns(filters: {
  status?: string;
  stage?: string;
  query?: string;
  limit?: number;
}): Promise<RunList> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.stage) params.set("stage", filters.stage);
  if (filters.query) params.set("query", filters.query);
  params.set("limit", String(filters.limit ?? 100));
  return request<RunList>(`/admin/planning-runs?${params.toString()}`);
}

export function getRun(runId: string): Promise<PlanningRunDetail> {
  return request<PlanningRunDetail>(`/admin/planning-runs/${runId}`);
}

export function listGoldenCases(module = ""): Promise<{
  items: GoldenCase[];
  total: number;
  modules: string[];
}> {
  const params = new URLSearchParams();
  if (module) params.set("module", module);
  return request(`/admin/planning-runs/golden/cases?${params.toString()}`);
}

export function runGoldenCase(caseId: string): Promise<GoldenCaseExecution> {
  return request(
    `/admin/planning-runs/golden/cases/${encodeURIComponent(caseId)}/run`,
    { method: "POST" }
  );
}

export function updateGoldenCaseInput(caseId: string, input: unknown): Promise<GoldenCase> {
  return request(
    `/admin/planning-runs/golden/cases/${encodeURIComponent(caseId)}`,
    { method: "PUT", body: JSON.stringify(input) }
  );
}

export function testRegionOverview(input: unknown): Promise<unknown> {
  return request(`/admin/planning-runs/tools/region-overview`, {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export function testConstraintResearch(input: unknown): Promise<unknown> {
  return request(`/admin/planning-runs/tools/constraint-research`, {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export function testFestivalDiscovery(input: unknown): Promise<unknown> {
  return request(`/admin/planning-runs/tools/festival-discovery`, {
    method: "POST",
    body: JSON.stringify(input)
  });
}
