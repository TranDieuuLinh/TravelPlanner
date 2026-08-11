"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { APIError } from "../../lib/shared/api-client";
import {
  GraphImportMeta,
  GraphImportSummary,
  ProposedEdgePage,
  ProposedEdgeMutation,
  ProposedGraphEdge,
  ProposedNodeMutation,
  ProposedNodePage,
  ProposedGraphNode,
  applyGraphImport,
  createGraphImport,
  deleteGraphImport,
  deleteProposedGraphEdge,
  deleteProposedGraphNode,
  getGraphImportMeta,
  listGraphImportEdges,
  listGraphImportNodes,
  listGraphImports,
  revalidateGraphImport,
  updateProposedGraphEdge,
  updateProposedGraphNode
} from "../features/knowledge-graph/lib";

type ReviewTab = "nodes" | "edges" | "source";

const PAGE_SIZE = 25;
const DETAIL_PAGE_SIZE = 50;
type StatusFilter = GraphImportSummary["status"] | "all";

type LazyList<T> = {
  items: T[];
  total: number;
  hasMore: boolean;
  loading: boolean;
  error: string;
};

const EMPTY_LAZY = { items: [], total: 0, hasMore: false, loading: false, error: "" };

export function KnowledgeGraphAIImports({
  nodeTypes,
  nodeTypeProperties,
  relationshipTypes,
  onApplied
}: {
  nodeTypes: string[];
  nodeTypeProperties: Record<string, { requiredProperties: string[]; optionalProperties: string[] }>;
  relationshipTypes: string[];
  onApplied: () => void;
}) {
  const [jobs, setJobs] = useState<GraphImportSummary[]>([]);
  const [jobsTotal, setJobsTotal] = useState(0);
  const [jobsHasMore, setJobsHasMore] = useState(false);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [selected, setSelected] = useState<GraphImportMeta | null>(null);
  const [activeTab, setActiveTab] = useState<ReviewTab>("nodes");
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [selectedEdgeId, setSelectedEdgeId] = useState("");
  const [showCreate, setShowCreate] = useState(true);
  const [sourceLabel, setSourceLabel] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [nodesByJob, setNodesByJob] = useState<Record<string, LazyList<ProposedGraphNode>>>({});
  const [edgesByJob, setEdgesByJob] = useState<Record<string, LazyList<ProposedGraphEdge>>>({});

  async function reloadJobs(selectId?: string) {
    setLoading(true);
    setError("");
    try {
      const result = await listGraphImports({
        limit: PAGE_SIZE,
        offset: 0,
        status: statusFilter === "all" ? undefined : statusFilter,
        search: searchTerm.trim() || undefined
      });
      setJobs(result.items);
      setJobsTotal(result.total);
      setJobsHasMore(result.hasMore);
      const targetId = selectId ?? selected?.id ?? result.items[0]?.id;
      if (targetId) {
        const meta = await getGraphImportMeta(targetId);
        setSelected(meta);
      }
    } catch (caught) {
      setError(messageFor(caught, "Không tải được AI imports."));
    } finally {
      setLoading(false);
    }
  }

  async function loadMoreJobs() {
    if (!jobsHasMore || loadingMore) return;
    setLoadingMore(true);
    setError("");
    try {
      const result = await listGraphImports({
        limit: PAGE_SIZE,
        offset: jobs.length,
        status: statusFilter === "all" ? undefined : statusFilter,
        search: searchTerm.trim() || undefined
      });
      setJobs((current) => {
        const known = new Set(current.map((item) => item.id));
        return [...current, ...result.items.filter((item) => !known.has(item.id))];
      });
      setJobsHasMore(result.hasMore);
    } catch (caught) {
      setError(messageFor(caught, "Không tải thêm được AI imports."));
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    void reloadJobs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, searchTerm]);

  const setNodesForJob = useCallback(
    (jobId: string, updater: (current: LazyList<ProposedGraphNode>) => LazyList<ProposedGraphNode>) => {
      setNodesByJob((current) => ({ ...current, [jobId]: updater(current[jobId] ?? EMPTY_LAZY) }));
    },
    []
  );

  const setEdgesForJob = useCallback(
    (jobId: string, updater: (current: LazyList<ProposedGraphEdge>) => LazyList<ProposedGraphEdge>) => {
      setEdgesByJob((current) => ({ ...current, [jobId]: updater(current[jobId] ?? EMPTY_LAZY) }));
    },
    []
  );

  async function loadNodes(jobId: string, reset = false) {
    const current = nodesByJob[jobId] ?? EMPTY_LAZY;
    setNodesForJob(jobId, (state) => ({ ...state, loading: true, error: "" }));
    try {
      const offset = reset ? 0 : current.items.length;
      const result: ProposedNodePage = await listGraphImportNodes(jobId, {
        limit: DETAIL_PAGE_SIZE,
        offset
      });
      setNodesForJob(jobId, () => ({
        items: reset ? result.items : [...current.items, ...result.items],
        total: result.total,
        hasMore: result.hasMore,
        loading: false,
        error: ""
      }));
    } catch (caught) {
      setNodesForJob(jobId, (state) => ({
        ...state,
        loading: false,
        error: messageFor(caught, "Không tải được danh sách node.")
      }));
    }
  }

  async function loadEdges(jobId: string, reset = false) {
    const current = edgesByJob[jobId] ?? EMPTY_LAZY;
    setEdgesForJob(jobId, (state) => ({ ...state, loading: true, error: "" }));
    try {
      const offset = reset ? 0 : current.items.length;
      const result: ProposedEdgePage = await listGraphImportEdges(jobId, {
        limit: DETAIL_PAGE_SIZE,
        offset
      });
      setEdgesForJob(jobId, () => ({
        items: reset ? result.items : [...current.items, ...result.items],
        total: result.total,
        hasMore: result.hasMore,
        loading: false,
        error: ""
      }));
    } catch (caught) {
      setEdgesForJob(jobId, (state) => ({
        ...state,
        loading: false,
        error: messageFor(caught, "Không tải được danh sách edge.")
      }));
    }
  }

  function ensureNodesLoaded(jobId: string) {
    const state = nodesByJob[jobId];
    if (!state || (!state.loading && state.items.length === 0 && state.total === 0 && !state.error)) {
      void loadNodes(jobId, true);
    }
  }

  function ensureEdgesLoaded(jobId: string) {
    const state = edgesByJob[jobId];
    if (!state || (!state.loading && state.items.length === 0 && state.total === 0 && !state.error)) {
      void loadEdges(jobId, true);
    }
  }

  async function chooseJob(importId: string) {
    setError("");
    try {
      const meta = await getGraphImportMeta(importId);
      setSelected(meta);
      setSelectedNodeId("");
      setSelectedEdgeId("");
      setActiveTab("nodes");
      setShowCreate(false);
      ensureNodesLoaded(importId);
      ensureEdgesLoaded(importId);
    } catch (caught) {
      setError(messageFor(caught, "Không mở được AI import."));
    }
  }

  async function submitSource(event: FormEvent) {
    event.preventDefault();
    setError("");
    setCreating(true);
    try {
      const meta = await createGraphImport({
        sourceLabel: sourceLabel.trim(),
        ...(sourceUrl.trim() ? { sourceUrl: sourceUrl.trim() } : {}),
        content: content.trim()
      });
      setSelected(meta);
      setJobs((current) => {
        const summary: GraphImportSummary = {
          id: meta.id,
          sourceLabel: meta.sourceLabel,
          sourceUrl: meta.sourceUrl,
          status: meta.status,
          nodeCount: meta.nodeCount,
          edgeCount: meta.edgeCount,
          issueCount: meta.issueCount,
          createdAt: meta.createdAt,
          appliedAt: meta.appliedAt,
          errorMessage: meta.errorMessage
        };
        return [summary, ...current.filter((item) => item.id !== meta.id)];
      });
      setShowCreate(false);
      setSourceLabel("");
      setSourceUrl("");
      setContent("");
      ensureNodesLoaded(meta.id);
      ensureEdgesLoaded(meta.id);
    } catch (caught) {
      setError(messageFor(caught, "Không tạo được graph proposal."));
    } finally {
      setCreating(false);
    }
  }

  function applyNodeMutation(jobId: string, mutation: ProposedNodeMutation) {
    setSelected(mutation.meta);
    replaceSummary(mutation.summary);
    setNodesForJob(jobId, (state) => ({
      ...state,
      items: state.items.map((node) => (node.tempId === mutation.node.tempId ? mutation.node : node)),
      total: mutation.meta.nodeCount
    }));
  }

  function applyEdgeMutation(jobId: string, mutation: ProposedEdgeMutation) {
    setSelected(mutation.meta);
    replaceSummary(mutation.summary);
    setEdgesForJob(jobId, (state) => ({
      ...state,
      items: state.items.map((edge) => (edge.tempId === mutation.edge.tempId ? mutation.edge : edge)),
      total: mutation.meta.edgeCount
    }));
  }

  async function saveNode(node: ProposedGraphNode) {
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      const mutation = await updateProposedGraphNode(selected.id, node.tempId, {
        entityId: node.entityId,
        type: node.type,
        canonicalName: node.canonicalName,
        aliases: node.aliases,
        properties: node.properties,
        selectedEntityId: node.selectedEntityId,
        decision: node.decision
      });
      applyNodeMutation(selected.id, mutation);
    } catch (caught) {
      setError(messageFor(caught, "Không lưu được node proposal."));
    } finally {
      setSaving(false);
    }
  }

  async function saveEdge(edge: ProposedGraphEdge) {
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      const mutation = await updateProposedGraphEdge(selected.id, edge.tempId, {
        fromRef: edge.fromRef,
        relationship: edge.relationship,
        toRef: edge.toRef,
        recommendations: edge.recommendations,
        source: edge.source,
        decision: edge.decision
      });
      applyEdgeMutation(selected.id, mutation);
    } catch (caught) {
      setError(messageFor(caught, "Không lưu được edge proposal."));
    } finally {
      setSaving(false);
    }
  }

  async function applyApproved() {
    if (!selected || !window.confirm("Apply toàn bộ node và edge đã duyệt vào knowledge graph hiện tại?")) return;
    setSaving(true);
    setError("");
    try {
      const meta = await applyGraphImport(selected.id);
      setSelected(meta);
      replaceSummary(meta);
      onApplied();
    } catch (caught) {
      setError(messageFor(caught, "Không apply được graph proposal."));
    } finally {
      setSaving(false);
    }
  }

  async function revalidateSelected() {
    if (!selected || !window.confirm("Chạy lại matching theo graph hiện tại? Mọi quyết định trong job sẽ trở về Chưa duyệt.")) return;
    setSaving(true);
    setError("");
    try {
      const meta = await revalidateGraphImport(selected.id);
      setSelected(meta);
      replaceSummary(meta);
      await loadNodes(selected.id, true);
      await loadEdges(selected.id, true);
    } catch (caught) {
      setError(messageFor(caught, "Không revalidate được graph proposal."));
    } finally {
      setSaving(false);
    }
  }

  async function removeNode(tempId: string) {
    if (!selected) return;
    if (!window.confirm("Xóa node proposal này? Các edge liên quan cũng sẽ bị xóa.")) return;
    setSaving(true);
    setError("");
    try {
      await deleteProposedGraphNode(selected.id, tempId);
      const meta = await getGraphImportMeta(selected.id);
      setSelected(meta);
      replaceSummary(meta);
      await loadNodes(selected.id, true);
      await loadEdges(selected.id, true);
      if (selectedNodeId === tempId) setSelectedNodeId("");
    } catch (caught) {
      setError(messageFor(caught, "Không xóa được node proposal."));
    } finally {
      setSaving(false);
    }
  }

  async function removeEdge(tempId: string) {
    if (!selected) return;
    if (!window.confirm("Xóa edge proposal này?")) return;
    setSaving(true);
    setError("");
    try {
      await deleteProposedGraphEdge(selected.id, tempId);
      const meta = await getGraphImportMeta(selected.id);
      setSelected(meta);
      replaceSummary(meta);
      await loadEdges(selected.id, true);
      if (selectedEdgeId === tempId) setSelectedEdgeId("");
    } catch (caught) {
      setError(messageFor(caught, "Không xóa được edge proposal."));
    } finally {
      setSaving(false);
    }
  }

  async function removeSelectedJob() {
    if (!selected) return;
    if (!window.confirm(`Xóa import job "${selected.sourceLabel}"? Hành động này không thể hoàn tác.`)) return;
    setSaving(true);
    setError("");
    try {
      await deleteGraphImport(selected.id);
      setSelected(null);
      setSelectedNodeId("");
      setSelectedEdgeId("");
      setJobs((current) => current.filter((item) => item.id !== selected.id));
      setNodesByJob((current) => {
        const { [selected.id]: _removed, ...rest } = current;
        return rest;
      });
      setEdgesByJob((current) => {
        const { [selected.id]: _removed, ...rest } = current;
        return rest;
      });
    } catch (caught) {
      setError(messageFor(caught, "Không xóa được import job."));
    } finally {
      setSaving(false);
    }
  }

  function replaceSummary(meta: GraphImportSummary) {
    setJobs((current) => current.map((item) => (item.id === meta.id ? meta : item)));
  }

  const currentNodes: ProposedGraphNode[] = selected ? (nodesByJob[selected.id]?.items ?? []) : [];
  const currentEdges: ProposedGraphEdge[] = selected ? (edgesByJob[selected.id]?.items ?? []) : [];
  const nodesState = selected ? (nodesByJob[selected.id] ?? EMPTY_LAZY) : EMPTY_LAZY;
  const edgesState = selected ? (edgesByJob[selected.id] ?? EMPTY_LAZY) : EMPTY_LAZY;
  const selectedNode = currentNodes.find((item) => item.tempId === selectedNodeId) ?? null;
  const selectedEdge = currentEdges.find((item) => item.tempId === selectedEdgeId) ?? null;
  const approvedCount = useMemo(() => {
    const approved = [...currentNodes, ...currentEdges].filter((item) => item.decision.startsWith("approve_")).length;
    return approved > 0 ? approved : 0;
  }, [currentNodes, currentEdges]);

  function handleTabChange(tab: ReviewTab) {
    setActiveTab(tab);
    if (!selected) return;
    if (tab === "nodes") ensureNodesLoaded(selected.id);
    if (tab === "edges") ensureEdgesLoaded(selected.id);
  }

  return (
    <section className="kgAiWorkspace">
      <header className="kgAiHeader">
        <div><p className="eyebrow">Human-in-the-loop extraction</p><h2>AI Imports</h2><p>Gemini tạo proposal; rule matcher tìm bản ghi hiện có; admin là người quyết định cuối.</p></div>
        <button className="kgPrimaryButton" type="button" onClick={() => setShowCreate((value) => !value)}>＋ Nguồn mới</button>
      </header>

      {error && <div className="pageError kgAiError">{error}</div>}

      {showCreate && (
        <form className="kgAiSourceForm" onSubmit={submitSource}>
          <div className="kgAiFormTitle"><span>✦</span><div><b>Tạo graph proposal</b><p>Nguồn được coi là dữ liệu không tin cậy và không được quyền thay đổi schema.</p></div></div>
          <div className="kgAiFormGrid">
            <label><span>Nhãn nguồn</span><input required minLength={2} value={sourceLabel} onChange={(event) => setSourceLabel(event.target.value)} placeholder="Bài viết ẩm thực Hà Nội" /></label>
            <label><span>URL provenance (không bắt buộc)</span><input value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://..." /></label>
          </div>
          <label><span>Nội dung nguồn</span><textarea required minLength={20} maxLength={50000} value={content} onChange={(event) => setContent(event.target.value)} placeholder="Dán nội dung để AI trích xuất node và edge…" rows={9} /></label>
          <footer><small>{content.length.toLocaleString("vi-VN")} / 50.000 ký tự</small><button className="kgPrimaryButton" disabled={creating} type="submit">{creating ? "Gemini đang trích xuất…" : "✦ Tạo proposal"}</button></footer>
        </form>
      )}

      <div className="kgAiLayout">
        <aside className="kgAiJobList">
          <header>
            <span>
              Hiển thị <b>{jobs.length.toLocaleString("vi-VN")}</b> / {jobsTotal.toLocaleString("vi-VN")} import jobs
            </span>
            <button type="button" onClick={() => void reloadJobs()}>↻</button>
          </header>
          <div className="kgAiJobFilters">
            <input
              type="search"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Tìm theo nhãn hoặc ID…"
            />
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}>
              <option value="all">Tất cả trạng thái</option>
              <option value="needs_review">Needs review</option>
              <option value="applied">Applied</option>
              <option value="failed">Failed</option>
              <option value="extracting">Extracting</option>
            </select>
          </div>
          {loading && <p className="kgAiMuted">Đang tải imports…</p>}
          {!loading && jobs.length === 0 && <p className="kgAiMuted">Chưa có AI import.</p>}
          {jobs.map((job) => <button key={job.id} type="button" className={selected?.id === job.id ? "active" : ""} onClick={() => void chooseJob(job.id)}><div><span className={`status status-${job.status === "applied" ? "completed" : job.status === "failed" ? "failed" : "warning"}`}>{job.status.replaceAll("_", " ")}</span><time>{new Date(job.createdAt).toLocaleDateString("vi-VN")}</time></div><b>{job.sourceLabel}</b><p>{job.nodeCount} nodes · {job.edgeCount} edges · {job.issueCount} issues</p></button>)}
          {jobsHasMore && (
            <button type="button" className="kgSecondaryButton kgAiLoadMore" disabled={loadingMore} onClick={() => void loadMoreJobs()}>
              {loadingMore ? "Đang tải…" : `Tải thêm ${Math.min(PAGE_SIZE, jobsTotal - jobs.length)} jobs`}
            </button>
          )}
        </aside>

        <article className="kgAiReview">
          {!selected ? <div className="detailEmpty"><b>Chọn một import để review</b><p>Node, edge và matching result sẽ xuất hiện tại đây.</p></div> : <>
            <header className="kgAiReviewHeader"><div><p className="eyebrow">Proposal {selected.id.slice(0, 8)}</p><h3>{selected.sourceLabel}</h3><p>Schema {selected.schemaVersion} · Ontology {selected.ontologyVersion}</p></div><div><span className={`status status-${selected.status === "applied" ? "completed" : selected.status === "failed" ? "failed" : "warning"}`}>{selected.status.replaceAll("_", " ")}</span>{selected.status === "needs_review" && <><button className="kgSecondaryButton" disabled={saving} type="button" onClick={() => void revalidateSelected()}>↻ Revalidate</button><button className="kgPrimaryButton" disabled={saving || approvedCount === 0} type="button" onClick={() => void applyApproved()}>Apply {approvedCount} đã duyệt</button></>}<button className="kgDangerButton" disabled={saving} type="button" onClick={() => void removeSelectedJob()}>🗑 Xóa job</button></div></header>
            <nav className="kgAiTabs">{(["nodes", "edges", "source"] as ReviewTab[]).map((tab) => <button key={tab} type="button" className={activeTab === tab ? "active" : ""} onClick={() => handleTabChange(tab)}>{tab === "nodes" ? `Nodes (${nodesState.total || selected.nodeCount})` : tab === "edges" ? `Edges (${edgesState.total || selected.edgeCount})` : "Nguồn & warnings"}</button>)}</nav>

            {activeTab === "nodes" && <div className="kgAiReviewSplit"><div className="kgAiProposalList">{nodesState.error ? <p className="kgAiMuted">{nodesState.error}</p> : <ProposalNodeTable nodes={currentNodes} selectedId={selectedNodeId} onSelect={setSelectedNodeId} />}{nodesState.hasMore && <button type="button" className="kgSecondaryButton kgAiLoadMore" disabled={nodesState.loading} onClick={() => void loadNodes(selected.id, false)}>{nodesState.loading ? "Đang tải…" : `Tải thêm ${Math.min(DETAIL_PAGE_SIZE, nodesState.total - currentNodes.length)} nodes`}</button>}</div><div className="kgAiProposalInspector">{selectedNode ? <NodeEditor key={`${selectedNode.tempId}-${selectedNode.decision}-${selectedNode.canonicalName}`} node={selectedNode} nodeTypes={nodeTypes} nodeTypeProperties={nodeTypeProperties} saving={saving} onSave={saveNode} onDelete={removeNode} /> : <InspectorEmpty label="Chọn node để xem matching và chỉnh sửa" />}</div></div>}
            {activeTab === "edges" && <div className="kgAiReviewSplit"><div className="kgAiProposalList">{edgesState.error ? <p className="kgAiMuted">{edgesState.error}</p> : <ProposalEdgeTable edges={currentEdges} nodes={currentNodes} selectedId={selectedEdgeId} onSelect={setSelectedEdgeId} />}{edgesState.hasMore && <button type="button" className="kgSecondaryButton kgAiLoadMore" disabled={edgesState.loading} onClick={() => void loadEdges(selected.id, false)}>{edgesState.loading ? "Đang tải…" : `Tải thêm ${Math.min(DETAIL_PAGE_SIZE, edgesState.total - currentEdges.length)} edges`}</button>}</div><div className="kgAiProposalInspector">{selectedEdge ? <EdgeEditor key={`${selectedEdge.tempId}-${selectedEdge.decision}-${selectedEdge.relationship}`} edge={selectedEdge} nodes={currentNodes} relationshipTypes={relationshipTypes} saving={saving} onSave={saveEdge} onDelete={removeEdge} /> : <InspectorEmpty label="Chọn edge để xem và chỉnh sửa" />}</div></div>}
            {activeTab === "source" && <div className="kgAiSourceReview"><div><h4>Nguồn</h4>{selected.sourceUrl && <a href={selected.sourceUrl} target="_blank" rel="noreferrer">{selected.sourceUrl}</a>}<pre>{selected.sourceContent}</pre></div><div><h4>Warnings</h4>{selected.warnings.length ? selected.warnings.map((warning) => <p key={warning}>△ {warning}</p>) : <p className="kgAiMuted">Không có warning từ extractor.</p>}</div></div>}
          </>}
        </article>
      </div>
    </section>
  );
}

