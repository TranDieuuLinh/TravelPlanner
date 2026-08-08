"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  getKGStats,
  listKGEntities,
  getKGEntityDetail,
  listKGRelationships,
  getKGOntology,
  updateKGEntity,
  createKGAlias,
  updateKGAlias,
  deleteKGAlias,
  createKGProperty,
  updateKGProperty,
  deleteKGProperty,
  createKGRelationship,
  updateKGRelationship,
  deleteKGRelationship,
  deleteKGEntity,
  createKGEntity,
  copyKGEntity,
  deleteKGLowReviewEntities,
  getKGLowReviewEntityCount,
  type KGStats,
  type KGEntitySummary,
  type KGEntityDetail,
  type KGRelationshipSummary,
  type KGOntology,
} from "../../../lib/api";
import { KnowledgeGraphAIImports } from "../../components/KnowledgeGraphAIImports";

type WorkspaceTab = "entities" | "relationships" | "aiImports";

const TABS: Array<{ id: WorkspaceTab; label: string }> = [
  { id: "entities", label: "Entities" },
  { id: "relationships", label: "Relationships" },
  { id: "aiImports", label: "AI Imports" },
];

const DEFAULT_PAGE_SIZE = 50;

// Common quick entity types for pill selection
const QUICK_ENTITY_TYPES = [
  "Destination",
  "Attraction",
  "Hotel",
  "Restaurant",
  "Activity",
  "Topic",
  "Tag",
];

