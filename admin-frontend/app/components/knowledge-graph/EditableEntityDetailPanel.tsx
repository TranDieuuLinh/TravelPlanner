"use client";

import { useCallback, useEffect, useState } from "react";
import {
  type KGEntityDetail,
} from "../../features/knowledge-graph/lib";
import {
  createKGAlias,
  createKGProperty,
  createKGRelationship,
  deleteKGAlias,
  deleteKGProperty,
  deleteKGRelationship,
  getKGEntityDetail,
  updateKGAlias,
  updateKGEntity,
  updateKGProperty,
  updateKGRelationship,
  listKGEntities,
  type KGEntitySummary,
} from "../../features/knowledge-graph/lib";
import {
  InspectorSection,
  KG_DEFAULT_COLLAPSED_SECTIONS,
  KG_DETAIL_PROPERTY_FETCH_LIMIT,
  useCollapsedSections,
} from "./KnowledgeGraphSections";

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
};

type EditableRelationshipRow = {
  clientKey: string;
  id: number | null;
  fromEntityId: string;
  relationship: string;
  toEntityId: string;
};

type RelationshipSearchFilter = {
  name?: string;
  relationship?: string;
  from?: string;
  to?: string;
  id?: string;
};

function parseRelationshipSearch(value: string): RelationshipSearchFilter | null {
  const query = value.trim();
  if (!query) return {};
  try {
    const parsed: unknown = JSON.parse(query);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    const filter: RelationshipSearchFilter = {};
    for (const key of ["name", "relationship", "from", "to", "id"] as const) {
      const field = (parsed as Record<string, unknown>)[key];
      if (typeof field === "string" && field.trim()) filter[key] = field.trim();
    }
    return filter;
  } catch {
    return null;
  }
}

