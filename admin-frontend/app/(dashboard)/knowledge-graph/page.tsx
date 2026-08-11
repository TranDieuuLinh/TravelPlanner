"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  getKGStats,
  getKGEntityFilterOptions,
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
  type KGEntityFilterOptions,
  type KGEntitySummary,
  type KGEntityDetail,
  type KGRelationshipSummary,
  type KGOntology,
} from "../../features/knowledge-graph/lib";
import { KnowledgeGraphAIImports } from "../../components/KnowledgeGraphAIImports";
import { EditableEntityDetailPanel } from "../../components/knowledge-graph/EditableEntityDetailPanel";
import { EntityDetailPanel } from "../../components/knowledge-graph/EntityDetailPanel";
import { RelationshipGraph } from "../../components/knowledge-graph/RelationshipGraph";
import { KG_DETAIL_PROPERTY_FETCH_LIMIT } from "../../components/knowledge-graph/KnowledgeGraphSections";

type WorkspaceTab = "entities" | "relationships" | "aiImports";

const TABS: Array<{ id: WorkspaceTab; label: string }> = [
  { id: "entities", label: "Entities" },
  { id: "relationships", label: "Relationships" },
  { id: "aiImports", label: "AI Imports" },
];

const DEFAULT_PAGE_SIZE = 50;
const KNOWLEDGE_GRAPH_ENABLED = process.env.NEXT_PUBLIC_KNOWLEDGE_GRAPH_ENABLED !== "false";
const ENTITY_TYPE_ICONS: Record<string, string> = {
  Destination: "\u{1f9ed}",
  TravelPlace: "\u{1f4cd}",
  Attraction: "\u{1f3af}",
  Hotel: "\u{1f3e8}",
  Restaurant: "\u{1f37d}\ufe0f",
  FoodItem: "\u{1f35c}",
  Activity: "\u{1f3ab}",
  Topic: "\u{1f3f7}\ufe0f",
};

// Compact number formatter for the topbar stats badge.
//   0–999 → "123", 1k–999k → "1.2K", ≥1M → "1.2M".
function formatCompactNumber(value: number): string {
  if (!Number.isFinite(value) || value < 0) {
    return "—";
  }
  if (value < 1000) {
    return String(value);
  }
  if (value < 1_000_000) {
    const scaled = value / 1000;
    return `${scaled >= 10 ? Math.round(scaled) : scaled.toFixed(1).replace(/\.0$/, "")}K`;
  }
  const scaled = value / 1_000_000;
  return `${scaled >= 10 ? Math.round(scaled) : scaled.toFixed(1).replace(/\.0$/, "")}M`;
}

