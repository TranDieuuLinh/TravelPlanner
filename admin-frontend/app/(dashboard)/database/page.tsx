"use client";

import { useCallback, useEffect, useState } from "react";
import {
  createKGProperty,
  deleteKGProperty,
  getKGEntityDetail,
  getKGEntityFilterOptions,
  getKGStats,
  getKGOntology,
  listKGEntities,
  listKGRelationships,
  updateKGEntity,
  updateKGProperty,
  updateKGRelationship,
  type KGEntityDetail,
  type KGEntityFilterOptions,
  type KGEntitySummary,
  type KGRelationshipListPage,
  type KGRelationshipSummary,
  type KGOntology,
  type KGStats,
} from "../../features/knowledge-graph/lib";

type View = "entities" | "relationships";
type Notice = { tone: "success" | "error"; message: string } | null;

const PAGE_SIZE = 25;

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function shortId(value: string): string {
  return value.length > 28 ? `${value.slice(0, 14)}…${value.slice(-10)}` : value;
}

export default function DatabasePage() {
  const [view, setView] = useState<View>("entities");
  const [stats, setStats] = useState<KGStats | null>(null);
  const [filters, setFilters] = useState<KGEntityFilterOptions | null>(null);
  const [ontology, setOntology] = useState<KGOntology | null>(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [relationshipFilter, setRelationshipFilter] = useState("");
  const [page, setPage] = useState(0);
  const [entities, setEntities] = useState<{ items: KGEntitySummary[]; total: number } | null>(null);
  const [relationships, setRelationships] = useState<KGRelationshipListPage | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<KGEntityDetail | null>(null);
  const [selectedRelationship, setSelectedRelationship] = useState<KGRelationshipSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  const loadOptions = useCallback(async () => {
    const [nextStats, nextFilters, nextOntology] = await Promise.all([
      getKGStats(),
      getKGEntityFilterOptions(),
      getKGOntology(),
    ]);
    setStats(nextStats);
    setFilters(nextFilters);
    setOntology(nextOntology);
  }, []);

  const loadRows = useCallback(async () => {
    setLoading(true);
    try {
      if (view === "entities") {
        const result = await listKGEntities({
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
          search: search || undefined,
          entityType: typeFilter || undefined,
          status: statusFilter || undefined,
          sortBy: "name",
          sortDirection: "asc",
        });
        setEntities({ items: result.items, total: result.total });
      } else {
        setRelationships(await listKGRelationships({
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
          search: search || undefined,
          relationship: relationshipFilter || undefined,
          sortBy: "id",
          sortDirection: "desc",
        }));
      }
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "Không tải được dữ liệu." });
    } finally {
      setLoading(false);
    }
  }, [page, relationshipFilter, search, statusFilter, typeFilter, view]);

  useEffect(() => { void loadOptions().catch((error) => setNotice({ tone: "error", message: error.message })); }, [loadOptions]);
  useEffect(() => { void loadRows(); }, [loadRows]);

  async function openEntity(entity: KGEntitySummary | string) {
    const entityId = typeof entity === "string" ? entity : entity.id;
    try {
      setSelectedEntity(await getKGEntityDetail(entityId, { aliasLimit: 100, propertyLimit: 100, relationshipLimit: 100 }));
      setSelectedRelationship(null);
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "Không tải được entity." });
    }
  }

  async function saveEntity(payload: { canonicalName: string; entityType: string; status: string }) {
    if (!selectedEntity) return;
    try {
      const next = await updateKGEntity(selectedEntity.id, payload);
      setSelectedEntity(next);
      setNotice({ tone: "success", message: "Đã cập nhật entity." });
      await loadRows();
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "Không cập nhật được entity." });
    }
  }

  async function saveProperty(propertyId: number | null, key: string, value: string, source: string) {
    if (!selectedEntity) return;
    try {
      const next = propertyId === null
        ? await createKGProperty(selectedEntity.id, { key, value, source: source || null })
        : await updateKGProperty(selectedEntity.id, propertyId, { key, value, source: source || null });
      setSelectedEntity(next);
      setNotice({ tone: "success", message: "Đã lưu property." });
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "Không lưu được property." });
    }
  }

  async function removeProperty(propertyId: number) {
    if (!selectedEntity || !window.confirm("Xóa property này khỏi entity?")) return;
    try {
      setSelectedEntity(await deleteKGProperty(selectedEntity.id, propertyId).then(() => getKGEntityDetail(selectedEntity.id, { propertyLimit: 100 })));
      setNotice({ tone: "success", message: "Đã xóa property." });
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "Không xóa được property." });
    }
  }

  async function saveRelationship(relationship: KGRelationshipSummary, type: string, toEntityId: string, source: string) {
    try {
      await updateKGRelationship(relationship.fromEntityId, relationship.id, {
        fromEntityId: relationship.fromEntityId,
        relationship: type,
        toEntityId,
        source: source || null,
      });
      setNotice({ tone: "success", message: "Đã cập nhật relationship." });
      setSelectedRelationship(null);
      await loadRows();
      if (selectedEntity) await openEntity(selectedEntity.id);
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "Không cập nhật được relationship." });
    }
  }

  const total = view === "entities" ? entities?.total ?? 0 : relationships?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const relationshipTypes = ontology?.relationshipTypes ?? filters?.relationshipTypes ?? [];

  function resetQuery() {
    setSearch("");
    setTypeFilter("");
    setStatusFilter("");
    setRelationshipFilter("");
    setPage(0);
  }

  return (
    <section className="databasePage">
      <header className="databaseHeader">
        <div>
          <p className="eyebrow">Data workspace</p>
          <h1>Database</h1>
          <p>Đọc và chỉnh sửa dữ liệu Knowledge Graph qua API admin an toàn.</p>
        </div>
        <div className="databaseStats" aria-label="Database totals">
          <span><b>{stats?.entityCount.toLocaleString() ?? "—"}</b> entities</span>
          <span><b>{stats?.aliasCount.toLocaleString() ?? "—"}</b> aliases</span>
          <span><b>{stats?.relationshipCount.toLocaleString() ?? "—"}</b> relationships</span>
        </div>
      </header>

      {notice && <div className={`databaseNotice ${notice.tone}`} role="status">{notice.message}<button type="button" onClick={() => setNotice(null)}>×</button></div>}

      <div className="databaseWorkspace">
        <section className="databaseMainPanel">
          <div className="databaseTabs" role="tablist" aria-label="Database tables">
            <button className={view === "entities" ? "active" : ""} onClick={() => { setView("entities"); setPage(0); setSelectedRelationship(null); }} type="button">Entities</button>
            <button className={view === "relationships" ? "active" : ""} onClick={() => { setView("relationships"); setPage(0); setSelectedEntity(null); }} type="button">Relationships</button>
          </div>

          <div className="databaseQueryBar">
            <input value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); }} placeholder={view === "entities" ? "Tìm theo tên hoặc ID…" : "Tìm theo ID hoặc source…"} aria-label="Database search" />
            {view === "entities" ? <>
              <select value={typeFilter} onChange={(event) => { setTypeFilter(event.target.value); setPage(0); }} aria-label="Entity type">
                <option value="">Tất cả loại</option>{(filters?.entityTypes ?? []).map((value) => <option key={value}>{value}</option>)}
              </select>
              <select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(0); }} aria-label="Entity status">
                <option value="">Tất cả trạng thái</option>{(filters?.statuses ?? []).map((value) => <option key={value}>{value}</option>)}
              </select>
            </> : <select value={relationshipFilter} onChange={(event) => { setRelationshipFilter(event.target.value); setPage(0); }} aria-label="Relationship type">
              <option value="">Tất cả relationship</option>{relationshipTypes.map((value) => <option key={value}>{value}</option>)}
            </select>}
            <button type="button" className="databaseGhostButton" onClick={resetQuery}>Reset</button>
          </div>

          <div className="databaseTableWrap">
            {loading ? <div className="databaseEmpty">Đang tải dữ liệu…</div> : view === "entities" ? <EntityTable items={entities?.items ?? []} selectedId={selectedEntity?.id} onSelect={openEntity} /> : <RelationshipTable items={relationships?.items ?? []} selectedId={selectedRelationship?.id} onSelect={setSelectedRelationship} onOpenEntity={openEntity} />}
          </div>
          <footer className="databasePagination"><span>{total.toLocaleString()} bản ghi · trang {page + 1}/{totalPages}</span><div><button type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>←</button><button type="button" disabled={page + 1 >= totalPages} onClick={() => setPage((value) => value + 1)}>→</button></div></footer>
        </section>

        <aside className="databaseInspector">
          {selectedEntity ? <EntityInspector entity={selectedEntity} entityTypes={filters?.entityTypes ?? []} statuses={filters?.statuses ?? []} onSaveEntity={saveEntity} onSaveProperty={saveProperty} onRemoveProperty={removeProperty} onOpenEntity={openEntity} /> : selectedRelationship ? <RelationshipInspector relationship={selectedRelationship} relationshipTypes={relationshipTypes} onSave={saveRelationship} onOpenEntity={openEntity} /> : <div className="databaseInspectorEmpty"><span>⌘</span><h2>Chọn một bản ghi</h2><p>Chọn entity hoặc relationship bên trái để xem chi tiết và chỉnh sửa.</p></div>}
        </aside>
      </div>
    </section>
  );
}

