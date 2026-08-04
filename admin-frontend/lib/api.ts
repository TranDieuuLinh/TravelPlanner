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

export type KnowledgeGraphFileName =
  | "aliases.csv"
  | "entities.csv"
  | "ontology.yaml"
  | "properties.csv"
  | "relationships.csv"
  | "schema.yaml";

export type KnowledgeGraphFiles = Record<KnowledgeGraphFileName, string>;

export async function loadKnowledgeGraphFiles(): Promise<KnowledgeGraphFiles> {
  const response = await fetch("/api/knowledge-graph", {
    cache: "no-store",
    credentials: "include"
  });
  if (!response.ok) throw await parseError(response);
  const payload = (await response.json()) as { files: KnowledgeGraphFiles };
  return payload.files;
}

export async function saveKnowledgeGraphFile(
  fileName: KnowledgeGraphFileName,
  content: string
): Promise<void> {
  const csrf = cookie("vsf_csrf");
  const response = await fetch("/api/knowledge-graph", {
    method: "PUT",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {})
    },
    body: JSON.stringify({ fileName, content })
  });
  if (!response.ok) throw await parseError(response);
}

export async function saveKnowledgeGraphFiles(
  files: Partial<KnowledgeGraphFiles>
): Promise<void> {
  const csrf = cookie("vsf_csrf");
  const response = await fetch("/api/knowledge-graph", {
    method: "PUT",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {})
    },
    body: JSON.stringify({ files })
  });
  if (!response.ok) throw await parseError(response);
}

export type GraphMatchCandidate = {
  entityId: string;
  canonicalName: string;
  type: string;
  score: number;
  matchedRules: string[];
};

export type ProposedGraphNode = {
  tempId: string;
  entityId: string;
  type: string;
  canonicalName: string;
  aliases: string[];
  properties: Record<string, string>;
  evidence: string[];
  confidence: number;
  matchStatus: "existing" | "possible_duplicate" | "new";
  matchCandidates: GraphMatchCandidate[];
  selectedEntityId: string | null;
  decision: "pending" | "approve_create" | "approve_existing" | "reject";
  validationIssues: string[];
  requiredProperties: string[];
  optionalProperties: string[];
};

export type ProposedGraphEdge = {
  tempId: string;
  fromRef: string;
  relationship: string;
  toRef: string;
  recommendations: Array<Record<string, unknown>>;
  source: string;
  evidence: string[];
  confidence: number;
  matchStatus: "existing" | "new" | "needs_review" | "invalid";
  decision: "pending" | "approve_create" | "approve_existing" | "reject";
  validationIssues: string[];
};

export type GraphImportSummary = {
  id: string;
  sourceLabel: string;
  sourceUrl: string | null;
  status: "extracting" | "needs_review" | "applied" | "failed";
  nodeCount: number;
  edgeCount: number;
  issueCount: number;
  createdAt: string;
  appliedAt: string | null;
  errorMessage: string | null;
};

export type GraphImportDetail = GraphImportSummary & {
  sourceContent: string;
  schemaVersion: string;
  ontologyVersion: string;
  datasetHash: string;
  warnings: string[];
  nodes: ProposedGraphNode[];
  edges: ProposedGraphEdge[];
};

export type GraphImportMeta = GraphImportSummary & {
  sourceContent: string;
  schemaVersion: string;
  ontologyVersion: string;
  datasetHash: string;
  warnings: string[];
};