export default function KnowledgeGraphPage() {
  const [stats, setStats] = useState<KGStats | null>(null);
  const [filterOptions, setFilterOptions] = useState<KGEntityFilterOptions | null>(null);
  const [ontology, setOntology] = useState<KGOntology | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<KGEntityDetail | null>(null);
  const [showOutgoingRelations, setShowOutgoingRelations] = useState(true);
  const [showIncomingRelations, setShowIncomingRelations] = useState(true);
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

  // Entity filters
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [entityTypeFilter, setEntityTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [excludeNames, setExcludeNames] = useState("");
  const [missingProperties, setMissingProperties] = useState("");
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

  useEffect(() => {
    if (!filterOptions?.statuses.length) return;
    setNewEntity((current) => ({
      ...current,
      status: filterOptions.statuses.includes(current.status)
        ? current.status
        : filterOptions.statuses[0],
    }));
  }, [filterOptions]);

  // Load stats
  const loadStats = useCallback(async () => {
    if (!KNOWLEDGE_GRAPH_ENABLED) return;
    try {
      const data = await getKGStats();
      setStats(data);
    } catch (err) {
      console.error("Failed to load stats:", err);
    }
  }, []);

  // Load ontology
  const loadOntology = useCallback(async () => {
    if (!KNOWLEDGE_GRAPH_ENABLED) return;
    try {
      const data = await getKGOntology();
      setOntology(data);
    } catch (err) {
      console.error("Failed to load ontology:", err);
    }
  }, []);

  // Load filter values from the entity table instead of a frontend enum.
  const loadFilterOptions = useCallback(async () => {
    if (!KNOWLEDGE_GRAPH_ENABLED) return;
    try {
      setFilterOptions(await getKGEntityFilterOptions());
    } catch (err) {
      console.error("Failed to load entity filter options:", err);
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
      append = false,
      currentMissingProperties = ""
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
          missingProperties: currentMissingProperties || undefined,
          sortBy: currentSortBy,
          sortDirection: currentSortDirection,
        });

        if (append) {
          setEntities((prev) => [...prev, ...data.items]);
        } else {
          setEntities(data.items);
        }
        setTotalEntities(data.total);
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
    if (!KNOWLEDGE_GRAPH_ENABLED) {
      setLoading(false);
      return;
    }
    loadStats();
    loadFilterOptions();
    loadOntology();
    loadEntities(0, "", "", "", "", "name", "asc", false);
  }, [loadStats, loadFilterOptions, loadOntology, loadEntities]);

  // Trigger entity list reload when filters change
  useEffect(() => {
    if (!loading) {
      loadEntities((entityPage - 1) * DEFAULT_PAGE_SIZE, search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection, false, missingProperties);
    }
  }, [search, entityTypeFilter, statusFilter, excludeNames, missingProperties, entitySortBy, entitySortDirection, entityPage]);

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
      const data = await getKGEntityDetail(entityId, { propertyLimit: KG_DETAIL_PROPERTY_FETCH_LIMIT });
      setSelectedEntity(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load entity detail");
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    setShowOutgoingRelations(true);
    setShowIncomingRelations(true);
  }, [selectedEntity?.id]);

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
      loadFilterOptions();
      loadEntities(0, search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection, false, missingProperties);
    },
    [loadStats, loadFilterOptions, loadEntities, search, entityTypeFilter, statusFilter, excludeNames, missingProperties, entitySortBy, entitySortDirection]
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
        loadFilterOptions(),
        loadEntities((entityPage - 1) * DEFAULT_PAGE_SIZE, search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection, false, missingProperties),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete entity");
    } finally {
      setDeletingEntity(false);
    }
  }, [entityToDelete, entityPage, entitySortBy, entitySortDirection, entityTypeFilter, excludeNames, missingProperties, loadEntities, loadFilterOptions, loadStats, search, statusFilter]);

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
        loadFilterOptions(),
        loadEntities(0, search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection, false, missingProperties),
      ]);
      setEntityPage(1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete low-review entities");
    } finally {
      setDeletingLowReviewEntities(false);
    }
  }, [entitySortBy, entitySortDirection, entityTypeFilter, excludeNames, missingProperties, loadEntities, loadFilterOptions, loadStats, search, statusFilter]);

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
        loadFilterOptions(),
        loadEntities(0, search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection, false, missingProperties),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create entity");
    } finally {
      setCreatingEntity(false);
    }
  }, [entitySortBy, entitySortDirection, entityTypeFilter, excludeNames, missingProperties, loadEntities, loadFilterOptions, loadStats, newEntity, search, statusFilter]);

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
        loadFilterOptions(),
        loadEntities(0, search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection, false, missingProperties),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to copy entity");
    } finally {
      setCopyingEntity(false);
    }
  }, [copyEntityId, copyEntityName, entitySortBy, entitySortDirection, entityTypeFilter, excludeNames, missingProperties, loadEntities, loadFilterOptions, loadStats, search, selectedEntity, statusFilter]);

  // Jump directly to an entity ID from anywhere (e.g. relationship card)
  const handleJumpToEntity = useCallback(
    (entityId: string) => {
      setActiveTab("entities");
      loadEntityDetail(entityId);
    },
    [loadEntityDetail]
  );

  // Keep entity pagination inside the valid page range.
  const handleEntityPageChange = useCallback(
    (nextPage: number) => {
      const totalPages = Math.max(1, Math.ceil(totalEntities / DEFAULT_PAGE_SIZE));
      if (loadingEntities || nextPage < 1 || nextPage > totalPages || nextPage === entityPage) {
        return;
      }
      setEntityPage(nextPage);
    },
    [entityPage, loadingEntities, totalEntities]
  );

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
    setMissingProperties("");
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
    loadFilterOptions();
    loadEntities(0, search, entityTypeFilter, statusFilter, excludeNames, entitySortBy, entitySortDirection, false, missingProperties);
  }, [loadStats, loadFilterOptions, loadEntities, search, entityTypeFilter, statusFilter, excludeNames, missingProperties, entitySortBy, entitySortDirection]);

  if (!KNOWLEDGE_GRAPH_ENABLED) {
    return (
      <section className="kgPage">
        <header className="topbar kgTopbar">
          <div>
            <p className="eyebrow">Catalog intelligence</p>
            <h1>Knowledge Graph</h1>
            <p className="kgLead">
              Knowledge Graph UI is disabled until the refactored backend exposes its admin contract.
            </p>
          </div>
        </header>
        <div className="kgNotice" role="status">
          <span>i</span>
          <p>
            Set <code>NEXT_PUBLIC_KNOWLEDGE_GRAPH_ENABLED=true</code> only after the matching
            <code>/admin/knowledge-graph/*</code> endpoints are available.
          </p>
        </div>
      </section>
    );
  }

  // Ontology is used for import validation; entity filters come from PostgreSQL.
  const availableNodeTypes = ontology?.nodeTypes?.length
    ? ontology.nodeTypes
    : ["Destination", "Attraction", "Hotel", "Restaurant", "Activity", "Topic", "Tag", "Region", "Event", "TransportHub"];

  // Keep ontology keys available even when a key/type has not been used in the DB yet.
  const availableRelTypes = ontology?.relationshipTypes?.length
    ? ontology.relationshipTypes
    : filterOptions?.relationshipTypes || [];
  const availableEntityTypes = filterOptions?.entityTypes || [];
  const availableStatuses = filterOptions?.statuses || [];
  const selectedEntityPropertySchema = selectedEntity
    ? ontology?.nodeTypeProperties[selectedEntity.entityType]
    : undefined;
  const availablePropertyKeys = Array.from(
    new Set([
      ...(ontology?.propertyKeys || []),
      ...(filterOptions?.propertyKeys || []),
      ...(selectedEntityPropertySchema?.requiredProperties || []),
      ...(selectedEntityPropertySchema?.optionalProperties || []),
      ...(selectedEntity?.properties.map((property) => property.key) || []),
    ])
  ).sort();
  const relationshipDirectionStats = selectedEntity
    ? selectedEntity.relationships.reduce(
        (stats, relationship) => ({
          outgoing: stats.outgoing + (relationship.fromEntityId === selectedEntity.id ? 1 : 0),
          incoming: stats.incoming + (relationship.toEntityId === selectedEntity.id ? 1 : 0),
        }),
        { outgoing: 0, incoming: 0 }
      )
    : { outgoing: 0, incoming: 0 };

  return (
    <section className="kgPage">
      {error && (
        <div className="kgNotice" role="alert">
          <span>!</span>
          <p>{error}</p>
          <button type="button" aria-label="Dismiss error" onClick={() => setError("")}>
            ×
          </button>
        </div>
      )}

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
        <div
          className="kgSourceBadge"
          title={
            stats
              ? `${stats.entityCount.toLocaleString()} entities · ${stats.aliasCount.toLocaleString()} aliases · ${stats.relationshipCount.toLocaleString()} relationships`
              : "Loading stats…"
          }
          aria-label={
            stats
              ? `PostgreSQL backend: ${stats.entityCount} entities, ${stats.aliasCount} aliases, ${stats.relationshipCount} relationships`
              : "PostgreSQL backend stats loading"
          }
        >
          <span className="kgPulse" />
          <span className="kgSourceBadgeLabel">PG</span>
          <span className="kgSourceBadgeDivider">·</span>
          <span>{stats ? formatCompactNumber(stats.entityCount) : "—"}</span>
          <span className="kgSourceBadgeUnit">ent</span>
          <span className="kgSourceBadgeDivider">·</span>
          <span>{stats ? formatCompactNumber(stats.aliasCount) : "—"}</span>
          <span className="kgSourceBadgeUnit">alias</span>
          <span className="kgSourceBadgeDivider">·</span>
          <span>{stats ? formatCompactNumber(stats.relationshipCount) : "—"}</span>
          <span className="kgSourceBadgeUnit">rel</span>
        </div>
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
              {availableEntityTypes.map((type) => (
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
              {availableStatuses.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
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

            <input
              className="kgSelectFilter"
              aria-label="Missing property keys"
              onChange={(event) => {
                setMissingProperties(event.target.value);
                setEntityPage(1);
              }}
              placeholder="Missing fields: description, image"
              value={missingProperties}
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
            {(search || entityTypeFilter || statusFilter || excludeNames || missingProperties) && (
              <button type="button" className="kgResetBtn" onClick={handleResetEntityFilters}>
                Reset Filters
              </button>
            )}

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
            {availableEntityTypes.map((type) => (
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
                <span>Entities</span>
                {(search || entityTypeFilter || statusFilter) && (
                  <small>
                    Filtered: {[search && `"${search}"`, entityTypeFilter, statusFilter].filter(Boolean).join(" • ")}
                  </small>
                )}
                <div className="kgPagination kgPaginationInline" aria-label="Entity pages">
                  <button
                    type="button"
                    aria-label="Previous entity page"
                    onClick={() => handleEntityPageChange(entityPage - 1)}
                    disabled={loadingEntities || entityPage <= 1}
                  >
                    ‹
                  </button>
                  <span>{entityPage} / {Math.max(1, Math.ceil(totalEntities / DEFAULT_PAGE_SIZE))}</span>
                  <button
                    type="button"
                    aria-label="Next entity page"
                    onClick={() => handleEntityPageChange(entityPage + 1)}
                    disabled={loadingEntities || entityPage >= Math.max(1, Math.ceil(totalEntities / DEFAULT_PAGE_SIZE))}
                  >
                    ›
                  </button>
                </div>
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
                      <div className="kgEntityCardRow">
                        <h3>{entity.canonicalName}</h3>
                        <span
                          className={`kgEntityTypeIcon kgNode-${entity.entityType.toLowerCase()}`}
                          title={entity.entityType}
                          aria-label={`Entity type: ${entity.entityType}`}
                        >
                          {ENTITY_TYPE_ICONS[entity.entityType] || "\u{1f517}"}
                        </span>
                        <span
                          className={`kgEntityStatusDot status-${entity.status === "missing" ? "failed" : entity.status}`}
                          title={`Status: ${entity.status}`}
                          aria-label={`Entity status: ${entity.status}`}
                        />
                      </div>
                    </button>
                  ))}

                </>
              )}
            </div>

            {/* Relationship map */}
            {selectedEntity ? (
              <section className="kgRelationshipOverview" aria-label="Relationship map">
                <header className="kgRelationshipOverviewHeader">
                  <div>
                    <p className="eyebrow">Relationship map</p>
                  </div>
                  <div className="kgRelationshipOverviewStats" aria-label="Relationship direction statistics">
                    <span className="kgRelationshipOverviewCount">
                      {selectedEntity.relationshipTotal} total
                    </span>
                    <span className="kgRelationshipStat loaded" title="Relationships currently loaded for this entity">
                      {selectedEntity.relationships.length} loaded
                    </span>
                    <button
                      type="button"
                      className={`kgRelationshipStat directionToggle outgoing${showOutgoingRelations ? " active" : ""}`}
                      aria-pressed={showOutgoingRelations}
                      onClick={() => setShowOutgoingRelations((visible) => !visible)}
                    >
                      <b>→</b> {relationshipDirectionStats.outgoing} outgoing
                    </button>
                    <button
                      type="button"
                      className={`kgRelationshipStat directionToggle incoming${showIncomingRelations ? " active" : ""}`}
                      aria-pressed={showIncomingRelations}
                      onClick={() => setShowIncomingRelations((visible) => !visible)}
                    >
                      <b>←</b> {relationshipDirectionStats.incoming} incoming
                    </button>
                  </div>
                </header>
                <RelationshipGraph
                  entity={selectedEntity}
                  onJumpToEntity={handleJumpToEntity}
                  showOutgoing={showOutgoingRelations}
                  showIncoming={showIncomingRelations}
                />
              </section>
            ) : (
              <section className="kgRelationshipOverview kgRelationshipOverviewEmpty" aria-label="Relationship map">
                <div className="detailEmpty">
                  <b>Select an entity to view its relationship map</b>
                  <p>The icon map will appear here after you select an entity.</p>
                </div>
              </section>
            )}

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
                    availableEntityTypes={availableEntityTypes}
                    availableStatuses={availableStatuses}
                    availableRelationshipTypes={availableRelTypes}
                    availablePropertyKeys={availablePropertyKeys}
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
              <label><span>ID</span><input value={newEntity.entityId} onChange={(event) => setNewEntity((current) => ({ ...current, entityId: event.target.value }))} placeholder="place_example" /></label>
              <label><span>Name</span><input value={newEntity.canonicalName} onChange={(event) => setNewEntity((current) => ({ ...current, canonicalName: event.target.value }))} placeholder="Example place" /></label>
              <label><span>Type</span><select value={newEntity.entityType} onChange={(event) => setNewEntity((current) => ({ ...current, entityType: event.target.value }))}><option value="">Select type</option>{availableEntityTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></label>
              <label><span>Status</span><select value={newEntity.status} onChange={(event) => setNewEntity((current) => ({ ...current, status: event.target.value }))}>{availableStatuses.map((status) => <option key={status} value={status}>{status}</option>)}</select></label>
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