function EntityTable({ items, selectedId, onSelect }: { items: KGEntitySummary[]; selectedId?: string; onSelect: (item: KGEntitySummary) => void }) {
  if (items.length === 0) return <div className="databaseEmpty">Không có entity phù hợp.</div>;
  return <table className="databaseTable"><thead><tr><th>Tên</th><th>Loại</th><th>Trạng thái</th><th>Cập nhật</th></tr></thead><tbody>{items.map((item) => <tr className={item.id === selectedId ? "selected" : ""} key={item.id} onClick={() => onSelect(item)}><td><b>{item.canonicalName}</b><small>{shortId(item.id)}</small></td><td><span className="databaseTag">{item.entityType}</span></td><td><span className={`databaseStatus ${item.status}`}>{item.status}</span></td><td>{formatDate(item.updatedAt)}</td></tr>)}</tbody></table>;
}

function RelationshipTable({ items, selectedId, onSelect, onOpenEntity }: { items: KGRelationshipSummary[]; selectedId?: number; onSelect: (item: KGRelationshipSummary) => void; onOpenEntity: (id: string) => void }) {
  if (items.length === 0) return <div className="databaseEmpty">Không có relationship phù hợp.</div>;
  return <table className="databaseTable"><thead><tr><th>From</th><th>Relationship</th><th>To</th><th>Source</th></tr></thead><tbody>{items.map((item) => <tr className={item.id === selectedId ? "selected" : ""} key={item.id} onClick={() => onSelect(item)}><td><button className="databaseIdButton" type="button" onClick={(event) => { event.stopPropagation(); onOpenEntity(item.fromEntityId); }}>{shortId(item.fromEntityId)}</button></td><td><span className="databaseTag accent">{item.relationship}</span></td><td><button className="databaseIdButton" type="button" onClick={(event) => { event.stopPropagation(); onOpenEntity(item.toEntityId); }}>{shortId(item.toEntityId)}</button></td><td>{item.source || "—"}</td></tr>)}</tbody></table>;
}

