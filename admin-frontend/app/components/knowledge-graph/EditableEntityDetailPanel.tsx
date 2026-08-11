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
    canonicalName: entity.canonicalName,
    entityType: entity.entityType,
    status: entity.status,
  });
  const [aliasRows, setAliasRows] = useState<EditableAliasRow[]>([]);
  const [propertyRows, setPropertyRows] = useState<EditablePropertyRow[]>([]);
  const [relationshipRows, setRelationshipRows] = useState<EditableRelationshipRow[]>([]);
  const [localError, setLocalError] = useState("");
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const sections = useCollapsedSections(KG_DEFAULT_COLLAPSED_SECTIONS);

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
    setPropertyRows((current) => [
      ...current,
      { clientKey: createRowKey(), id: null, key: availablePropertyKeys[0] ?? "", value: "" },
    ]);
  }, [availablePropertyKeys, createRowKey]);

  const addRelationshipRow = useCallback(() => {
    setRelationshipRows((current) => [
      ...current,
      {
        clientKey: createRowKey(),
        id: null,
        fromEntityId: entity.id,
        relationship: availableRelationshipTypes[0] ?? "",
        toEntityId: "",
      },
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
              <input value={entity.id} disabled />
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
                onChange={(event) => setDraftEntity((current) => ({ ...current, entityType: event.target.value }))}
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
            <button type="button" className="kgSectionEdit" disabled={isSaving} onClick={addRelationshipRow}>
              Add relationship
            </button>
          }
        >
          {relationshipRows.length > 0 ? (
            <div className="kgSectionEditList">
              {relationshipRows.map((row) => (
                <div key={row.clientKey} className="kgRelationshipEditRow">
                  <input
                    value={row.fromEntityId}
                    onChange={(event) =>
                      updateRelationshipRow(row.clientKey, (current) => ({ ...current, fromEntityId: event.target.value }))
                    }
                    placeholder="From ID"
                    aria-label="From entity ID"
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
                  <input
                    value={row.toEntityId}
                    onChange={(event) =>
                      updateRelationshipRow(row.clientKey, (current) => ({ ...current, toEntityId: event.target.value }))
                    }
                    placeholder="To ID"
                    aria-label="To entity ID"
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
              <b>No relationships</b>
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
