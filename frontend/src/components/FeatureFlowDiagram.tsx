/**
 * FeatureFlowDiagram — 3D-depth enabled feature flow visualization using React Flow.
 *
 * Each tier of nodes (User → Server → API → Service → DB) sits at a
 * DIFFERENT Z-depth. When the user rotates with arrow keys the layers
 * visually fan out in perspective, making individual connections easy to
 * trace through the stack.
 *
 * Controls:
 *   ↑ / ↓  — tilt the X-axis (pitch) to reveal layer depth
 *   ← / →  — rotate the Y-axis (yaw) to orbit the stack
 *   W / S  — zoom the camera along the Z-axis
 *   R      — reset to default perspective
 */

import { useMemo, useCallback, useState, useEffect, useRef } from "react";
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { FeatureWithFlow, FlowInsight } from "../api";
import { nodeTypes } from "./FlowNode";
import { edgeTypes, type FlowEdgePayload } from "./FlowEdge";

type Props = {
  featureFlows: FeatureWithFlow[];
  activeFeatureId: string | null;
  onHoverInsight?: (insight: FlowEdgePayload | null) => void;
};

/* ── Z-depth for each tier (in CSS px) ── */
const TIER_Z: Record<string, number> = {
  user: 0,
  server: -120,
  api: -240,
  service: -360,
  cache: -360,
  queue: -360,
  worker: -480,
  database: -600,
  external: -480,
};

/* ── Row (Y position) for each tier ── */
const TYPE_ROW: Record<string, number> = {
  user: 0,
  server: 1,
  api: 2,
  service: 3,
  cache: 3,
  queue: 3,
  worker: 4,
  database: 5,
  external: 4,
};

/** Layout nodes in a vertical flow: each node type gets a row */
function layoutNodes(
  featureFlows: FeatureWithFlow[],
  activeFeatureId: string | null,
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const nodeIdSet = new Set<string>();

  const activeFFs = activeFeatureId
    ? featureFlows.filter((ff) => ff.feature.id === activeFeatureId)
    : featureFlows;

  type NodeInfo = { id: string; type: string; label: string; method?: string; featureIdx: number };
  const allNodes: NodeInfo[] = [];

  activeFFs.forEach((ff, fIdx) => {
    if (!ff.flow) return;
    for (const n of ff.flow.nodes) {
      const nid = activeFFs.length > 1 ? `${ff.feature.id}__${n.id}` : n.id;
      if (nodeIdSet.has(nid)) continue;
      nodeIdSet.add(nid);

      let method: string | undefined;
      if (n.type === "api") {
        const match = n.label.match(/^(GET|POST|PUT|DELETE|PATCH)\s/);
        if (match) method = match[1];
      }

      allNodes.push({ id: nid, type: n.type, label: n.label, method, featureIdx: fIdx });
    }
  });

  // Group by row
  const rowGroups: Map<number, NodeInfo[]> = new Map();
  for (const n of allNodes) {
    const row = TYPE_ROW[n.type] ?? 3;
    const list = rowGroups.get(row) ?? [];
    list.push(n);
    rowGroups.set(row, list);
  }

  // Position nodes, attaching tier info in data for CSS z-depth
  let y = 0;
  for (let r = 0; r <= 6; r++) {
    const group = rowGroups.get(r);
    if (!group?.length) continue;
    const count = group.length;
    group.forEach((n, i) => {
      const x = (i - (count - 1) / 2) * 240;
      const zDepth = TIER_Z[n.type] ?? -300;
      nodes.push({
        id: n.id,
        type: "flowNode",
        position: { x, y },
        className: `flow-tier flow-tier-${n.type}`,
        data: {
          label: n.label,
          nodeType: n.type,
          method: n.method,
          zDepth,
        },
      });
    });
    y += 140;
  }

  // Build edges
  activeFFs.forEach((ff) => {
    if (!ff.flow) return;
    const color = ff.feature.color;
    const prefix = activeFFs.length > 1 ? `${ff.feature.id}__` : "";

    const insightMap = new Map<string, FlowInsight>();
    for (const ins of ff.flow.insights ?? []) {
      insightMap.set(`${ins.from}->${ins.to}`, ins);
    }

    ff.flow.edges.forEach((e, eIdx) => {
      const fromId = prefix + e.from;
      const toId = prefix + e.to;
      const edgeKey = `${e.from}->${e.to}`;
      const insight = insightMap.get(edgeKey);
      const isActive = !activeFeatureId || ff.feature.id === activeFeatureId;

      edges.push({
        id: `${ff.feature.id}-${eIdx}`,
        source: fromId,
        target: toId,
        type: "flowEdge",
        animated: isActive,
        data: {
          label: e.label,
          edgeData: e.data,
          condition: e.condition,
          insight: insight?.insight || "",
          pattern: insight?.pattern,
          performanceNote: insight?.performance_note,
          securityNote: insight?.security_note,
          color: isActive ? color : "#334155",
        },
      });
    });
  });

  return { nodes, edges };
}