export type ProposedNodePage = {
  items: ProposedGraphNode[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
};

export type ProposedEdgePage = {
  items: ProposedGraphEdge[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
};

export type ProposedNodeMutation = {
  summary: GraphImportSummary;
  meta: GraphImportMeta;
  node: ProposedGraphNode;
};

export type ProposedEdgeMutation = {
  summary: GraphImportSummary;
  meta: GraphImportMeta;
  edge: ProposedGraphEdge;
};

export type GraphImportListPage = {
  items: GraphImportSummary[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
};

export type GraphImportListFilters = {
  limit?: number;
  offset?: number;
  status?: GraphImportSummary["status"];
  search?: string;
};

export function listGraphImports(
  filters: GraphImportListFilters = {}
): Promise<GraphImportListPage> {
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined && filters.offset > 0) params.set("offset", String(filters.offset));
  if (filters.status) params.set("status", filters.status);
  if (filters.search) params.set("search", filters.search);
  const query = params.toString();
  return request(`/admin/knowledge-graph/imports${query ? `?${query}` : ""}`);
}

export function getGraphImportMeta(importId: string): Promise<GraphImportMeta> {
  return request(`/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/meta`);
}

export function getGraphImport(importId: string): Promise<GraphImportDetail> {
  return request(`/admin/knowledge-graph/imports/${encodeURIComponent(importId)}`);
}

export function listGraphImportNodes(
  importId: string,
  filters: { limit?: number; offset?: number } = {}
): Promise<ProposedNodePage> {
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined && filters.offset > 0) params.set("offset", String(filters.offset));
  const query = params.toString();
  return request(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/nodes${query ? `?${query}` : ""}`
  );
}

export function listGraphImportEdges(
  importId: string,
  filters: { limit?: number; offset?: number } = {}
): Promise<ProposedEdgePage> {
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined && filters.offset > 0) params.set("offset", String(filters.offset));
  const query = params.toString();
  return request(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/edges${query ? `?${query}` : ""}`
  );
}

export function createGraphImport(payload: {
  sourceLabel: string;
  sourceUrl?: string;
  content: string;
}): Promise<GraphImportMeta> {
  return request("/admin/knowledge-graph/imports", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateProposedGraphNode(
  importId: string,
  tempId: string,
  payload: Pick<ProposedGraphNode, "entityId" | "type" | "canonicalName" | "aliases" | "properties" | "selectedEntityId" | "decision">
): Promise<ProposedNodeMutation> {
  return request(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/nodes/${encodeURIComponent(tempId)}`,
    { method: "PUT", body: JSON.stringify(payload) }
  );
}

export function updateProposedGraphEdge(
  importId: string,
  tempId: string,
  payload: Pick<ProposedGraphEdge, "fromRef" | "relationship" | "toRef" | "recommendations" | "source" | "decision">
): Promise<ProposedEdgeMutation> {
  return request(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/edges/${encodeURIComponent(tempId)}`,
    { method: "PUT", body: JSON.stringify(payload) }
  );
}

export function applyGraphImport(importId: string): Promise<GraphImportMeta> {
  return request(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/apply`,
    { method: "POST" }
  );
}

export function revalidateGraphImport(importId: string): Promise<GraphImportMeta> {
  return request(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/revalidate`,
    { method: "POST" }
  );
}

export function deleteProposedGraphNode(
  importId: string,
  tempId: string
): Promise<{ deletedTempId: string }> {
  return request(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/nodes/${encodeURIComponent(tempId)}`,
    { method: "DELETE" }
  );
}

export function deleteProposedGraphEdge(
  importId: string,
  tempId: string
): Promise<{ deletedTempId: string }> {
  return request(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/edges/${encodeURIComponent(tempId)}`,
    { method: "DELETE" }
  );
}

export function deleteGraphImport(importId: string): Promise<{ deletedImportId: string }> {
  return request(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}`,
    { method: "DELETE" }
  );
}

// --- Knowledge Graph Entities API ---

export type KGStats = {
  entityCount: number;
  aliasCount: number;
  relationshipCount: number;
};

export type KGEntitySummary = {
  id: string;
  canonicalName: string;
  entityType: string;
  status: string;
  createdAt: string;
  updatedAt: string;
};

export type KGEntityListPage = {
  items: KGEntitySummary[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
};

export type KGAliasDetail = {
  id: number;
  alias: string;
  language: string;
  createdAt: string;
};

export type KGPropertyDetail = {
  id: number;
  key: string;
  value: string;
  source: string | null;
  updatedAt: string;
};

export type KGRelationshipSummary = {
  id: number;
  fromEntityId: string;
  relationship: string;
  toEntityId: string;
  source: string | null;
  createdAt: string;
};

export type KGEntityDetail = {
  id: string;
  canonicalName: string;
  entityType: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  aliases: KGAliasDetail[];
  aliasTotal: number;
  aliasHasMore: boolean;
  properties: KGPropertyDetail[];
  propertyTotal: number;
  propertyHasMore: boolean;
  relationships: KGRelationshipSummary[];
  relationshipTotal: number;
  relationshipHasMore: boolean;
};

export type KGEntityUpdatePayload = {
  canonicalName?: string;
  entityType?: string;
  status?: string;
};

export type KGAliasUpsertPayload = {
  alias: string;
  language: string;
};

export type KGPropertyUpsertPayload = {
  key: string;
  value: string;
  source?: string | null;
};

export type KGRelationshipUpsertPayload = {
  relationship: string;
  toEntityId: string;
  source?: string | null;
  recommendations?: Record<string, unknown> | null;
};

export type KGRelationshipListPage = {
  items: KGRelationshipSummary[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
};

export function getKGStats(): Promise<KGStats> {
  return request("/admin/knowledge-graph/stats");
}

export function listKGEntities(filters: {
  limit?: number;
  offset?: number;
  search?: string;
  entityType?: string;
  status?: string;
}): Promise<KGEntityListPage> {
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined && filters.offset > 0) params.set("offset", String(filters.offset));
  if (filters.search) params.set("search", filters.search);
  if (filters.entityType) params.set("entity_type", filters.entityType);
  if (filters.status) params.set("status", filters.status);
  const query = params.toString();
  return request(`/admin/knowledge-graph/entities${query ? `?${query}` : ""}`);
}

export function getKGEntityDetail(
  entityId: string,
  options?: {
    aliasOffset?: number;
    aliasLimit?: number;
    propertyOffset?: number;
    propertyLimit?: number;
    relationshipOffset?: number;
    relationshipLimit?: number;
  }
): Promise<KGEntityDetail> {
  const params = new URLSearchParams();
  if (options?.aliasOffset !== undefined) params.set("alias_offset", String(options.aliasOffset));
  if (options?.aliasLimit !== undefined) params.set("alias_limit", String(options.aliasLimit));
  if (options?.propertyOffset !== undefined) params.set("property_offset", String(options.propertyOffset));
  if (options?.propertyLimit !== undefined) params.set("property_limit", String(options.propertyLimit));
  if (options?.relationshipOffset !== undefined) params.set("relationship_offset", String(options.relationshipOffset));
  if (options?.relationshipLimit !== undefined) params.set("relationship_limit", String(options.relationshipLimit));
  const query = params.toString();
  return request(
    `/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}${query ? `?${query}` : ""}`
  );
}

export function updateKGEntity(
  entityId: string,
  payload: KGEntityUpdatePayload
): Promise<KGEntityDetail> {
  return request(`/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function createKGAlias(
  entityId: string,
  payload: KGAliasUpsertPayload
): Promise<KGEntityDetail> {
  return request(`/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}/aliases`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateKGAlias(
  entityId: string,
  aliasId: number,
  payload: KGAliasUpsertPayload
): Promise<KGEntityDetail> {
  return request(
    `/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}/aliases/${aliasId}`,
    {
      method: "PUT",
      body: JSON.stringify(payload)
    }
  );
}

export function deleteKGAlias(entityId: string, aliasId: number): Promise<{ deletedAliasId: number }> {
  return request(
    `/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}/aliases/${aliasId}`,
    { method: "DELETE" }
  );
}

export function createKGProperty(
  entityId: string,
  payload: KGPropertyUpsertPayload
): Promise<KGEntityDetail> {
  return request(`/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}/properties`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateKGProperty(
  entityId: string,
  propertyId: number,
  payload: KGPropertyUpsertPayload
): Promise<KGEntityDetail> {
  return request(
    `/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}/properties/${propertyId}`,
    {
      method: "PUT",
      body: JSON.stringify(payload)
    }
  );
}

export function deleteKGProperty(
  entityId: string,
  propertyId: number
): Promise<{ deletedPropertyId: number }> {
  return request(
    `/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}/properties/${propertyId}`,
    { method: "DELETE" }
  );
}

export function createKGRelationship(
  entityId: string,
  payload: KGRelationshipUpsertPayload
): Promise<KGEntityDetail> {
  return request(
    `/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}/relationships`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function updateKGRelationship(
  entityId: string,
  relationshipId: number,
  payload: KGRelationshipUpsertPayload
): Promise<KGEntityDetail> {
  return request(
    `/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}/relationships/${relationshipId}`,
    {
      method: "PUT",
      body: JSON.stringify(payload)
    }
  );
}

export function deleteKGRelationship(
  entityId: string,
  relationshipId: number
): Promise<{ deletedRelationshipId: number }> {
  return request(
    `/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}/relationships/${relationshipId}`,
    { method: "DELETE" }
  );
}

export function listKGRelationships(filters: {
  limit?: number;
  offset?: number;
  relationship?: string;
  fromEntityId?: string;
  toEntityId?: string;
  search?: string;
}): Promise<KGRelationshipListPage> {
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined && filters.offset > 0) params.set("offset", String(filters.offset));
  if (filters.relationship) params.set("relationship", filters.relationship);
  if (filters.fromEntityId) params.set("from_entity_id", filters.fromEntityId);
  if (filters.toEntityId) params.set("to_entity_id", filters.toEntityId);
  if (filters.search) params.set("search", filters.search);
  const query = params.toString();
  return request(`/admin/knowledge-graph/relationships${query ? `?${query}` : ""}`);
}

export type KGOntology = {
  nodeTypes: string[];
  relationshipTypes: string[];
  nodeTypeProperties: Record<
    string,
    {
      requiredProperties: string[];
      optionalProperties: string[];
    }
  >;
};

export function getKGOntology(): Promise<KGOntology> {
  return request("/admin/knowledge-graph/ontology");
}

