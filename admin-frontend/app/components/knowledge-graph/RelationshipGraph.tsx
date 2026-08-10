"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ComponentType } from "react";
import dynamic from "next/dynamic";
import { getKGEntityDetail, type KGEntityDetail, type KGEntitySummary } from "../../../lib/api/knowledge-graph";

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
  source: string;
  target: string;
  relationship: string;
  direction: "out" | "in";
  sourceId: string;
  targetId: string;
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
  linkWidth?: (link: GraphLink) => number;
  linkLabel?: (link: GraphLink) => string;
  linkDirectionalArrowLength?: number;
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
}>;

const ForceGraph2D = dynamic(() => import("react-force-graph-2d") as Promise<{ default: ForceGraph2DComponent }>, { ssr: false }) as unknown as ForceGraph2DComponent;

const ENTITY_TYPE_PALETTE: Record<string, string> = {
  Destination: "#67e8bd",
  Attraction: "#fbbf24",
  Hotel: "#a78bfa",
  Restaurant: "#f87171",
  Activity: "#60a5fa",
  Topic: "#94a3b8",
};

const ENTITY_TYPE_DEFAULT_COLOR = "#67e8bd";
const ENTITY_TYPE_ICON: Record<string, string> = {
  Destination: "◆",
  Attraction: "★",
  Hotel: "▣",
  Restaurant: "●",
  Activity: "▲",
  Topic: "◌",
};

// Draw a small glyph centered inside a node circle. The glyph scales with the
// circle radius (clamped) so it stays readable at the new bigger node sizes.
function drawNodeIcon(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  radius: number,
  glyph: string
): void {
  const iconSize = Math.max(8, Math.min(radius * 1.1, 14));
  ctx.save();
  ctx.font = `${iconSize}px var(--mono, monospace)`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "rgba(11, 22, 20, 0.85)";
  ctx.fillText(glyph, x, y + 1);
  ctx.restore();
}

export function RelationshipGraph({
  entity,
  onJumpToEntity,
}: {
  entity: KGEntityDetail;
  onJumpToEntity: (entityId: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 320 });
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
        if (w > 0) {
          setSize((prev) => ({ ...prev, width: w }));
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
      if (rel.fromEntityId !== entity.id) ids.add(rel.fromEntityId);
      if (rel.toEntityId !== entity.id) ids.add(rel.toEntityId);
    }
    return Array.from(ids);
  }, [entity.id, entity.relationships]);

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
    const links: GraphLink[] = entity.relationships
      .filter((rel) => rel.fromEntityId in neighbors || rel.toEntityId in neighbors || rel.fromEntityId === entity.id || rel.toEntityId === entity.id)
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
  }, [entity, neighborIds, neighbors]);

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
      const radius = node.isCenter ? 14 : 10;
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

      // Type glyph centered inside the circle.
      const glyph = ENTITY_TYPE_ICON[node.type ?? ""] ?? "◇";
      drawNodeIcon(ctx, node.x ?? 0, node.y ?? 0, radius, glyph);

      // Label below node — fixed pixel size so text stays small even when the
// camera is zoomed out (low globalScale would otherwise inflate the font).
      const fontSize = node.isCenter ? 5 : 4;
      ctx.font = `${fontSize}px var(--mono, monospace)`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillStyle = node.isCenter ? "#c8ddd5" : "#9fb3ad";
      const label = node.name.length > 22 ? `${node.name.slice(0, 21)}…` : node.name;
      ctx.fillText(label, node.x ?? 0, (node.y ?? 0) + radius + 2);
    },
    []
  );

  const nodeCanvasObjectMode = useCallback(() => "replace" as const, []);
  const linkColor = useCallback(
    (link: GraphLink) => (link.direction === "out" ? "rgba(103, 232, 189, 0.55)" : "rgba(167, 215, 198, 0.45)"),
    []
  );
  const linkWidth = useCallback((link: GraphLink) => (link.sourceId === entity.id || link.targetId === entity.id ? 1.4 : 0.9), [entity.id]);
  const linkLabel = useCallback((link: GraphLink) => link.relationship, []);

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
            linkWidth={linkWidth}
            linkLabel={linkLabel}
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelPos={0.85}
            linkDirectionalParticles={(link: GraphLink) => (link.sourceId === entity.id ? 1 : 0)}
            linkDirectionalParticleSpeed={0.006}
            linkDirectionalParticleColor="rgba(103, 232, 189, 0.85)"
            linkDirectionalParticleWidth={1.5}
            onNodeClick={handleNodeClick}
            enableNodeDrag={false}
            enableZoomInteraction={false}
            enablePanInteraction={false}
            cooldownTime={2000}
            d3AlphaDecay={0.05}
            d3VelocityDecay={0.4}
            warmupTicks={40}
          />
        )}
      </div>
      <div className="kgRelationshipGraphLegend">
        <span className="kgRelationshipGraphLegendItem">
          <span className="kgRelationshipGraphLegendDot" style={{ background: "var(--mint)" }} />
          Outgoing
        </span>
        <span className="kgRelationshipGraphLegendItem">
          <span className="kgRelationshipGraphLegendDot" style={{ background: "rgba(167, 215, 198, 0.7)" }} />
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