function EntityInspector({ entity, entityTypes, statuses, onSaveEntity, onSaveProperty, onRemoveProperty, onOpenEntity }: { entity: KGEntityDetail; entityTypes: string[]; statuses: string[]; onSaveEntity: (payload: { canonicalName: string; entityType: string; status: string }) => Promise<void>; onSaveProperty: (id: number | null, key: string, value: string, source: string) => Promise<void>; onRemoveProperty: (id: number) => Promise<void>; onOpenEntity: (id: string) => Promise<void> }) {
  const [name, setName] = useState(entity.canonicalName);
  const [type, setType] = useState(entity.entityType);
  const [status, setStatus] = useState(entity.status);
  const [editingProperty, setEditingProperty] = useState<number | null>(null);
  const [propertyEditorOpen, setPropertyEditorOpen] = useState(false);
  const [propertyKey, setPropertyKey] = useState("");
  const [propertyValue, setPropertyValue] = useState("");
  const [propertySource, setPropertySource] = useState("");

  useEffect(() => { setName(entity.canonicalName); setType(entity.entityType); setStatus(entity.status); setEditingProperty(null); setPropertyEditorOpen(false); }, [entity]);

  function startProperty(id: number | null, key = "", value = "", source = "") { setEditingProperty(id); setPropertyKey(key); setPropertyValue(value); setPropertySource(source); setPropertyEditorOpen(true); }

  return <div className="databaseInspectorContent"><div className="databaseInspectorTitle"><div><span className="databaseKicker">Entity</span><h2>{entity.canonicalName}</h2><code>{entity.id}</code></div><span className="databaseTag">{entity.entityType}</span></div><div className="databaseFormGrid"><label>Tên<input value={name} onChange={(event) => setName(event.target.value)} /></label><label>Loại<select value={type} onChange={(event) => setType(event.target.value)}>{entityTypes.map((value) => <option key={value}>{value}</option>)}</select></label><label>Trạng thái<select value={status} onChange={(event) => setStatus(event.target.value)}>{statuses.map((value) => <option key={value}>{value}</option>)}</select></label></div><button className="databasePrimaryButton" type="button" onClick={() => void onSaveEntity({ canonicalName: name, entityType: type, status })}>Lưu entity</button><InspectorSection title={`Properties · ${entity.propertyTotal}`} action={<button type="button" onClick={() => startProperty(null)}>+ Thêm</button>}>{propertyEditorOpen ? <PropertyEditor key={editingProperty ?? "new"} propertyKey={propertyKey} value={propertyValue} source={propertySource} onSave={() => void onSaveProperty(editingProperty, propertyKey, propertyValue, propertySource)} onChangeKey={setPropertyKey} onChangeValue={setPropertyValue} onChangeSource={setPropertySource} onCancel={() => { setEditingProperty(null); setPropertyEditorOpen(false); setPropertyKey(""); }} /> : <div className="databaseMiniList">{entity.properties.map((property) => <div className="databaseMiniRow" key={property.id}><div><b>{property.key}</b><span>{property.value}</span></div><button type="button" onClick={() => startProperty(property.id, property.key, property.value, property.source ?? "")}>Sửa</button><button type="button" onClick={() => void onRemoveProperty(property.id)}>Xóa</button></div>)}</div>}</InspectorSection><InspectorSection title={`Aliases · ${entity.aliasTotal}`}><div className="databaseMiniList">{entity.aliases.slice(0, 12).map((alias) => <div className="databaseMiniRow" key={alias.id}><div><b>{alias.alias}</b><span>{alias.language}</span></div></div>)}{entity.aliasTotal > 12 && <small>Hiển thị 12 alias đầu tiên.</small>}</div></InspectorSection><InspectorSection title={`Relationships · ${entity.relationshipTotal}`}><div className="databaseMiniList">{entity.relationships.slice(0, 20).map((relationship) => <div className="databaseMiniRow" key={relationship.id}><div><b>{relationship.relationship}</b><span>{relationship.fromEntityId === entity.id ? "→ " : "← "}{shortId(relationship.fromEntityId === entity.id ? relationship.toEntityId : relationship.fromEntityId)}</span></div><button type="button" onClick={() => void onOpenEntity(relationship.fromEntityId === entity.id ? relationship.toEntityId : relationship.fromEntityId)}>Mở</button></div>)}</div></InspectorSection></div>;
}

