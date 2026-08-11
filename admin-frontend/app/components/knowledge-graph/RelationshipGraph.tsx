"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ComponentType, Ref } from "react";
import dynamic from "next/dynamic";
import { getKGEntityDetail, type KGEntityDetail, type KGEntitySummary } from "../../features/knowledge-graph/lib";

type GraphNode = {
  id: string;
  name: string;
  type: string;
  status: string;
  isCenter: boolean;
  // Position values are populated at runtime by react-force-graph.
  x?: number;
  y?: number;
};

type GraphLink = {
  source: string | GraphNode;
  target: string | GraphNode;
  relationship: string;
  direction: "out" | "in";
  sourceId: string;
  targetId: string;
};

type GraphForce = {
  distance?: (value: number) => GraphForce;
  strength?: (value: number) => GraphForce;
};

type ForceGraphHandle = {
  d3Force: (forceName: string) => GraphForce | undefined;
  d3ReheatSimulation: () => void;
};

type ForceGraph2DComponent = ComponentType<{
  graphData: { nodes: GraphNode[]; links: GraphLink[] };
  width: number;
  height: number;
  backgroundColor?: string;
  nodeId?: string;
  nodeRelSize?: number;
  nodeCanvasObject?: (node: GraphNode, ctx: CanvasRenderingContext2D, globalScale: number) => void;
  nodeCanvasObjectMode?: () => "replace" | "before" | "after";
  nodeLabel?: (node: GraphNode) => string;
  linkColor?: (link: GraphLink) => string;
  linkLineDash?: (link: GraphLink) => number[] | null;
  linkWidth?: (link: GraphLink) => number;
  linkCanvasObject?: (link: GraphLink, ctx: CanvasRenderingContext2D, globalScale: number) => void;
  linkCanvasObjectMode?: () => "replace" | "before" | "after";
  linkLabel?: (link: GraphLink) => string;
  linkDirectionalArrowLength?: number;
  linkDirectionalArrowColor?: (link: GraphLink) => string;
  linkDirectionalArrowRelPos?: number;
  linkDirectionalParticles?: (link: GraphLink) => number;
  linkDirectionalParticleSpeed?: number;
  linkDirectionalParticleColor?: string;
  linkDirectionalParticleWidth?: number;
  onNodeClick?: (node: GraphNode) => void;
  enableNodeDrag?: boolean;
  enableZoomInteraction?: boolean;
  enablePanInteraction?: boolean;
  cooldownTime?: number;
  d3AlphaDecay?: number;
  d3VelocityDecay?: number;
  warmupTicks?: number;
  ref?: Ref<ForceGraphHandle | null>;
}>;

const ForceGraph2D = dynamic(() => import("react-force-graph-2d") as Promise<{ default: ForceGraph2DComponent }>, { ssr: false }) as unknown as ForceGraph2DComponent;

const ENTITY_TYPE_PALETTE: Record<string, string> = {
  Destination: "#67e8bd",
  TravelPlace: "#67e8bd",
  Attraction: "#fbbf24",
  Hotel: "#a78bfa",
  Restaurant: "#f87171",
  FoodItem: "#ef8dcf",
  Activity: "#60a5fa",
  Topic: "#94a3b8",
};

const ENTITY_TYPE_DEFAULT_COLOR = "#67e8bd";
const ENTITY_TYPE_ICON: Record<string, string> = {
  Destination: "\u{1f9ed}",
  TravelPlace: "\u{1f4cd}",
  Attraction: "\u{1f3af}",
  Hotel: "\u{1f3e8}",
  Restaurant: "\u{1f37d}\ufe0f",
  FoodItem: "\u{1f35c}",
  Activity: "\u{1f3ab}",
  Topic: "\u{1f3f7}\ufe0f",
};
const RELATIONSHIP_ICON: Record<string, string> = {
  adjacent_to: "\u{1f91d}",
  located_in: "\u{1f4cc}",
  offer_item: "\u{1f381}",
  special_experience: "\u2b50",
  special_near: "\u{1f4cd}",
  has_accommodation: "\u{1f3e8}",
  has_activity: "\u{1f3ab}",
  has_place: "\u{1f4cd}",
  has_restaurant: "\u{1f37d}\ufe0f",
  is_in_area: "\u{1f5fa}\ufe0f",
  is_in_city: "\u{1f3d9}\ufe0f",
  is_in_district: "\u{1f3d8}\ufe0f",
  serves_food: "\u{1f35c}",
};

