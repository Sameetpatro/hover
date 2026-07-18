import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  type ArchitectureSnapshot,
  type GraphPayload,
  type ProjectFileRow,
} from "../api";
import { ArchitectureScene } from "../scenes/ArchitectureScene";
import { ProjectTree } from "../components/ProjectTree";
import { ClassDiagram } from "../components/ClassDiagram";
import { NodeInspector } from "../components/NodeInspector";
import { describeFlow, describeStep } from "../lib/flowNarrative";
import "./Visualize.css";

type Tab = "scene" | "tree" | "classes" | "flows";

export function VisualizePage() {
  const { id } = useParams();
  const [snap, setSnap] = useState<ArchitectureSnapshot | null>(null);
  const [files, setFiles] = useState<ProjectFileRow[]>([]);
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [activeFlowId, setActiveFlowId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("scene");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [regen, setRegen] = useState(false);

  const load = async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const [arch, tree, g] = await Promise.all([
        api.getArchitecture(id),
        api.getTree(id).catch(() => ({ files: [], count: 0 })),
        api.getGraph(id).catch(() => null),
      ]);
      setSnap(arch);
      setFiles(tree.files);
      setGraph(g);
      setActiveFlowId(arch.data.flows[0]?.id ?? null);
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
      setActiveFlowId(data.data.flows[0]?.id ?? null);
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

  const byId = useMemo(() => {
    const m = new Map((snap?.data.components ?? []).map((c) => [c.id, c]));
    return m;
  }, [snap]);

  return (
    <div className="viz-page">
      <div className="viz-canvas">
        {snap && tab === "scene" ? (
          <ArchitectureScene
            data={snap.data}
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
        ) : snap && tab === "flows" ? (
          <div className="viz-panel-main flows-main">
            {snap.data.flows.map((flow) => (
              <article
                key={flow.id}
                className={`flow-card ${activeFlowId === flow.id ? "active" : ""}`}
                onClick={() => {
                  setActiveFlowId(flow.id);
                  setTab("scene");
                }}
              >
                <h3>{flow.label}</h3>
                <p>{describeFlow(flow, snap.data.components)}</p>
                <ol>
                  {flow.steps.map((step, i) => (
                    <li key={`${flow.id}-${i}`}>
                      <strong>
                        {(byId.get(step.from)?.name ?? "?") +
                          " → " +
                          (byId.get(step.to)?.name ?? "?")}
                      </strong>
                      <span>
                        {" "}
                        · {step.via} · payload: {step.data}
                      </span>
                      <em>{describeStep(step, byId)}</em>
                    </li>
                  ))}
                </ol>
              </article>
            ))}
          </div>
        ) : (
          <div className="viz-empty">
            {loading ? "Assembling architecture…" : error || "No architecture yet"}
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
                  ["scene", "3D map"],
                  ["tree", "Tree"],
                  ["classes", "Classes"],
                  ["flows", "Flows"],
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

            {tab === "scene" && (
              <>
                <p className="hint-click">Tap a node to inspect data in / out</p>
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

            <button className="regen" onClick={onRegen} disabled={regen}>
              {regen ? "Regenerating…" : "Regenerate"}
            </button>
            <p className="meta">
              v{snap.version} · {files.length} files
            </p>
          </>
        )}
        {error && !snap && <p className="error">{error}</p>}
      </aside>

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