function InspectorSection({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) { return <section className="databaseInspectorSection"><header><h3>{title}</h3>{action}</header>{children}</section>; }

function PropertyEditor({ propertyKey, value, source, onSave, onChangeKey, onChangeValue, onChangeSource, onCancel }: { propertyKey: string; value: string; source: string; onSave: () => void; onChangeKey: (value: string) => void; onChangeValue: (value: string) => void; onChangeSource: (value: string) => void; onCancel: () => void }) { return <div className="databasePropertyEditor"><input value={propertyKey} placeholder="key" onChange={(event) => onChangeKey(event.target.value)} /><textarea value={value} placeholder="value" onChange={(event) => onChangeValue(event.target.value)} /><input value={source} placeholder="source (optional)" onChange={(event) => onChangeSource(event.target.value)} /><div><button type="button" className="databasePrimaryButton" onClick={onSave}>Lưu</button><button type="button" className="databaseGhostButton" onClick={onCancel}>Hủy</button></div></div>; }

function RelationshipInspector({ relationship, relationshipTypes, onSave, onOpenEntity }: { relationship: KGRelationshipSummary; relationshipTypes: string[]; onSave: (relationship: KGRelationshipSummary, type: string, toEntityId: string, source: string) => Promise<void>; onOpenEntity: (id: string) => Promise<void> }) { const [type, setType] = useState(relationship.relationship); const [toEntityId, setToEntityId] = useState(relationship.toEntityId); const [source, setSource] = useState(relationship.source ?? ""); useEffect(() => { setType(relationship.relationship); setToEntityId(relationship.toEntityId); setSource(relationship.source ?? ""); }, [relationship]); return <div className="databaseInspectorContent"><span className="databaseKicker">Relationship #{relationship.id}</span><h2>{relationship.relationship}</h2><p className="databaseFlow"><button type="button" onClick={() => void onOpenEntity(relationship.fromEntityId)}>{shortId(relationship.fromEntityId)}</button> → <button type="button" onClick={() => void onOpenEntity(relationship.toEntityId)}>{shortId(relationship.toEntityId)}</button></p><label>Loại<select value={type} onChange={(event) => setType(event.target.value)}>{relationshipTypes.map((value) => <option key={value}>{value}</option>)}</select></label><label>To entity ID<input value={toEntityId} onChange={(event) => setToEntityId(event.target.value)} /></label><label>Source<input value={source} onChange={(event) => setSource(event.target.value)} /></label><button className="databasePrimaryButton" type="button" onClick={() => void onSave(relationship, type, toEntityId, source)}>Lưu relationship</button><p className="databaseHint">Thay đổi relationship sẽ cập nhật trực tiếp dữ liệu cloud qua API admin.</p></div>; }
