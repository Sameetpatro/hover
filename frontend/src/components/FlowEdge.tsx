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
        <div style={{
          fontSize: "9px",
          fontWeight: 600,
          color: isActive ? "#f8fafc" : "#94a3b8",
          textAlign: "center",
          padding: "2px 6px",
          background: isActive ? "rgba(15,23,42,0.9)" : "transparent",
          borderRadius: "4px",
          whiteSpace: "nowrap",
          transition: "all 0.2s ease",
        }}>
          {payload?.label || ""}
          {isConditional && (
            <span style={{ color: "#fbbf24", marginLeft: "4px", fontSize: "8px" }}>
              ({payload.condition})
            </span>
          )}
        </div>
      </foreignObject>

      {/* Hover tooltip with insights */}
      {hovered && payload?.insight && (
        <foreignObject
          x={labelX - 150}
          y={labelY + 16}
          width={300}
          height={200}
          style={{ overflow: "visible", pointerEvents: "none" }}
        >
          <div style={{
            background: "rgba(15,23,42,0.95)",
            border: "1px solid rgba(148,163,184,0.3)",
            borderRadius: "10px",
            padding: "12px 16px",
            boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
            backdropFilter: "blur(12px)",
            color: "#e2e8f0",
            fontSize: "11px",
            lineHeight: 1.5,
            maxWidth: "280px",
          }}>
            <div style={{ fontWeight: 700, marginBottom: "6px", color: color }}>
              {payload.label}: {payload.edgeData}
            </div>
            <div style={{ marginBottom: "6px" }}>{payload.insight}</div>
            {payload.pattern && (
              <div style={{
                display: "inline-block",
                background: "rgba(167,139,250,0.2)",
                color: "#c4b5fd",
                padding: "2px 8px",
                borderRadius: "4px",
                fontSize: "9px",
                fontWeight: 600,
                marginBottom: "4px",
              }}>
                🔷 {payload.pattern}
              </div>
            )}
            {payload.performanceNote && (
              <div style={{ color: "#fbbf24", fontSize: "10px", marginTop: "4px" }}>
                ⚡ {payload.performanceNote}
              </div>
            )}
            {payload.securityNote && (
              <div style={{ color: "#fb7185", fontSize: "10px", marginTop: "2px" }}>
                🔒 {payload.securityNote}
              </div>
            )}
          </div>
        </foreignObject>
      )}
    </>
  );
}

/** React Flow edge type registry */
export const edgeTypes = {
  flowEdge: FlowEdge,
};
