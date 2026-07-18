import type { ArchitectureComponent, ArchitectureData, GraphPayload } from "../api";

export type Vec3 = [number, number, number];

export type LayoutNode = {
  id: string;
  name: string;
  kind: string;
  layerId: string;
  position: Vec3;
  description: string;
  files: string[];
};

export type LayoutEdge = {
  id: string;
  from: string;
  to: string;
  via: string;
  data: string;
  flowId: string;
  /** story = curated architecture flow; dep = lifted from file import graph (class diagram) */
  kind: "story" | "dep";
};

const LAYER_Z: Record<string, number> = {
  client: 6,
  api: 2,
  services: -2,
  data: -6,
};

const KIND_COLOR: Record<string, string> = {
  ui: "#5eead4",
  entry: "#67e8f9",
  controller: "#fbbf24",
  service: "#a78bfa",
  worker: "#fb7185",
  model: "#34d399",
  config: "#94a3b8",
};

export function colorForKind(kind: string): string {
  return KIND_COLOR[kind] ?? "#e2e8f0";
}

/** Same edges as the Classes tab: file imports → component-to-component links. */
export function liftComponentEdges(
  components: ArchitectureComponent[],
  graph: GraphPayload | null,
): { from: string; to: string; via: string }[] {
  const fileToComp = new Map<string, string>();
  for (const c of components) {
    for (const f of c.files) fileToComp.set(f, c.id);
  }
  const seen = new Set<string>();
  const out: { from: string; to: string; via: string }[] = [];
  for (const e of graph?.edges ?? []) {
    const a = fileToComp.get(e.source);
    const b = fileToComp.get(e.target);
    if (!a || !b || a === b) continue;
    const key = `${a}->${b}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ from: a, to: b, via: e.edge_type || "import" });
  }
  if (!out.length && components.length > 1) {
    const order = ["client", "api", "services", "data"];
    const sorted = [...components].sort(
      (x, y) => order.indexOf(x.layer_id) - order.indexOf(y.layer_id),
    );
    for (let i = 0; i < sorted.length - 1; i++) {
      out.push({ from: sorted[i].id, to: sorted[i + 1].id, via: "flow" });
    }
  }
  return out;
}

export function mapArchitecture(
  data: ArchitectureData,
  graph: GraphPayload | null = null,
): {
  nodes: LayoutNode[];
  edges: LayoutEdge[];
} {
  const byLayer = new Map<string, ArchitectureComponent[]>();
  for (const c of data.components) {
    const list = byLayer.get(c.layer_id) ?? [];
    list.push(c);
    byLayer.set(c.layer_id, list);
  }

  const nodes: LayoutNode[] = [];
  for (const [layerId, comps] of byLayer) {
    const z = LAYER_Z[layerId] ?? 0;
    const count = comps.length;
    comps.forEach((c, i) => {
      const x = (i - (count - 1) / 2) * 3.2;
      const y = Math.sin(i * 1.7) * 0.4;
      nodes.push({
        id: c.id,
        name: c.name,
        kind: c.kind,
        layerId: c.layer_id,
        position: [x, y, z],
        description: c.description,
        files: c.files,
      });
    });
  }

  const edges: LayoutEdge[] = [];
  const storyPairs = new Set<string>();

  for (const flow of data.flows) {
    flow.steps.forEach((step, idx) => {
      const pair = `${step.from}->${step.to}`;
      storyPairs.add(pair);
      edges.push({
        id: `${flow.id}-${idx}`,
        from: step.from,
        to: step.to,
        via: step.via,
        data: step.data,
        flowId: flow.id,
        kind: "story",
      });
    });
  }

  // Add every class-diagram edge so 3D matches Classes tab
  for (const e of liftComponentEdges(data.components, graph)) {
    const pair = `${e.from}->${e.to}`;
    if (storyPairs.has(pair)) continue; // already drawn as story
    edges.push({
      id: `dep-${e.from}-${e.to}`,
      from: e.from,
      to: e.to,
      via: e.via,
      data: "import / dependency",
      flowId: "__deps__",
      kind: "dep",
    });
  }

  return { nodes, edges };
}
