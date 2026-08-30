import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  type ArchitectureSnapshot,
  type FeatureWithFlow,
  type GraphPayload,
  type ProjectFileRow,
  type ProjectMetadata,
} from "../api";
import { ProjectTree } from "../components/ProjectTree";
import { ClassDiagram } from "../components/ClassDiagram";
import { NodeInspector } from "../components/NodeInspector";
import { FeatureFlowDiagram } from "../components/FeatureFlowDiagram";
import { FeatureSidebar } from "../components/FeatureSidebar";
import { SystemDesignPanel } from "../components/SystemDesignPanel";
import { CodebaseChatbot } from "../components/CodebaseChatbot";
import { BottomInsightBar } from "../components/BottomInsightBar";
import type { FlowEdgePayload } from "../components/FlowEdge";
import "./Visualize.css";

type Tab = "flows" | "system" | "classes" | "tree";

export function VisualizePage() {
  const { id } = useParams();
  const [snap, setSnap] = useState<ArchitectureSnapshot | null>(null);
  const [files, setFiles] = useState<ProjectFileRow[]>([]);
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [featureFlows, setFeatureFlows] = useState<FeatureWithFlow[]>([]);
  const [metadata, setMetadata] = useState<ProjectMetadata | null>(null);
  const [activeFeatureId, setActiveFeatureId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredInsight, setHoveredInsight] = useState<FlowEdgePayload | null>(null);
  const [tab, setTab] = useState<Tab>("flows");
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [regen, setRegen] = useState(false);

  const load = async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const [arch, tree, g, flows, meta] = await Promise.all([
        api.getArchitecture(id),
        api.getTree(id).catch(() => ({ files: [], count: 0 })),
        api.getGraph(id).catch(() => null),
        api.getAllFlows(id).catch(() => []),
        api.getMetadata(id).catch(() => null),
      ]);
      setSnap(arch);
      setFiles(tree.files);
      setGraph(g);
      setFeatureFlows(flows);
      setMetadata(meta);
      setActiveFeatureId(null);
      setTab("flows");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load architecture");
      setSnap(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [id]);

  const onRegen = async () => {
    if (!id) return;
    setRegen(true);
    try {
      const data = await api.regenerateArchitecture(id);
      setSnap(data);
      const [flows, meta] = await Promise.all([
        api.getAllFlows(id).catch(() => []),
        api.getMetadata(id).catch(() => null),
      ]);
      setFeatureFlows(flows);
      setMetadata(meta);
      setActiveFeatureId(null);
      setSelectedId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Regenerate failed");
    } finally {
      setRegen(false);
    }
  };

  const selected = useMemo(
    () => snap?.data.components.find((c) => c.id === selectedId) ?? null,
    [snap, selectedId],
  );

  const features = useMemo(
    () => featureFlows.map((ff) => ff.feature),
    [featureFlows],
  );

  return (
    <div className="viz-page">
      {/* 1. TOP NAVBAR: Brand, Project Info, Tab Switcher, Actions */}
      <header className="viz-top-navbar">
        <div className="viz-top-left">
          <Link to="/" className="top-brand">
            HOVER
          </Link>
          {snap && (
            <div className="top-project-badge">
              <span className="top-project-name">{snap.data.project_name}</span>
              <span className="top-project-meta">
                v{snap.version} · {files.length} files · {features.length} endpoints
              </span>
            </div>
          )}
        </div>

        {/* Navigation Tabs in Header */}
        <nav className="viz-top-tabs">
          <button
            type="button"
            className={`top-tab ${tab === "flows" ? "active" : ""}`}
            onClick={() => setTab("flows")}
          >
            ⚡ 3D Flows
            {features.length > 0 && <span className="tab-pill">{features.length}</span>}
          </button>
          <button
            type="button"
            className={`top-tab ${tab === "system" ? "active" : ""}`}
            onClick={() => setTab("system")}
          >
            📐 System Design Map
          </button>
          <button
            type="button"
            className={`top-tab ${tab === "classes" ? "active" : ""}`}
            onClick={() => setTab("classes")}
          >
            🏛️ Classes
          </button>
          <button
            type="button"
            className={`top-tab ${tab === "tree" ? "active" : ""}`}
            onClick={() => setTab("tree")}
          >
            📂 Tree
          </button>
        </nav>

        {/* Action Controls on Header Right */}
        <div className="viz-top-right">
          <button
            type="button"
            className="top-btn chat-btn"
            onClick={() => setIsChatOpen((prev) => !prev)}
          >
            💬 AI Assistant
          </button>
          <button
            type="button"
            className="top-btn regen-btn"
            onClick={onRegen}
            disabled={regen}
          >
            {regen ? "🤖 Analyzing…" : "🔄 Re-analyze"}
          </button>
          <Link to="/" className="top-btn upload-btn">
            + Upload New
          </Link>
        </div>
      </header>

      {/* 2. MAIN WORKSPACE: Left Sidebar + Center Canvas */}
      <div className="viz-workspace">
        {/* Left Sidebar: APIs & Features list */}
        {tab === "flows" && features.length > 0 && (
          <aside className="viz-left-sidebar">
            <FeatureSidebar
              features={features}
              activeId={activeFeatureId}
              onSelect={setActiveFeatureId}
            />
          </aside>
        )}

        {/* Center Canvas Area */}
        <main className={`viz-canvas-area ${tab === "flows" ? "has-sidebar" : "full-width"}`}>
          {tab === "flows" ? (
            <FeatureFlowDiagram
              featureFlows={featureFlows}
              activeFeatureId={activeFeatureId}
              onHoverInsight={setHoveredInsight}
            />
          ) : snap && tab === "system" ? (
            <div className="viz-panel-main sysdesign-main">
              <SystemDesignPanel metadata={metadata} />
            </div>
          ) : snap && tab === "classes" ? (
            <div className="viz-panel-main diagram-main">
              <ClassDiagram
                components={snap.data.components}
                graph={graph}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
            </div>
          ) : snap && tab === "tree" ? (
            <div className="viz-panel-main">
              <ProjectTree files={files} />
            </div>
          ) : (
            <div className="viz-empty">
              {loading ? "🤖 DeepAgents analyzing your project…" : error || "No architecture yet"}
            </div>
          )}
        </main>
      </div>

      {/* 3. BOTTOM INSIGHT INSPECTOR: Animates up from bottom without overlapping nodes */}
      <BottomInsightBar
        insight={hoveredInsight}
        onClose={() => setHoveredInsight(null)}
      />

      {/* 4. CHATBOT MODAL & FLOATING TRIGGER */}
      {id && (
        <CodebaseChatbot
          projectId={id}
          projectName={snap?.data.project_name || "Codebase"}
          isOpen={isChatOpen}
          onClose={() => setIsChatOpen(false)}
        />
      )}

      {/* Node Inspector Drawer */}
      {selected && snap && (
        <aside className="viz-inspector">
          <NodeInspector
            component={selected}
            data={snap.data}
            onClose={() => setSelectedId(null)}
          />
        </aside>
      )}
    </div>
  );
}
