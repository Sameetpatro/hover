/**
 * SystemDesignPanel — shows tech stack, architecture layers, patterns, and DB schema.
 */

import type { ProjectMetadata } from "../api";

const CATEGORY_ICONS: Record<string, string> = {
  language: "🔤",
  framework: "⚙️",
  database: "🗄️",
  cache: "⚡",
  queue: "📨",
  devops: "🔧",
};

const CATEGORY_COLORS: Record<string, string> = {
  language: "#60a5fa",
  framework: "#a78bfa",
  database: "#34d399",
  cache: "#fb7185",
  queue: "#fb923c",
  devops: "#94a3b8",
};

type Props = {
  metadata: ProjectMetadata | null;
};

export function SystemDesignPanel({ metadata }: Props) {
  if (!metadata) {
    return (
      <div className="sysdesign-empty">
        No metadata available. Run analysis with an API key for full insights.
      </div>
    );
  }

  // Group tech stack by category
  const grouped = new Map<string, typeof metadata.tech_stack>();
  for (const item of metadata.tech_stack) {
    const cat = item.category || "other";
    const list = grouped.get(cat) ?? [];
    list.push(item);
    grouped.set(cat, list);
  }

  return (
    <div className="sysdesign-panel">
      {/* Tech Stack */}
      <section className="sysdesign-section">
        <h3>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="2" y="2" width="20" height="20" rx="2" />
            <path d="M7 2v20M2 12h20" />
          </svg>
          Tech Stack
        </h3>
        <div className="tech-grid">
          {[...grouped.entries()].map(([cat, items]) => (
            <div key={cat} className="tech-category">
              <div className="tech-cat-label" style={{ color: CATEGORY_COLORS[cat] || "#94a3b8" }}>
                {CATEGORY_ICONS[cat] || "📦"} {cat}
              </div>
              <div className="tech-chips">
                {items.map((item) => (
                  <span
                    key={item.name}
                    className="tech-chip"
                    style={{ borderColor: CATEGORY_COLORS[cat] || "#334155" }}
                  >
                    {item.name}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* System Design */}
      {metadata.system_design && (
        <section className="sysdesign-section">
          <h3>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 6v6l4 2" />
            </svg>
            System Design
          </h3>
          <p className="sysdesign-desc">{metadata.system_design}</p>
        </section>
      )}

      {/* Patterns */}
      {metadata.patterns.length > 0 && (
        <section className="sysdesign-section">
          <h3>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
            </svg>
            Design Patterns
          </h3>
          <div className="pattern-list">
            {metadata.patterns.map((p, i) => (
              <div key={i} className="pattern-card">
                <div className="pattern-name">{p.name}</div>
                <div className="pattern-desc">{p.description}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* DB Schema */}
      {metadata.db_schema.length > 0 && (
        <section className="sysdesign-section">
          <h3>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <ellipse cx="12" cy="5" rx="9" ry="3" />
              <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
              <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
            </svg>
            Database Schema
          </h3>
          <div className="schema-list">
            {metadata.db_schema.map((table: any, i: number) => (
              <div key={i} className="schema-card">
                <div className="schema-table">{table.table || `Table ${i + 1}`}</div>
                {table.columns && (
                  <div className="schema-cols">
                    {(table.columns as string[]).map((col: string) => (
                      <span key={col} className="schema-col">{col}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
