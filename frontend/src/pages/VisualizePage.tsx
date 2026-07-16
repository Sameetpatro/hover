import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type ArchitectureSnapshot } from "../api";
import { ArchitectureScene } from "../scenes/ArchitectureScene";
import "./Visualize.css";

export function VisualizePage() {
  const { id } = useParams();
  const [snap, setSnap] = useState<ArchitectureSnapshot | null>(null);
  const [activeFlowId, setActiveFlowId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [regen, setRegen] = useState(false);

  const load = async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getArchitecture(id);
      setSnap(data);
      setActiveFlowId(data.data.flows[0]?.id ?? null);
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
    } catch (e) {
      setError(e instanceof Error ? e.message : "Regenerate failed");
    } finally {
      setRegen(false);
    }
  };

  return (
    <div className="viz-page">
      <div className="viz-canvas">
        {snap ? (
          <ArchitectureScene data={snap.data} activeFlowId={activeFlowId} />
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
            <div className="flow-picker">
              <span className="label">Flows</span>
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
            <button className="regen" onClick={onRegen} disabled={regen}>
              {regen ? "Regenerating…" : "Regenerate"}
            </button>
            <p className="meta">v{snap.version}</p>
          </>
        )}
        {error && !snap && <p className="error">{error}</p>}
      </aside>
    </div>
  );
}