export default function KnowledgeGraphPage() {
  const [stats, setStats] = useState<KGStats | null>(null);
  const [ontology, setOntology] = useState<KGOntology | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<KGEntityDetail | null>(null);
  const [entityToDelete, setEntityToDelete] = useState<KGEntityDetail | null>(null);
  const [deletingEntity, setDeletingEntity] = useState(false);
  const [lowReviewEntityCount, setLowReviewEntityCount] = useState<number | null>(null);
  const [loadingLowReviewPreview, setLoadingLowReviewPreview] = useState(false);
  const [deletingLowReviewEntities, setDeletingLowReviewEntities] = useState(false);
  const [creatingEntity, setCreatingEntity] = useState(false);
  const [createEntityOpen, setCreateEntityOpen] = useState(false);
  const [newEntity, setNewEntity] = useState({ entityId: "", canonicalName: "", entityType: "", status: "draft" });
  const [copyEntityOpen, setCopyEntityOpen] = useState(false);
  const [copyEntityId, setCopyEntityId] = useState("");
  const [copyEntityName, setCopyEntityName] = useState("");
  const [copyingEntity, setCopyingEntity] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("entities");

  // --- Entities Tab State ---
  const [entities, setEntities] = useState<KGEntitySummary[]>([]);
  const [loadingEntities, setLoadingEntities] = useState(false);
  const [totalEntities, setTotalEntities] = useState(0);
  const [entityOffset, setEntityOffset] = useState(0);
  const [entityPage, setEntityPage] = useState(1);
  const [hasMoreEntities, setHasMoreEntities] = useState(false);

  // Entity filters
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [entityTypeFilter, setEntityTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [excludeNames, setExcludeNames] = useState("");
  const [entitySortBy, setEntitySortBy] = useState("name");
  const [entitySortDirection, setEntitySortDirection] = useState<"asc" | "desc">("asc");

  // --- Relationships Tab State ---
  const [relationships, setRelationships] = useState<KGRelationshipSummary[]>([]);
  const [loadingRelationships, setLoadingRelationships] = useState(false);
  const [totalRelationships, setTotalRelationships] = useState(0);
  const [relOffset, setRelOffset] = useState(0);
  const [relPage, setRelPage] = useState(1);
  const [hasMoreRelationships, setHasMoreRelationships] = useState(false);

  // Relationship filters
  const [relSearch, setRelSearch] = useState("");
  const [relSearchInput, setRelSearchInput] = useState("");
  const [relTypeFilter, setRelTypeFilter] = useState("");
  const [fromEntityFilter, setFromEntityFilter] = useState("");
  const [fromEntityInput, setFromEntityInput] = useState("");
  const [toEntityFilter, setToEntityFilter] = useState("");
  const [toEntityInput, setToEntityInput] = useState("");
  const [relationshipSortBy, setRelationshipSortBy] = useState("id");
  const [relationshipSortDirection, setRelationshipSortDirection] = useState<"asc" | "desc">("asc");

  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const relSearchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fromEntityTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toEntityTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Debounced search for Entities
  useEffect(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    searchTimeoutRef.current = setTimeout(() => {
      if (searchInput !== search) {
        setSearch(searchInput);
        setEntityPage(1);
        setEntityOffset(0);
        setEntities([]);
      }
    }, 300);
    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, [searchInput, search]);

  // Debounced search & inputs for Relationships
  useEffect(() => {
    if (relSearchTimeoutRef.current) clearTimeout(relSearchTimeoutRef.current);
    relSearchTimeoutRef.current = setTimeout(() => {
      if (relSearchInput !== relSearch) {
        setRelSearch(relSearchInput);
        setRelPage(1);
        setRelOffset(0);
        setRelationships([]);
      }
    }, 300);
    return () => {
      if (relSearchTimeoutRef.current) clearTimeout(relSearchTimeoutRef.current);
    };
  }, [relSearchInput, relSearch]);

  useEffect(() => {
    if (fromEntityTimeoutRef.current) clearTimeout(fromEntityTimeoutRef.current);
    fromEntityTimeoutRef.current = setTimeout(() => {
      if (fromEntityInput !== fromEntityFilter) {
        setFromEntityFilter(fromEntityInput);
        setRelPage(1);
        setRelOffset(0);
        setRelationships([]);
      }
    }, 300);
    return () => {
      if (fromEntityTimeoutRef.current) clearTimeout(fromEntityTimeoutRef.current);
    };
  }, [fromEntityInput, fromEntityFilter]);

  useEffect(() => {
    if (toEntityTimeoutRef.current) clearTimeout(toEntityTimeoutRef.current);
    toEntityTimeoutRef.current = setTimeout(() => {
      if (toEntityInput !== toEntityFilter) {
        setToEntityFilter(toEntityInput);
        setRelPage(1);
        setRelOffset(0);
        setRelationships([]);
      }
    }, 300);
    return () => {
      if (toEntityTimeoutRef.current) clearTimeout(toEntityTimeoutRef.current);
    };
  }, [toEntityInput, toEntityFilter]);

  // Load stats
  const loadStats = useCallback(async () => {
    try {
      const data = await getKGStats();
      setStats(data);
    } catch (err) {
      console.error("Failed to load stats:", err);
    }
  }, []);

  // Load ontology
  const loadOntology = useCallback(async () => {
    try {
      const data = await getKGOntology();
      setOntology(data);
    } catch (err) {
      console.error("Failed to load ontology:", err);
    }
  }, []);

  // Load entities
  const loadEntities = useCallback(
    async (
      currentOffset: number,
      currentSearch: string,
      currentType: string,
      currentStatus: string,
      currentExcludeNames: string,
      currentSortBy: string,
      currentSortDirection: "asc" | "desc",
      append = false
    ) => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();

      setLoadingEntities(true);
      try {
        const data = await listKGEntities({
          limit: DEFAULT_PAGE_SIZE,
          offset: currentOffset,
          search: currentSearch || undefined,
          entityType: currentType || undefined,
          status: currentStatus || undefined,
          excludeNames: currentExcludeNames || undefined,
          sortBy: currentSortBy,
          sortDirection: currentSortDirection,
        });

        if (append) {
          setEntities((prev) => [...prev, ...data.items]);
        } else {
          setEntities(data.items);
        }
        setTotalEntities(data.total);
        setHasMoreEntities(data.hasMore);
        setEntityOffset(currentOffset + data.items.length);
      } catch (err) {
        if (err instanceof Error && err.name !== "AbortError") {
          setError(err.message || "Failed to load entities");
        }
      } finally {
        setLoadingEntities(false);
        setLoading(false);
      }
    },
    []
  );

  // Load relationships
  const loadRelationships = useCallback(
    async (
      currentOffset: number,
      currentSearch: string,
      currentRelType: string,
      currentFrom: string,
      currentTo: string,
      currentSortBy: string,
      currentSortDirection: "asc" | "desc",
      append = false
    ) => {
      setLoadingRelationships(true);
      try {
        const data = await listKGRelationships({
          limit: DEFAULT_PAGE_SIZE,
          offset: currentOffset,
          search: currentSearch || undefined,
          relationship: currentRelType || undefined,
          fromEntityId: currentFrom || undefined,
          toEntityId: currentTo || undefined,
          sortBy: currentSortBy,
          sortDirection: currentSortDirection,
        });

        if (append) {
          setRelationships((prev) => [...prev, ...data.items]);
        } else {
          setRelationships(data.items);
        }
        setTotalRelationships(data.total);
        setHasMoreRelationships(data.hasMore);
        setRelOffset(currentOffset + data.items.length);
      } catch (err) {
        if (err instanceof Error && err.name !== "AbortError") {
          setError(err.message || "Failed to load relationships");
        }
      } finally {
        setLoadingRelationships(false);
      }
    },
    []
  );

  // Initial load
  useEffect(() => {
    loadStats();
    loadOntology();
    loadEntities(0, "", "", "", "", "name", "asc", false);
  }, [loadStats, loadOntology, loadEntities]);

  // Trigger entity list reload when filters change
  useEffect(() => {
    if (!loading) {
      loadEntities((entityPage - 1) * DEFAULT_PAGE_SIZE, search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection, false);
    }
  }, [search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection, entityPage]);

  // Trigger relationship list reload when switching to tab or filters change
  useEffect(() => {
    if (activeTab === "relationships") {
      loadRelationships((relPage - 1) * DEFAULT_PAGE_SIZE, relSearch, relTypeFilter, fromEntityFilter, toEntityFilter, relationshipSortBy, relationshipSortDirection, false);
    }
  }, [activeTab, relSearch, relTypeFilter, fromEntityFilter, toEntityFilter, relationshipSortBy, relationshipSortDirection, relPage]);

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
  const handleSelectEntity = useCallback(
    (entity: KGEntitySummary) => {
      setSelectedEntity(null);
      loadEntityDetail(entity.id);
    },
    [loadEntityDetail]
  );

  const handleEntityUpdated = useCallback(
    (updatedEntity: KGEntityDetail) => {
      setSelectedEntity(updatedEntity);
      loadStats();
      loadEntities(0, search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection, false);
    },
    [loadStats, loadEntities, search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection]
  );

  const handleDeleteEntity = useCallback(async () => {
    if (!entityToDelete) return;
    setDeletingEntity(true);
    setError("");
    try {
      await deleteKGEntity(entityToDelete.id);
      setSelectedEntity(null);
      setEntityToDelete(null);
      await Promise.all([
        loadStats(),
        loadEntities((entityPage - 1) * DEFAULT_PAGE_SIZE, search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection, false),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete entity");
    } finally {
      setDeletingEntity(false);
    }
  }, [entityToDelete, entityPage, entitySortBy, entitySortDirection, entityTypeFilter, excludeNames, loadEntities, loadStats, search, statusFilter]);

  const handleOpenLowReviewDelete = useCallback(async () => {
    setLoadingLowReviewPreview(true);
    setError("");
    try {
      const preview = await getKGLowReviewEntityCount(50);
      setLowReviewEntityCount(preview.entityCount);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to count low-review entities");
    } finally {
      setLoadingLowReviewPreview(false);
    }
  }, []);

  const handleDeleteLowReviewEntities = useCallback(async () => {
    setDeletingLowReviewEntities(true);
    setError("");
    try {
      await deleteKGLowReviewEntities(50);
      setLowReviewEntityCount(null);
      setSelectedEntity(null);
      await Promise.all([
        loadStats(),
        loadEntities(0, search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection, false),
      ]);
      setEntityPage(1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete low-review entities");
    } finally {
      setDeletingLowReviewEntities(false);
    }
  }, [entitySortBy, entitySortDirection, entityTypeFilter, excludeNames, loadEntities, loadStats, search, statusFilter]);

  const handleCreateEntity = useCallback(async () => {
    const payload = {
      entityId: newEntity.entityId.trim(),
      canonicalName: newEntity.canonicalName.trim(),
      entityType: newEntity.entityType.trim(),
      status: newEntity.status,
    };
    if (!payload.entityId || !payload.canonicalName || !payload.entityType) {
      setError("Entity ID, canonical name, and type are required.");
      return;
    }
    setCreatingEntity(true);
    setError("");
    try {
      const created = await createKGEntity(payload);
      setCreateEntityOpen(false);
      setNewEntity({ entityId: "", canonicalName: "", entityType: "", status: "draft" });
      setSelectedEntity(created);
      setEntityPage(1);
      await Promise.all([
        loadStats(),
        loadEntities(0, search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection, false),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create entity");
    } finally {
      setCreatingEntity(false);
    }
  }, [entitySortBy, entitySortDirection, entityTypeFilter, excludeNames, loadEntities, loadStats, newEntity, search, statusFilter]);

  const handleCopyEntity = useCallback(async () => {
    if (!selectedEntity) return;
    const entityId = copyEntityId.trim();
    if (!entityId) {
      setError("A new entity ID is required.");
      return;
    }
    setCopyingEntity(true);
    setError("");
    try {
      const copied = await copyKGEntity(selectedEntity.id, {
        entityId,
        canonicalName: copyEntityName.trim() || `Copy of ${selectedEntity.canonicalName}`,
      });
      setCopyEntityOpen(false);
      setCopyEntityId("");
      setCopyEntityName("");
      setSelectedEntity(copied);
      setEntityPage(1);
      await Promise.all([
        loadStats(),
        loadEntities(0, search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection, false),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to copy entity");
    } finally {
      setCopyingEntity(false);
    }
  }, [copyEntityId, copyEntityName, entitySortBy, entitySortDirection, entityTypeFilter, excludeNames, loadEntities, loadStats, search, selectedEntity, statusFilter]);

  // Jump directly to an entity ID from anywhere (e.g. relationship card)
  const handleJumpToEntity = useCallback(
    (entityId: string) => {
      setActiveTab("entities");
      loadEntityDetail(entityId);
    },
    [loadEntityDetail]
  );

  // Load more entities
  const handleLoadMoreEntities = useCallback(() => {
    if (!loadingEntities && hasMoreEntities) {
      setEntityPage((current) => current + 1);
    }
  }, [loadingEntities, hasMoreEntities]);

  // Load more relationships
  const handleLoadMoreRelationships = useCallback(() => {
    if (!loadingRelationships && hasMoreRelationships) {
      setRelPage((current) => current + 1);
    }
  }, [loadingRelationships, hasMoreRelationships]);

  // Reset entity filters
  const handleResetEntityFilters = useCallback(() => {
    setSearchInput("");
    setSearch("");
    setEntityTypeFilter("");
    setStatusFilter("");
    setExcludeNames("");
  }, []);

  // Reset relationship filters
  const handleResetRelFilters = useCallback(() => {
    setRelSearchInput("");
    setRelSearch("");
    setRelTypeFilter("");
    setFromEntityInput("");
    setFromEntityFilter("");
    setToEntityInput("");
    setToEntityFilter("");
  }, []);

  // Refresh after AI import apply
  const handleApplied = useCallback(() => {
    loadStats();
    loadEntities(0, search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection, false);
  }, [loadStats, loadEntities, search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection]);

  // List of available node types from ontology or defaults
  const availableNodeTypes = ontology?.nodeTypes?.length
    ? ontology.nodeTypes
    : ["Destination", "Attraction", "Hotel", "Restaurant", "Activity", "Topic", "Tag", "Region", "Event", "TransportHub"];

  // List of available relationship types from ontology
  const availableRelTypes = ontology?.relationshipTypes || [];

  return (
    <section className="kgPage">
      <header className="topbar kgTopbar">
        <div>
          <p className="eyebrow">Catalog intelligence</p>
          <h1>Knowledge Graph</h1>
          <p className="kgLead">
            Quản lý entity, alias, relationship và ontology từ PostgreSQL backend.
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
          <span>API-driven Query & Pagination</span>
        </div>
      </section>

      {error && (
        <div className="kgNotice" role="alert">
          <span>!</span>
          <p>{error}</p>
          <button type="button" aria-label="Dismiss error" onClick={() => setError("")}>
            ×
          </button>
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
          nodeTypes={availableNodeTypes}
          nodeTypeProperties={ontology?.nodeTypeProperties || {}}
          relationshipTypes={availableRelTypes}
          onApplied={handleApplied}
        />
      )}

      {/* Entities Tab */}
      {activeTab === "entities" && (
        <>
          {/* Multi-Filter Bar */}
          <section className="kgControlBarMulti" aria-label="Entity query filters">
            {/* Search Input */}
            <div className="kgSearchFieldWrap">
              <label className="searchField" style={{ width: "100%" }}>
                <span>⌕</span>
                <input
                  type="search"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  placeholder="Search by canonical name or ID..."
                />
              </label>
              {searchInput && (
                <button
                  type="button"
                  className="kgClearSearchBtn"
                  title="Clear search"
                  onClick={() => {
                    setSearchInput("");
                    setSearch("");
                  }}
                >
                  ✕
                </button>
              )}
            </div>

            {/* Entity Type Filter Dropdown */}
            <select
              className="kgSelectFilter"
              value={entityTypeFilter}
              onChange={(e) => {
                setEntityTypeFilter(e.target.value);
                setEntityOffset(0);
                setEntities([]);
              }}
            >
              <option value="">All Entity Types</option>
              {availableNodeTypes.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>

            {/* Status Filter Dropdown */}
            <select
              className="kgSelectFilter"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setEntityOffset(0);
                setEntities([]);
              }}
            >
              <option value="">All Statuses</option>
              <option value="active">active</option>
              <option value="draft">draft</option>
              <option value="missing">missing</option>
              <option value="archived">archived</option>
            </select>

            <input
              className="kgSelectFilter"
              aria-label="Exclude entity names"
              onChange={(event) => {
                setExcludeNames(event.target.value);
                setEntityPage(1);
              }}
              placeholder="Exclude names: coffee, cafe"
              value={excludeNames}
            />

            <select
              className="kgSelectFilter"
              aria-label="Entity sort order"
              value={`${entitySortBy}:${entitySortDirection}`}
              onChange={(event) => {
                const [sortBy, sortDirection] = event.target.value.split(":") as [string, "asc" | "desc"];
                setEntitySortBy(sortBy);
                setEntitySortDirection(sortDirection);
                setEntityPage(1);
              }}
            >
              <option value="name:asc">Name: A-Z</option>
              <option value="name:desc">Name: Z-A</option>
              <option value="updated_at:desc">Recently updated</option>
              <option value="created_at:desc">Recently created</option>
              <option value="review_count:desc">Review count: high to low</option>
              <option value="review_count:asc">Review count: low to high</option>
              <option value="type:asc">Type: A-Z</option>
              <option value="status:asc">Status: A-Z</option>
            </select>

            {/* Reset Button */}
            {(search || entityTypeFilter || statusFilter || excludeNames) && (
              <button type="button" className="kgResetBtn" onClick={handleResetEntityFilters}>
                Reset Filters
              </button>
            )}

            <button type="button" className="kgMiniDanger" disabled={loadingLowReviewPreview} onClick={() => void handleOpenLowReviewDelete()}>
              {loadingLowReviewPreview ? "Checking..." : "Delete review count < 50"}
            </button>
            <button type="button" className="kgSectionEdit" onClick={() => setCreateEntityOpen(true)}>
              Create node
            </button>

            <span className="kgResultCount" style={{ marginLeft: "auto" }}>
              {loadingEntities && entities.length === 0
                ? "Loading..."
                : `${totalEntities.toLocaleString()} entities match`}
            </span>
          </section>

          {/* Quick Entity Type Pills */}
          <section className="kgFilterPills" aria-label="Quick type pills">
            <button
              type="button"
              className={!entityTypeFilter ? "kgFilterPill active" : "kgFilterPill"}
              onClick={() => {
                setEntityTypeFilter("");
                setEntityOffset(0);
                setEntities([]);
              }}
            >
              All Types
            </button>
            {QUICK_ENTITY_TYPES.map((type) => (
              <button
                key={type}
                type="button"
                className={entityTypeFilter === type ? "kgFilterPill active" : "kgFilterPill"}
                onClick={() => {
                  setEntityTypeFilter(entityTypeFilter === type ? "" : type);
                  setEntityOffset(0);
                  setEntities([]);
                }}
              >
                {type}
              </button>
            ))}
          </section>

          {/* Entity List & Detail Inspector Layout */}
          <section className="dataLayout kgDataLayout">
            {/* Entity List */}
            <div className="runList kgEntityList">
              <header>
                <span>{totalEntities.toLocaleString()} total match</span>
                {(search || entityTypeFilter || statusFilter) && (
                  <small>
                    Filtered: {[search && `"${search}"`, entityTypeFilter, statusFilter].filter(Boolean).join(" • ")}
                  </small>
                )}
              </header>

              {loadingEntities && entities.length === 0 ? (
                <div className="emptyState">
                  <b>Loading entities...</b>
                </div>
              ) : entities.length === 0 ? (
                <div className="emptyState">
                  <b>No entities found</b>
                  <p>Try adjusting your search keyword or filters.</p>
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
                        <span className={`kgNodeType kgNode-${entity.entityType.toLowerCase()}`}>
                          {entity.entityType}
                        </span>
                        <span className={`status status-${entity.status === "missing" ? "failed" : entity.status}`}>
                          {entity.status}
                        </span>
                      </div>
                      <h3>{entity.canonicalName}</h3>
                      <small>{entity.reviewCount == null ? "No review count" : `${entity.reviewCount.toLocaleString()} reviews`}</small>
                      <code>{entity.id}</code>
                    </button>
                  ))}

                  <div className="kgPagination">
                    <button type="button" className="kgLoadMoreButton" onClick={() => setEntityPage((current) => Math.max(1, current - 1))} disabled={loadingEntities || entityPage === 1}>Previous</button>
                    <span>Page {entityPage} / {Math.max(1, Math.ceil(totalEntities / DEFAULT_PAGE_SIZE))}</span>
                    <button type="button" className="kgLoadMoreButton" onClick={handleLoadMoreEntities} disabled={loadingEntities || !hasMoreEntities}>Next</button>
                  </div>
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
                <EditableEntityDetailPanel
                  entity={selectedEntity}
                  onJumpToEntity={handleJumpToEntity}
                  onUpdated={handleEntityUpdated}
                  onRequestDelete={() => setEntityToDelete(selectedEntity)}
                  onRequestCopy={() => {
                    setCopyEntityId("");
                    setCopyEntityName(`Copy of ${selectedEntity.canonicalName}`);
                    setCopyEntityOpen(true);
                  }}
                  onError={setError}
                  availableNodeTypes={availableNodeTypes}
                />
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

      {/* Relationships Tab */}
      {activeTab === "relationships" && (
        <>
          {/* Relationship Filter Bar */}
          <section className="kgControlBarMulti" aria-label="Relationship query filters">
            {/* Search Input */}
            <div className="kgSearchFieldWrap">
              <label className="searchField" style={{ width: "100%" }}>
                <span>⌕</span>
                <input
                  type="search"
                  value={relSearchInput}
                  onChange={(e) => setRelSearchInput(e.target.value)}
                  placeholder="Search relationship or entity IDs..."
                />
              </label>
              {relSearchInput && (
                <button
                  type="button"
                  className="kgClearSearchBtn"
                  title="Clear search"
                  onClick={() => {
                    setRelSearchInput("");
                    setRelSearch("");
                  }}
                >
                  ✕
                </button>
              )}
            </div>

            {/* Relationship Type Select */}
            <select
              className="kgSelectFilter"
              value={relTypeFilter}
              onChange={(e) => {
                setRelTypeFilter(e.target.value);
                setRelOffset(0);
                setRelationships([]);
              }}
            >
              <option value="">All Relationships</option>
              {availableRelTypes.map((rel) => (
                <option key={rel} value={rel}>
                  {rel}
                </option>
              ))}
            </select>

            <select
              className="kgSelectFilter"
              aria-label="Relationship sort order"
              value={`${relationshipSortBy}:${relationshipSortDirection}`}
              onChange={(event) => {
                const [sortBy, sortDirection] = event.target.value.split(":") as [string, "asc" | "desc"];
                setRelationshipSortBy(sortBy);
                setRelationshipSortDirection(sortDirection);
                setRelPage(1);
              }}
            >
              <option value="id:asc">ID: low to high</option>
              <option value="id:desc">ID: high to low</option>
              <option value="relationship:asc">Type: A-Z</option>
              <option value="relationship:desc">Type: Z-A</option>
              <option value="created_at:desc">Recently created</option>
            </select>

            {/* From Entity ID Input */}
            <input
              type="text"
              className="kgSelectFilter"
              value={fromEntityInput}
              onChange={(e) => setFromEntityInput(e.target.value)}
              placeholder="From Entity ID..."
              style={{ width: "150px" }}
            />

            {/* To Entity ID Input */}
            <input
              type="text"
              className="kgSelectFilter"
              value={toEntityInput}
              onChange={(e) => setToEntityInput(e.target.value)}
              placeholder="To Entity ID..."
              style={{ width: "150px" }}
            />

            {/* Reset Button */}
            {(relSearch || relTypeFilter || fromEntityFilter || toEntityFilter) && (
              <button type="button" className="kgResetBtn" onClick={handleResetRelFilters}>
                Reset Filters
              </button>
            )}

            <span className="kgResultCount" style={{ marginLeft: "auto" }}>
              {loadingRelationships && relationships.length === 0
                ? "Loading..."
                : `${totalRelationships.toLocaleString()} edges match`}
            </span>
          </section>

          {/* Relationship Edge List */}
          <section className="dataLayout kgDataLayout" style={{ gridTemplateColumns: "1fr" }}>
            <div className="runList" style={{ maxHeight: "760px" }}>
              <header>
                <span>{totalRelationships.toLocaleString()} total edges</span>
                {(relSearch || relTypeFilter || fromEntityFilter || toEntityFilter) && (
                  <small>
                    Filtered:{" "}
                    {[
                      relSearch && `"${relSearch}"`,
                      relTypeFilter,
                      fromEntityFilter && `from: ${fromEntityFilter}`,
                      toEntityFilter && `to: ${toEntityFilter}`,
                    ]
                      .filter(Boolean)
                      .join(" • ")}
                  </small>
                )}
              </header>

              {loadingRelationships && relationships.length === 0 ? (
                <div className="emptyState">
                  <b>Loading graph relationships...</b>
                </div>
              ) : relationships.length === 0 ? (
                <div className="emptyState">
                  <b>No graph relationships found</b>
                  <p>Try adjusting your relationship search query or filters.</p>
                </div>
              ) : (
                <>
                  {relationships.map((rel) => (
                    <article key={rel.id} className="kgRelCard">
                      <div className="kgRelCardFlow">
                        <button
                          type="button"
                          className="kgEntityBtnLink"
                          title="Click to view entity"
                          onClick={() => handleJumpToEntity(rel.fromEntityId)}
                        >
                          {rel.fromEntityId}
                        </button>
                        <span>→</span>
                        <span className="kgRelTypeBadge">{rel.relationship}</span>
                        <span>→</span>
                        <button
                          type="button"
                          className="kgEntityBtnLink"
                          title="Click to view entity"
                          onClick={() => handleJumpToEntity(rel.toEntityId)}
                        >
                          {rel.toEntityId}
                        </button>
                      </div>
                      <div style={{ display: "flex", gap: "16px", color: "var(--muted)", fontSize: "0.6rem" }}>
                        <span>Edge ID: #{rel.id}</span>
                        {rel.source && <span>Source: {rel.source}</span>}
                        {rel.createdAt && <span>Created: {new Date(rel.createdAt).toLocaleString()}</span>}
                      </div>
                    </article>
                  ))}

                  <div className="kgPagination">
                    <button type="button" className="kgLoadMoreButton" onClick={() => setRelPage((current) => Math.max(1, current - 1))} disabled={loadingRelationships || relPage === 1}>Previous</button>
                    <span>Page {relPage} / {Math.max(1, Math.ceil(totalRelationships / DEFAULT_PAGE_SIZE))}</span>
                    <button type="button" className="kgLoadMoreButton" onClick={handleLoadMoreRelationships} disabled={loadingRelationships || !hasMoreRelationships}>Next</button>
                  </div>
                </>
              )}
            </div>
          </section>
        </>
      )}

      <footer className="kgFooter">
        <p>
          Knowledge Graph data is stored in PostgreSQL. Entity and relationship query management
          is handled through the admin API with pagination.
        </p>
      </footer>

      {entityToDelete && (
        <div className="kgDeleteDialogBackdrop" role="presentation">
          <section aria-describedby="kg-delete-description" aria-labelledby="kg-delete-title" aria-modal="true" className="kgDeleteDialog" role="dialog">
            <p className="eyebrow">Permanent action</p>
            <h2 id="kg-delete-title">Delete {entityToDelete.canonicalName}?</h2>
            <p id="kg-delete-description">This permanently deletes the entity, all aliases, properties, and every relationship connected to ID {entityToDelete.id}.</p>
            <div className="kgDeleteDialogActions">
              <button type="button" className="kgSectionEdit" disabled={deletingEntity} onClick={() => setEntityToDelete(null)}>Cancel</button>
              <button type="button" className="kgMiniDanger" disabled={deletingEntity} onClick={() => void handleDeleteEntity()}>{deletingEntity ? "Deleting..." : "Delete entity"}</button>
            </div>
          </section>
        </div>
      )}

      {lowReviewEntityCount !== null && (
        <div className="kgDeleteDialogBackdrop" role="presentation">
          <section aria-describedby="kg-low-review-delete-description" aria-labelledby="kg-low-review-delete-title" aria-modal="true" className="kgDeleteDialog" role="dialog">
            <p className="eyebrow">Bulk permanent action</p>
            <h2 id="kg-low-review-delete-title">Delete {lowReviewEntityCount.toLocaleString()} entities?</h2>
            <p id="kg-low-review-delete-description">This permanently deletes every entity with a valid review_count below 50, plus its aliases, properties, and all connected relationships.</p>
            <div className="kgDeleteDialogActions">
              <button type="button" className="kgSectionEdit" disabled={deletingLowReviewEntities} onClick={() => setLowReviewEntityCount(null)}>Cancel</button>
              <button type="button" className="kgMiniDanger" disabled={deletingLowReviewEntities || lowReviewEntityCount === 0} onClick={() => void handleDeleteLowReviewEntities()}>{deletingLowReviewEntities ? "Deleting..." : "Delete all"}</button>
            </div>
          </section>
        </div>
      )}

      {createEntityOpen && (
        <div className="kgDeleteDialogBackdrop" role="presentation">
          <section aria-labelledby="kg-create-node-title" aria-modal="true" className="kgDeleteDialog" role="dialog">
            <p className="eyebrow">Knowledge Graph</p>
            <h2 id="kg-create-node-title">Create node</h2>
            <div className="kgSectionForm kgIdentitySectionForm">
              <label><span>Entity ID</span><input value={newEntity.entityId} onChange={(event) => setNewEntity((current) => ({ ...current, entityId: event.target.value }))} placeholder="place_example" /></label>
              <label><span>Canonical name</span><input value={newEntity.canonicalName} onChange={(event) => setNewEntity((current) => ({ ...current, canonicalName: event.target.value }))} placeholder="Example place" /></label>
              <label><span>Type</span><select value={newEntity.entityType} onChange={(event) => setNewEntity((current) => ({ ...current, entityType: event.target.value }))}><option value="">Select type</option>{availableNodeTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></label>
              <label><span>Status</span><select value={newEntity.status} onChange={(event) => setNewEntity((current) => ({ ...current, status: event.target.value }))}><option value="draft">draft</option><option value="active">active</option><option value="archived">archived</option></select></label>
            </div>
            <div className="kgDeleteDialogActions">
              <button type="button" className="kgSectionEdit" disabled={creatingEntity} onClick={() => setCreateEntityOpen(false)}>Cancel</button>
              <button type="button" className="save" disabled={creatingEntity} onClick={() => void handleCreateEntity()}>{creatingEntity ? "Creating..." : "Create node"}</button>
            </div>
          </section>
        </div>
      )}

      {copyEntityOpen && selectedEntity && (
        <div className="kgDeleteDialogBackdrop" role="presentation">
          <section aria-labelledby="kg-copy-entity-title" aria-modal="true" className="kgDeleteDialog" role="dialog">
            <p className="eyebrow">Copy from {selectedEntity.id}</p>
            <h2 id="kg-copy-entity-title">Copy entity</h2>
            <div className="kgSectionForm kgIdentitySectionForm">
              <label><span>New entity ID</span><input value={copyEntityId} onChange={(event) => setCopyEntityId(event.target.value)} placeholder="place_example_copy" /></label>
              <label><span>Canonical name</span><input value={copyEntityName} onChange={(event) => setCopyEntityName(event.target.value)} /></label>
            </div>
            <p>The copy includes aliases, properties, and outgoing relationships. The original entity remains unchanged.</p>
            <div className="kgDeleteDialogActions">
              <button type="button" className="kgSectionEdit" disabled={copyingEntity} onClick={() => setCopyEntityOpen(false)}>Cancel</button>
              <button type="button" className="save" disabled={copyingEntity} onClick={() => void handleCopyEntity()}>{copyingEntity ? "Copying..." : "Create copy"}</button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}

type EditableAliasRow = {
  clientKey: string;
  id: number | null;
  alias: string;
  language: string;
};

type EditablePropertyRow = {
  clientKey: string;
  id: number | null;
  key: string;
  value: string;
  source: string;
};

type EditableRelationshipRow = {
  clientKey: string;
  id: number | null;
  relationship: string;
  toEntityId: string;
  source: string;
};

function EditableEntityDetailPanel({
  entity,
  onJumpToEntity,
  onUpdated,
  onRequestDelete,
  onRequestCopy,
  onError,
  availableNodeTypes,
}: {
  entity: KGEntityDetail;
  onJumpToEntity: (entityId: string) => void;
  onUpdated: (entity: KGEntityDetail) => void;
  onRequestDelete: () => void;
  onRequestCopy: () => void;
  onError: (message: string) => void;
  availableNodeTypes: string[];
}) {
  const [draftEntity, setDraftEntity] = useState({
    canonicalName: entity.canonicalName,
    entityType: entity.entityType,
    status: entity.status,
  });
  const [aliasRows, setAliasRows] = useState<EditableAliasRow[]>([]);
  const [propertyRows, setPropertyRows] = useState<EditablePropertyRow[]>([]);
  const [relationshipRows, setRelationshipRows] = useState<EditableRelationshipRow[]>([]);
  const [localError, setLocalError] = useState("");
  const [savingKey, setSavingKey] = useState<string | null>(null);

  const createRowKey = useCallback(
    () => globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
    []
  );

  useEffect(() => {
    setDraftEntity({
      canonicalName: entity.canonicalName,
      entityType: entity.entityType,
      status: entity.status,
    });
    setAliasRows(
      entity.aliases.map((alias) => ({
        clientKey: `alias-${alias.id}`,
        id: alias.id,
        alias: alias.alias,
        language: alias.language,
      }))
    );
    setPropertyRows(
      entity.properties.map((prop) => ({
        clientKey: `property-${prop.id}`,
        id: prop.id,
        key: prop.key,
        value: prop.value,
        source: prop.source ?? "",
      }))
    );
    setRelationshipRows(
      entity.relationships.map((rel) => ({
        clientKey: `relationship-${rel.id}`,
        id: rel.id,
        relationship: rel.relationship,
        toEntityId: rel.toEntityId,
        source: rel.source ?? "",
      }))
    );
    setLocalError("");
    setSavingKey(null);
  }, [entity]);

  const isSaving = savingKey !== null;

  const reportError = useCallback(
    (message: string) => {
      setLocalError(message);
      onError(message);
    },
    [onError]
  );

  const saveSection = useCallback(
    async (key: string, action: () => Promise<KGEntityDetail>) => {
      setSavingKey(key);
      setLocalError("");
      onError("");
      try {
        const updated = await action();
        onUpdated(updated);
      } catch (err) {
        reportError(err instanceof Error ? err.message : "Không thể lưu thay đổi.");
      } finally {
        setSavingKey(null);
      }
    },
    [onError, onUpdated, reportError]
  );

  const updateAliasRow = useCallback(
    (clientKey: string, updater: (row: EditableAliasRow) => EditableAliasRow) => {
      setAliasRows((current) => current.map((row) => (row.clientKey === clientKey ? updater(row) : row)));
    },
    []
  );

  const updatePropertyRow = useCallback(
    (clientKey: string, updater: (row: EditablePropertyRow) => EditablePropertyRow) => {
      setPropertyRows((current) => current.map((row) => (row.clientKey === clientKey ? updater(row) : row)));
    },
    []
  );

  const updateRelationshipRow = useCallback(
    (clientKey: string, updater: (row: EditableRelationshipRow) => EditableRelationshipRow) => {
      setRelationshipRows((current) => current.map((row) => (row.clientKey === clientKey ? updater(row) : row)));
    },
    []
  );

  const addAliasRow = useCallback(() => {
    setAliasRows((current) => [...current, { clientKey: createRowKey(), id: null, alias: "", language: "en" }]);
  }, [createRowKey]);

  const addPropertyRow = useCallback(() => {
    setPropertyRows((current) => [...current, { clientKey: createRowKey(), id: null, key: "", value: "", source: "" }]);
  }, [createRowKey]);

  const addRelationshipRow = useCallback(() => {
    setRelationshipRows((current) => [
      ...current,
      {
        clientKey: createRowKey(),
        id: null,
        relationship: availableNodeTypes[0] ?? "",
        toEntityId: "",
        source: "",
      },
    ]);
  }, [availableNodeTypes, createRowKey]);

  const saveEntity = useCallback(async () => {
    const canonicalName = draftEntity.canonicalName.trim();
    const entityType = draftEntity.entityType.trim();
    const status = draftEntity.status.trim();
    if (!canonicalName) {
      reportError("Canonical name không được để trống.");
      return;
    }
    if (!entityType) {
      reportError("Entity type không được để trống.");
      return;
    }
    if (!status) {
      reportError("Status không được để trống.");
      return;
    }
    await saveSection("entity", () =>
      updateKGEntity(entity.id, {
        canonicalName,
        entityType,
        status,
      })
    );
  }, [draftEntity, entity.id, reportError, saveSection]);

  const saveAlias = useCallback(
    async (row: EditableAliasRow) => {
      const alias = row.alias.trim();
      const language = row.language.trim() || "en";
      if (!alias) {
        reportError("Alias không được để trống.");
        return;
      }
      await saveSection(`alias-${row.clientKey}`, () =>
        row.id === null
          ? createKGAlias(entity.id, { alias, language })
          : updateKGAlias(entity.id, row.id, { alias, language })
      );
    },
    [entity.id, reportError, saveSection]
  );

  const removeAlias = useCallback(
    async (row: EditableAliasRow) => {
      const aliasId = row.id;
      if (aliasId === null) {
        setAliasRows((current) => current.filter((item) => item.clientKey !== row.clientKey));
        return;
      }
      if (!window.confirm(`Xóa alias "${row.alias}"?`)) {
        return;
      }
      await saveSection(`alias-delete-${row.clientKey}`, () =>
        deleteKGAlias(entity.id, aliasId).then(() => getKGEntityDetail(entity.id))
      );
    },
    [entity.id, saveSection]
  );

  const saveProperty = useCallback(
    async (row: EditablePropertyRow) => {
      const key = row.key.trim();
      const value = row.value.trim();
      const source = row.source.trim();
      if (!key) {
        reportError("Property key không được để trống.");
        return;
      }
      if (!value) {
        reportError("Property value không được để trống.");
        return;
      }
      await saveSection(`property-${row.clientKey}`, () =>
        row.id === null
          ? createKGProperty(entity.id, { key, value, source: source || undefined })
          : updateKGProperty(entity.id, row.id, { key, value, source: source || undefined })
      );
    },
    [entity.id, reportError, saveSection]
  );

  const removeProperty = useCallback(
    async (row: EditablePropertyRow) => {
      const propertyId = row.id;
      if (propertyId === null) {
        setPropertyRows((current) => current.filter((item) => item.clientKey !== row.clientKey));
        return;
      }
      if (!window.confirm(`Xóa property "${row.key}"?`)) {
        return;
      }
      await saveSection(`property-delete-${row.clientKey}`, () =>
        deleteKGProperty(entity.id, propertyId).then(() => getKGEntityDetail(entity.id))
      );
    },
    [entity.id, saveSection]
  );

  const saveRelationship = useCallback(
    async (row: EditableRelationshipRow) => {
      const relationship = row.relationship.trim();
      const toEntityId = row.toEntityId.trim();
      const source = row.source.trim();
      if (!relationship) {
        reportError("Relationship không được để trống.");
        return;
      }
      if (!toEntityId) {
        reportError("To entity ID không được để trống.");
        return;
      }
      await saveSection(`relationship-${row.clientKey}`, () =>
        row.id === null
          ? createKGRelationship(entity.id, {
              relationship,
              toEntityId,
              source: source || undefined,
            })
          : updateKGRelationship(entity.id, row.id, {
              relationship,
              toEntityId,
              source: source || undefined,
            })
      );
    },
    [entity.id, reportError, saveSection]
  );

  const removeRelationship = useCallback(
    async (row: EditableRelationshipRow) => {
      const relationshipId = row.id;
      if (relationshipId === null) {
        setRelationshipRows((current) => current.filter((item) => item.clientKey !== row.clientKey));
        return;
      }
      if (!window.confirm(`Xóa relationship "${row.relationship}"?`)) {
        return;
      }
      await saveSection(`relationship-delete-${row.clientKey}`, () =>
        deleteKGRelationship(entity.id, relationshipId).then(() => getKGEntityDetail(entity.id))
      );
    },
    [entity.id, saveSection]
  );

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
        <section className="kgInspectorSection">
          <header className="kgSectionHeaderActions">
            <h3>Information</h3>
          </header>
          <div className="kgSectionForm kgIdentitySectionForm">
            <label>
              <span>Entity ID</span>
              <input value={entity.id} disabled />
            </label>
            <label>
              <span>Canonical Name</span>
              <input
                value={draftEntity.canonicalName}
                onChange={(event) => setDraftEntity((current) => ({ ...current, canonicalName: event.target.value }))}
              />
            </label>
            <label>
              <span>Type</span>
              <select
                value={draftEntity.entityType}
                onChange={(event) => setDraftEntity((current) => ({ ...current, entityType: event.target.value }))}
              >
                {availableNodeTypes.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Status</span>
              <select
                value={draftEntity.status}
                onChange={(event) => setDraftEntity((current) => ({ ...current, status: event.target.value }))}
              >
                <option value="active">active</option>
                <option value="draft">draft</option>
                <option value="missing">missing</option>
                <option value="archived">archived</option>
              </select>
            </label>
          </div>
          <div className="kgSectionActions" style={{ marginTop: "10px" }}>
            <button type="button" className="save" disabled={isSaving} onClick={() => void saveEntity()}>
              {savingKey === "entity" ? "Saving..." : "Save entity"}
            </button>
            <button type="button" className="kgMiniDanger" disabled={isSaving} onClick={onRequestDelete}>
              Delete entity
            </button>
            <button type="button" className="kgSectionEdit" disabled={isSaving} onClick={onRequestCopy}>
              Copy entity
            </button>
          </div>
        </section>

        <section className="kgInspectorSection">
          <header className="kgSectionHeaderActions">
            <h3>Aliases</h3>
            <span className="kgSectionCount">{entity.aliasTotal}</span>
            <button type="button" className="kgSectionEdit" disabled={isSaving} onClick={addAliasRow}>
              Add alias
            </button>
          </header>
          {aliasRows.length > 0 ? (
            <div className="kgSectionEditList">
              {aliasRows.map((row) => (
                <div key={row.clientKey} className="kgAliasEditRow">
                  <input
                    value={row.alias}
                    onChange={(event) =>
                      updateAliasRow(row.clientKey, (current) => ({ ...current, alias: event.target.value }))
                    }
                    placeholder="Alias"
                  />
                  <input
                    value={row.language}
                    onChange={(event) =>
                      updateAliasRow(row.clientKey, (current) => ({ ...current, language: event.target.value }))
                    }
                    placeholder="Lang"
                  />
                  <div className="kgSectionActions">
                    <button type="button" className="save" disabled={isSaving} onClick={() => void saveAlias(row)}>
                      {row.id === null ? "Create" : "Save"}
                    </button>
                    <button type="button" className="kgMiniDanger" disabled={isSaving} onClick={() => void removeAlias(row)}>
                      ×
                    </button>
                  </div>
                </div>
              ))}
              {entity.aliasHasMore && (
                <p className="kgMoreIndicator">+{entity.aliasTotal - entity.aliases.length} more aliases</p>
              )}
            </div>
          ) : (
            <div className="kgInspectorEmpty kgInspectorEmptyCompact">
              <span>◇</span>
              <b>No aliases</b>
            </div>
          )}
        </section>

        <section className="kgInspectorSection">
          <header className="kgSectionHeaderActions">
            <h3>Properties</h3>
            <span className="kgSectionCount">{entity.propertyTotal}</span>
            <button type="button" className="kgSectionEdit" disabled={isSaving} onClick={addPropertyRow}>
              Add property
            </button>
          </header>
          {propertyRows.length > 0 ? (
            <div className="kgSectionEditList">
              {propertyRows.map((row) => (
                <div key={row.clientKey} className="kgPropertyEditRow">
                  <input
                    value={row.key}
                    onChange={(event) =>
                      updatePropertyRow(row.clientKey, (current) => ({ ...current, key: event.target.value }))
                    }
                    placeholder="Key"
                  />
                  <input
                    value={row.value}
                    onChange={(event) =>
                      updatePropertyRow(row.clientKey, (current) => ({ ...current, value: event.target.value }))
                    }
                    placeholder="Value"
                  />
                  <input
                    value={row.source}
                    onChange={(event) =>
                      updatePropertyRow(row.clientKey, (current) => ({ ...current, source: event.target.value }))
                    }
                    placeholder="Source"
                  />
                  <div className="kgSectionActions">
                    <button type="button" className="save" disabled={isSaving} onClick={() => void saveProperty(row)}>
                      {row.id === null ? "Create" : "Save"}
                    </button>
                    <button type="button" className="kgMiniDanger" disabled={isSaving} onClick={() => void removeProperty(row)}>
                      ×
                    </button>
                  </div>
                </div>
              ))}
              {entity.propertyHasMore && (
                <p className="kgMoreIndicator">
                  +{entity.propertyTotal - entity.properties.length} more properties
                </p>
              )}
            </div>
          ) : (
            <div className="kgInspectorEmpty kgInspectorEmptyCompact">
              <span>◇</span>
              <b>No properties</b>
            </div>
          )}
        </section>

        <section className="kgInspectorSection">
          <header className="kgSectionHeaderActions">
            <h3>Relationships</h3>
            <span className="kgSectionCount">{entity.relationshipTotal}</span>
            <button type="button" className="kgSectionEdit" disabled={isSaving} onClick={addRelationshipRow}>
              Add relationship
            </button>
          </header>
          {relationshipRows.length > 0 ? (
            <div className="kgSectionEditList">
              {relationshipRows.map((row) => (
                <div key={row.clientKey} className="kgRelationshipEditRow">
                  <input
                    value={row.relationship}
                    onChange={(event) =>
                      updateRelationshipRow(row.clientKey, (current) => ({ ...current, relationship: event.target.value }))
                    }
                    placeholder="Relationship"
                  />
                  <input
                    value={row.toEntityId}
                    onChange={(event) =>
                      updateRelationshipRow(row.clientKey, (current) => ({ ...current, toEntityId: event.target.value }))
                    }
                    placeholder="To entity ID"
                  />
                  <input
                    value={row.source}
                    onChange={(event) =>
                      updateRelationshipRow(row.clientKey, (current) => ({ ...current, source: event.target.value }))
                    }
                    placeholder="Source"
                  />
                  <div className="kgSectionActions">
                    <button type="button" className="save" disabled={isSaving} onClick={() => void saveRelationship(row)}>
                      {row.id === null ? "Create" : "Save"}
                    </button>
                    <button type="button" className="kgMiniDanger" disabled={isSaving} onClick={() => void removeRelationship(row)}>
                      ×
                    </button>
                  </div>
                </div>
              ))}
              {entity.relationshipHasMore && (
                <p className="kgMoreIndicator">
                  +{entity.relationshipTotal - entity.relationships.length} more relationships
                </p>
              )}
            </div>
          ) : (
            <div className="kgInspectorEmpty kgInspectorEmptyCompact">
              <span>◇</span>
              <b>No relationships</b>
            </div>
          )}
        </section>

        {localError && (
          <div className="kgNotice" role="alert">
            <span>!</span>
            <p>{localError}</p>
            <button type="button" aria-label="Dismiss local error" onClick={() => setLocalError("")}>
              ×
            </button>
          </div>
        )}
      </div>
    </>
  );
}

// Entity Detail Panel Component with Jump Navigation
function EntityDetailPanel({
  entity,
  onJumpToEntity,
}: {
  entity: KGEntityDetail;
  onJumpToEntity: (entityId: string) => void;
}) {
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
          <header>
            <h3>Information</h3>
          </header>
          <dl>
            <div>
              <dt>Entity ID</dt>
              <dd>
                <code>{entity.id}</code>
              </dd>
            </div>
            <div>
              <dt>Canonical Name</dt>
              <dd>{entity.canonicalName}</dd>
            </div>
            <div>
              <dt>Type</dt>
              <dd>{entity.entityType}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{entity.status}</dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>{new Date(entity.createdAt).toLocaleString()}</dd>
            </div>
            <div>
              <dt>Updated</dt>
              <dd>{new Date(entity.updatedAt).toLocaleString()}</dd>
            </div>
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
              <span>◇</span>
              <b>No aliases</b>
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
                      <td>
                        <code>{prop.key}</code>
                      </td>
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
              <span>◇</span>
              <b>No properties</b>
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
              {entity.relationships.map((rel) => {
                const isOut = rel.fromEntityId === entity.id;
                const targetId = isOut ? rel.toEntityId : rel.fromEntityId;
                return (
                  <article key={rel.id}>
                    <span className="kgRelationDirection">{isOut ? "OUT" : "IN"}</span>
                    <div>
                      <code>{rel.relationship}</code>
                      <small style={{ display: "flex", alignItems: "center", gap: "6px", marginTop: "4px" }}>
                        <span>{isOut ? "To:" : "From:"}</span>
                        <button
                          type="button"
                          className="kgEntityBtnLink"
                          onClick={() => onJumpToEntity(targetId)}
                          title="Jump to target entity"
                        >
                          {targetId}
                        </button>
                      </small>
                    </div>
                  </article>
                );
              })}
              {entity.relationshipHasMore && (
                <p className="kgMoreIndicator">
                  +{entity.relationshipTotal - entity.relationships.length} more relationships
                </p>
              )}
            </div>
          ) : (
            <div className="kgInspectorEmpty kgInspectorEmptyCompact">
              <span>◇</span>
              <b>No relationships</b>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