function ProposalNodeTable({ nodes, selectedId, onSelect }: { nodes: ProposedGraphNode[]; selectedId: string; onSelect: (id: string) => void }) {
  return <table className="kgAiCompactTable"><thead><tr><th>Node</th><th>Match</th><th>Decision</th></tr></thead><tbody>{nodes.map((node) => <tr key={node.tempId} className={selectedId === node.tempId ? "active" : ""} onClick={() => onSelect(node.tempId)}><td><b>{node.canonicalName}</b><small>{node.type} · {node.entityId}</small></td><td><MatchBadge status={node.matchStatus} /></td><td><DecisionBadge decision={node.decision} /></td></tr>)}</tbody></table>;
}

function ProposalEdgeTable({ edges, nodes, selectedId, onSelect }: { edges: ProposedGraphEdge[]; nodes: ProposedGraphNode[]; selectedId: string; onSelect: (id: string) => void }) {
  const name = (ref: string) => nodes.find((node) => node.tempId === ref)?.canonicalName ?? ref;
  return <table className="kgAiCompactTable"><thead><tr><th>Edge</th><th>Match</th><th>Decision</th></tr></thead><tbody>{edges.map((edge) => <tr key={edge.tempId} className={selectedId === edge.tempId ? "active" : ""} onClick={() => onSelect(edge.tempId)}><td><b>{name(edge.fromRef)} → {name(edge.toRef)}</b><small>{edge.relationship}</small></td><td><MatchBadge status={edge.matchStatus} /></td><td><DecisionBadge decision={edge.decision} /></td></tr>)}</tbody></table>;
}

