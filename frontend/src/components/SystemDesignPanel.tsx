/**
 * SystemDesignPanel — interactive System Design Map for the analyzed application.
 * Visualizes the full multi-tier architecture, data pipeline, design patterns, and database schema.
 */

import { useState } from "react";
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
  const [activeTier, setActiveTier] = useState<string | null>("services");

  if (!metadata) {
    return (
      <div className="sysdesign-empty">
        No system design metadata available yet. Upload a project ZIP to analyze.
      </div>
    );
  }

  // Group tech stack
  const grouped = new Map<string, typeof metadata.tech_stack>();
  for (const item of metadata.tech_stack) {
    const cat = item.category || "other";
    const list = grouped.get(cat) ?? [];
    list.push(item);
    grouped.set(cat, list);
  }

  return (
    <div className="sysdesign-container">
      {/* 1. Header Banner */}
      <div className="sysdesign-hero">
        <div className="sysdesign-hero-left">
          <div className="sysdesign-title-row">
            <h2>📐 System Design Architecture Map</h2>
            <span className="arch-pattern-badge">Multi-Tier Layered Architecture</span>
          </div>
          <p className="sysdesign-summary-text">
            {metadata.system_design ||
              "High-availability architecture featuring FastAPI Ingress, Redis Cache-Aside, Atomic SQL Transactions, and Async Worker Notification Queues."}
          </p>
        </div>
      </div>

      {/* 2. Interactive System Architecture Flow Diagram */}
      <section className="sysdesign-section">
        <h3 className="section-heading">
          <span className="icon">🏛️</span> Architecture Tiers & Request Lifecycles
        </h3>
        <div className="arch-tier-grid">
          {/* Tier 1: Client Ingress */}
          <div
            className={`arch-tier-card ${activeTier === "client" ? "active" : ""}`}
            onClick={() => setActiveTier("client")}
          >
            <div className="tier-header">
              <span className="tier-badge client">Tier 1</span>
              <h4>Client & Consumer Layer</h4>
            </div>
            <p className="tier-desc">Web browser SPA, Mobile Clients, and external API integrations.</p>
            <div className="tier-chips">
              <span className="tier-chip">HTTP / HTTPS</span>
              <span className="tier-chip">JSON REST API</span>
            </div>
          </div>

          <div className="tier-arrow">➔</div>

          {/* Tier 2: Gateway & Controller */}
          <div
            className={`arch-tier-card ${activeTier === "gateway" ? "active" : ""}`}
            onClick={() => setActiveTier("gateway")}
          >
            <div className="tier-header">
              <span className="tier-badge gateway">Tier 2</span>
              <h4>API Gateway & Router</h4>
            </div>
            <p className="tier-desc">FastAPI Routing, CORS Middleware, Request Validation, and Rate Limiting.</p>
            <div className="tier-chips">
              <span className="tier-chip">FastAPI Router</span>
              <span className="tier-chip">Pydantic Schemas</span>
            </div>
          </div>

          <div className="tier-arrow">➔</div>

          {/* Tier 3: Business Logic Services */}
          <div
            className={`arch-tier-card ${activeTier === "services" ? "active" : ""}`}
            onClick={() => setActiveTier("services")}
          >
            <div className="tier-header">
              <span className="tier-badge service">Tier 3</span>
              <h4>Service & Business Logic</h4>
            </div>
            <p className="tier-desc">Transactional logic, balance calculations, state validation, and business rules.</p>
            <div className="tier-chips">
              <span className="tier-chip">Domain Services</span>
              <span className="tier-chip">Repository Pattern</span>
            </div>
          </div>

          <div className="tier-arrow">➔</div>

          {/* Tier 4: Cache & Queue */}
          <div
            className={`arch-tier-card ${activeTier === "cache" ? "active" : ""}`}
            onClick={() => setActiveTier("cache")}
          >
            <div className="tier-header">
              <span className="tier-badge cache">Tier 4</span>
              <h4>Cache & Async Workers</h4>
            </div>
            <p className="tier-desc">Redis in-memory caching (TTL 300s) and Celery / background worker tasks.</p>
            <div className="tier-chips">
              <span className="tier-chip">Redis Key-Value</span>
              <span className="tier-chip">Audit Worker</span>
            </div>
          </div>

          <div className="tier-arrow">➔</div>

          {/* Tier 5: Persistence Database */}
          <div
            className={`arch-tier-card ${activeTier === "db" ? "active" : ""}`}
            onClick={() => setActiveTier("db")}
          >
            <div className="tier-header">
              <span className="tier-badge db">Tier 5</span>
              <h4>Database & Persistence</h4>
            </div>
            <p className="tier-desc">Relational ACID database with foreign keys, indexes, and atomic commits.</p>
            <div className="tier-chips">
              <span className="tier-chip">SQLAlchemy ORM</span>
              <span className="tier-chip">PostgreSQL / SQLite</span>
            </div>
          </div>
        </div>
      </section>

      {/* 3. Tech Stack Breakdown */}
      <section className="sysdesign-section">
        <h3 className="section-heading">
          <span className="icon">📦</span> Technology Stack & Infrastructure
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

      {/* 4. Architecture Patterns */}
      {metadata.patterns.length > 0 && (
        <section className="sysdesign-section">
          <h3 className="section-heading">
            <span className="icon">🔷</span> Design Patterns & System Principles
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

      {/* 5. Database Schema & Data Models */}
      {metadata.db_schema.length > 0 && (
        <section className="sysdesign-section">
          <h3 className="section-heading">
            <span className="icon">🗄️</span> Relational Database Schema & Entities
          </h3>
          <div className="schema-list">
            {metadata.db_schema.map((table: any, i: number) => (
              <div key={i} className="schema-card">
                <div className="schema-table">{table.table || `Table ${i + 1}`}</div>
                {table.columns && (
                  <div className="schema-cols">
                    {(table.columns as string[]).map((col: string) => (
                      <span key={col} className="schema-col">
                        {col}
                      </span>
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
