import type {
  ArchitectureComponent,
  ArchitectureData,
  ArchitectureFlow,
  FlowStep,
} from "../api";

const VIA_MEANING: Record<string, string> = {
  HTTP: "Network request (REST/HTTP) from client to server",
  queue: "Async job pushed onto a queue / worker",
  db: "Read or write against a database / models layer",
  call: "In-process function or service call",
  import: "Module dependency (code imports another file)",
};

export function viaMeaning(via: string): string {
  return VIA_MEANING[via] ?? `Transfer via ${via}`;
}

export function kindLabel(kind: string): string {
  const map: Record<string, string> = {
    ui: "User interface",
    entry: "App entrypoint",
    controller: "API / controller",
    service: "Business logic service",
    worker: "Background worker",
    model: "Data / models",
    config: "Configuration",
  };
  return map[kind] ?? kind;
}

export function describeStep(
  step: FlowStep,
  byId: Map<string, ArchitectureComponent>,
): string {
  if (step.description?.trim()) return step.description;
  const from = byId.get(step.from)?.name ?? step.from;
  const to = byId.get(step.to)?.name ?? step.to;
  const payload = step.data || "payload";
  return `${from} sends “${payload}” to ${to} over ${step.via}. ${viaMeaning(step.via)}.`;
}

export function describeFlow(
  flow: ArchitectureFlow,
  components: ArchitectureComponent[],
): string {
  if (flow.description?.trim()) return flow.description;
  const byId = new Map(components.map((c) => [c.id, c]));
  const parts = flow.steps.map((s, i) => `${i + 1}. ${describeStep(s, byId)}`);
  return parts.join(" ");
}

export function componentStory(
  comp: ArchitectureComponent,
  data: ArchitectureData,
): {
  role: string;
  inbound: string[];
  outbound: string[];
  files: string[];
} {
  const byId = new Map(data.components.map((c) => [c.id, c]));
  const inbound: string[] = [];
  const outbound: string[] = [];
  for (const flow of data.flows) {
    for (const step of flow.steps) {
      if (step.to === comp.id) {
        const fromName = byId.get(step.from)?.name ?? step.from;
        inbound.push(
          `Receives “${step.data}” from ${fromName} (${step.via}) — ${viaMeaning(step.via)}`,
        );
      }
      if (step.from === comp.id) {
        const toName = byId.get(step.to)?.name ?? step.to;
        outbound.push(
          `Sends “${step.data}” to ${toName} (${step.via}) — ${viaMeaning(step.via)}`,
        );
      }
    }
  }
  return {
    role: `${kindLabel(comp.kind)} on the ${comp.layer_id} layer. ${comp.description}`,
    inbound,
    outbound,
    files: comp.files.slice(0, 12),
  };
}
