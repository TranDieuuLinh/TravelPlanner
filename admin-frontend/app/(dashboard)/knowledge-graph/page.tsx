"use client";

import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  KnowledgeAlias,
  KnowledgeEntity,
  KnowledgeEntityStatus,
  KnowledgeEntityType,
  KnowledgeProperty,
  KnowledgeRelationship,
  OntologyNode,
  OntologyRelationship,
  ValidationIssue,
  initialEntities,
  ontologyNodes,
  ontologyRelationships,
  parseAliases,
  parseEntities,
  parseOntology,
  parseNodeTypeDefinitions,
  parseProperties,
  parseRelationships,
  rawDataset,
  resolveNodeTypeProperties,
  serializeAliases,
  serializeEntities,
  serializeOntology,
  serializeProperties,
  serializeRelationships,
  serializeSchema,
  validateKnowledgeGraph
} from "../../../lib/knowledge-graph";
import {
  KnowledgeGraphFiles,
  loadKnowledgeGraphFiles,
  saveKnowledgeGraphFile,
  saveKnowledgeGraphFiles
} from "../../../lib/api";
import { KnowledgeGraphAIImports } from "../../components/KnowledgeGraphAIImports";

type WorkspaceTab =
  | "entities"
  | "aliases"
  | "relationships"
  | "ontology"
  | "aiImports"
  | "validation";

const TABS: Array<{ id: WorkspaceTab; label: string }> = [
  { id: "entities", label: "Entities" },
  { id: "aliases", label: "Aliases" },
  { id: "relationships", label: "Relationships" },
  { id: "ontology", label: "Ontology" },
  { id: "aiImports", label: "✦ AI Imports" },
  { id: "validation", label: "Validation" }
];

const STATUS_LABELS: Record<KnowledgeEntityStatus, string> = {
  missing: "Thiếu entity",
  draft: "Bản nháp",
  verified: "Đã xác minh"
};

function severityLabel(severity: ValidationIssue["severity"]) {
  return severity === "error" ? "Lỗi" : severity === "warning" ? "Cảnh báo" : "Thông tin";
}