function NodeEditor({ node, nodeTypes, nodeTypeProperties, saving, onSave, onDelete }: { node: ProposedGraphNode; nodeTypes: string[]; nodeTypeProperties: Record<string, { requiredProperties: string[]; optionalProperties: string[] }>; saving: boolean; onSave: (node: ProposedGraphNode) => Promise<void>; onDelete: (tempId: string) => Promise<void> }) {
  const [draft, setDraft] = useState(node);
  const [aliases, setAliases] = useState(node.aliases.join("\n"));
  const [properties, setProperties] = useState(JSON.stringify(node.properties, null, 2));
  const [error, setError] = useState("");
  const parsedProperties = parseProperties(properties);
  const schemaProperties = nodeTypeProperties[draft.type];
  const requiredProperties = uniqueProperties(
    schemaProperties?.requiredProperties ?? [],
    node.requiredProperties ?? []
  );
  const optionalProperties = uniqueProperties(
    schemaProperties?.optionalProperties ?? [],
    node.optionalProperties ?? []
  ).filter((key) => !requiredProperties.includes(key));
  const displayedProperties = parsedProperties ?? node.properties;
  const missingRequiredCount = requiredProperties.filter(
    (key) => !String(displayedProperties[key] ?? "").trim()
  ).length;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!parsedProperties) {
      setError("Properties JSON không hợp lệ.");
      return;
    }
    const missing = requiredProperties.filter((key) => !String(parsedProperties[key] ?? "").trim());
    if (missing.length > 0) {
      setError(`Thiếu trường bắt buộc: ${missing.join(", ")}`);
      return;
    }
    setError("");
    await onSave({
      ...draft,
      aliases: aliases.split("\n").map((item) => item.trim()).filter(Boolean),
      properties: parsedProperties
    });
  }

  function updateProperty(key: string, value: string) {
    const next = { ...(parsedProperties ?? node.properties), [key]: value };
    setProperties(JSON.stringify(next, null, 2));
  }

  function ruleLabel(rule: string) {
    if (rule === "name_exact") return "Name trùng khớp";
    if (rule === "alias_exact") return "Alias trùng khớp";
    if (rule.startsWith("name_similarity:")) return `Name tương tự ${(parseFloat(rule.split(":")[1]) * 100).toFixed(0)}%`;
    return rule;
  }
  return <form className="kgAiInspectorForm" onSubmit={submit}><header><div><p className="eyebrow">Proposed node</p><h4>{draft.canonicalName}</h4></div><div className="kgAiInspectorHeaderRight"><MatchBadge status={node.matchStatus} /><span className="kgAiConfidence">{Math.round(node.confidence * 100)}%</span></div></header>{node.validationIssues.length > 0 && <div className="kgAiIssues">{node.validationIssues.map((issue) => <p key={issue}>! {issue}</p>)}</div>}<div className="kgAiInspectorGrid"><label><span>Entity ID <i className="kgAiRequired">*</i></span><input required value={draft.entityId} onChange={(event) => setDraft((current) => ({ ...current, entityId: event.target.value }))} /></label><label><span>Canonical name <i className="kgAiRequired">*</i></span><input required value={draft.canonicalName} onChange={(event) => setDraft((current) => ({ ...current, canonicalName: event.target.value }))} /></label></div><label><span>Node type <i className="kgAiRequired">*</i></span><select required value={draft.type} onChange={(event) => setDraft((current) => ({ ...current, type: event.target.value }))}>{nodeTypes.map((type) => <option key={type}>{type}</option>)}</select></label><label><span>Aliases · mỗi dòng một alias</span><textarea rows={3} value={aliases} onChange={(event) => setAliases(event.target.value)} /></label><div className="kgAiPropertySection"><h5>Trường bắt buộc <span className="kgAiRequired">*</span><span className={missingRequiredCount ? "kgAiFieldMissingCount" : "kgAiFieldComplete"}>{missingRequiredCount ? `${missingRequiredCount} thiếu` : "Đã đủ"}</span></h5><div className="kgAiPropertyGrid">{requiredProperties.map((key) => <PropertyField key={key} name={key} value={String(displayedProperties[key] ?? "")} required onChange={updateProperty} />)}</div></div><div className="kgAiPropertySection"><h5>Trường tùy chọn <span className="kgAiOptional">Nên nhập</span></h5><div className="kgAiPropertyGrid">{optionalProperties.map((key) => <PropertyField key={key} name={key} value={String(displayedProperties[key] ?? "")} onChange={updateProperty} />)}</div></div><label><span>Properties JSON</span><textarea className="mono" rows={5} value={properties} onChange={(event) => setProperties(event.target.value)} /></label><div className="kgAiEvidence"><b>Evidence</b>{node.evidence.map((value) => <blockquote key={value}>{value}</blockquote>)}</div>{node.matchCandidates.length > 0 && <div className="kgAiMatchCandidates"><h5>Entity hiện có</h5><div className="kgAiCandidateList">{node.matchCandidates.map((candidate) => <div key={candidate.entityId} className={`kgAiCandidate ${draft.selectedEntityId === candidate.entityId ? "selected" : ""}`} onClick={() => setDraft((current) => ({ ...current, selectedEntityId: candidate.entityId }))}><div className="kgAiCandidateHeader"><b>{candidate.canonicalName}</b><span className="kgAiScore">{candidate.score}</span></div><div className="kgAiCandidateMeta"><code>{candidate.entityId}</code><span>{candidate.type}</span></div><div className="kgAiCandidateRules">{candidate.matchedRules.map((rule) => <span key={rule} className="kgAiRuleTag">{ruleLabel(rule)}</span>)}</div></div>)}</div></div>}<label><span>Quyết định</span><select value={draft.decision} onChange={(event) => setDraft((current) => ({ ...current, decision: event.target.value as ProposedGraphNode["decision"] }))}><option value="pending">Chưa quyết định</option><option value="approve_create">Duyệt tạo mới</option><option value="approve_existing">Dùng entity hiện có</option><option value="reject">Từ chối</option></select></label>{error && <p className="kgAiFormError">{error}</p>}<footer className="kgAiInspectorFooter"><button className="kgDangerButton" type="button" disabled={saving} onClick={() => void onDelete(node.tempId)}>🗑 Xóa node</button><button className="kgPrimaryButton" disabled={saving} type="submit">{saving ? "Đang lưu…" : "Lưu & chạy lại matching"}</button></footer></form>;
}