export function FeatureFlowDiagram({ featureFlows, activeFeatureId, onHoverInsight }: Props) {
  const { nodes, edges } = useMemo(
    () => layoutNodes(featureFlows, activeFeatureId),
    [featureFlows, activeFeatureId],
  );

  // 3D perspective state
  const [is3D, setIs3D] = useState(true);
  const [tiltX, setTiltX] = useState(0);      // pitch (reveal depth)
  const [rotY, setRotY] = useState(0);         // yaw   (orbit)
  const [camZ, setCamZ] = useState(0);         // camera zoom along Z
  const [depthSpread, setDepthSpread] = useState(1.0); // depth multiplier
  const [showToast, setShowToast] = useState(true);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Keyboard controls
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        document.activeElement?.tagName === "INPUT" ||
        document.activeElement?.tagName === "TEXTAREA"
      ) {
        return;
      }

      switch (e.key) {
        case "ArrowUp":
          e.preventDefault();
          setTiltX((x) => Math.min(x + 5, 55));
          break;
        case "ArrowDown":
          e.preventDefault();
          setTiltX((x) => Math.max(x - 5, -15));
          break;
        case "ArrowLeft":
          e.preventDefault();
          setRotY((y) => y - 5);
          break;
        case "ArrowRight":
          e.preventDefault();
          setRotY((y) => y + 5);
          break;
        case "w":
        case "W":
          e.preventDefault();
          setCamZ((z) => Math.min(z + 60, 800));
          break;
        case "s":
        case "S":
          e.preventDefault();
          setCamZ((z) => Math.max(z - 60, -400));
          break;
        case "+":
        case "=":
          e.preventDefault();
          setDepthSpread((d) => Math.min(d + 0.2, 3.0));
          break;
        case "-":
        case "_":
          e.preventDefault();
          setDepthSpread((d) => Math.max(d - 0.2, 0.0));
          break;
        case "r":
        case "R":
          setTiltX(0);
          setRotY(0);
          setCamZ(0);
          setDepthSpread(1.0);
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Inject per-node translateZ via CSS custom properties on the wrapper
  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;

    // Apply depth spread multiplier and 3D mode as CSS custom properties
    wrapper.style.setProperty("--depth-spread", String(is3D ? depthSpread : 0));

    // Apply per-tier Z values
    for (const [type, z] of Object.entries(TIER_Z)) {
      wrapper.style.setProperty(`--tier-z-${type}`, `${z * (is3D ? depthSpread : 0)}px`);
    }
  }, [is3D, depthSpread]);

  const defaultViewport = useMemo(() => ({ x: 280, y: 40, zoom: 0.82 }), []);

  const onInit = useCallback((instance: any) => {
    setTimeout(() => instance.fitView({ padding: 0.2 }), 100);
  }, []);

  const handleEdgeMouseEnter = useCallback(
    (_event: React.MouseEvent, edge: Edge) => {
      if (edge.data) {
        onHoverInsight?.(edge.data as unknown as FlowEdgePayload);
      }
    },
    [onHoverInsight],
  );

  const handleEdgeMouseLeave = useCallback(() => {
    onHoverInsight?.(null);
  }, [onHoverInsight]);

  const depthPct = Math.round(depthSpread * 100);

  return (
    <div className="flow-3d-wrapper" ref={wrapperRef}>
      {/* 3D Toast Notification */}
      {showToast && is3D && (
        <div className="flow-3d-toast">
          <span className="toast-icon">🎮</span>
          <span className="toast-text">
            <strong>3D Layer View:</strong>{" "}
            <strong>↑↓</strong> tilt to reveal depth layers ·{" "}
            <strong>←→</strong> orbit ·{" "}
            <strong>W/S</strong> zoom ·{" "}
            <strong>+/−</strong> spread layers ·{" "}
            <strong>R</strong> reset
          </span>
          <button
            type="button"
            className="toast-close"
            onClick={() => setShowToast(false)}
          >
            ✕
          </button>
        </div>
      )}

      {/* 3D Controls HUD */}
      <div className="flow-3d-hud">
        <button
          type="button"
          className={`hud-btn ${is3D ? "active" : ""}`}
          onClick={() => setIs3D((prev) => !prev)}
        >
          {is3D ? "🌐 3D Layers" : "📄 2D Flat"}
        </button>

        {is3D && (
          <>
            <span className="hud-badge">Tilt {tiltX}°</span>
            <span className="hud-badge">Orbit {rotY}°</span>
            <span className="hud-badge">Depth {depthPct}%</span>
            <button
              type="button"
              className="hud-btn"
              onClick={() => setDepthSpread((d) => Math.min(d + 0.3, 3.0))}
              title="Increase layer spread (+)"
            >
              + Spread
            </button>
            <button
              type="button"
              className="hud-btn"
              onClick={() => setDepthSpread((d) => Math.max(d - 0.3, 0.0))}
              title="Decrease layer spread (-)"
            >
              − Flatten
            </button>
            <button
              type="button"
              className="hud-btn reset"
              onClick={() => {
                setTiltX(0);
                setRotY(0);
                setCamZ(0);
                setDepthSpread(1.0);
              }}
              title="Reset View (R)"
            >
              🔄 Reset
            </button>
          </>
        )}
      </div>

      {/* 3D Scene Viewport */}
      <div
        className={`flow-3d-stage ${is3D ? "is-3d" : "is-2d"}`}
        style={{
          transform: is3D
            ? `perspective(1800px) rotateX(${tiltX}deg) rotateY(${rotY}deg) translateZ(${camZ}px)`
            : "none",
        }}
      >
        {/* SVG defs for arrow marker */}
        <svg width="0" height="0" style={{ position: "absolute" }}>
          <defs>
            <marker
              id="flow-arrow"
              markerWidth="8"
              markerHeight="8"
              refX="6"
              refY="3"
              orient="auto"
            >
              <path d="M0,0 L6,3 L0,6 Z" fill="#94a3b8" />
            </marker>
          </defs>
        </svg>

        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          defaultViewport={defaultViewport}
          onInit={onInit}
          onEdgeMouseEnter={handleEdgeMouseEnter}
          onEdgeMouseLeave={handleEdgeMouseLeave}
          onEdgeClick={handleEdgeMouseEnter}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          proOptions={{ hideAttribution: true }}
          minZoom={0.2}
          maxZoom={2.5}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
        >
          <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#1e293b" />
          <Controls
            style={{
              background: "rgba(15,23,42,0.9)",
              border: "1px solid #334155",
              borderRadius: "8px",
            }}
          />
          <MiniMap
            style={{
              background: "rgba(15,23,42,0.95)",
              border: "1px solid #334155",
              borderRadius: "8px",
            }}
            nodeColor="#334155"
            maskColor="rgba(0,0,0,0.5)"
          />
        </ReactFlow>
      </div>

      {featureFlows.length === 0 && (
        <div className="flow-empty-msg">
          No feature flows discovered yet. Upload a project ZIP to analyze.
        </div>
      )}
    </div>
  );
}
