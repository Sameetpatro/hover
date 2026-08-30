/**
 * Custom animated edges for the feature flow diagram.
 * Shows data flow direction with animated dashes and hover tooltips.
 */

import { useState, useCallback } from "react";
import {
  BaseEdge,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";

export type FlowEdgePayload = {
  label: string;
  edgeData: string;
  condition?: string;
  insight?: string;
  pattern?: string | null;
  performanceNote?: string | null;
  securityNote?: string | null;
  color: string;
};

export function FlowEdge(props: EdgeProps) {
  const {
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    data,
    selected,
  } = props;

  const payload = data as unknown as FlowEdgePayload;
  const [hovered, setHovered] = useState(false);

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  const color = payload?.color || "#64748b";
  const isConditional = !!payload?.condition;
  const isActive = hovered || selected;

  const onMouseEnter = useCallback(() => setHovered(true), []);
  const onMouseLeave = useCallback(() => setHovered(false), []);

  return (
    <>
      {/* Invisible wider hit area for hover */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        style={{ cursor: "pointer" }}
      />

      {/* Main edge */}
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: isActive ? color : color + "99",
          strokeWidth: isActive ? 2.5 : 1.5,
          strokeDasharray: isConditional ? "6 4" : "none",
          filter: isActive ? `drop-shadow(0 0 4px ${color}80)` : "none",
          transition: "all 0.2s ease",
        }}
        markerEnd="url(#flow-arrow)"
      />

      {/* Animated dot traveling along the edge */}
      <circle r="3" fill={color} opacity={0.9}>
        <animateMotion dur="3s" repeatCount="indefinite" path={edgePath} />
      </circle>

      {/* Label on the edge */}
      <foreignObject
        x={labelX - 60}
        y={labelY - 12}
        width={120}
        height={24}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        style={{ overflow: "visible", pointerEvents: "all", cursor: "pointer" }}
      >
        <div
          style={{
            fontSize: "9px",
            fontWeight: 600,
            color: isActive ? "#f8fafc" : "#94a3b8",
            textAlign: "center",
            padding: "2px 6px",
            background: isActive ? "rgba(15,23,42,0.95)" : "rgba(15,23,42,0.6)",
            border: isActive ? `1px solid ${color}80` : "1px solid rgba(148,163,184,0.15)",
            borderRadius: "4px",
            whiteSpace: "nowrap",
            transition: "all 0.2s ease",
            backdropFilter: "blur(4px)",
          }}
        >
          {payload?.label || ""}
          {isConditional && (
            <span style={{ color: "#fbbf24", marginLeft: "4px", fontSize: "8px" }}>
              ({payload.condition})
            </span>
          )}
        </div>
      </foreignObject>
    </>
  );
}

/** React Flow edge type registry */
export const edgeTypes = {
  flowEdge: FlowEdge,
};
