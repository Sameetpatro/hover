/**
 * Custom React Flow node types for the feature flow diagram.
 * Each node type has a distinct visual treatment matching the infra component it represents.
 */

import { Handle, Position, type NodeProps } from "@xyflow/react";

/* ---- SVG icons ---- */

const PersonIcon = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <circle cx="12" cy="7" r="4" />
    <path d="M5.5 21a6.5 6.5 0 0113 0" />
  </svg>
);

const ServerIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <rect x="2" y="2" width="20" height="8" rx="2" />
    <rect x="2" y="14" width="20" height="8" rx="2" />
    <circle cx="6" cy="6" r="1" fill="currentColor" />
    <circle cx="6" cy="18" r="1" fill="currentColor" />
  </svg>
);

const ApiIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
  </svg>
);

const CacheIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
  </svg>
);

const DatabaseIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <ellipse cx="12" cy="5" rx="9" ry="3" />
    <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
    <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
  </svg>
);

const QueueIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <rect x="2" y="6" width="20" height="12" rx="2" />
    <path d="M6 12h4M14 12h4" />
    <path d="M10 9l-2 3 2 3M14 9l2 3-2 3" />
  </svg>
);

const ServiceIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
  </svg>
);

/* ---- Colors per type ---- */

const NODE_STYLES: Record<string, { bg: string; border: string; text: string; glow: string }> = {
  user:     { bg: "rgba(147,197,253,0.15)", border: "#93c5fd", text: "#93c5fd", glow: "0 0 20px rgba(147,197,253,0.3)" },
  server:   { bg: "rgba(148,163,184,0.15)", border: "#94a3b8", text: "#cbd5e1", glow: "0 0 20px rgba(148,163,184,0.2)" },
  api:      { bg: "rgba(251,191,36,0.15)",  border: "#fbbf24", text: "#fde68a", glow: "0 0 20px rgba(251,191,36,0.3)" },
  service:  { bg: "rgba(167,139,250,0.15)", border: "#a78bfa", text: "#c4b5fd", glow: "0 0 20px rgba(167,139,250,0.3)" },
  cache:    { bg: "rgba(251,113,133,0.15)", border: "#fb7185", text: "#fda4af", glow: "0 0 20px rgba(251,113,133,0.3)" },
  database: { bg: "rgba(52,211,153,0.15)",  border: "#34d399", text: "#6ee7b7", glow: "0 0 20px rgba(52,211,153,0.3)" },
  queue:    { bg: "rgba(251,146,60,0.15)",  border: "#fb923c", text: "#fdba74", glow: "0 0 20px rgba(251,146,60,0.3)" },
  worker:   { bg: "rgba(232,121,249,0.15)", border: "#e879f9", text: "#f0abfc", glow: "0 0 20px rgba(232,121,249,0.3)" },
  external: { bg: "rgba(148,163,184,0.10)", border: "#64748b", text: "#94a3b8", glow: "0 0 12px rgba(148,163,184,0.15)" },
};

function getIcon(type: string) {
  switch (type) {
    case "user": return <PersonIcon />;
    case "server": return <ServerIcon />;
    case "api": return <ApiIcon />;
    case "cache": return <CacheIcon />;
    case "database": return <DatabaseIcon />;
    case "queue": return <QueueIcon />;
    case "service": return <ServiceIcon />;
    case "worker": return <ServiceIcon />;
    default: return <ServerIcon />;
  }
}

export type FlowNodePayload = {
  label: string;
  nodeType: string;
  method?: string;
};

export function FlowNode({ data }: NodeProps) {
  const payload = data as unknown as FlowNodePayload;
  const type = payload.nodeType || "server";
  const style = NODE_STYLES[type] || NODE_STYLES.server;
  const method = payload.method;

  return (
    <div
      style={{
        background: style.bg,
        border: `1.5px solid ${style.border}`,
        borderRadius: type === "user" ? "50%" : type === "database" ? "8px 8px 20px 20px" : "12px",
        padding: type === "user" ? "16px" : "12px 20px",
        color: style.text,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "6px",
        boxShadow: style.glow,
        backdropFilter: "blur(8px)",
        minWidth: type === "user" ? "64px" : "120px",
        transition: "all 0.2s ease",
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: style.border, width: 8, height: 8, border: "none" }} />

      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
        {getIcon(type)}
        {method && (
          <span style={{
            background: method === "GET" ? "rgba(52,211,153,0.3)" :
                        method === "POST" ? "rgba(96,165,250,0.3)" :
                        method === "PUT" ? "rgba(251,191,36,0.3)" :
                        method === "DELETE" ? "rgba(251,113,133,0.3)" : "rgba(148,163,184,0.3)",
            padding: "1px 6px",
            borderRadius: "4px",
            fontSize: "9px",
            fontWeight: 700,
            letterSpacing: "0.5px",
          }}>
            {method}
          </span>
        )}
      </div>

      <span style={{ fontSize: "11px", fontWeight: 600, textAlign: "center", maxWidth: "140px", lineHeight: 1.3 }}>
        {payload.label}
      </span>

      <Handle type="source" position={Position.Bottom} style={{ background: style.border, width: 8, height: 8, border: "none" }} />
    </div>
  );
}

/** React Flow node type registry */
export const nodeTypes = {
  flowNode: FlowNode,
};
