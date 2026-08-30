/**
 * FeatureSidebar — left sidebar listing discovered features with color dots.
 * Click to highlight a feature's flow in the diagram.
 */

import type { FeatureItem } from "../api";

const METHOD_COLORS: Record<string, string> = {
  GET: "#34d399",
  POST: "#60a5fa",
  PUT: "#fbbf24",
  PATCH: "#fb923c",
  DELETE: "#fb7185",
};

type Props = {
  features: FeatureItem[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
};

export function FeatureSidebar({ features, activeId, onSelect }: Props) {
  // Group by category
  const grouped = new Map<string, FeatureItem[]>();
  for (const f of features) {
    const cat = f.category || "general";
    const list = grouped.get(cat) ?? [];
    list.push(f);
    grouped.set(cat, list);
  }

  return (
    <div className="feature-sidebar">
      <h3 className="feature-sidebar-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
        </svg>
        Features
        <span className="feature-count">{features.length}</span>
      </h3>

      <button
        className={`feature-item feature-all ${activeId === null ? "active" : ""}`}
        onClick={() => onSelect(null)}
      >
        <span className="feature-dot" style={{ background: "linear-gradient(135deg, #60a5fa, #34d399, #fbbf24, #fb7185)" }} />
        <span className="feature-name">All Features</span>
      </button>

      {[...grouped.entries()].map(([cat, feats]) => (
        <div key={cat} className="feature-group">
          <div className="feature-category">{cat}</div>
          {feats.map((f) => (
            <button
              key={f.id}
              className={`feature-item ${activeId === f.id ? "active" : ""}`}
              onClick={() => onSelect(f.id === activeId ? null : f.id)}
            >
              <span className="feature-dot" style={{ background: f.color }} />
              <div className="feature-info">
                <span className="feature-name">{f.name}</span>
                {f.method && (
                  <span
                    className="feature-method"
                    style={{ color: METHOD_COLORS[f.method] || "#94a3b8" }}
                  >
                    {f.method}
                  </span>
                )}
                {f.path && <span className="feature-path">{f.path}</span>}
              </div>
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
