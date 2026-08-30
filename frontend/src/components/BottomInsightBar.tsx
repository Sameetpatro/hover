import type { FlowEdgePayload } from "./FlowEdge";

type Props = {
  insight: FlowEdgePayload | null;
  onClose: () => void;
};

export function BottomInsightBar({ insight, onClose }: Props) {
  if (!insight || (!insight.insight && !insight.label)) return null;

  const color = insight.color || "#38bdf8";

  return (
    <div className="bottom-insight-container">
      <div
        className="bottom-insight-card"
        style={{
          borderLeft: `4px solid ${color}`,
        }}
      >
        <div className="insight-header">
          <div className="insight-title-group">
            <span className="insight-badge" style={{ color: color }}>
              {insight.label || "Data Flow Step"}
            </span>
            {insight.edgeData && (
              <span className="insight-edge-data">{insight.edgeData}</span>
            )}
            {insight.pattern && (
              <span className="insight-pattern-pill">🔷 {insight.pattern}</span>
            )}
          </div>
          <button
            type="button"
            className="insight-close-btn"
            onClick={onClose}
            title="Dismiss"
          >
            ✕
          </button>
        </div>

        {insight.insight && (
          <p className="insight-narrative">{insight.insight}</p>
        )}

        <div className="insight-meta-row">
          {insight.performanceNote && (
            <div className="insight-meta-chip perf">
              ⚡ <span>{insight.performanceNote}</span>
            </div>
          )}
          {insight.securityNote && (
            <div className="insight-meta-chip sec">
              🔒 <span>{insight.securityNote}</span>
            </div>
          )}
          {insight.condition && (
            <div className="insight-meta-chip cond">
              🔀 <span>Branch: {insight.condition}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