function PropertyField({ name, value, required = false, onChange }: { name: string; value: string; required?: boolean; onChange: (name: string, value: string) => void }) {
  const missing = required && !value.trim();
  return <label className={missing ? "kgAiPropertyMissing" : ""}><span>{name}{missing && <em>Thiếu</em>}</span><input required={required} aria-invalid={missing} value={value} onChange={(event) => onChange(name, event.target.value)} placeholder={`Nhập ${name}…`} /></label>;
}

function parseProperties(value: string): Record<string, string> | null {
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    return parsed as Record<string, string>;
  } catch {
    return null;
  }
}

function uniqueProperties(...groups: string[][]): string[] {
  return [...new Set(groups.flat())].sort();
}

function EdgeEditor({ edge, nodes, relationshipTypes, saving, onSave, onDelete }: { edge: ProposedGraphEdge; nodes: ProposedGraphNode[]; relationshipTypes: string[]; saving: boolean; onSave: (edge: ProposedGraphEdge) => Promise<void>; onDelete: (tempId: string) => Promise<void> }) {
  const [draft, setDraft] = useState(edge);
  const [recommendations, setRecommendations] = useState(JSON.stringify(edge.recommendations, null, 2));
  const [error, setError] = useState("");
  return <form className="kgAiInspectorForm" onSubmit={(event) => { event.preventDefault(); try { const parsed = JSON.parse(recommendations); if (!Array.isArray(parsed)) throw new Error(); setError(""); void onSave({ ...draft, recommendations: parsed }); } catch { setError("Recommendations phải là JSON array hợp lệ."); } }}><header><div><p className="eyebrow">Proposed edge</p><h4>{draft.relationship}</h4></div><div className="kgAiInspectorHeaderRight"><MatchBadge status={edge.matchStatus} /><span className="kgAiConfidence">{Math.round(edge.confidence * 100)}%</span></div></header>{edge.validationIssues.length > 0 && <div className="kgAiIssues">{edge.validationIssues.map((issue) => <p key={issue}>! {issue}</p>)}</div>}<label><span>From node</span><select value={draft.fromRef} onChange={(event) => setDraft((current) => ({ ...current, fromRef: event.target.value }))}>{nodes.map((node) => <option key={node.tempId} value={node.tempId}>{node.canonicalName} · {node.type}</option>)}</select></label><label><span>Relationship</span><select value={draft.relationship} onChange={(event) => setDraft((current) => ({ ...current, relationship: event.target.value }))}>{relationshipTypes.map((type) => <option key={type}>{type}</option>)}</select></label><label><span>To node</span><select value={draft.toRef} onChange={(event) => setDraft((current) => ({ ...current, toRef: event.target.value }))}>{nodes.map((node) => <option key={node.tempId} value={node.tempId}>{node.canonicalName} · {node.type}</option>)}</select></label><label><span>Recommendations JSON</span><textarea className="mono" rows={6} value={recommendations} onChange={(event) => setRecommendations(event.target.value)} /></label><label><span>Nguồn</span><input value={draft.source} onChange={(event) => setDraft((current) => ({ ...current, source: event.target.value }))} /></label><div className="kgAiEvidence"><b>Evidence</b>{edge.evidence.map((value) => <blockquote key={value}>{value}</blockquote>)}</div><label><span>Quyết định</span><select value={draft.decision} onChange={(event) => setDraft((current) => ({ ...current, decision: event.target.value as ProposedGraphEdge["decision"] }))}><option value="pending">Chưa quyết định</option><option value="approve_create">Duyệt tạo edge</option><option value="approve_existing">Edge đã tồn tại · thêm nguồn</option><option value="reject">Từ chối</option></select></label>{error && <p className="kgAiFormError">{error}</p>}<footer className="kgAiInspectorFooter"><button className="kgDangerButton" type="button" disabled={saving} onClick={() => void onDelete(edge.tempId)}>🗑 Xóa edge</button><button className="kgPrimaryButton" disabled={saving} type="submit">{saving ? "Đang lưu…" : "Lưu & validate lại"}</button></footer></form>;
}

function MatchBadge({ status }: { status: string }) { const tone = status === "existing" ? "completed" : status === "new" ? "running" : "warning"; return <span className={`status status-${tone}`}>{status.replaceAll("_", " ")}</span>; }
function DecisionBadge({ decision }: { decision: string }) { const tone = decision.startsWith("approve_") ? "completed" : decision === "reject" ? "failed" : "draft"; return <span className={`status status-${tone}`}>{decision.replaceAll("_", " ")}</span>; }
function InspectorEmpty({ label }: { label: string }) { return <div className="kgAiInspectorEmpty"><span>◇</span><p>{label}</p></div>; }
function messageFor(caught: unknown, fallback: string) { return caught instanceof APIError || caught instanceof Error ? caught.message : fallback; }