function relationshipIcon(relationship: string): string {
  const normalized = relationship.trim().toLowerCase().replace(/\s+/g, "_");
  return RELATIONSHIP_ICON[normalized] || "\u{1f517}";
}

// Draw a small glyph centered inside a node circle. The glyph scales with the
// circle radius (clamped) so it stays readable at the new bigger node sizes.
function drawNodeIcon(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  glyph: string,
  globalScale: number,
  iconPixels: number
): void {
  const iconSize = iconPixels / globalScale;
  ctx.save();
  ctx.font = `${iconSize}px "Segoe UI Emoji", "Apple Color Emoji", sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(glyph, x, y + 1);
  ctx.restore();
}

export function RelationshipGraph({
  entity,
  onJumpToEntity,
  showOutgoing = true,
  showIncoming = true,
}: {
  entity: KGEntityDetail;
  onJumpToEntity: (entityId: string) => void;
  showOutgoing?: boolean;
  showIncoming?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<ForceGraphHandle | null>(null);
  const [size, setSize] = useState({ width: 0, height: 180 });
  const [neighbors, setNeighbors] = useState<Record<string, KGEntitySummary>>({});
  const [loadError, setLoadError] = useState("");

  // Track container size for canvas sizing (no zoom/pan, so width is fixed).
  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = entry.contentRect.width;
        const h = entry.contentRect.height;
        if (w > 0 || h > 0) {
          setSize((prev) => ({
            width: w > 0 ? w : prev.width,
            height: h > 0 ? h : prev.height,
          }));
        }
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Collect unique neighbor IDs across all relationships (both directions).
  const neighborIds = useMemo(() => {
    const ids = new Set<string>();
    for (const rel of entity.relationships) {
      const isOutgoing = rel.fromEntityId === entity.id;
      const isIncoming = rel.toEntityId === entity.id;
      if ((!isOutgoing && !isIncoming) || (!showOutgoing && isOutgoing) || (!showIncoming && isIncoming)) {
        continue;
      }
      if (rel.fromEntityId !== entity.id) ids.add(rel.fromEntityId);
      if (rel.toEntityId !== entity.id) ids.add(rel.toEntityId);
    }
    return Array.from(ids);
  }, [entity.id, entity.relationships, showIncoming, showOutgoing]);

  // Fetch missing neighbor summaries (cached for the lifetime of this graph).
  useEffect(() => {
    let cancelled = false;
    const missing = neighborIds.filter((id) => !(id in neighbors));
    if (missing.length === 0) {
      return;
    }
    setLoadError("");
    Promise.allSettled(
      missing.map((id) =>
        getKGEntityDetail(id, { aliasLimit: 0, propertyLimit: 0, relationshipLimit: 0 }).then(
          (detail) => [id, { id: detail.id, canonicalName: detail.canonicalName, entityType: detail.entityType, status: detail.status, createdAt: detail.createdAt, updatedAt: detail.updatedAt, reviewCount: null }] as const
        )
      )
    ).then((results) => {
      if (cancelled) return;
      const fetched: Record<string, KGEntitySummary> = {};
      const failures: string[] = [];
      results.forEach((res) => {
        if (res.status === "fulfilled") {
          const [id, summary] = res.value;
          fetched[id] = summary;
        } else {
          failures.push("neighbor");
        }
      });
      if (Object.keys(fetched).length > 0) {
        setNeighbors((prev) => ({ ...prev, ...fetched }));
      }
      if (failures.length > 0 && missing.length === failures.length) {
        setLoadError("Không thể tải thông tin entity lân cận.");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [neighborIds, neighbors]);

  // Build graph data (centered entity + neighbors).
  const graphData = useMemo(() => {
    const centerNode: GraphNode = {
      id: entity.id,
      name: entity.canonicalName,
      type: entity.entityType,
      status: entity.status,
      isCenter: true,
    };
    const neighborNodes: GraphNode[] = neighborIds
      .map((id) => neighbors[id])
      .filter((n): n is KGEntitySummary => Boolean(n))
      .map((n) => ({
        id: n.id,
        name: n.canonicalName,
        type: n.entityType,
        status: n.status,
        isCenter: false,
      }));
    const availableNodeIds = new Set([entity.id, ...neighborNodes.map((node) => node.id)]);
    const links: GraphLink[] = entity.relationships
      .filter(
        (rel) =>
          (rel.fromEntityId === entity.id || rel.toEntityId === entity.id) &&
          ((rel.fromEntityId === entity.id && showOutgoing) || (rel.toEntityId === entity.id && showIncoming)) &&
          availableNodeIds.has(rel.fromEntityId) &&
          availableNodeIds.has(rel.toEntityId)
      )
      .map((rel) => {
        const isOut = rel.fromEntityId === entity.id;
        return {
          source: rel.fromEntityId,
          target: rel.toEntityId,
          sourceId: rel.fromEntityId,
          targetId: rel.toEntityId,
          relationship: rel.relationship,
          direction: isOut ? "out" : "in",
        };
      });
    return { nodes: [centerNode, ...neighborNodes], links };
  }, [entity, neighborIds, neighbors, showIncoming, showOutgoing]);

  useEffect(() => {
    const linkForce = graphRef.current?.d3Force("link");
    const chargeForce = graphRef.current?.d3Force("charge");
    linkForce?.distance?.(48);
    chargeForce?.strength?.(-90);
    graphRef.current?.d3ReheatSimulation();
  }, [graphData]);

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      if (!node.isCenter) {
        onJumpToEntity(node.id);
      }
    },
    [onJumpToEntity]
  );

  const drawNode = useCallback(
    (node: GraphNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const radius = (node.isCenter ? 22 : 12) / globalScale;
      const color =
        (node.type && ENTITY_TYPE_PALETTE[node.type]) || ENTITY_TYPE_DEFAULT_COLOR;
      ctx.beginPath();
      ctx.arc(node.x ?? 0, node.y ?? 0, radius, 0, 2 * Math.PI, false);
      ctx.fillStyle = color;
      if (node.isCenter) {
        ctx.lineWidth = 2 / globalScale;
        ctx.strokeStyle = "#0b1614";
      } else {
        ctx.lineWidth = 1 / globalScale;
        ctx.strokeStyle = "rgba(11, 22, 20, 0.5)";
      }
      ctx.fill();
      ctx.stroke();

      // Type icon centered inside the circle. The name remains available in
      // the hover tooltip so the compact map stays readable.
      const glyph = ENTITY_TYPE_ICON[node.type ?? ""] ?? "\u{1f517}";
      drawNodeIcon(ctx, node.x ?? 0, node.y ?? 0, glyph, globalScale, node.isCenter ? 24 : 16);
    },
    []
  );

  const nodeCanvasObjectMode = useCallback(() => "replace" as const, []);
  const linkColor = useCallback(
    (link: GraphLink) => (link.direction === "out" ? "rgba(103, 232, 189, 0.55)" : "rgba(167, 215, 198, 0.45)"),
    []
  );
  const linkLineDash = useCallback((link: GraphLink) => (link.direction === "in" ? [5, 4] : null), []);
  const linkWidth = useCallback((link: GraphLink) => (link.sourceId === entity.id || link.targetId === entity.id ? 1.4 : 0.9), [entity.id]);
  const linkLabel = useCallback((link: GraphLink) => link.relationship, []);
  const linkCanvasObject = useCallback((link: GraphLink, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const source = typeof link.source === "object" ? link.source : undefined;
    const target = typeof link.target === "object" ? link.target : undefined;
    if (source?.x == null || source.y == null || target?.x == null || target.y == null) {
      return;
    }
    const x = (source.x + target.x) / 2;
    const y = (source.y + target.y) / 2;
    const icon = relationshipIcon(link.relationship);
    const iconSize = 13 / globalScale;
    const badgeRadius = 9 / globalScale;
    ctx.save();
    ctx.beginPath();
    ctx.arc(x, y, badgeRadius, 0, 2 * Math.PI);
    ctx.fillStyle = "rgba(7, 16, 15, 0.92)";
    ctx.fill();
    ctx.font = `${iconSize}px "Segoe UI Emoji", "Apple Color Emoji", sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(icon, x, y + 1);
    ctx.restore();
  }, []);
  const linkCanvasObjectMode = useCallback(() => "after" as const, []);

  if (neighborIds.length === 0) {
    return (
      <div className="kgInspectorEmpty kgInspectorEmptyCompact">
        <span>◇</span>
        <b>No relationships to visualize</b>
      </div>
    );
  }

  const ready = neighborIds.every((id) => id in neighbors);

  return (
    <div className="kgRelationshipGraph">
      <div ref={containerRef} className="kgRelationshipGraphCanvas" aria-busy={!ready}>
        {size.width > 0 && (
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            width={size.width}
            height={size.height}
            backgroundColor="rgba(11, 23, 21, 0.4)"
            nodeId="id"
            nodeRelSize={6}
            nodeCanvasObject={drawNode}
            nodeCanvasObjectMode={nodeCanvasObjectMode}
            nodeLabel={(node: GraphNode) =>
              `${node.name}\n${node.type} · ${node.status}${node.isCenter ? "\n(current entity)" : "\nClick to jump"}`
            }
            linkColor={linkColor}
            linkLineDash={linkLineDash}
            linkWidth={linkWidth}
            linkCanvasObject={linkCanvasObject}
            linkCanvasObjectMode={linkCanvasObjectMode}
            linkLabel={linkLabel}
            linkDirectionalArrowLength={4}
            linkDirectionalArrowColor={(link: GraphLink) => (link.direction === "out" ? "#67e8bd" : "#a7d7c6")}
            linkDirectionalArrowRelPos={0.85}
            linkDirectionalParticles={(link: GraphLink) => (link.sourceId === entity.id ? 1 : 0)}
            linkDirectionalParticleSpeed={0.006}
            linkDirectionalParticleColor="rgba(103, 232, 189, 0.85)"
            linkDirectionalParticleWidth={1.5}
            onNodeClick={handleNodeClick}
            enableNodeDrag={false}
            enableZoomInteraction={false}
            enablePanInteraction={false}
            cooldownTime={1200}
            d3AlphaDecay={0.05}
            d3VelocityDecay={0.4}
            warmupTicks={28}
          />
        )}
      </div>
      <div className="kgRelationshipGraphLegend">
        <span className="kgRelationshipGraphLegendItem">
          <span className="kgRelationshipGraphDirectionIcon outgoing">➜</span>
          Outgoing
        </span>
        <span className="kgRelationshipGraphLegendItem">
          <span className="kgRelationshipGraphDirectionIcon incoming">⬅</span>
          Incoming
        </span>
        <span className="kgRelationshipGraphLegendHint">
          {ready ? "Click a node to jump to that entity." : `Loading neighbors…`}
        </span>
      </div>
      {loadError && (
        <p className="kgRelationshipGraphError" role="alert">
          {loadError}
        </p>
      )}
    </div>
  );
}
