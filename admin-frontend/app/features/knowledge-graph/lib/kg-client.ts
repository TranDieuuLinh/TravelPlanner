import { apiRequest } from "../../../../lib/shared/api-client";

export type KGStats = {
  entityCount: number;
  aliasCount: number;
  relationshipCount: number;
};

export type KGSearchStats = {
  query: string;
  entityCount: number;
  aliasCount: number;
  propertyCount: number;
  relationshipCount: number;
  totalCount: number;
};

export type KGEntitySummary = {
  id: string;
  canonicalName: string;
  entityType: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  reviewCount: number | null;
};

export type KGEntityListPage = {
  items: KGEntitySummary[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
};

export type KGEntityFilterOptions = {
  entityTypes: string[];
  statuses: string[];
  propertyKeys: string[];
  relationshipTypes: string[];
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
  entityId?: string;
  canonicalName?: string;
  entityType?: string;
  status?: string;
};

export type KGEntityCreatePayload = {
  entityId: string;
  canonicalName: string;
  entityType: string;
  status: string;
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
  fromEntityId?: string;
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

export type KGOntology = {
  nodeTypes: string[];
  propertyKeys: string[];
  relationshipTypes: string[];
  nodeTypeProperties: Record<
    string,
    {
      requiredProperties: string[];
      optionalProperties: string[];
    }
  >;
};

export type KGLowReviewEntityResponse = {
  threshold: number;
  entityCount: number;
  deletedEntityCount?: number;
};

export function getKGStats(): Promise<KGStats> {
  return apiRequest("/admin/knowledge-graph/stats");
}

export function getKGSearchStats(query: string): Promise<KGSearchStats> {
  return apiRequest(`/admin/knowledge-graph/search-stats?query=${encodeURIComponent(query)}`);
}

export function getKGEntityFilterOptions(): Promise<KGEntityFilterOptions> {
  return apiRequest("/admin/knowledge-graph/entities/filters");
}

export function listKGEntities(filters: {
  limit?: number;
  offset?: number;
  search?: string;
  entityType?: string;
  status?: string;
  excludeNames?: string;
  missingProperties?: string;
  sortBy?: string;
  sortDirection?: "asc" | "desc";
}): Promise<KGEntityListPage> {
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined && filters.offset > 0) params.set("offset", String(filters.offset));
  if (filters.search) params.set("search", filters.search);
  if (filters.entityType) params.set("entity_type", filters.entityType);
  if (filters.status) params.set("status", filters.status);
  if (filters.excludeNames) params.set("excludeNames", filters.excludeNames);
  if (filters.missingProperties) params.set("missingProperties", filters.missingProperties);
  if (filters.sortBy) params.set("sortBy", filters.sortBy);
  if (filters.sortDirection) params.set("sortDirection", filters.sortDirection);
  const query = params.toString();
  return apiRequest(`/admin/knowledge-graph/entities${query ? `?${query}` : ""}`);
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
  return apiRequest(
    `/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}${query ? `?${query}` : ""}`
  );
}

export function updateKGEntity(
  entityId: string,
  payload: KGEntityUpdatePayload
): Promise<KGEntityDetail> {
  return apiRequest(`/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function createKGEntity(payload: KGEntityCreatePayload): Promise<KGEntityDetail> {
  return apiRequest("/admin/knowledge-graph/entities", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function copyKGEntity(
  entityId: string,
  payload: Pick<KGEntityCreatePayload, "entityId" | "canonicalName">
): Promise<KGEntityDetail> {
  return apiRequest(`/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}/copy`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deleteKGEntity(entityId: string): Promise<{ deletedEntityId: string }> {
  return apiRequest(`/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}`, {
    method: "DELETE",
  });
}

export function getKGLowReviewEntityCount(threshold = 50): Promise<KGLowReviewEntityResponse> {
  return apiRequest(`/admin/knowledge-graph/entities/low-review-count?threshold=${threshold}`);
}

export function deleteKGLowReviewEntities(threshold = 50): Promise<KGLowReviewEntityResponse> {
  return apiRequest(`/admin/knowledge-graph/entities/low-review-count?threshold=${threshold}`, {
    method: "DELETE",
  });
}

export function createKGAlias(
  entityId: string,
  payload: KGAliasUpsertPayload
): Promise<KGEntityDetail> {
  return apiRequest(`/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}/aliases`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateKGAlias(
  entityId: string,
  aliasId: number,
  payload: KGAliasUpsertPayload
): Promise<KGEntityDetail> {
  return apiRequest(
    `/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}/aliases/${aliasId}`,
    {
      method: "PUT",
      body: JSON.stringify(payload)
    }
  );
}

export function deleteKGAlias(entityId: string, aliasId: number): Promise<{ deletedAliasId: number }> {
  return apiRequest(
    `/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}/aliases/${aliasId}`,
    { method: "DELETE" }
  );
}

export function createKGProperty(
  entityId: string,
  payload: KGPropertyUpsertPayload
): Promise<KGEntityDetail> {
  return apiRequest(`/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}/properties`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateKGProperty(
  entityId: string,
  propertyId: number,
  payload: KGPropertyUpsertPayload
): Promise<KGEntityDetail> {
  return apiRequest(
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
  return apiRequest(
    `/admin/knowledge-graph/entities/${encodeURIComponent(entityId)}/properties/${propertyId}`,
    { method: "DELETE" }
  );
}

export function createKGRelationship(
  entityId: string,
  payload: KGRelationshipUpsertPayload
): Promise<KGEntityDetail> {
  return apiRequest(
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
  return apiRequest(
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
  return apiRequest(
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
  sortBy?: string;
  sortDirection?: "asc" | "desc";
}): Promise<KGRelationshipListPage> {
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined && filters.offset > 0) params.set("offset", String(filters.offset));
  if (filters.relationship) params.set("relationship", filters.relationship);
  if (filters.fromEntityId) params.set("from_entity_id", filters.fromEntityId);
  if (filters.toEntityId) params.set("to_entity_id", filters.toEntityId);
  if (filters.search) params.set("search", filters.search);
  if (filters.sortBy) params.set("sortBy", filters.sortBy);
  if (filters.sortDirection) params.set("sortDirection", filters.sortDirection);
  const query = params.toString();
  return apiRequest(`/admin/knowledge-graph/relationships${query ? `?${query}` : ""}`);
}

export function getKGOntology(): Promise<KGOntology> {
  return apiRequest("/admin/knowledge-graph/ontology");
}

export type KGAutoAttachTimeWindow = {
  start: string;
  end: string;
};

export type KGAutoAttachRule = {
  ruleId: string;
  name: string;
  styleGroup: string;
  entityTypes: string[];
  keywords: string[];
  exactNames: string[];
  excludeKeywords: string[];
  timeDuration: string;
  timeWindows: KGAutoAttachTimeWindow[];
  overrideCount: number;
  status: string;
  source: string;
};

export type KGAutoAttachRuleList = {
  items: KGAutoAttachRule[];
  total: number;
};

export function listKGAutoAttachRules(): Promise<KGAutoAttachRuleList> {
  return apiRequest("/admin/knowledge-graph/auto-attach/rules");
}

export function upsertKGAutoAttachRule(rule: KGAutoAttachRule): Promise<KGAutoAttachRule> {
  return apiRequest(`/admin/knowledge-graph/auto-attach/rules/${encodeURIComponent(rule.ruleId)}`, {
    method: "PUT",
    body: JSON.stringify(rule),
  });
}

export function deleteKGAutoAttachRule(ruleId: string): Promise<void> {
  return apiRequest(`/admin/knowledge-graph/auto-attach/rules/${encodeURIComponent(ruleId)}`, {
    method: "DELETE",
  });
}

export type KGAutoAttachAlias = {
  keyword: string;
  aliases: string[];
  source: string;
};

export type KGAutoAttachAliasList = {
  items: KGAutoAttachAlias[];
  total: number;
};

export function listKGAutoAttachAliases(): Promise<KGAutoAttachAliasList> {
  return apiRequest("/admin/knowledge-graph/auto-attach/aliases");
}

export function upsertKGAutoAttachAlias(alias: KGAutoAttachAlias): Promise<KGAutoAttachAlias> {
  return apiRequest(`/admin/knowledge-graph/auto-attach/aliases/${encodeURIComponent(alias.keyword)}`, {
    method: "PUT",
    body: JSON.stringify(alias),
  });
}

// --- Knowledge Graph AI Imports ---

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
  return apiRequest(`/admin/knowledge-graph/imports${query ? `?${query}` : ""}`);
}

export function getGraphImportMeta(importId: string): Promise<GraphImportMeta> {
  return apiRequest(`/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/meta`);
}

export function getGraphImport(importId: string): Promise<GraphImportDetail> {
  return apiRequest(`/admin/knowledge-graph/imports/${encodeURIComponent(importId)}`);
}

export function listGraphImportNodes(
  importId: string,
  filters: { limit?: number; offset?: number } = {}
): Promise<ProposedNodePage> {
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined && filters.offset > 0) params.set("offset", String(filters.offset));
  const query = params.toString();
  return apiRequest(
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
  return apiRequest(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/edges${query ? `?${query}` : ""}`
  );
}

