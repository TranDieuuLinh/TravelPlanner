"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  getKGOntology,
  getKGStats,
  listKGEntities,
  getKGEntityDetail,
  type KGStats,
  type KGEntitySummary,
  type KGEntityDetail,
  type KGOntology,
} from "../../../lib/api";
import { KnowledgeGraphAIImports } from "../../components/KnowledgeGraphAIImports";

type WorkspaceTab = "entities" | "aiImports";

const TABS: Array<{ id: WorkspaceTab; label: string }> = [
  { id: "entities", label: "Entities" },
  { id: "aiImports", label: "AI Imports" },
];

const DEFAULT_PAGE_SIZE = 50;
const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;

export default function KnowledgeGraphPage() {
  const [stats, setStats] = useState<KGStats | null>(null);
  const [ontology, setOntology] = useState<KGOntology | null>(null);
  const [entities, setEntities] = useState<KGEntitySummary[]>([]);
  const [selectedEntity, setSelectedEntity] = useState<KGEntityDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [loadingEntities, setLoadingEntities] = useState(false);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("entities");
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [entityType, setEntityType] = useState("");
  const [status, setStatus] = useState("");
  const [refreshVersion, setRefreshVersion] = useState(0);
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounced search
  useEffect(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    searchTimeoutRef.current = setTimeout(() => {
      if (searchInput !== search) {
        setSearch(searchInput);
        setPage(0);
      }
    }, 300);
    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, [searchInput]);

  // Load stats
  const loadStats = useCallback(async () => {
    try {
      const data = await getKGStats();
      setStats(data);
    } catch (err) {
      console.error("Failed to load stats:", err);
    }
  }, []);

  // Load ontology (node types, relationship types, property definitions)
  const loadOntology = useCallback(async () => {
    try {
      const data = await getKGOntology();
      setOntology(data);
    } catch (err) {
      console.error("Failed to load ontology:", err);
    }
  }, []);

  // Initial load
  useEffect(() => {
    loadStats();
    loadOntology();
  }, [loadStats, loadOntology]);

  // Fetch exactly one server-side page. Old requests are cancelled when filters change.
  useEffect(() => {
    const controller = new AbortController();
    setLoadingEntities(true);
    setError("");

    listKGEntities({
      limit: pageSize,
      offset: page * pageSize,
      search: search || undefined,
      entityType: entityType || undefined,
      status: status || undefined,
      signal: controller.signal,
    })
      .then((data) => {
        setEntities(data.items);
        setTotal(data.total);
        setSelectedEntity(null);
      })
      .catch((err) => {
        if (err instanceof Error && err.name !== "AbortError") {
          setError(err.message || "Failed to load entities");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoadingEntities(false);
          setLoading(false);
        }
      });

    return () => controller.abort();
  }, [page, pageSize, search, entityType, status, refreshVersion]);

  // Load entity detail
  const loadEntityDetail = useCallback(async (entityId: string) => {
    setLoadingDetail(true);
    setSelectedEntity(null);
    try {
      const data = await getKGEntityDetail(entityId);
      setSelectedEntity(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load entity detail");
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  // Handle entity selection
  const handleSelectEntity = useCallback((entity: KGEntitySummary) => {
    setSelectedEntity(null);
    loadEntityDetail(entity.id);
  }, [loadEntityDetail]);

  // Handle search change
  const handleSearchChange = useCallback((value: string) => {
    setSearchInput(value);
  }, []);

  // Refresh after AI import apply
  const handleApplied = useCallback(() => {
    loadStats();
    setPage(0);
    setRefreshVersion((value) => value + 1);
  }, [loadStats]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const rangeStart = total === 0 ? 0 : page * pageSize + 1;
  const rangeEnd = Math.min((page + 1) * pageSize, total);
  const hasFilters = Boolean(searchInput || entityType || status);

  const clearFilters = useCallback(() => {
    setSearchInput("");
    setSearch("");
    setEntityType("");
    setStatus("");
    setPage(0);
  }, []);

  return (
    <section className="kgPage">
      <header className="topbar kgTopbar">
        <div>
          <p className="eyebrow">Catalog intelligence</p>
          <h1>Knowledge Graph</h1>
          <p className="kgLead">
            Quản lý entity, alias và ontology từ PostgreSQL backend.
          </p>
        </div>
      </header>

      <section className="kgSourceStrip" aria-label="Data source">
        <div>
          <span className="kgPulse" />
          <span>
            <b>PostgreSQL Backend</b>
            <small>Knowledge Graph runtime database</small>
          </span>
        </div>
        <div className="kgSourceMeta">
          <span>API-driven pagination</span>
        </div>
      </section>

      {error && (
        <div className="kgNotice" role="alert">
          <span>!</span>
          <p>{error}</p>
          <button type="button" aria-label="Dismiss error" onClick={() => setError("")}>×</button>
        </div>
      )}

      {/* Stats */}
      <section className="metricGrid kgMetrics" aria-label="Knowledge graph metrics">
        <article>
          <span>Entities</span>
          <strong>{stats?.entityCount ?? "—"}</strong>
          <small>Total entities in database</small>
        </article>
        <article>
          <span>Aliases</span>
          <strong>{stats?.aliasCount ?? "—"}</strong>
          <small>Entity name aliases</small>
        </article>
        <article>
          <span>Relationships</span>
          <strong>{stats?.relationshipCount ?? "—"}</strong>
          <small>Graph edges</small>
        </article>
      </section>

      {/* Tabs */}
      <nav className="kgWorkspaceTabs" aria-label="Knowledge graph sections">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={activeTab === tab.id ? "active" : ""}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* AI Imports Tab */}
      {activeTab === "aiImports" && (
        <KnowledgeGraphAIImports
          nodeTypes={ontology?.nodeTypes ?? []}
          nodeTypeProperties={ontology?.nodeTypeProperties ?? {}}
          relationshipTypes={ontology?.relationshipTypes ?? []}
          onApplied={handleApplied}
        />
      )}

      {/* Entities Tab */}
      {activeTab === "entities" && (
        <>
          {/* Search Bar */}
          <section className="controlBar kgControlBar">
            <label className="searchField">
              <span>⌕</span>
              <input
                type="search"
                value={searchInput}
                onChange={(e) => handleSearchChange(e.target.value)}
                placeholder="Search by name or ID..."
              />
            </label>
            <label className="kgFilterField">
              <span>Node type</span>
              <select
                value={entityType}
                onChange={(event) => {
                  setEntityType(event.target.value);
                  setPage(0);
                }}
              >
                <option value="">All types</option>
                {(ontology?.nodeTypes ?? []).map((type) => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
            </label>
            <label className="kgFilterField">
              <span>Status</span>
              <select
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value);
                  setPage(0);
                }}
              >
                <option value="">All statuses</option>
                <option value="draft">Draft</option>
                <option value="verified">Verified</option>
              </select>
            </label>
            <label className="kgFilterField kgPageSizeField">
              <span>Rows</span>
              <select
                value={pageSize}
                onChange={(event) => {
                  setPageSize(Number(event.target.value));
                  setPage(0);
                }}
              >
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <option key={size} value={size}>{size} / page</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="kgClearFilters"
              onClick={clearFilters}
              disabled={!hasFilters}
            >
              Clear
            </button>
            <span className="kgResultCount">
              {loadingEntities
                ? "Querying PostgreSQL..."
                : `${rangeStart.toLocaleString()}–${rangeEnd.toLocaleString()} of ${total.toLocaleString()}`}
            </span>
          </section>

          {/* Entity List and Detail Layout */}
          <section className="dataLayout kgDataLayout">
            {/* Entity List */}
            <div className="runList kgEntityList">
              <header>
                <span>Page {page + 1} of {totalPages.toLocaleString()}</span>
                {(search || entityType || status) && <small>Server-side query</small>}
              </header>

              {loadingEntities ? (
                <div className="emptyState">
                  <b>Querying entities...</b>
                  <p>Only the requested page is loaded into the browser.</p>
                </div>
              ) : entities.length === 0 ? (
                <div className="emptyState">
                  <b>No entities found</b>
                  <p>Try a different search term or adjust filters.</p>
                </div>
              ) : (
                <>
                  {entities.map((entity) => (
                    <button
                      key={entity.id}
                      type="button"
                      className={selectedEntity?.id === entity.id ? "kgEntityCard active" : "kgEntityCard"}
                      onClick={() => handleSelectEntity(entity)}
                    >
                      <div className="kgEntityCardTop">
                        <span className={`kgNodeType kgNode-${(entity.entityType || "unknown").toLowerCase()}`}>
                          {entity.entityType || "Unknown"}
                        </span>
                        <span className={`status status-${entity.status === "missing" ? "failed" : entity.status}`}>
                          {entity.status}
                        </span>
                      </div>
                      <h3>{entity.canonicalName}</h3>
                      <code>{entity.id}</code>
                    </button>
                  ))}

                  <nav className="kgPagination" aria-label="Entity pages">
                    <button type="button" onClick={() => setPage(0)} disabled={page === 0}>First</button>
                    <button type="button" onClick={() => setPage((value) => Math.max(0, value - 1))} disabled={page === 0}>Previous</button>
                    <span>{rangeStart.toLocaleString()}–{rangeEnd.toLocaleString()}</span>
                    <button type="button" onClick={() => setPage((value) => Math.min(totalPages - 1, value + 1))} disabled={page >= totalPages - 1}>Next</button>
                    <button type="button" onClick={() => setPage(totalPages - 1)} disabled={page >= totalPages - 1}>Last</button>
                  </nav>
                </>
              )}
            </div>

            {/* Entity Detail Panel */}
            <div className="detailPane kgInspector">
              {loadingDetail ? (
                <div className="detailLoading">
                  <b>Loading entity detail...</b>
                </div>
              ) : selectedEntity ? (
                <EntityDetailPanel entity={selectedEntity} />
              ) : (
                <div className="detailEmpty">
                  <b>Select an entity to view details</b>
                  <p>Click on an entity from the list to see its aliases, properties, and relationships.</p>
                </div>
              )}
            </div>
          </section>
        </>
      )}

      <footer className="kgFooter">
        <p>
          Knowledge Graph data is stored in PostgreSQL. Entity and relationship management
          is handled through the admin API with pagination.
        </p>
      </footer>
    </section>
  );
}

// Entity Detail Panel Component
function EntityDetailPanel({ entity }: { entity: KGEntityDetail }) {
  return (
    <>
      <header className="detailHeader kgInspectorHeader">
        <div>
          <p className="eyebrow">Entity Detail</p>
          <h2>{entity.canonicalName}</h2>
          <p>{entity.id}</p>
        </div>
        <span className={`status status-${entity.status === "missing" ? "failed" : entity.status}`}>
          {entity.status}
        </span>
      </header>

      <div className="kgInspectorBody kgInspectorAll">
        {/* Basic Info */}
        <section className="kgDefinitionList kgInspectorSection">
          <header><h3>Information</h3></header>
          <dl>
            <div><dt>Entity ID</dt><dd><code>{entity.id}</code></dd></div>
            <div><dt>Canonical Name</dt><dd>{entity.canonicalName}</dd></div>
            <div><dt>Type</dt><dd>{entity.entityType}</dd></div>
            <div><dt>Status</dt><dd>{entity.status}</dd></div>
            <div><dt>Created</dt><dd>{new Date(entity.createdAt).toLocaleString()}</dd></div>
            <div><dt>Updated</dt><dd>{new Date(entity.updatedAt).toLocaleString()}</dd></div>
          </dl>
        </section>

        {/* Aliases */}
        <section className="kgInspectorSection">
          <header>
            <h3>Aliases</h3>
            <span className="kgSectionCount">{entity.aliasTotal}</span>
          </header>
          {entity.aliases.length > 0 ? (
            <div className="kgAliasCards">
              {entity.aliases.map((alias, index) => (
                <article key={alias.id}>
                  <span>{index + 1}</span>
                  <div>
                    <b>{alias.alias}</b>
                    <small>{alias.language.toUpperCase()}</small>
                  </div>
                </article>
              ))}
              {entity.aliasHasMore && (
                <p className="kgMoreIndicator">
                  +{entity.aliasTotal - entity.aliases.length} more aliases
                </p>
              )}
            </div>
          ) : (
            <div className="kgInspectorEmpty kgInspectorEmptyCompact">
              <span>◇</span><b>No aliases</b>
            </div>
          )}
        </section>

        {/* Properties */}
        <section className="kgInspectorSection">
          <header>
            <h3>Properties</h3>
            <span className="kgSectionCount">{entity.propertyTotal}</span>
          </header>
          {entity.properties.length > 0 ? (
            <div className="kgPropertyTableWrap">
              <table className="kgPropertyTable">
                <thead>
                  <tr>
                    <th>Key</th>
                    <th>Value</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {entity.properties.map((prop) => (
                    <tr key={prop.id}>
                      <td><code>{prop.key}</code></td>
                      <td>{prop.value || <span className="kgMissingText">Empty</span>}</td>
                      <td>{prop.source || <span className="kgMissingText">Unknown</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {entity.propertyHasMore && (
                <p className="kgMoreIndicator">
                  +{entity.propertyTotal - entity.properties.length} more properties
                </p>
              )}
            </div>
          ) : (
            <div className="kgInspectorEmpty kgInspectorEmptyCompact">
              <span>◇</span><b>No properties</b>
            </div>
          )}
        </section>

        {/* Relationships */}
        <section className="kgInspectorSection">
          <header>
            <h3>Relationships</h3>
            <span className="kgSectionCount">{entity.relationshipTotal}</span>
          </header>
          {entity.relationships.length > 0 ? (
            <div className="kgRelationCards">
              {entity.relationships.map((rel) => (
                <article key={rel.id}>
                  <span className="kgRelationDirection">
                    {rel.fromEntityId === entity.id ? "OUT" : "IN"}
                  </span>
                  <div>
                    <code>{rel.relationship}</code>
                    <small>
                      {rel.fromEntityId === entity.id
                        ? `${entity.id} → ${rel.toEntityId}`
                        : `${rel.fromEntityId} → ${entity.id}`}
                    </small>
                  </div>
                </article>
              ))}
              {entity.relationshipHasMore && (
                <p className="kgMoreIndicator">
                  +{entity.relationshipTotal - entity.relationships.length} more relationships
                </p>
              )}
            </div>
          ) : (
            <div className="kgInspectorEmpty kgInspectorEmptyCompact">
              <span>◇</span><b>No relationships</b>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
