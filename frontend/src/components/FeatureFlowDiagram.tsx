/**
 * FeatureFlowDiagram — main feature flow visualization using React Flow.
 *
 * Renders all feature flows as interactive diagrams with:
 * - Custom node types (User/Server/API/Cache/DB icons)
 * - Animated edges with hover insights
 * - Color-coded per feature
 * - Active feature highlighting
 */

import { useMemo, useCallback } from "react";
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
import { edgeTypes } from "./FlowEdge";

type Props = {
  featureFlows: FeatureWithFlow[];
  activeFeatureId: string | null;
};

/** Layout nodes in a vertical flow: each node type gets a row */
function layoutNodes(
  featureFlows: FeatureWithFlow[],
  activeFeatureId: string | null,
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const nodeIdSet = new Set<string>();

  // Filter to active or all
  const activeFFs = activeFeatureId
    ? featureFlows.filter((ff) => ff.feature.id === activeFeatureId)
    : featureFlows;

  // Row order by node type
  const typeRow: Record<string, number> = {
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

  // Collect unique nodes across all active flows
  type NodeInfo = { id: string; type: string; label: string; method?: string; featureIdx: number };
  const allNodes: NodeInfo[] = [];

  activeFFs.forEach((ff, fIdx) => {
    if (!ff.flow) return;
    for (const n of ff.flow.nodes) {
      // Make node IDs unique per feature if multiple flows are shown
      const nid = activeFFs.length > 1 ? `${ff.feature.id}__${n.id}` : n.id;
      if (nodeIdSet.has(nid)) continue;
      nodeIdSet.add(nid);

      // Extract method from API labels
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
    const row = typeRow[n.type] ?? 3;
    const list = rowGroups.get(row) ?? [];
    list.push(n);
    rowGroups.set(row, list);
  }

  // Position nodes
  const rowY: Record<number, number> = {};
  let y = 0;
  for (let r = 0; r <= 6; r++) {
    const group = rowGroups.get(r);
    if (!group?.length) continue;
    rowY[r] = y;
    const count = group.length;
    group.forEach((n, i) => {
      const x = (i - (count - 1) / 2) * 220;
      nodes.push({
        id: n.id,
        type: "flowNode",
        position: { x, y },
        data: {
          label: n.label,
          nodeType: n.type,
          method: n.method,
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

    // Build insight map for this feature
    const insightMap = new Map<string, FlowInsight>();
    for (const ins of ff.flow.insights ?? []) {
      insightMap.set(`${ins.from}->${ins.to}`, ins);
    }

    ff.flow.edges.forEach((e, eIdx) => {
      const fromId = prefix + e.from;
      const toId = prefix + e.to;
      const edgeKey = `${e.from}->${e.to}`;
      const insight = insightMap.get(edgeKey);

      // Dim non-active features when one is selected
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

export function FeatureFlowDiagram({ featureFlows, activeFeatureId }: Props) {
  const { nodes, edges } = useMemo(
    () => layoutNodes(featureFlows, activeFeatureId),
    [featureFlows, activeFeatureId],
  );

  const defaultViewport = useMemo(() => ({ x: 300, y: 30, zoom: 0.85 }), []);

  const onInit = useCallback((instance: any) => {
    // Auto-fit on load
    setTimeout(() => instance.fitView({ padding: 0.2 }), 100);
  }, []);

  return (
    <div style={{ width: "100%", height: "100%", background: "#020617" }}>
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
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        minZoom={0.3}
        maxZoom={2}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#1e293b" />
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

      {featureFlows.length === 0 && (
        <div style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#64748b",
          fontSize: "14px",
        }}>
          No feature flows discovered yet. Try regenerating with an API key set.
        </div>
      )}
    </div>
  );
}