export default function KnowledgeGraphPage() {
  const [entities, setEntities] = useState(initialEntities);
  const [aliasRows, setAliasRows] = useState<KnowledgeAlias[]>(parseAliases(rawDataset["aliases.csv"]));
  const [propertyRows, setPropertyRows] = useState<KnowledgeProperty[]>(parseProperties(rawDataset["properties.csv"]));
  const [relationshipRows, setRelationshipRows] = useState<KnowledgeRelationship[]>([]);
  const [nodeDefinitions, setNodeDefinitions] = useState<OntologyNode[]>(ontologyNodes);
  const [relationshipDefinitions, setRelationshipDefinitions] = useState<OntologyRelationship[]>(ontologyRelationships);
  const [datasetFiles, setDatasetFiles] = useState<KnowledgeGraphFiles>(rawDataset);
  const [datasetLoading, setDatasetLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("entities");
  const [selectedId, setSelectedId] = useState(initialEntities[0]?.id ?? "");
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<KnowledgeEntityType | "all">("all");
  const [statusFilter, setStatusFilter] = useState<KnowledgeEntityStatus | "all">("all");
  const [notice, setNotice] = useState("");
  const [validatedAt, setValidatedAt] = useState<Date | null>(null);
  const [importedFiles, setImportedFiles] = useState<string[]>([]);
  const [entityEditor, setEntityEditor] = useState<"new" | string | null>(null);
  const [entityDraft, setEntityDraft] = useState({ id: "", name: "", type: "TravelPlace", status: "draft" });
  const importInputRef = useRef<HTMLInputElement>(null);

  const nodeTypeDefinitions = useMemo(
    () => parseNodeTypeDefinitions(datasetFiles["schema.yaml"]),
    [datasetFiles]
  );
  const nodeTypeProperties = useMemo(
    () => Object.fromEntries(
      nodeDefinitions.map((node) => [
        node.type,
        resolveNodeTypeProperties(node.type, nodeTypeDefinitions)
      ])
    ),
    [nodeDefinitions, nodeTypeDefinitions]
  );
  const issues = useMemo(
    () => validateKnowledgeGraph(entities, relationshipRows, nodeDefinitions, relationshipDefinitions, nodeTypeDefinitions),
    [entities, nodeDefinitions, nodeTypeDefinitions, relationshipDefinitions, relationshipRows]
  );
  const errorCount = issues.filter((issue) => issue.severity === "error").length;
  const typeFilterOptions = useMemo<Array<KnowledgeEntityType | "all">>(
    () => ["all", ...nodeDefinitions.map((node) => node.type)],
    [nodeDefinitions]
  );
  const persistedCount = entities.filter((entity) => entity.status !== "missing").length;
  const selectedEntity = entities.find((entity) => entity.id === selectedId) ?? null;
  const selectedProperties = useMemo(
    () => propertyRows.filter((property) => property.entityId === selectedId),
    [propertyRows, selectedId]
  );
  const selectedRelationships = useMemo(
    () => relationshipRows.filter(
      (relationship) => relationship.fromEntityId === selectedId || relationship.toEntityId === selectedId
    ),
    [relationshipRows, selectedId]
  );

  const filteredEntities = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("vi");
    return entities.filter((entity) => {
      const matchesQuery =
        !normalizedQuery ||
        entity.id.toLocaleLowerCase("vi").includes(normalizedQuery) ||
        entity.name.toLocaleLowerCase("vi").includes(normalizedQuery) ||
        entity.aliases.some((alias) =>
          alias.toLocaleLowerCase("vi").includes(normalizedQuery)
        );
      const matchesType = typeFilter === "all" || entity.type === typeFilter;
      const matchesStatus = statusFilter === "all" || entity.status === statusFilter;
      return matchesQuery && matchesType && matchesStatus;
    });
  }, [entities, query, statusFilter, typeFilter]);

  useEffect(() => {
    let active = true;
    loadKnowledgeGraphFiles()
      .then((files) => {
        if (!active) return;
        const loadedAliases = parseAliases(files["aliases.csv"]);
        const loadedEntities = parseEntities(files["entities.csv"]);
        const loadedProperties = parseProperties(files["properties.csv"]);
        const loadedRelationships = parseRelationships(files["relationships.csv"]);
        const loadedOntology = parseOntology(files["ontology.yaml"]);
        const mergedNodes = loadedOntology.nodes.length > 0
          ? loadedOntology.nodes
          : ontologyNodes;
        const mergedRelationships = loadedOntology.relationships.length > 0
          ? loadedOntology.relationships
          : ontologyRelationships;
        const referenced = Array.from(new Set([
          ...loadedAliases.map((item) => item.entityId),
          ...loadedRelationships.flatMap((item) => [item.fromEntityId, item.toEntityId])
        ]));
        setAliasRows(loadedAliases);
        setPropertyRows(loadedProperties);
        setRelationshipRows(loadedRelationships);
        setNodeDefinitions(mergedNodes);
        setRelationshipDefinitions(mergedRelationships);
        setDatasetFiles(files);
        const combinedEntities = loadedEntities.map((entity) => ({
          ...entity,
          aliases: loadedAliases.filter((item) => item.entityId === entity.id).map((item) => item.alias),
          properties: Object.fromEntries(
            loadedProperties
              .filter((item) => item.entityId === entity.id)
              .map((item) => [item.key, item.value])
          )
        }));
        referenced.forEach((entityId) => {
          if (combinedEntities.some((item) => item.id === entityId)) return;
            const entityAliases = loadedAliases.filter((item) => item.entityId === entityId);
            const current = initialEntities.find((item) => item.id === entityId);
            const relatedEdge = loadedRelationships.find(
              (item) => item.fromEntityId === entityId || item.toEntityId === entityId
            );
            const relatedDefinition = mergedRelationships.find(
              (item) => item.type === relatedEdge?.relationship
            );
            const inferredType = relatedEdge?.fromEntityId === entityId
              ? relatedDefinition?.from
              : relatedDefinition?.to;
            combinedEntities.push(current
              ? { ...current, aliases: entityAliases.map((item) => item.alias) }
              : {
                  id: entityId,
                  name: entityAliases[0]?.alias ?? entityId,
                  type: inferredType ?? "Place",
                  status: "missing" as const,
                  aliases: entityAliases.map((item) => item.alias),
                  properties: Object.fromEntries(
                    loadedProperties
                      .filter((item) => item.entityId === entityId)
                      .map((item) => [item.key, item.value])
                  ),
                  sourceFile: "aliases.csv"
                });
        });
        setEntities(combinedEntities);
      })
      .catch((error) => {
        if (active) setNotice(error instanceof Error ? error.message : "Không đọc được knowledge graph.");
      })
      .finally(() => {
        if (active) setDatasetLoading(false);
      });
    return () => { active = false; };
  }, []);

  async function persistFile(
    fileName: keyof KnowledgeGraphFiles,
    content: string,
    successMessage: string
  ) {
    setSaving(true);
    setNotice("");
    try {
      await saveKnowledgeGraphFile(fileName, content);
      setDatasetFiles((current) => ({ ...current, [fileName]: content }));
      setNotice(successMessage);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : `Không lưu được ${fileName}.`);
      throw error;
    } finally {
      setSaving(false);
    }
  }

  async function persistFiles(
    updates: Partial<KnowledgeGraphFiles>,
    successMessage: string
  ) {
    setSaving(true);
    setNotice("");
    try {
      await saveKnowledgeGraphFiles(updates);
      setDatasetFiles((current) => ({ ...current, ...updates }));
      setNotice(successMessage);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Không lưu được knowledge graph.");
      throw error;
    } finally {
      setSaving(false);
    }
  }

  async function saveAliases(nextRows: KnowledgeAlias[]) {
    const content = serializeAliases(nextRows);
    await persistFile("aliases.csv", content, "Đã lưu thay đổi trực tiếp vào aliases.csv.");
    setAliasRows(nextRows);
    setEntities((current) => {
      const referencedIds = new Set([
        ...nextRows.map((item) => item.entityId),
        ...relationshipRows.flatMap((item) => [item.fromEntityId, item.toEntityId])
      ]);
      const nextEntities = current
        .filter((entity) => entity.status !== "missing" || referencedIds.has(entity.id))
        .map((entity) => ({
        ...entity,
        aliases: nextRows.filter((item) => item.entityId === entity.id).map((item) => item.alias)
        }));
      referencedIds.forEach((entityId) => {
        if (nextEntities.some((entity) => entity.id === entityId)) return;
        const entityAliases = nextRows.filter((item) => item.entityId === entityId).map((item) => item.alias);
        nextEntities.push({
          id: entityId,
          name: entityAliases[0] ?? entityId,
          type: "Place",
          status: "missing",
          aliases: entityAliases,
          properties: {},
          sourceFile: "aliases.csv"
        });
      });
      return nextEntities;
    });
  }

  async function saveProperties(nextRows: KnowledgeProperty[]) {
    const content = serializeProperties(nextRows);
    await persistFile("properties.csv", content, "Đã lưu properties trực tiếp vào properties.csv.");
    setPropertyRows(nextRows);
    setEntities((current) => current.map((entity) => ({
      ...entity,
      properties: Object.fromEntries(
        nextRows
          .filter((property) => property.entityId === entity.id)
          .map((property) => [property.key, property.value])
      )
    })));
  }

  async function saveEntityIdentity(
    entityId: string,
    input: Pick<KnowledgeEntity, "name" | "type" | "status">
  ) {
    const nextEntities = entities.map((entity) =>
      entity.id === entityId ? { ...entity, ...input } : entity
    );
    await persistFile(
      "entities.csv",
      serializeEntities(nextEntities),
      "Đã lưu thông tin entity trực tiếp vào entities.csv."
    );
    setEntities(nextEntities);
  }

  function beginAddEntity(prefill?: KnowledgeEntity) {
    setEntityEditor(prefill?.id ?? "new");
    setEntityDraft({
      id: prefill?.id ?? "",
      name: prefill?.name ?? "",
      type: prefill?.type ?? nodeDefinitions[0]?.type ?? "TravelPlace",
      status: prefill?.status === "verified" ? "verified" : "draft"
    });
  }

  async function submitEntity(event: FormEvent) {
    event.preventDefault();
    if (!entityDraft.id.trim() || !entityDraft.name.trim() || !entityDraft.type.trim()) {
      setNotice("ID, tên và loại entity là bắt buộc.");
      return;
    }
    const duplicate = entities.some(
      (item) => item.id === entityDraft.id.trim() && item.id !== entityEditor
    );
    if (duplicate) {
      setNotice(`Entity ID ${entityDraft.id.trim()} đã tồn tại.`);
      return;
    }
    const nextEntity: KnowledgeEntity = {
      id: entityDraft.id.trim(),
      name: entityDraft.name.trim(),
      type: entityDraft.type.trim() as KnowledgeEntityType,
      status: entityDraft.status as KnowledgeEntityStatus,
      aliases: aliasRows.filter((item) => item.entityId === entityDraft.id.trim()).map((item) => item.alias),
      properties: {},
      sourceFile: "entities.csv"
    };
    const isExisting = entityEditor !== "new" && entities.some((item) => item.id === entityEditor);
    const nextEntities = isExisting
      ? entities.map((item) => item.id === entityEditor ? nextEntity : item)
      : [...entities.filter((item) => item.id !== nextEntity.id), nextEntity];
    try {
      await persistFile(
        "entities.csv",
        serializeEntities(nextEntities),
        "Đã lưu entity trực tiếp vào entities.csv."
      );
      setEntities(nextEntities);
      setSelectedId(nextEntity.id);
      setEntityEditor(null);
    } catch {
      // persistFile displays the error.
    }
  }

  async function deleteEntity(entity: KnowledgeEntity) {
    if (entity.status === "missing") return;
    if (!window.confirm(`Xóa entity ${entity.id} khỏi entities.csv? Alias và relationship tham chiếu sẽ được giữ lại để validation báo lỗi.`)) return;
    const hasReferences = aliasRows.some((item) => item.entityId === entity.id) || relationshipRows.some((item) => item.fromEntityId === entity.id || item.toEntityId === entity.id);
    const nextEntities = hasReferences
      ? entities.map((item) => item.id === entity.id ? { ...item, status: "missing" as const, sourceFile: "aliases.csv" } : item)
      : entities.filter((item) => item.id !== entity.id);
    try {
      await persistFile("entities.csv", serializeEntities(nextEntities), `Đã xóa ${entity.id} khỏi entities.csv.`);
      setEntities(nextEntities);
      setSelectedId(nextEntities[0]?.id ?? "");
    } catch {
      // persistFile displays the error.
    }
  }

  async function saveRelationships(nextRows: KnowledgeRelationship[]) {
    const content = serializeRelationships(nextRows);
    await persistFile(
      "relationships.csv",
      content,
      "Đã lưu relationship và nguồn trực tiếp vào relationships.csv."
    );
    setRelationshipRows(nextRows);
    setEntities((current) => {
      const referencedIds = new Set([
        ...aliasRows.map((item) => item.entityId),
        ...nextRows.flatMap((item) => [item.fromEntityId, item.toEntityId])
      ]);
      const nextEntities = current.filter(
        (entity) => entity.status !== "missing" || referencedIds.has(entity.id)
      );
      referencedIds.forEach((entityId) => {
        if (nextEntities.some((entity) => entity.id === entityId)) return;
        const entityAliases = aliasRows.filter((item) => item.entityId === entityId).map((item) => item.alias);
        const relatedEdge = nextRows.find(
          (item) => item.fromEntityId === entityId || item.toEntityId === entityId
        );
        const relatedDefinition = relationshipDefinitions.find(
          (item) => item.type === relatedEdge?.relationship
        );
        const inferredType = relatedEdge?.fromEntityId === entityId
          ? relatedDefinition?.from
          : relatedDefinition?.to;
        nextEntities.push({
          id: entityId,
          name: entityAliases[0] ?? entityId,
          type: inferredType ?? "Place",
          status: "missing",
          aliases: entityAliases,
          properties: {},
          sourceFile: "relationships.csv"
        });
      });
      return nextEntities;
    });
  }

  async function saveOntology(
    nextNodes: OntologyNode[],
    nextRelationships: OntologyRelationship[]
  ) {
    const ontologyContent = serializeOntology(nextNodes, nextRelationships);
    const schemaContent = serializeSchema(nextNodes, nextRelationships, datasetFiles["schema.yaml"]);
    await persistFiles(
      { "ontology.yaml": ontologyContent, "schema.yaml": schemaContent },
      "Đã lưu ontology.yaml và đồng bộ danh sách type trong schema.yaml."
    );
    setNodeDefinitions(nextNodes);
    setRelationshipDefinitions(nextRelationships);
  }

  function openEntity(entityId: string) {
    setSelectedId(entityId);
    setActiveTab("entities");
  }

  function openIssue(issue: ValidationIssue) {
    if (issue.entityId) {
      setSelectedId(issue.entityId);
    }
    setActiveTab(issue.target);
  }

  function resetDraft() {
    window.location.reload();
  }

  function runValidation() {
    setValidatedAt(new Date());
    setNotice(
      errorCount
        ? `Validation hoàn tất: ${errorCount} lỗi đang chặn publish.`
        : "Validation hoàn tất: dataset sẵn sàng để review."
    );
    setActiveTab("validation");
  }

  function handleImport(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;
    setImportedFiles(files.map((file) => file.name));
    setNotice(
      `Đã chọn ${files.length} tệp cho draft import. Parser và API lưu dữ liệu chưa được kết nối.`
    );
    event.target.value = "";
  }

  return (
    <section className="kgPage">
      <header className="topbar kgTopbar">
        <div>
          <p className="eyebrow">Catalog intelligence</p>
          <h1>Knowledge Graph</h1>
          <p className="kgLead">
            Kiểm tra entity, alias và ontology trước khi dữ liệu được đưa vào Planner.
          </p>
        </div>
        <div className="kgHeaderActions">
          <input
            ref={importInputRef}
            className="kgFileInput"
            type="file"
            accept=".csv,.yaml,.yml"
            multiple
            onChange={handleImport}
          />
          <button className="kgSecondaryButton" type="button" onClick={() => importInputRef.current?.click()}>
            ⇧ Import dataset
          </button>
          <button className="kgPrimaryButton" type="button" onClick={runValidation}>
            ✓ Validate graph
          </button>
        </div>
      </header>

      <section className="kgSourceStrip" aria-label="Dataset source">
        <div>
          <span className="kgPulse" />
          <span>
            <b>Local prototype snapshot</b>
            <small>{datasetLoading ? "Đang đọc dataset…" : "knowledge-graph-real-v2 · 6 files"}</small>
          </span>
        </div>
        <div className="kgSourceMeta">
          {importedFiles.length > 0 && <span>{importedFiles.length} file chờ import</span>}
          <span>Draft workspace</span>
          <button type="button" onClick={resetDraft}>Tải lại từ file</button>
        </div>
      </section>

      {notice && (
        <div className="kgNotice" role="status">
          <span>i</span>
          <p>{notice}</p>
          <button type="button" aria-label="Đóng thông báo" onClick={() => setNotice("")}>×</button>
        </div>
      )}

      <section className="metricGrid kgMetrics" aria-label="Knowledge graph metrics">
        <article>
          <span>Entities</span>
          <strong>{persistedCount}</strong>
          <small>{entities.filter((entity) => entity.status === "missing").length} tham chiếu chưa tồn tại</small>
        </article>
        <article>
          <span>Aliases</span>
          <strong>{aliasRows.length}</strong>
          <small>Tiếng Việt và tiếng Anh</small>
        </article>
        <article>
          <span>Relationships</span>
          <strong>{relationshipRows.length}</strong>
          <small>{relationshipDefinitions.length} loại đã khai báo</small>
        </article>
        <article className={errorCount ? "kgMetricDanger" : ""}>
          <span>Validation issues</span>
          <strong>{issues.length}</strong>
          <small>{errorCount} lỗi đang chặn publish</small>
        </article>
      </section>

      <nav className="kgWorkspaceTabs" aria-label="Knowledge graph sections">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={activeTab === tab.id ? "active" : ""}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
            {tab.id === "validation" && <span>{issues.length}</span>}
          </button>
        ))}
      </nav>

      {activeTab === "aiImports" && (
        <KnowledgeGraphAIImports
          nodeTypes={nodeDefinitions.map((node) => node.type)}
          nodeTypeProperties={nodeTypeProperties}
          relationshipTypes={relationshipDefinitions.map((relationship) => relationship.type)}
          onApplied={resetDraft}
        />
      )}

      {activeTab === "entities" && (
        <>
          <section className="controlBar kgControlBar">
            <label className="searchField">
              <span>⌕</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Tìm tên, entity ID hoặc alias…"
              />
            </label>
            <select
              value={typeFilter}
              onChange={(event) => setTypeFilter(event.target.value as KnowledgeEntityType | "all")}
              aria-label="Lọc loại entity"
            >
              {typeFilterOptions.map((type) => (
                <option key={type} value={type}>{type === "all" ? "Mọi loại node" : type}</option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as KnowledgeEntityStatus | "all")}
              aria-label="Lọc trạng thái entity"
            >
              <option value="all">Mọi trạng thái</option>
              <option value="missing">Thiếu entity</option>
              <option value="draft">Bản nháp</option>
              <option value="verified">Đã xác minh</option>
            </select>
            <button className="kgPrimaryButton" type="button" onClick={() => beginAddEntity()}>
              ＋ Thêm entity
            </button>
          </section>

          {entityEditor !== null && (
            <form className="kgInlineEditor kgEntityEditor" onSubmit={submitEntity}>
              <label>
                <span>Entity ID</span>
                <input
                  value={entityDraft.id}
                  disabled={entityEditor !== "new" && entities.some((item) => item.id === entityEditor && item.status !== "missing")}
                  onChange={(event) => setEntityDraft((current) => ({ ...current, id: event.target.value }))}
                  placeholder="place_001"
                />
              </label>
              <label><span>Canonical name</span><input value={entityDraft.name} onChange={(event) => setEntityDraft((current) => ({ ...current, name: event.target.value }))} placeholder="Tên chuẩn" /></label>
              <label><span>Node type</span><select value={entityDraft.type} onChange={(event) => setEntityDraft((current) => ({ ...current, type: event.target.value }))}>{nodeDefinitions.map((node) => <option key={node.type} value={node.type}>{node.type}</option>)}</select></label>
              <label><span>Trạng thái</span><select value={entityDraft.status} onChange={(event) => setEntityDraft((current) => ({ ...current, status: event.target.value }))}><option value="draft">Bản nháp</option><option value="verified">Đã xác minh</option></select></label>
              <div className="kgEditorActions"><button className="kgQuietButton" type="button" onClick={() => setEntityEditor(null)}>Hủy</button><button className="kgPrimaryButton" type="submit" disabled={saving}>{saving ? "Đang lưu…" : "Lưu entity"}</button></div>
            </form>
          )}

          <section className="dataLayout kgDataLayout">
            <div className="runList kgEntityList">
              <header>
                <span>{filteredEntities.length} referenced entities</span>
                <small>entities.csv: {persistedCount} records</small>
              </header>
              {filteredEntities.length === 0 && (
                <div className="emptyState">
                  <b>Không tìm thấy entity</b>
                  <p>Thử đổi từ khóa hoặc bộ lọc hiện tại.</p>
                </div>
              )}
              {filteredEntities.map((entity) => (
                <button
                  key={entity.id}
                  type="button"
                  className={selectedId === entity.id ? "kgEntityCard active" : "kgEntityCard"}
                  onClick={() => setSelectedId(entity.id)}
                >
                  <div className="kgEntityCardTop">
                    <span className={`kgNodeType kgNode-${entity.type.toLowerCase()}`}>{entity.type}</span>
                    <span className={`status status-${entity.status === "missing" ? "failed" : entity.status}`}>
                      {STATUS_LABELS[entity.status]}
                    </span>
                  </div>
                  <h3>{entity.name}</h3>
                  <code>{entity.id}</code>
                  <p>{entity.aliases.length} alias · nguồn {entity.sourceFile}</p>
                </button>
              ))}
            </div>

            <div className="detailPane kgInspector">
              {selectedEntity ? (
                <EntityInspector
                  key={selectedEntity.id}
                  entity={selectedEntity}
                  properties={selectedProperties}
                  relationships={selectedRelationships}
                  entities={entities}
                  nodeTypes={nodeDefinitions.map((node) => node.type)}
                  relationshipTypes={relationshipDefinitions.map((relationship) => relationship.type)}
                  saving={saving}
                  issues={issues.filter((issue) => issue.entityId === selectedEntity.id)}
                  onCreate={() => beginAddEntity(selectedEntity)}
                  onDelete={() => deleteEntity(selectedEntity)}
                  onOpenEntity={openEntity}
                  onSaveIdentity={(input) => saveEntityIdentity(selectedEntity.id, input)}
                  onSaveProperties={(rows) => saveProperties([
                    ...propertyRows.filter((property) => property.entityId !== selectedEntity.id),
                    ...rows
                  ])}
                  onSaveAliases={(values) => saveAliases([
                    ...aliasRows.filter((alias) => alias.entityId !== selectedEntity.id),
                    ...values.map((alias) => ({
                      entityId: selectedEntity.id,
                      alias,
                      language: /[À-ỹ]/u.test(alias) ? "vi" as const : "en" as const
                    }))
                  ])}
                  onSaveRelationships={(rows) => saveRelationships([
                    ...relationshipRows.filter(
                      (relationship) => !selectedRelationships.some((selected) => selected.id === relationship.id)
                    ),
                    ...rows
                  ])}
                />
              ) : (
                <div className="detailEmpty">
                  <b>Chọn một entity để kiểm tra</b>
                  <p>Alias, properties và raw record sẽ xuất hiện tại đây.</p>
                </div>
              )}
            </div>
          </section>
        </>
      )}

      {activeTab === "aliases" && (
        <AliasTable
          aliases={aliasRows}
          entities={entities}
          saving={saving}
          onOpenEntity={openEntity}
          onSave={saveAliases}
        />
      )}

      {activeTab === "relationships" && (
        <RelationshipTable
          relationships={relationshipRows}
          definitions={relationshipDefinitions}
          saving={saving}
          onSave={saveRelationships}
        />
      )}

      {activeTab === "ontology" && (
        <OntologyTable
          nodes={nodeDefinitions}
          relationships={relationshipDefinitions}
          rawSchema={datasetFiles["schema.yaml"]}
          saving={saving}
          onSave={saveOntology}
        />
      )}

      {activeTab === "validation" && (
        <section className="kgPanel">
          <header className="kgPanelHeader">
            <div>
              <p className="eyebrow">Contract health</p>
              <h2>Validation report</h2>
              <p>
                {validatedAt
                  ? `Kiểm tra gần nhất lúc ${validatedAt.toLocaleTimeString("vi-VN")}`
                  : "Kết quả tự động từ snapshot đang mở."}
              </p>
            </div>
            <button className="kgPrimaryButton" type="button" onClick={runValidation}>↻ Chạy lại</button>
          </header>
          <div className="kgValidationSummary">
            <div className="kgHealthScore"><strong>{Math.max(0, 100 - errorCount * 18 - (issues.length - errorCount) * 4)}</strong><span>/ 100</span></div>
            <div><b>Dataset chưa sẵn sàng để publish</b><p>Xử lý lỗi contract trước, sau đó review các cảnh báo về độ đầy đủ dữ liệu.</p></div>
            <span className="status status-failed">{errorCount} blocking</span>
          </div>
          <div className="kgIssueList">
            {issues.map((issue) => (
              <button key={issue.id} type="button" onClick={() => openIssue(issue)}>
                <span className={`kgIssueIcon kgIssue-${issue.severity}`}>{issue.severity === "error" ? "!" : issue.severity === "warning" ? "△" : "i"}</span>
                <div><b>{issue.title}</b><p>{issue.message}</p><code>{issue.path}</code></div>
                <span className={`status status-${issue.severity === "error" ? "failed" : "warning"}`}>{severityLabel(issue.severity)}</span>
                <i>→</i>
              </button>
            ))}
          </div>
        </section>
      )}

      <footer className="kgFooter">
        <p>
          Snapshot này chỉ phục vụ giao diện quản trị. Dữ liệu chưa được ghi vào PostgreSQL,
          Place Resolver hoặc các file nguồn cho đến khi có API admin tương ứng.
        </p>
        <button type="button" disabled title="Cần xử lý validation issues và kết nối API lưu draft">
          Publish version
        </button>
      </footer>
    </section>
  );
}

