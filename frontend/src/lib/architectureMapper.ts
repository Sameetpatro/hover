import type { ArchitectureComponent, ArchitectureData } from "../api";

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

export function mapArchitecture(data: ArchitectureData): {
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
  for (const flow of data.flows) {
    flow.steps.forEach((step: ArchitectureData["flows"][number]["steps"][number], idx: number) => {
      edges.push({
        id: `${flow.id}-${idx}`,
        from: step.from,
        to: step.to,
        via: step.via,
        data: step.data,
        flowId: flow.id,
      });
    });
  }

  return { nodes, edges };
}
