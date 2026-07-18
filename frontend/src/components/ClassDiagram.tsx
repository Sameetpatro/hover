import { useMemo } from "react";
import type { ArchitectureComponent, GraphPayload } from "../api";
import { colorForKind, liftComponentEdges } from "../lib/architectureMapper";
import { kindLabel } from "../lib/flowNarrative";

type Props = {
  components: ArchitectureComponent[];
  graph: GraphPayload | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
};

export function ClassDiagram({ components, graph, selectedId, onSelect }: Props) {
  const layout = useMemo(() => {
    const layers = ["client", "api", "services", "data"];
    const byLayer = new Map<string, ArchitectureComponent[]>();
    for (const c of components) {
      const list = byLayer.get(c.layer_id) ?? [];
      list.push(c);
      byLayer.set(c.layer_id, list);
    }
    const positions = new Map<string, { x: number; y: number; w: number; h: number }>();
    const boxW = 160;
    const boxH = 72;
    const gapX = 28;
    const gapY = 110;
    let maxW = 400;
    layers.forEach((layer, row) => {
      const comps = byLayer.get(layer) ?? [];
      const rowW = comps.length * boxW + Math.max(0, comps.length - 1) * gapX;
      maxW = Math.max(maxW, rowW + 80);
      const startX = 40;
      comps.forEach((c, i) => {
        positions.set(c.id, {
          x: startX + i * (boxW + gapX),
          y: 40 + row * gapY,
          w: boxW,
          h: boxH,
        });
      });
    });
    // orphans
    let orphanI = 0;
    for (const c of components) {
      if (positions.has(c.id)) continue;
      positions.set(c.id, {
        x: 40 + orphanI * (boxW + gapX),
        y: 40 + layers.length * gapY,
        w: boxW,
        h: boxH,
      });
      orphanI++;
    }
    const edges = liftComponentEdges(components, graph);
    const height = 40 + (layers.length + (orphanI ? 1 : 0)) * gapY + 40;
    return { positions, edges, width: maxW, height, boxW, boxH };
  }, [components, graph]);

  const byId = useMemo(() => new Map(components.map((c) => [c.id, c])), [components]);

  return (
    <div className="diagram-wrap">
      <p className="panel-hint">
        Class / module diagram — boxes are components; arrows show “who depends on whom”
        (imports lifted from the file graph).
      </p>
      <svg
        className="class-svg"
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        width="100%"
        role="img"
      >
        <defs>
          <marker
            id="arrow"
            markerWidth="8"
            markerHeight="8"
            refX="6"
            refY="3"
            orient="auto"
          >
            <path d="M0,0 L6,3 L0,6 Z" fill="#94a3b8" />
          </marker>
        </defs>
        {layout.edges.map((e, i) => {
          const a = layout.positions.get(e.from);
          const b = layout.positions.get(e.to);
          if (!a || !b) return null;
          const x1 = a.x + a.w / 2;
          const y1 = a.y + a.h;
          const x2 = b.x + b.w / 2;
          const y2 = b.y;
          const midY = (y1 + y2) / 2;
          return (
            <g key={`${e.from}-${e.to}-${i}`}>
              <path
                d={`M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`}
                fill="none"
                stroke="#64748b"
                strokeWidth={1.5}
                markerEnd="url(#arrow)"
                opacity={0.85}
              />
              <text
                x={(x1 + x2) / 2}
                y={midY - 4}
                fill="#94a3b8"
                fontSize={10}
                textAnchor="middle"
              >
                {e.via}
              </text>
            </g>
          );
        })}
        {[...layout.positions.entries()].map(([id, p]) => {
          const c = byId.get(id);
          if (!c) return null;
          const selected = selectedId === id;
          const fill = colorForKind(c.kind);
          return (
            <g
              key={id}
              className="class-box"
              style={{ cursor: "pointer" }}
              onClick={() => onSelect(id)}
            >
              <rect
                x={p.x}
                y={p.y}
                width={p.w}
                height={p.h}
                rx={10}
                fill={selected ? "rgba(45,212,191,0.2)" : "rgba(15,23,42,0.95)"}
                stroke={selected ? "#5eead4" : fill}
                strokeWidth={selected ? 2.5 : 1.5}
              />
              <text x={p.x + 12} y={p.y + 22} fill="#e2e8f0" fontSize={12} fontWeight={600}>
                {c.name.length > 18 ? `${c.name.slice(0, 16)}…` : c.name}
              </text>
              <text x={p.x + 12} y={p.y + 40} fill="#94a3b8" fontSize={10}>
                {kindLabel(c.kind)} · {c.layer_id}
              </text>
              <text x={p.x + 12} y={p.y + 56} fill="#64748b" fontSize={9}>
                {c.files.length} file{c.files.length === 1 ? "" : "s"}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