export function createGraphImport(payload: {
  sourceLabel: string;
  sourceUrl?: string;
  content: string;
}): Promise<GraphImportMeta> {
  return apiRequest("/admin/knowledge-graph/imports", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateProposedGraphNode(
  importId: string,
  tempId: string,
  payload: Pick<ProposedGraphNode, "entityId" | "type" | "canonicalName" | "aliases" | "properties" | "selectedEntityId" | "decision">
): Promise<ProposedNodeMutation> {
  return apiRequest(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/nodes/${encodeURIComponent(tempId)}`,
    { method: "PUT", body: JSON.stringify(payload) }
  );
}

export function updateProposedGraphEdge(
  importId: string,
  tempId: string,
  payload: Pick<ProposedGraphEdge, "fromRef" | "relationship" | "toRef" | "recommendations" | "source" | "decision">
): Promise<ProposedEdgeMutation> {
  return apiRequest(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/edges/${encodeURIComponent(tempId)}`,
    { method: "PUT", body: JSON.stringify(payload) }
  );
}

export function applyGraphImport(importId: string): Promise<GraphImportMeta> {
  return apiRequest(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/apply`,
    { method: "POST" }
  );
}

export function revalidateGraphImport(importId: string): Promise<GraphImportMeta> {
  return apiRequest(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/revalidate`,
    { method: "POST" }
  );
}

export function deleteProposedGraphNode(
  importId: string,
  tempId: string
): Promise<{ deletedTempId: string }> {
  return apiRequest(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/nodes/${encodeURIComponent(tempId)}`,
    { method: "DELETE" }
  );
}

export function deleteProposedGraphEdge(
  importId: string,
  tempId: string
): Promise<{ deletedTempId: string }> {
  return apiRequest(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}/edges/${encodeURIComponent(tempId)}`,
    { method: "DELETE" }
  );
}

export function deleteGraphImport(importId: string): Promise<{ deletedImportId: string }> {
  return apiRequest(
    `/admin/knowledge-graph/imports/${encodeURIComponent(importId)}`,
    { method: "DELETE" }
  );
}
