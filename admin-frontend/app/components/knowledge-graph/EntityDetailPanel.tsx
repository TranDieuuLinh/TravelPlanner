"use client";

import {
  InspectorSection,
  KG_DEFAULT_COLLAPSED_SECTIONS,
  useCollapsedSections,
} from "./KnowledgeGraphSections";
import { RelationshipGraph } from "./RelationshipGraph";
import type { KGEntityDetail } from "../../../lib/api/knowledge-graph";

export function EntityDetailPanel({
  entity,
  onJumpToEntity,
}: {
  entity: KGEntityDetail;
  onJumpToEntity: (entityId: string) => void;
}) {
  const sections = useCollapsedSections(KG_DEFAULT_COLLAPSED_SECTIONS);
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
        <InspectorSection
          sectionId="information"
          title="Information"
          isCollapsed={sections.isCollapsed("information")}
          onToggle={() => sections.toggle("information")}
        >
          <dl className="kgDefinitionList">
            <div>
              <dt>ID</dt>
              <dd>
                <code>{entity.id}</code>
              </dd>
            </div>
            <div>
              <dt>Name</dt>
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
        </InspectorSection>

        {/* Aliases */}
        <InspectorSection
          sectionId="aliases"
          title="Aliases"
          count={entity.aliasTotal}
          isCollapsed={sections.isCollapsed("aliases")}
          onToggle={() => sections.toggle("aliases")}
        >
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
        </InspectorSection>

        {/* Properties */}
        <InspectorSection
          sectionId="properties"
          title="Properties"
          count={entity.propertyTotal}
          isCollapsed={sections.isCollapsed("properties")}
          onToggle={() => sections.toggle("properties")}
        >
          {entity.properties.length > 0 ? (
            <div className="kgPropertyTableWrap">
              <table className="kgPropertyTable">
                <thead>
                  <tr>
                    <th>Key</th>
                    <th>Value</th>
                  </tr>
                </thead>
                <tbody>
                  {entity.properties.map((prop) => (
                    <tr key={prop.id}>
                      <td>
                        <code>{prop.key}</code>
                      </td>
                      <td>{prop.value || <span className="kgMissingText">Empty</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="kgInspectorEmpty kgInspectorEmptyCompact">
              <span>◇</span>
              <b>No properties</b>
            </div>
          )}
        </InspectorSection>

        {/* Relationships */}
        <InspectorSection
          sectionId="relationships"
          title="Relationships"
          count={entity.relationshipTotal}
          isCollapsed={sections.isCollapsed("relationships")}
          onToggle={() => sections.toggle("relationships")}
        >
          {entity.relationships.length > 0 ? (
            <>
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
              <RelationshipGraph entity={entity} onJumpToEntity={onJumpToEntity} />
            </>
          ) : (
            <div className="kgInspectorEmpty kgInspectorEmptyCompact">
              <span>◇</span>
              <b>No relationships</b>
            </div>
          )}
        </InspectorSection>
      </div>
    </>
  );
}
