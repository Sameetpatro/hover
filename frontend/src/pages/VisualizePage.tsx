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
import { ArchitectureScene } from "../scenes/ArchitectureScene";
import { ProjectTree } from "../components/ProjectTree";
import { ClassDiagram } from "../components/ClassDiagram";
import { NodeInspector } from "../components/NodeInspector";
import { FeatureFlowDiagram } from "../components/FeatureFlowDiagram";
import { FeatureSidebar } from "../components/FeatureSidebar";
import { SystemDesignPanel } from "../components/SystemDesignPanel";
import { CodebaseChatbot } from "../components/CodebaseChatbot";
import { describeFlow } from "../lib/flowNarrative";
import "./Visualize.css";

type Tab = "flows" | "scene" | "system" | "classes" | "tree";

export function VisualizePage() {
  const { id } = useParams();
  const [snap, setSnap] = useState<ArchitectureSnapshot | null>(null);
  const [files, setFiles] = useState<ProjectFileRow[]>([]);
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [featureFlows, setFeatureFlows] = useState<FeatureWithFlow[]>([]);
  const [metadata, setMetadata] = useState<ProjectMetadata | null>(null);
  const [activeFlowId, setActiveFlowId] = useState<string | null>(null);
  const [activeFeatureId, setActiveFeatureId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
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
      setActiveFlowId(null);
      setActiveFeatureId(null);
      // Default to flows tab if features exist, else 3D scene
      if (flows.length > 0) {
        setTab("flows");
      } else {
        setTab("scene");
      }
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
      // Reload feature flows and metadata
      const [flows, meta] = await Promise.all([
        api.getAllFlows(id).catch(() => []),
        api.getMetadata(id).catch(() => null),
      ]);
      setFeatureFlows(flows);
      setMetadata(meta);
      setActiveFlowId(data.data.flows[0]?.id ?? null);
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

  const activeFlow = useMemo(
    () => snap?.data.flows.find((f) => f.id === activeFlowId) ?? null,
    [snap, activeFlowId],
  );

  const features = useMemo(
    () => featureFlows.map((ff) => ff.feature),
    [featureFlows],
  );

  return (
    <div className="viz-page">
      {/* Feature sidebar — only visible on flows tab */}
      {tab === "flows" && features.length > 0 && (
        <aside className="viz-features">
          <FeatureSidebar
            features={features}
            activeId={activeFeatureId}
            onSelect={setActiveFeatureId}
          />
        </aside>
      )}

      <div className="viz-canvas">
        {tab === "flows" ? (
          <FeatureFlowDiagram
            featureFlows={featureFlows}
            activeFeatureId={activeFeatureId}
          />
        ) : snap && tab === "scene" ? (
          <ArchitectureScene
            data={snap.data}
            graph={graph}
            activeFlowId={activeFlowId}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        ) : snap && tab === "tree" ? (
          <div className="viz-panel-main">
            <ProjectTree files={files} />
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
        ) : snap && tab === "system" ? (
          <div className="viz-panel-main sysdesign-main">
            <SystemDesignPanel metadata={metadata} />
          </div>
        ) : (
          <div className="viz-empty">
            {loading ? "🤖 DeepAgents analyzing your project…" : error || "No architecture yet"}
          </div>
        )}
      </div>

      <aside className="viz-chrome">
        <Link to="/" className="brand-mini">
          HOVER
        </Link>
        {snap && (
          <>
            <h1>{snap.data.project_name}</h1>
            <p className="summary">{snap.data.summary}</p>

            <div className="tab-row">
              {(
                [
                  ["flows", "⚡ Flows"],
                  ["scene", "3D Map"],
                  ["system", "System"],
                  ["classes", "Classes"],
                  ["tree", "Tree"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className={tab === key ? "tab active" : "tab"}
                  onClick={() => setTab(key)}
                >
                  {label}
                </button>
              ))}
            </div>

            {tab === "flows" && (
              <>
                <p className="hint-click">
                  Select a feature to see its flow. Hover arrows for insights.
                </p>
                {activeFeatureId && (
                  <div className="flow-detail">
                    <span className="label">Active feature</span>
                    <p>{features.find((f) => f.id === activeFeatureId)?.description}</p>
                  </div>
                )}
              </>
            )}

            {tab === "scene" && (
              <>
                <p className="hint-click">
                  Tap a node for details. Gold = story flows · Teal = same links as Classes tab
                </p>
                <div className="flow-picker">
                  <span className="label">Highlight flow</span>
                  {snap.data.flows.map((f) => (
                    <button
                      key={f.id}
                      className={activeFlowId === f.id ? "flow active" : "flow"}
                      onClick={() => setActiveFlowId(f.id)}
                    >
                      {f.label}
                    </button>
                  ))}
                  <button
                    className={activeFlowId === null ? "flow active" : "flow"}
                    onClick={() => setActiveFlowId(null)}
                  >
                    All traffic
                  </button>
                </div>
                {activeFlow && (
                  <div className="flow-detail">
                    <span className="label">What this flow does</span>
                    <p>{describeFlow(activeFlow, snap.data.components)}</p>
                  </div>
                )}
              </>
            )}

            <button className="chat-trigger-btn" onClick={() => setIsChatOpen(true)}>
              💬 Ask AI Assistant (Chatbot)
            </button>
            <button className="regen" onClick={onRegen} disabled={regen}>
              {regen ? "🤖 Agents working…" : "🔄 Re-analyze"}
            </button>
            <p className="meta">
              v{snap.version} · {files.length} files · {features.length} features
            </p>
          </>
        )}
        {error && !snap && <p className="error">{error}</p>}
      </aside>

      {/* Floating Chatbot Action Button */}
      {id && (
        <button
          type="button"
          className="chat-floating-btn"
          onClick={() => setIsChatOpen((prev) => !prev)}
          title="Chat with Codebase"
        >
          <span>💬</span>
          <span className="chat-floating-label">Ask Codebase AI</span>
        </button>
      )}

      {/* Interactive Codebase Chatbot Modal */}
      {id && (
        <CodebaseChatbot
          projectId={id}
          projectName={snap?.data.project_name || "Codebase"}
          isOpen={isChatOpen}
          onClose={() => setIsChatOpen(false)}
        />
      )}

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