function AliasTable({
  aliases,
  entities,
  saving,
  onOpenEntity,
  onSave
}: {
  aliases: KnowledgeAlias[];
  entities: KnowledgeEntity[];
  saving: boolean;
  onOpenEntity: (entityId: string) => void;
  onSave: (rows: KnowledgeAlias[]) => Promise<void>;
}) {
  const [editingIndex, setEditingIndex] = useState<number | "new" | null>(null);
  const [entityId, setEntityId] = useState("");
  const [aliasValue, setAliasValue] = useState("");
  const [formError, setFormError] = useState("");

  function beginEdit(index: number) {
    setEditingIndex(index);
    setEntityId(aliases[index].entityId);
    setAliasValue(aliases[index].alias);
    setFormError("");
  }

  function beginAdd() {
    setEditingIndex("new");
    setEntityId("");
    setAliasValue("");
    setFormError("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!entityId.trim() || !aliasValue.trim()) {
      setFormError("Entity ID và alias là bắt buộc.");
      return;
    }
    const nextRow: KnowledgeAlias = {
      entityId: entityId.trim(),
      alias: aliasValue.trim(),
      language: /[À-ỹ]/u.test(aliasValue) ? "vi" : "en"
    };
    const nextRows = editingIndex === "new"
      ? [...aliases, nextRow]
      : aliases.map((item, index) => index === editingIndex ? nextRow : item);
    try {
      await onSave(nextRows);
      setEditingIndex(null);
    } catch {
      // The parent displays the API error.
    }
  }

  async function removeAlias(index: number) {
    const item = aliases[index];
    if (!window.confirm(`Xóa alias “${item.alias}” khỏi aliases.csv?`)) return;
    try {
      await onSave(aliases.filter((_, itemIndex) => itemIndex !== index));
      if (editingIndex === index) setEditingIndex(null);
    } catch {
      // The parent displays the API error.
    }
  }

  return (
    <section className="kgPanel kgTablePanel">
      <header className="kgPanelHeader">
        <div>
          <p className="eyebrow">Identity resolution</p>
          <h2>Aliases</h2>
          <p>Mỗi alias là một dòng và được lưu trực tiếp vào aliases.csv.</p>
        </div>
        <div className="kgPanelActions">
          <span className="status status-warning">{aliases.length} records</span>
          <button className="kgPrimaryButton" type="button" onClick={beginAdd}>＋ Thêm alias</button>
        </div>
      </header>
      {editingIndex !== null && (
        <form className="kgInlineEditor kgAliasEditor" onSubmit={submit}>
          <label><span>Entity ID</span><input value={entityId} onChange={(event) => setEntityId(event.target.value)} placeholder="place_001" /></label>
          <label><span>Alias</span><input value={aliasValue} onChange={(event) => setAliasValue(event.target.value)} placeholder="Tên địa điểm" /></label>
          <div className="kgEditorActions">
            <button className="kgQuietButton" type="button" onClick={() => setEditingIndex(null)}>Hủy</button>
            <button className="kgPrimaryButton" type="submit" disabled={saving}>{saving ? "Đang lưu…" : "Lưu vào file"}</button>
          </div>
          {formError && <p>{formError}</p>}
        </form>
      )}
      <div className="kgTableScroll">
        <table className="kgTable">
          <thead><tr><th>Alias</th><th>Ngôn ngữ</th><th>Entity ID</th><th>Entity</th><th>Thao tác</th></tr></thead>
          <tbody>
            {aliases.map((alias, index) => {
              const entity = entities.find((item) => item.id === alias.entityId);
              return (
                <tr key={`${alias.entityId}-${alias.alias}-${index}`}>
                  <td><strong>{alias.alias}</strong></td>
                  <td><span className="kgLanguage">{alias.language.toUpperCase()}</span></td>
                  <td><code>{alias.entityId}</code></td>
                  <td><span className={`status status-${entity?.status === "missing" ? "failed" : "draft"}`}>{entity?.status === "missing" ? "Không tồn tại" : "Draft"}</span></td>
                  <td><div className="kgRowActions"><button type="button" onClick={() => beginEdit(index)}>Sửa</button><button type="button" onClick={() => onOpenEntity(alias.entityId)}>Mở</button><button className="danger" type="button" onClick={() => removeAlias(index)}>Xóa</button></div></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RelationshipTable({
  relationships,
  definitions,
  saving,
  onSave
}: {
  relationships: KnowledgeRelationship[];
  definitions: OntologyRelationship[];
  saving: boolean;
  onSave: (rows: KnowledgeRelationship[]) => Promise<void>;
}) {
  const [editingIndex, setEditingIndex] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState({ fromEntityId: "", relationship: "LOCATED_IN", toEntityId: "", recommendations: "[]", source: "" });
  const [formError, setFormError] = useState("");

  function beginEdit(index: number) {
    const item = relationships[index];
    setEditingIndex(index);
    setDraft({ fromEntityId: item.fromEntityId, relationship: item.relationship, toEntityId: item.toEntityId, recommendations: item.recommendations, source: item.source });
    setFormError("");
  }

  function beginAdd() {
    setEditingIndex("new");
    setDraft({ fromEntityId: "", relationship: definitions[0]?.type ?? "LOCATED_IN", toEntityId: "", recommendations: "[]", source: "" });
    setFormError("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (editingIndex === null) return;
    if (!draft.fromEntityId.trim() || !draft.toEntityId.trim() || !draft.source.trim()) {
      setFormError("Entity nguồn, entity đích và nguồn dữ liệu là bắt buộc.");
      return;
    }
    try {
      if (!Array.isArray(JSON.parse(draft.recommendations))) throw new Error();
    } catch {
      setFormError("Recommendations phải là một JSON array hợp lệ.");
      return;
    }
    const nextRow: KnowledgeRelationship = {
      id: editingIndex === "new" ? `relationship-${Date.now()}` : relationships[editingIndex].id,
      fromEntityId: draft.fromEntityId.trim(),
      relationship: draft.relationship as KnowledgeRelationship["relationship"],
      toEntityId: draft.toEntityId.trim(),
      recommendations: draft.recommendations.trim(),
      source: draft.source.trim()
    };
    const nextRows = editingIndex === "new"
      ? [...relationships, nextRow]
      : relationships.map((item, index) => index === editingIndex ? nextRow : item);
    try {
      await onSave(nextRows);
      setEditingIndex(null);
    } catch {
      // The parent displays the API error.
    }
  }

  async function removeRelationship(index: number) {
    const item = relationships[index];
    if (!window.confirm(`Xóa relationship ${item.fromEntityId} —${item.relationship}→ ${item.toEntityId}?`)) return;
    try {
      await onSave(relationships.filter((_, itemIndex) => itemIndex !== index));
      if (editingIndex === index) setEditingIndex(null);
    } catch {
      // The parent displays the API error.
    }
  }

  return (
    <section className="kgPanel kgTablePanel">
      <header className="kgPanelHeader">
        <div>
          <p className="eyebrow">Graph edges</p>
          <h2>Relationships</h2>
          <p>Mỗi relationship là một dòng; recommendations là JSON array có nguồn.</p>
        </div>
        <div className="kgPanelActions">
          <span className={`status status-${relationships.length ? "completed" : "warning"}`}>{relationships.length} records</span>
          <button className="kgPrimaryButton" type="button" onClick={beginAdd}>＋ Thêm relationship</button>
        </div>
      </header>
      {editingIndex !== null && (
        <form className="kgInlineEditor kgRelationshipEditor" onSubmit={submit}>
          <label><span>From entity</span><input value={draft.fromEntityId} onChange={(event) => setDraft((current) => ({ ...current, fromEntityId: event.target.value }))} placeholder="place_001" /></label>
          <label><span>Relationship</span><select value={draft.relationship} onChange={(event) => setDraft((current) => ({ ...current, relationship: event.target.value }))}>{definitions.map((definition) => <option key={definition.type} value={definition.type}>{definition.type}</option>)}</select></label>
          <label><span>To entity</span><input value={draft.toEntityId} onChange={(event) => setDraft((current) => ({ ...current, toEntityId: event.target.value }))} placeholder="city_001" /></label>
          <label><span>Recommendations JSON</span><input value={draft.recommendations} onChange={(event) => setDraft((current) => ({ ...current, recommendations: event.target.value }))} placeholder="[]" /></label>
          <label><span>Nguồn</span><input value={draft.source} onChange={(event) => setDraft((current) => ({ ...current, source: event.target.value }))} placeholder="Google Maps URL hoặc dataset" /></label>
          <div className="kgEditorActions">
            <button className="kgQuietButton" type="button" onClick={() => setEditingIndex(null)}>Hủy</button>
            <button className="kgPrimaryButton" type="submit" disabled={saving}>{saving ? "Đang lưu…" : "Lưu vào file"}</button>
          </div>
          {formError && <p>{formError}</p>}
        </form>
      )}
      <div className="kgTableScroll">
        <table className="kgTable kgRelationshipTable">
          <thead><tr><th>From</th><th>Relationship</th><th>To</th><th>Recommendations</th><th>Nguồn</th><th>Thao tác</th></tr></thead>
          <tbody>
            {relationships.length === 0 ? (
              <tr className="kgEmptyRow"><td colSpan={6}>relationships.csv chưa có bản ghi. Bấm “Thêm relationship” để tạo dòng đầu tiên.</td></tr>
            ) : relationships.map((relationship, index) => (
              <tr key={relationship.id}>
                <td><code>{relationship.fromEntityId}</code></td>
                <td><span className="kgRelationBadge">{relationship.relationship}</span></td>
                <td><code>{relationship.toEntityId}</code></td>
                <td><RecommendationView value={relationship.recommendations} compact /></td>
                <td><span className="kgSourceCell" title={relationship.source}>{relationship.source}</span></td>
                <td><div className="kgRowActions"><button type="button" onClick={() => beginEdit(index)}>Sửa</button><button className="danger" type="button" onClick={() => removeRelationship(index)}>Xóa</button></div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function OntologyTable({
  nodes,
  relationships,
  rawSchema,
  saving,
  onSave
}: {
  nodes: OntologyNode[];
  relationships: OntologyRelationship[];
  rawSchema: string;
  saving: boolean;
  onSave: (nodes: OntologyNode[], relationships: OntologyRelationship[]) => Promise<void>;
}) {
  const [editingKey, setEditingKey] = useState("");
  const [draft, setDraft] = useState({ name: "", description: "", from: "", to: "" });
  const [formError, setFormError] = useState("");

  function addNode() {
    setEditingKey("new-node");
    setDraft({ name: "", description: "", from: "", to: "" });
    setFormError("");
  }

  function addRelationship() {
    setEditingKey("new-relationship");
    setDraft({ name: "", description: "", from: "", to: "" });
    setFormError("");
  }

  function editNode(node: OntologyNode) {
    setEditingKey(`node:${node.type}`);
    setDraft({ name: node.type, description: node.description ?? "", from: "", to: "" });
    setFormError("");
  }

  function editRelationship(relationship: OntologyRelationship) {
    setEditingKey(`relationship:${relationship.type}`);
    setDraft({ name: relationship.type, description: relationship.description, from: relationship.from ?? "", to: relationship.to ?? "" });
    setFormError("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.name.trim()) {
      setFormError("Tên node hoặc relationship là bắt buộc.");
      return;
    }
    const normalizedName = draft.name.trim();
    if (
      editingKey.startsWith("new-") &&
      [...nodes.map((item) => String(item.type)), ...relationships.map((item) => String(item.type))]
        .some((item) => item === normalizedName)
    ) {
      setFormError(`${normalizedName} đã tồn tại trong ontology.`);
      return;
    }
    const [kind, name] = editingKey.split(":");
    let nextNodes = kind === "node"
      ? nodes.map((node) => node.type === name ? { ...node, description: draft.description.trim() || null } : node)
      : nodes;
    let nextRelationships = kind === "relationship"
      ? relationships.map((relationship) => relationship.type === name ? {
          ...relationship,
          from: (draft.from || null) as KnowledgeEntityType | null,
          to: (draft.to || null) as KnowledgeEntityType | null,
          description: draft.description.trim()
        } : relationship)
      : relationships;
    if (editingKey === "new-node") {
      nextNodes = [...nodes, { type: normalizedName as KnowledgeEntityType, description: draft.description.trim() || null }];
    }
    if (editingKey === "new-relationship") {
      nextRelationships = [...relationships, {
        type: normalizedName as OntologyRelationship["type"],
        from: (draft.from || null) as KnowledgeEntityType | null,
        to: (draft.to || null) as KnowledgeEntityType | null,
        description: draft.description.trim()
      }];
    }
    try {
      await onSave(nextNodes, nextRelationships);
      setEditingKey("");
    } catch {
      // The parent displays the API error.
    }
  }

  async function removeNode(node: OntologyNode) {
    if (!window.confirm(`Xóa node type ${node.type} khỏi ontology.yaml và schema.yaml?`)) return;
    try {
      await onSave(nodes.filter((item) => item.type !== node.type), relationships);
      if (editingKey === `node:${node.type}`) setEditingKey("");
    } catch {
      // The parent displays the API error.
    }
  }

  async function removeOntologyRelationship(relationship: OntologyRelationship) {
    if (!window.confirm(`Xóa relationship type ${relationship.type} khỏi ontology.yaml và schema.yaml?`)) return;
    try {
      await onSave(nodes, relationships.filter((item) => item.type !== relationship.type));
      if (editingKey === `relationship:${relationship.type}`) setEditingKey("");
    } catch {
      // The parent displays the API error.
    }
  }

  return (
    <section className="kgPanel kgTablePanel">
      <header className="kgPanelHeader">
        <div><p className="eyebrow">Domain contract</p><h2>Schema & Ontology</h2><p>Mỗi node hoặc relationship type là một dòng compact.</p></div>
        <div className="kgPanelActions"><span className="status status-draft">ontology.yaml</span><button className="kgSecondaryButton" type="button" onClick={addNode}>＋ Node</button><button className="kgPrimaryButton" type="button" onClick={addRelationship}>＋ Relationship</button></div>
      </header>
      {editingKey && (
        <form className="kgInlineEditor kgOntologyEditor" onSubmit={submit}>
          {editingKey.startsWith("new-") && <label><span>Tên type</span><input value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} placeholder={editingKey === "new-node" ? "Attraction" : "HAS_CATEGORY"} /></label>}
          <label><span>Mô tả</span><input value={draft.description} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} placeholder="Mô tả nghiệp vụ" /></label>
          {(editingKey.startsWith("relationship:") || editingKey === "new-relationship") && <>
            <label><span>From type</span><input value={draft.from} onChange={(event) => setDraft((current) => ({ ...current, from: event.target.value }))} placeholder="Area|Place" /></label>
            <label><span>To type</span><input value={draft.to} onChange={(event) => setDraft((current) => ({ ...current, to: event.target.value }))} placeholder="TravelPlace|Restaurant" /></label>
          </>}
          <div className="kgEditorActions"><button className="kgQuietButton" type="button" onClick={() => setEditingKey("")}>Hủy</button><button className="kgPrimaryButton" type="submit" disabled={saving}>{saving ? "Đang lưu…" : "Lưu ontology"}</button></div>
          {formError && <p>{formError}</p>}
        </form>
      )}
      <div className="kgTableScroll">
        <table className="kgTable kgOntologyTable">
          <thead><tr><th>Loại</th><th>Tên</th><th>From</th><th>To</th><th>Mô tả</th><th>Trạng thái</th><th>Thao tác</th></tr></thead>
          <tbody>
            {nodes.map((node) => <tr key={`node-${node.type}`}><td><span className="kgLanguage">NODE</span></td><td><strong>{node.type}</strong></td><td>—</td><td>—</td><td>{node.description ?? <span className="kgMissingText">Chưa có mô tả</span>}</td><td><span className={`status status-${node.description ? "completed" : "warning"}`}>{node.description ? "Defined" : "Missing"}</span></td><td><div className="kgRowActions"><button type="button" onClick={() => editNode(node)}>Sửa</button><button className="danger" type="button" onClick={() => removeNode(node)}>Xóa</button></div></td></tr>)}
            {relationships.map((relationship) => <tr key={`relationship-${relationship.type}`}><td><span className="kgLanguage">EDGE</span></td><td><code>{relationship.type}</code></td><td>{relationship.from ?? <span className="kgMissingText">?</span>}</td><td>{relationship.to ?? <span className="kgMissingText">?</span>}</td><td>{relationship.description}</td><td><span className={`status status-${relationship.from && relationship.to ? "completed" : "failed"}`}>{relationship.from && relationship.to ? "Defined" : "Incomplete"}</span></td><td><div className="kgRowActions"><button type="button" onClick={() => editRelationship(relationship)}>Sửa</button><button className="danger" type="button" onClick={() => removeOntologyRelationship(relationship)}>Xóa</button></div></td></tr>)}
          </tbody>
        </table>
      </div>
      <details className="kgSchemaDetails"><summary>Xem schema.yaml</summary><RawFile name="schema.yaml" value={rawSchema} /></details>
    </section>
  );
}

function EntityInspector({
  entity,
  properties,
  relationships,
  entities,
  nodeTypes,
  relationshipTypes,
  saving,
  issues,
  onCreate,
  onDelete,
  onOpenEntity,
  onSaveIdentity,
  onSaveProperties,
  onSaveAliases,
  onSaveRelationships
}: {
  entity: KnowledgeEntity;
  properties: KnowledgeProperty[];
  relationships: KnowledgeRelationship[];
  entities: KnowledgeEntity[];
  nodeTypes: KnowledgeEntityType[];
  relationshipTypes: string[];
  saving: boolean;
  issues: ValidationIssue[];
  onCreate: () => void;
  onDelete: () => void;
  onOpenEntity: (entityId: string) => void;
  onSaveIdentity: (input: Pick<KnowledgeEntity, "name" | "type" | "status">) => Promise<void>;
  onSaveProperties: (rows: KnowledgeProperty[]) => Promise<void>;
  onSaveAliases: (values: string[]) => Promise<void>;
  onSaveRelationships: (rows: KnowledgeRelationship[]) => Promise<void>;
}) {
  type EditSection = "identity" | "properties" | "aliases" | "relationships";
  const [editing, setEditing] = useState<EditSection | null>(null);
  const [sectionError, setSectionError] = useState("");
  const [identityDraft, setIdentityDraft] = useState({
    name: entity.name,
    type: entity.type,
    status: entity.status
  });
  const [propertyDraft, setPropertyDraft] = useState(properties.map((property) => ({ ...property })));
  const [aliasDraft, setAliasDraft] = useState([...entity.aliases]);
  const [relationshipDraft, setRelationshipDraft] = useState(relationships.map((relationship) => ({ ...relationship })));

  function beginSection(section: EditSection) {
    setSectionError("");
    if (section === "identity") setIdentityDraft({ name: entity.name, type: entity.type, status: entity.status });
    if (section === "properties") setPropertyDraft(properties.map((property) => ({ ...property })));
    if (section === "aliases") setAliasDraft([...entity.aliases]);
    if (section === "relationships") setRelationshipDraft(relationships.map((relationship) => ({ ...relationship })));
    setEditing(section);
  }

  async function saveSection(section: EditSection) {
    setSectionError("");
    try {
      if (section === "identity") {
        if (!identityDraft.name.trim() || !identityDraft.type.trim()) throw new Error("Tên và node type là bắt buộc.");
        await onSaveIdentity({ ...identityDraft, name: identityDraft.name.trim() });
      }
      if (section === "properties") {
        if (propertyDraft.some((row) => !row.key.trim() || !row.source.trim())) throw new Error("Mỗi property phải có key và nguồn.");
        const keys = propertyDraft.map((row) => row.key.trim());
        if (new Set(keys).size !== keys.length) throw new Error("Key property không được trùng trong cùng entity.");
        const specialExperienceRow = propertyDraft.find((row) => row.key.trim() === "special_experience");
        if (specialExperienceRow) {
          try {
            if (!Array.isArray(JSON.parse(specialExperienceRow.value))) throw new Error();
          } catch {
            throw new Error("Property special_experience phải là một JSON array hợp lệ.");
          }
        }
        await onSaveProperties(propertyDraft.map((row) => ({ ...row, entityId: entity.id, key: row.key.trim(), source: row.source.trim() })));
      }
      if (section === "aliases") {
        const values = aliasDraft.map((value) => value.trim()).filter(Boolean);
        if (new Set(values).size !== values.length) throw new Error("Alias không được trùng trong cùng entity.");
        await onSaveAliases(values);
      }
      if (section === "relationships") {
        if (relationshipDraft.some((row) => !row.fromEntityId || !row.relationship || !row.toEntityId || !row.source.trim())) {
          throw new Error("From, relationship, to và nguồn là bắt buộc.");
        }
        if (relationshipDraft.some((row) => {
          try { return !Array.isArray(JSON.parse(row.recommendations)); } catch { return true; }
        })) throw new Error("Recommendations của mỗi relationship phải là JSON array hợp lệ.");
        await onSaveRelationships(relationshipDraft.map((row) => ({ ...row, source: row.source.trim() })));
      }
      setEditing(null);
    } catch (error) {
      setSectionError(error instanceof Error ? error.message : "Không lưu được thay đổi.");
    }
  }

  function sectionActions(section: EditSection) {
    if (editing !== section) {
      return <button className="kgSectionEdit" type="button" disabled={editing !== null || entity.status === "missing"} onClick={() => beginSection(section)}>Sửa</button>;
    }
    return (
      <span className="kgSectionActions">
        <button type="button" disabled={saving} onClick={() => setEditing(null)}>Hủy</button>
        <button className="save" type="button" disabled={saving} onClick={() => void saveSection(section)}>{saving ? "Đang lưu…" : "Lưu"}</button>
      </span>
    );
  }

  return (
    <>
      <header className="detailHeader kgInspectorHeader">
        <div>
          <p className="eyebrow">Referenced entity</p>
          <h2>{entity.name}</h2>
          <p>{entity.id} · nguồn {entity.sourceFile}</p>
        </div>
        <span className={`status status-${entity.status === "missing" ? "failed" : entity.status}`}>{STATUS_LABELS[entity.status]}</span>
      </header>

      <div className="kgInspectorBody kgInspectorAll">
        {issues.length > 0 && (
          <div className="kgInlineIssues">
            <b>Validation issues</b>
            {issues.map((issue) => <p key={issue.id}><span>!</span>{issue.message}</p>)}
          </div>
        )}

        <section className="kgDefinitionList kgInspectorSection">
          <header>
            <h3>Thông tin entity</h3>
            <div className="kgSectionHeaderActions">
              {entity.status === "missing" ? (
                <button className="kgSectionEdit" type="button" onClick={onCreate}>Tạo entity</button>
              ) : (
                <>{sectionActions("identity")}<button className="kgSectionDelete" type="button" disabled={editing !== null || saving} onClick={onDelete}>Xóa</button></>
              )}
            </div>
          </header>
          {editing === "identity" ? (
            <div className="kgSectionForm kgIdentitySectionForm">
              <label><span>Canonical ID</span><input value={entity.id} disabled /></label>
              <label><span>Canonical name</span><input value={identityDraft.name} onChange={(event) => setIdentityDraft((current) => ({ ...current, name: event.target.value }))} /></label>
              <label><span>Node type</span><select value={identityDraft.type} onChange={(event) => setIdentityDraft((current) => ({ ...current, type: event.target.value }))}>{nodeTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></label>
              <label><span>Trạng thái</span><select value={identityDraft.status} onChange={(event) => setIdentityDraft((current) => ({ ...current, status: event.target.value as KnowledgeEntityStatus }))}><option value="draft">Bản nháp</option><option value="verified">Đã xác minh</option></select></label>
            </div>
          ) : (
            <dl>
              <div><dt>Canonical name</dt><dd>{entity.name}</dd></div>
              <div><dt>Canonical ID</dt><dd><code>{entity.id}</code></dd></div>
              <div><dt>Node type</dt><dd>{entity.type}</dd></div>
              <div><dt>Status</dt><dd>{STATUS_LABELS[entity.status]}</dd></div>
              <div><dt>Source file</dt><dd><code>{entity.sourceFile}</code></dd></div>
            </dl>
          )}
          {editing === "identity" && sectionError && <p className="kgSectionError">{sectionError}</p>}
        </section>

        <section className="kgInspectorSection">
          <header><h3>Properties</h3><div className="kgSectionHeaderActions"><span className="kgSectionCount">{properties.length}</span>{sectionActions("properties")}</div></header>
          {editing === "properties" ? (
            <div className="kgSectionEditList">
              {propertyDraft.map((property, index) => (
                <div className="kgPropertyEditRow" key={`${property.key}-${index}`}>
                  <input aria-label="Property key" value={property.key} onChange={(event) => setPropertyDraft((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, key: event.target.value } : row))} placeholder="key" />
                  <input aria-label="Property value" value={property.value} onChange={(event) => setPropertyDraft((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, value: event.target.value } : row))} placeholder="value" />
                  <input aria-label="Property source" value={property.source} onChange={(event) => setPropertyDraft((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, source: event.target.value } : row))} placeholder="Nguồn" />
                  <input aria-label="Property note" value={property.note} onChange={(event) => setPropertyDraft((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, note: event.target.value } : row))} placeholder="Ghi chú" />
                  <button className="kgMiniDanger" type="button" onClick={() => setPropertyDraft((current) => current.filter((_, rowIndex) => rowIndex !== index))}>×</button>
                </div>
              ))}
              <button className="kgAddRowButton" type="button" onClick={() => setPropertyDraft((current) => [...current, { entityId: entity.id, key: "", value: "", source: "", note: "" }])}>＋ Thêm property</button>
            </div>
          ) : properties.length > 0 ? (
            <div className="kgPropertyTableWrap">
              <table className="kgPropertyTable">
                <thead><tr><th>Key</th><th>Value</th><th>Nguồn</th><th>Ghi chú</th></tr></thead>
                <tbody>
                  {properties.map((property, index) => (
                    <tr key={`${property.key}-${index}`}>
                      <td><code>{property.key}</code></td>
                      <td>{property.key === "special_experience" ? <RecommendationView value={property.value} /> : property.value || <span className="kgMissingText">Trống</span>}</td>
                      <td><SourceValue source={property.source} /></td>
                      <td>{property.note || <span className="kgMissingText">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="kgInspectorEmpty kgInspectorEmptyCompact"><span>◇</span><b>Chưa có property</b><p>Không có dòng tương ứng trong properties.csv.</p></div>
          )}
          {editing === "properties" && sectionError && <p className="kgSectionError">{sectionError}</p>}
        </section>

        <section className="kgInspectorSection">
          <header><h3>Aliases</h3><div className="kgSectionHeaderActions"><span className="kgSectionCount">{entity.aliases.length}</span>{sectionActions("aliases")}</div></header>
          {editing === "aliases" ? (
            <div className="kgSectionEditList">
              {aliasDraft.map((alias, index) => (
                <div className="kgAliasEditRow" key={`${alias}-${index}`}>
                  <input aria-label={`Alias ${index + 1}`} value={alias} onChange={(event) => setAliasDraft((current) => current.map((value, rowIndex) => rowIndex === index ? event.target.value : value))} placeholder="Alias" />
                  <button className="kgMiniDanger" type="button" onClick={() => setAliasDraft((current) => current.filter((_, rowIndex) => rowIndex !== index))}>×</button>
                </div>
              ))}
              <button className="kgAddRowButton" type="button" onClick={() => setAliasDraft((current) => [...current, ""])}>＋ Thêm alias</button>
            </div>
          ) : entity.aliases.length > 0 ? (
            <div className="kgAliasCards">
              {entity.aliases.map((alias, index) => (
                <article key={`${alias}-${index}`}><span>{index + 1}</span><div><b>{alias}</b><small>{/[À-ỹ]/u.test(alias) ? "Vietnamese" : "Other"}</small></div><code>aliases.csv</code></article>
              ))}
            </div>
          ) : (
            <div className="kgInspectorEmpty kgInspectorEmptyCompact"><span>◇</span><b>Chưa có alias</b></div>
          )}
          {editing === "aliases" && sectionError && <p className="kgSectionError">{sectionError}</p>}
        </section>

        <section className="kgInspectorSection">
          <header><h3>Relationships</h3><div className="kgSectionHeaderActions"><span className="kgSectionCount">{relationships.length}</span>{sectionActions("relationships")}</div></header>
          {editing === "relationships" ? (
            <div className="kgSectionEditList">
              {relationshipDraft.map((relationship, index) => (
                <div className="kgRelationshipEditRow" key={relationship.id}>
                  <select aria-label="From entity" value={relationship.fromEntityId} onChange={(event) => setRelationshipDraft((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, fromEntityId: event.target.value } : row))}>{entities.filter((item) => item.status !== "missing").map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
                  <select aria-label="Relationship type" value={relationship.relationship} onChange={(event) => setRelationshipDraft((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, relationship: event.target.value } : row))}>{relationshipTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select>
                  <select aria-label="To entity" value={relationship.toEntityId} onChange={(event) => setRelationshipDraft((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, toEntityId: event.target.value } : row))}>{entities.filter((item) => item.status !== "missing").map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
                  <input aria-label="Relationship recommendations" value={relationship.recommendations} onChange={(event) => setRelationshipDraft((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, recommendations: event.target.value } : row))} placeholder="Recommendations JSON array" />
                  <input aria-label="Relationship source" value={relationship.source} onChange={(event) => setRelationshipDraft((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, source: event.target.value } : row))} placeholder="Nguồn" />
                  <button className="kgMiniDanger" type="button" onClick={() => setRelationshipDraft((current) => current.filter((_, rowIndex) => rowIndex !== index))}>×</button>
                </div>
              ))}
              <button className="kgAddRowButton" type="button" onClick={() => setRelationshipDraft((current) => [...current, {
                id: `relationship-new-${Date.now()}-${current.length}`,
                fromEntityId: entity.id,
                relationship: relationshipTypes[0] ?? "",
                toEntityId: entities.find((item) => item.id !== entity.id && item.status !== "missing")?.id ?? entity.id,
                recommendations: "[]",
                source: ""
              }])}>＋ Thêm relationship</button>
            </div>
          ) : relationships.length > 0 ? (
            <div className="kgRelationCards">
              {relationships.map((relationship) => {
                const outgoing = relationship.fromEntityId === entity.id;
                const relatedId = outgoing ? relationship.toEntityId : relationship.fromEntityId;
                const relatedEntity = entities.find((item) => item.id === relatedId);
                return (
                  <article key={relationship.id}>
                    <span className={`kgRelationDirection ${outgoing ? "outgoing" : "incoming"}`}>{outgoing ? "OUT" : "IN"}</span>
                    <div>
                      <code>{relationship.relationship}</code>
                      <button type="button" onClick={() => onOpenEntity(relatedId)}>{relatedEntity?.name ?? relatedId}</button>
                      <small>{outgoing ? `${entity.id} → ${relatedId}` : `${relatedId} → ${entity.id}`}</small>
                      <RecommendationView value={relationship.recommendations} />
                    </div>
                    <SourceValue source={relationship.source} />
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="kgInspectorEmpty kgInspectorEmptyCompact"><span>◇</span><b>Chưa có relationship</b><p>Entity này chưa được nối với node nào khác.</p></div>
          )}
          {editing === "relationships" && sectionError && <p className="kgSectionError">{sectionError}</p>}
        </section>
      </div>
    </>
  );
}

function SourceValue({ source }: { source: string }) {
  if (!source) return <span className="kgMissingText">Thiếu nguồn</span>;
  if (/^https?:\/\//i.test(source)) {
    return <a className="kgSourceLink" href={source} target="_blank" rel="noreferrer">Mở nguồn ↗</a>;
  }
  return <code className="kgSourceCode">{source}</code>;
}

function RecommendationView({ value, compact = false }: { value: string; compact?: boolean }) {
  let items: Array<Record<string, unknown>>;
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!Array.isArray(parsed)) throw new Error();
    items = parsed.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item));
  } catch {
    return <code className="kgRecommendationInvalid">JSON không hợp lệ</code>;
  }
  if (items.length === 0) return <span className="kgMissingText">Không có recommendation</span>;
  const intentLabels: Record<string, string> = {
    visit: "Tham quan",
    eat: "Ăn uống",
    drink: "Đồ uống",
    stay: "Lưu trú",
    transfer: "Di chuyển",
    combine_visit: "Kết hợp tham quan",
    explore: "Khám phá"
  };
  const priorityLabels: Record<string, string> = {
    must: "Phải thử",
    recommended: "Nên thử",
    optional: "Tùy chọn"
  };
  if (compact) {
    return <div className="kgRecommendationCompact">{items.map((item, index) => {
      const intent = String(item.intent ?? "recommend");
      const priority = String(item.priority ?? "");
      return <span key={index}>{intentLabels[intent] ?? intent}{priority ? ` · ${priorityLabels[priority] ?? priority}` : ""}</span>;
    })}</div>;
  }
  return (
    <div className="kgRecommendationList">
      {items.map((item, index) => {
        const intent = String(item.intent ?? `recommend ${index + 1}`);
        const priority = String(item.priority ?? "");
        const timeSlots = Array.isArray(item.timeSlots)
          ? item.timeSlots.filter((slot): slot is Record<string, unknown> => Boolean(slot) && typeof slot === "object" && !Array.isArray(slot))
          : [];
        const recommendedItems = Array.isArray(item.recommendedItems) ? item.recommendedItems : [];
        const hiddenKeys = new Set(["intent", "priority", "reason", "timeSlots", "recommendedItems"]);
        const metadata = Object.entries(item).filter(([key]) => !hiddenKeys.has(key));
        return (
          <article key={index}>
            <header><b>{intentLabels[intent] ?? intent}</b>{priority && <span>{priorityLabels[priority] ?? priority}</span>}</header>
            {typeof item.reason === "string" && <p>{item.reason}</p>}
            {(metadata.length > 0 || timeSlots.length > 0) && (
              <div className="kgRecommendationFacts">
                {metadata.map(([key, metadataValue]) => (
                  <span key={key}><small>{key === "recommendedVisitMinutes" ? "Thời lượng" : key}</small><b>{key === "recommendedVisitMinutes" ? `${String(metadataValue)} phút` : Array.isArray(metadataValue) ? metadataValue.join(", ") : typeof metadataValue === "object" ? JSON.stringify(metadataValue) : String(metadataValue)}</b></span>
                ))}
                {timeSlots.map((slot, slotIndex) => <span key={slotIndex}><small>Khung giờ {slotIndex + 1}</small><b>{String(slot.start ?? "?")} – {String(slot.end ?? "?")}</b></span>)}
              </div>
            )}
            {recommendedItems.length > 0 && <div className="kgRecommendedItems">{recommendedItems.map((recommendedItem, itemIndex) => <span key={itemIndex}>{String(recommendedItem)}</span>)}</div>}
          </article>
        );
      })}
    </div>
  );
}

function RawFile({ name, value }: { name: string; value: string }) {
  return (
    <article className="kgRawFile">
      <header><span>{name}</span><small>{value ? `${value.split("\n").length} lines` : "EMPTY"}</small></header>
      <pre><code>{value || "// File is empty"}</code></pre>
    </article>
  );
}