function NodeFilterSelect({
  value,
  currentIds,
  options,
  labels,
  onSearch,
  onChange,
  disabled,
}: {
  value: string;
  currentIds: string[];
  options: KGEntitySummary[];
  labels: Record<string, string>;
  onSearch: (query: string) => void;
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const filteredCurrentIds = currentIds.filter((id) => id.toLocaleLowerCase().includes(normalizedQuery));
  const filteredOptions = options.filter((option) =>
    `${option.canonicalName} ${option.id}`.toLocaleLowerCase().includes(normalizedQuery)
  );

  return (
    <div className="kgNodeFilterSelect">
      <button
        type="button"
        className="kgNodeFilterTrigger"
        onClick={() => setOpen((current) => !current)}
        aria-label="Select to entity"
        aria-expanded={open}
        disabled={disabled}
      >
        <span>{(value && labels[value]) || value || "Chọn node đích..."}</span>
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="kgNodeFilterMenu">
          <input
            autoFocus
            type="search"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              onSearch(event.target.value);
            }}
            placeholder="Search node..."
            aria-label="Search nodes"
          />
          <div className="kgNodeFilterOptions">
            <button type="button" onClick={() => { onChange(""); setOpen(false); }}>
              Clear selection
            </button>
            {filteredOptions.map((option) => (
              <button
                type="button"
                key={option.id}
                onClick={() => { onChange(option.id); setOpen(false); }}
              >
                <strong>{option.canonicalName}</strong>
                <small>{option.id}</small>
              </button>
            ))}
            {filteredCurrentIds.map((id) => (
              <button type="button" key={`current-${id}`} onClick={() => { onChange(id); setOpen(false); }}>
                <strong>{labels[id] || id}</strong>
                {labels[id] && <small>{id}</small>}
              </button>
            ))}
            {filteredOptions.length === 0 && filteredCurrentIds.length === 0 && (
              <span className="kgNodeFilterEmpty">Không tìm thấy node</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const ENTITY_ID_PREFIXES: Record<string, string> = {
  ADM0: "adm0",
  ADM1: "adm1",
  ADM2: "adm2",
  Activity: "activity",
  ActivityItem: "activity_item",
  Accommodation: "accommodation",
  DrinkDessert: "drink_dessert",
  DrinkItem: "drink_item",
  FoodItem: "food_item",
  ProductItem: "product_item",
  Restaurant: "restaurant",
  TravelPlace: "travel_place",
};

function entityIdPrefix(entityType: string): string {
  return ENTITY_ID_PREFIXES[entityType] || entityType.trim().replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
}

function updateEntityIdPrefix(entityId: string, currentType: string, nextType: string): string {
  const currentPrefix = `${entityIdPrefix(currentType)}_`;
  const suffix = entityId.startsWith(currentPrefix)
    ? entityId.slice(currentPrefix.length)
    : entityId.includes("_")
      ? entityId.slice(entityId.indexOf("_") + 1)
      : entityId;
  return `${entityIdPrefix(nextType)}_${suffix || "entity"}`;
}

export function EditableEntityDetailPanel({
  entity,
  onJumpToEntity,
  onUpdated,
  onRequestDelete,
  onRequestCopy,
  onError,
  availableEntityTypes,
  availableStatuses,
  availableRelationshipTypes,
  availablePropertyKeys,
}: {
  entity: KGEntityDetail;
  onJumpToEntity: (entityId: string) => void;
  onUpdated: (entity: KGEntityDetail) => void;
  onRequestDelete: () => void;
  onRequestCopy: () => void;
  onError: (message: string) => void;
  availableEntityTypes: string[];
  availableStatuses: string[];
  availableRelationshipTypes: string[];
  availablePropertyKeys: string[];
}) {
    const [draftEntity, setDraftEntity] = useState({
      entityId: entity.id,
      canonicalName: entity.canonicalName,
    entityType: entity.entityType,
    status: entity.status,
  });
  const [aliasRows, setAliasRows] = useState<EditableAliasRow[]>([]);
  const [propertyRows, setPropertyRows] = useState<EditablePropertyRow[]>([]);
  const [relationshipRows, setRelationshipRows] = useState<EditableRelationshipRow[]>([]);
  const [hiddenRelationshipTypes, setHiddenRelationshipTypes] = useState<Set<string>>(new Set());
  const [relationshipSearch, setRelationshipSearch] = useState("");
  const [nodeSearch, setNodeSearch] = useState("");
  const [nodeOptions, setNodeOptions] = useState<KGEntitySummary[]>([]);
  const [nodeLabels, setNodeLabels] = useState<Record<string, string>>({});
  const [localError, setLocalError] = useState("");
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const sections = useCollapsedSections(KG_DEFAULT_COLLAPSED_SECTIONS);

  const createRowKey = useCallback(
    () => globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
    []
  );

  useEffect(() => {
      setDraftEntity({
        entityId: entity.id,
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
      }))
    );
    setRelationshipRows(
      entity.relationships.map((rel) => ({
        clientKey: `relationship-${rel.id}`,
        id: rel.id,
        fromEntityId: rel.fromEntityId,
        relationship: rel.relationship,
        toEntityId: rel.toEntityId,
      }))
    );
    setHiddenRelationshipTypes(new Set());
    setLocalError("");
    setSavingKey(null);
  }, [entity]);

  const isSaving = savingKey !== null;
  const relationshipNodeIds = Array.from(
    new Set(
      relationshipRows
        .flatMap((row) => [row.fromEntityId.trim(), row.toEntityId.trim()])
        .filter(Boolean)
    )
  );

  useEffect(() => {
    const ids = Array.from(
      new Set(relationshipRows.flatMap((row) => [row.fromEntityId, row.toEntityId]).filter(Boolean))
    );
    if (ids.length === 0) return;
    let cancelled = false;
    const chunks = Array.from({ length: Math.ceil(ids.length / 40) }, (_, index) => ids.slice(index * 40, index * 40 + 40));
    void Promise.all(chunks.map((chunk) => listKGEntities({ limit: 200, search: chunk.join(",") }))).then((results) => {
      if (cancelled) return;
      const labels: Record<string, string> = {};
      results.flatMap((result) => result.items).forEach((item) => {
        labels[item.id] = item.canonicalName;
      });
      setNodeLabels(labels);
    });
    return () => {
      cancelled = true;
    };
  }, [relationshipRows]);
  const relationshipTypes = Array.from(
    new Set(relationshipRows.map((row) => row.relationship).filter(Boolean))
  ).sort();
  const parsedRelationshipSearch = parseRelationshipSearch(relationshipSearch);
  const visibleRelationshipRows = relationshipRows.filter(
    (row) => {
      if (row.id !== null && hiddenRelationshipTypes.has(row.relationship)) return false;
      if (parsedRelationshipSearch === null) return false;
      if (Object.keys(parsedRelationshipSearch).length === 0) return true;
      const matches = (value: string | undefined, filter: string | undefined) =>
        !filter || value?.toLocaleLowerCase().includes(filter.toLocaleLowerCase());
      const fromName = nodeLabels[row.fromEntityId];
      const toName = nodeLabels[row.toEntityId];
      if (!matches(row.relationship, parsedRelationshipSearch.relationship)) return false;
      if (!matches(row.fromEntityId, parsedRelationshipSearch.from)) return false;
      if (!matches(row.toEntityId, parsedRelationshipSearch.to)) return false;
      if (!matches(String(row.id ?? ""), parsedRelationshipSearch.id)) return false;
      if (
        parsedRelationshipSearch.name &&
        !matches(fromName, parsedRelationshipSearch.name) &&
        !matches(toName, parsedRelationshipSearch.name)
      ) return false;
      return true;
    }
  );
  /*
   * Keep the old free-text behavior out of the JSON filter path. The editor is
   * intentionally queryable with a predictable object shape, like an Excel
   * filter with named columns.
   */
  const filteredRelationshipRows = relationshipSearch.trim().startsWith("{")
    ? visibleRelationshipRows
    : relationshipRows.filter((row) => {
        if (row.id !== null && hiddenRelationshipTypes.has(row.relationship)) return false;
        const query = relationshipSearch.trim().toLocaleLowerCase();
        if (!query) return true;
        const searchable = [
          row.relationship,
          row.fromEntityId,
        row.toEntityId,
        nodeLabels[row.fromEntityId],
        nodeLabels[row.toEntityId],
        ]
          .filter(Boolean)
          .join(" ")
          .toLocaleLowerCase();
        return searchable.includes(query);
      });

  useEffect(() => {
    const query = nodeSearch.trim();
    if (!query) {
      setNodeOptions([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void listKGEntities({ limit: 50, search: query, sortBy: "name", sortDirection: "asc" })
        .then((result) => {
          if (!cancelled) setNodeOptions(result.items);
        })
        .catch(() => {
          if (!cancelled) setNodeOptions([]);
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [nodeSearch]);

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
    setPropertyRows((current) => [
      ...current,
      { clientKey: createRowKey(), id: null, key: availablePropertyKeys[0] ?? "", value: "" },
    ]);
  }, [availablePropertyKeys, createRowKey]);

  const addRelationshipRow = useCallback(() => {
    setRelationshipRows((current) => [
      {
        clientKey: createRowKey(),
        id: null,
        fromEntityId: entity.id,
        relationship: availableRelationshipTypes[0] ?? "",
        toEntityId: "",
      },
      ...current,
    ]);
  }, [availableRelationshipTypes, createRowKey]);

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
        entityId: draftEntity.entityId,
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
          ? createKGProperty(entity.id, { key, value })
          : updateKGProperty(entity.id, row.id, { key, value })
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
        deleteKGProperty(entity.id, propertyId).then(() =>
          getKGEntityDetail(entity.id, { propertyLimit: KG_DETAIL_PROPERTY_FETCH_LIMIT })
        )
      );
    },
    [entity.id, saveSection]
  );

  const saveRelationship = useCallback(
    async (row: EditableRelationshipRow) => {
      const relationship = row.relationship.trim();
      const fromEntityId = row.fromEntityId.trim();
      const toEntityId = row.toEntityId.trim();
      if (!fromEntityId) {
        reportError("From entity ID không được để trống.");
        return;
      }
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
              fromEntityId,
              relationship,
              toEntityId,
            })
          : updateKGRelationship(entity.id, row.id, {
              fromEntityId,
              relationship,
              toEntityId,
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
        <div className="kgEntityHeaderActions">
          <div className="kgSectionActions kgEntityHeaderButtons">
            <button type="button" className="kgSectionEdit" disabled={isSaving} onClick={onRequestCopy}>
              Copy entity
            </button>
            <button type="button" className="kgMiniDanger" disabled={isSaving} onClick={onRequestDelete}>
              Delete entity
            </button>
          </div>
          <span className={`status status-${entity.status === "missing" ? "failed" : entity.status}`}>
            {entity.status}
          </span>
        </div>
      </header>

      <div className="kgInspectorBody kgInspectorAll">
        <InspectorSection
          sectionId="information"
          title="Information"
          collapsible={false}
          isCollapsed={sections.isCollapsed("information")}
          onToggle={() => sections.toggle("information")}
        >
          <div className="kgSectionForm kgIdentitySectionForm">
            <label className="kgIdentityFieldFull">
              <span>ID</span>
              <input value={draftEntity.entityId} disabled />
            </label>
            <label>
              <span>Name</span>
              <input
                value={draftEntity.canonicalName}
                onChange={(event) => setDraftEntity((current) => ({ ...current, canonicalName: event.target.value }))}
              />
            </label>
            <label>
              <span>Type</span>
              <select
                value={draftEntity.entityType}
                onChange={(event) =>
                  setDraftEntity((current) => ({
                    ...current,
                    entityType: event.target.value,
                    entityId: updateEntityIdPrefix(current.entityId, current.entityType, event.target.value),
                  }))
                }
              >
                {availableEntityTypes.map((type) => (
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
                {availableStatuses.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="kgSectionActions kgIdentityActions">
            <button type="button" className="save" disabled={isSaving} onClick={() => void saveEntity()}>
              {savingKey === "entity" ? "Saving..." : "Save entity"}
            </button>
          </div>
        </InspectorSection>

        <InspectorSection
          sectionId="aliases"
          title="Aliases"
          count={entity.aliasTotal}
          isCollapsed={sections.isCollapsed("aliases")}
          onToggle={() => sections.toggle("aliases")}
          headerExtras={
            <button type="button" className="kgSectionEdit" disabled={isSaving} onClick={addAliasRow}>
              Add alias
            </button>
          }
        >
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
                    disabled={isSaving}
                  />
                  <input
                    value={row.language}
                    onChange={(event) =>
                      updateAliasRow(row.clientKey, (current) => ({ ...current, language: event.target.value }))
                    }
                    placeholder="Lang"
                    disabled={isSaving}
                  />
                  <button
                    type="button"
                    className="kgMiniPrimary"
                    disabled={isSaving || savingKey === `alias-${row.clientKey}`}
                    onClick={() => void saveAlias(row)}
                    title={row.id === null ? "Create alias" : "Save alias changes"}
                    aria-label="Save alias"
                  >
                    ✓
                  </button>
                  <button
                    type="button"
                    className="kgMiniDanger"
                    disabled={isSaving}
                    onClick={() => void removeAlias(row)}
                    title={row.id === null ? "Discard this alias" : "Delete this alias"}
                    aria-label="Delete alias"
                  >
                    ×
                  </button>
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
        </InspectorSection>

        <InspectorSection
          sectionId="properties"
          title="Properties"
          count={entity.propertyTotal}
          isCollapsed={sections.isCollapsed("properties")}
          onToggle={() => sections.toggle("properties")}
          headerExtras={
            <button type="button" className="kgSectionEdit" disabled={isSaving} onClick={addPropertyRow}>
              Add property
            </button>
          }
        >
          {propertyRows.length > 0 ? (
            <div className="kgSectionEditList">
              {propertyRows.map((row) => (
                <div key={row.clientKey} className="kgPropertyEditRow">
                  <select
                    value={row.key}
                    onChange={(event) =>
                      updatePropertyRow(row.clientKey, (current) => ({ ...current, key: event.target.value }))
                    }
                    aria-label="Property key"
                    disabled={isSaving}
                  >
                    <option value="">Select property key</option>
                    {availablePropertyKeys.map((key) => (
                      <option key={key} value={key}>
                        {key}
                      </option>
                    ))}
                    {row.key && !availablePropertyKeys.includes(row.key) && (
                      <option value={row.key}>{row.key}</option>
                    )}
                  </select>
                  <input
                    value={row.value}
                    onChange={(event) =>
                      updatePropertyRow(row.clientKey, (current) => ({ ...current, value: event.target.value }))
                    }
                    placeholder="Value"
                    disabled={isSaving}
                  />
                  <button
                    type="button"
                    className="kgMiniPrimary"
                    disabled={isSaving || savingKey === `property-${row.clientKey}`}
                    onClick={() => void saveProperty(row)}
                    title={row.id === null ? "Create property" : "Save property changes"}
                    aria-label="Save property"
                  >
                    ✓
                  </button>
                  <button
                    type="button"
                    className="kgMiniDanger"
                    disabled={isSaving}
                    onClick={() => void removeProperty(row)}
                    title={row.id === null ? "Discard this property" : "Delete this property"}
                    aria-label="Delete property"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="kgInspectorEmpty kgInspectorEmptyCompact">
              <span>◇</span>
              <b>No properties</b>
            </div>
          )}
        </InspectorSection>

        <InspectorSection
          sectionId="relationships"
          title="Relationships"
          count={entity.relationshipTotal}
          isCollapsed={sections.isCollapsed("relationships")}
          onToggle={() => sections.toggle("relationships")}
          headerExtras={
            <div className="kgRelationshipHeaderActions">
              <input
                className="kgRelationshipSearch"
                type="search"
                value={relationshipSearch}
                onChange={(event) => setRelationshipSearch(event.target.value)}
                placeholder='{"name":"Hà Nội", "relationship":"special_experience"}'
                aria-label="Search relationships"
              />
              <details className="kgRelationshipHideFilter">
                <summary>Ẩn cạnh</summary>
                <div className="kgRelationshipHideMenu">
                  {relationshipTypes.map((relationshipType) => (
                    <label key={relationshipType}>
                      <input
                        type="checkbox"
                        checked={hiddenRelationshipTypes.has(relationshipType)}
                        onChange={() =>
                          setHiddenRelationshipTypes((current) => {
                            const next = new Set(current);
                            if (next.has(relationshipType)) next.delete(relationshipType);
                            else next.add(relationshipType);
                            return next;
                          })
                        }
                      />
                      {relationshipType}
                    </label>
                  ))}
                  {hiddenRelationshipTypes.size > 0 && (
                    <button type="button" onClick={() => setHiddenRelationshipTypes(new Set())}>
                      Hiện lại tất cả
                    </button>
                  )}
                </div>
              </details>
              <button type="button" className="kgSectionEdit" disabled={isSaving} onClick={addRelationshipRow}>
                Add relationship
              </button>
            </div>
          }
        >
          {filteredRelationshipRows.length > 0 ? (
            <div className="kgSectionEditList">
              <datalist id="kg-relationship-node-options">
                {relationshipNodeIds.map((nodeId) => (
                  <option key={`current-${nodeId}`} value={nodeId} />
                ))}
                {nodeOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.canonicalName}
                  </option>
                ))}
              </datalist>
              {filteredRelationshipRows.map((row) => (
                <div key={row.clientKey} className="kgRelationshipEditRow">
                  <NodeFilterSelect
                    value={row.fromEntityId}
                    currentIds={relationshipNodeIds}
                    options={nodeOptions}
                    labels={nodeLabels}
                    onSearch={setNodeSearch}
                    onChange={(value) =>
                      updateRelationshipRow(row.clientKey, (current) => ({ ...current, fromEntityId: value }))
                    }
                    disabled={isSaving}
                  />
                  <select
                    value={row.relationship}
                    onChange={(event) =>
                      updateRelationshipRow(row.clientKey, (current) => ({ ...current, relationship: event.target.value }))
                    }
                    aria-label="Relationship type"
                    disabled={isSaving}
                  >
                    <option value="">Select relationship type</option>
                    {availableRelationshipTypes.map((relationshipType) => (
                      <option key={relationshipType} value={relationshipType}>
                        {relationshipType}
                      </option>
                    ))}
                    {row.relationship && !availableRelationshipTypes.includes(row.relationship) && (
                      <option value={row.relationship}>{row.relationship}</option>
                    )}
                  </select>
                  <NodeFilterSelect
                    value={row.toEntityId}
                    currentIds={relationshipNodeIds}
                    options={nodeOptions}
                    labels={nodeLabels}
                    onSearch={setNodeSearch}
                    onChange={(value) =>
                      updateRelationshipRow(row.clientKey, (current) => ({ ...current, toEntityId: value }))
                    }
                    disabled={isSaving}
                  />
                  <button
                    type="button"
                    className="kgMiniPrimary"
                    disabled={isSaving || savingKey === `relationship-${row.clientKey}`}
                    onClick={() => void saveRelationship(row)}
                    title={row.id === null ? "Create relationship" : "Save relationship changes"}
                    aria-label="Save relationship"
                  >
                    ✓
                  </button>
                  <button
                    type="button"
                    className="kgMiniDanger"
                    disabled={isSaving}
                    onClick={() => void removeRelationship(row)}
                    title={row.id === null ? "Discard this relationship" : "Delete this relationship"}
                    aria-label="Delete relationship"
                  >
                    ×
                  </button>
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
              <b>Relationships đang bị ẩn theo filter</b>
            </div>
          )}
        </InspectorSection>

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
